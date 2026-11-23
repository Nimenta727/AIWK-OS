"""JSON Schema for the local model's output (constrained decoding hint) plus a tiny validator for tests.

Constrained decoding makes an invalid tool name, a missing argument or broken JSON IMPOSSIBLE to generate, which
saves the retries and the repair prompts that cost tokens on a small model.

The schema is only a DECODING HINT. `LocalPlanner.validate_any` stays the authority (semantic rules such as
"a plan may not touch a path an earlier step changes" are enforced later by the stage builder). A test pins the
important direction: anything this schema accepts is also accepted by `validate_any`.

Whether the deployed llama-server version accepts `response_format: {type: json_schema, ...}` is NOT verified in
this repository; the planner therefore treats this mode as opt-in and falls back to plain JSON mode on a 400.
"""
import re

from aiws_local_model import MAX_STEPS, MODEL_WRITE_TOOLS, READ_TOOLS, FINGERPRINTED
from aiws_toolplane import catalog

PATH_PATTERN = r"^(?!/)(?!.*\.\.)(?!.*\\)(?!(?:.*/)?(?:\.git|\.ssh|\.aiws-trash)(?:/|$))[^\x00-\x1f]{1,512}$"
TRASH_PATTERN = r"^[a-f0-9]{32}$"

def _app_id_pattern():
    import aiws_apps
    return "^(" + "|".join(sorted(r[0] for r in aiws_apps.REGISTRY if r[1] == "gui" and r[6] is not None)) + ")$"

# Patterns below are deliberately AT LEAST as strict as LocalPlanner._check_external (the schema may only narrow it).
# They avoid \b and inline flags so a grammar converter that supports only a regex subset can still use them.
LINE_NUMBER_PATTERN = r"^[1-9][0-9]{0,8}$"
GITLOG_COUNT_PATTERN = r"^([1-9]|[1-4][0-9]|50)$"
JQ_FILTER_PATTERN = r"^[^-].{0,511}$|^.$"
SQLITE_QUERY_PATTERN = r"^\s*([Ss][Ee][Ll][Ee][Cc][Tt]|[Ww][Ii][Tt][Hh])[\s(*][^;]*;?\s*$"

def _argument_schema(tool, spec):
    props, required = {}, []
    skip = {"expectedSha256"} if tool in FINGERPRINTED else set()    # the controller computes fingerprints, never the model
    for name in spec["properties"]:
        if name in skip:
            continue
        if name == "trashId":
            props[name] = {"type": "string", "pattern": TRASH_PATTERN}
        elif name == "id":
            props[name] = {"type": "string", "pattern": _app_id_pattern()}
        elif tool == "log.lines" and name in ("start", "end"):
            props[name] = {"type": "string", "pattern": LINE_NUMBER_PATTERN, "maxLength": 9}      # digits only: a real 9B once passed a whole log line here
        elif tool == "ext.gitlog" and name == "count":
            props[name] = {"type": "string", "pattern": GITLOG_COUNT_PATTERN}
        elif tool == "ext.jq" and name == "filter":
            props[name] = {"type": "string", "pattern": JQ_FILTER_PATTERN, "maxLength": 512}
        elif tool == "ext.sqlite" and name == "query":
            props[name] = {"type": "string", "pattern": SQLITE_QUERY_PATTERN, "maxLength": 512}
        elif name in ("path", "to"):
            props[name] = {"type": "string", "pattern": PATH_PATTERN}
        else:
            props[name] = {"type": "string", "maxLength": 512}
    required = [k for k in spec["required"] if k not in skip]
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}

def _step(tool, spec):
    return {"type": "object",
            "properties": {"tool": {"const": tool}, "arguments": _argument_schema(tool, spec),
                           "reason": {"type": "string", "minLength": 1, "maxLength": 500}},
            "required": ["tool", "arguments", "reason"], "additionalProperties": False}

def output_schema():
    """Deterministic (sorted) schema: byte-identical on every call, which keeps the request prefix cacheable."""
    specs = {x["name"]: x["inputSchema"] for x in catalog()}
    tools = sorted(READ_TOOLS | MODEL_WRITE_TOOLS)
    defs = {"s_" + t.replace(".", "_"): _step(t, specs[t]) for t in tools}      # each tool is described ONCE ($defs) so the schema stays small
    steps = [{"$ref": "#/$defs/" + k} for k in sorted(defs)]
    refuse = {"type": "object",
              "properties": {"tool": {"const": "refuse"}, "arguments": {"type": "object", "maxProperties": 0},
                             "reason": {"type": "string", "minLength": 1, "maxLength": 500}},
              "required": ["tool", "arguments", "reason"], "additionalProperties": False}
    plan = {"type": "object",
            "properties": {"steps": {"type": "array", "minItems": 1, "maxItems": MAX_STEPS, "items": {"oneOf": steps}},
                           "reason": {"type": "string", "minLength": 1, "maxLength": 500}},
            "required": ["steps", "reason"], "additionalProperties": False}
    return {"$defs": defs, "oneOf": steps + [refuse, plan]}

def response_format():
    return {"type": "json_schema", "json_schema": {"name": "aiws_proposal", "strict": True, "schema": output_schema()}}

# ---- minimal validator for the subset used above (tests only; not a general JSON Schema implementation) ----
def validate(schema, value, _root=None):
    """True when `value` satisfies `schema` (`$ref` resolves against the root's `$defs`)."""
    root = _root if _root is not None else schema
    if "$ref" in schema:
        return validate(root["$defs"][schema["$ref"].rsplit("/", 1)[1]], value, root)
    if "oneOf" in schema:
        return sum(validate(s, value, root) for s in schema["oneOf"]) == 1
    if "anyOf" in schema:
        return any(validate(s, value, root) for s in schema["anyOf"])
    if "const" in schema:
        return value == schema["const"] and not isinstance(value, bool)
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict):
            return False
        props = schema.get("properties", {})
        if any(k not in value for k in schema.get("required", [])):
            return False
        if schema.get("additionalProperties") is False and set(value) - set(props):
            return False
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            return False
        return all(validate(props[k], v, root) for k, v in value.items() if k in props)
    if kind == "array":
        if not isinstance(value, list) or not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 10 ** 9):
            return False
        return all(validate(schema["items"], v, root) for v in value)
    if kind == "string":
        if not isinstance(value, str) or not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 10 ** 9):
            return False
        return "pattern" not in schema or re.search(schema["pattern"], value) is not None
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return True
