"""A small JSON Schema checker that says WHERE and WHY a value is wrong.

Why not reuse the tests-only helper in aiws_model_schema: the local agent needs the reason. Constrained decoding is a *hint* that
not every server honours (older builds, Ollama, vLLM without guided decoding), so every model answer is re-checked here, and
when it fails the agent gives the model this exact message ("$.args.path: does not match pattern ...") to correct itself.

Supported keywords (the subset our own schemas use): type, const, enum, properties, required, additionalProperties(false),
maxProperties, items, minItems, maxItems, minLength, maxLength, pattern, minimum, maximum, oneOf, anyOf, $ref to #/$defs/NAME.
Unknown keywords are ignored, as the standard says. Standard library only; no network, no files.
"""
import re

MAX_DEPTH = 24


class SchemaError(ValueError):
    def __init__(self, path, message):
        super().__init__("%s: %s" % (path, message))
        self.path = path
        self.reason = message


_TYPES = {"string": lambda v: isinstance(v, str), "object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
          "boolean": lambda v: isinstance(v, bool), "null": lambda v: v is None,
          "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
          "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)}


def _resolve(ref, root):
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise SchemaError("$", "unsupported $ref " + str(ref)[:40])
    try:
        return root["$defs"][ref[len("#/$defs/"):]]
    except (KeyError, TypeError):
        raise SchemaError("$", "unknown $ref " + ref[:40])


def _short(value):
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."


def _discriminated(alts, value, root):
    """For {"tool": const ...} style unions: the alternative whose constant matches the value's own, so the error names the
    real problem (a bad argument) instead of 'none of 40 alternatives matched'."""
    if not isinstance(value, dict):
        return None
    for alt in alts:
        alt = _resolve(alt["$ref"], root) if "$ref" in alt else alt
        for key, sub in (alt.get("properties") or {}).items():
            if isinstance(sub, dict) and "const" in sub and key in value and value[key] == sub["const"]:
                return alt
    return None


def check(value, schema, root=None, path="$", depth=0):
    """Raise SchemaError on the first problem; return None when the value is valid."""
    if depth > MAX_DEPTH:
        raise SchemaError(path, "nested too deeply")
    root = schema if root is None else root
    if not isinstance(schema, dict):
        return
    if "$ref" in schema:
        return check(value, _resolve(schema["$ref"], root), root, path, depth + 1)
    if "oneOf" in schema or "anyOf" in schema:
        key = "oneOf" if "oneOf" in schema else "anyOf"
        alts = schema[key]
        ok, errors = 0, []
        for alt in alts:
            try:
                check(value, alt, root, path, depth + 1)
                ok += 1
            except SchemaError as exc:
                errors.append(exc)
        if ok == 1 or (key == "anyOf" and ok >= 1):
            return
        if ok > 1:
            raise SchemaError(path, "matches more than one alternative")
        best = _discriminated(alts, value, root)
        if best is not None:
            check(value, best, root, path, depth + 1)          # raises the specific error
        deepest = max(errors, key=lambda e: e.path.count(".") + e.path.count("["), default=None)
        raise SchemaError(path, "does not match any of %d alternatives%s" % (len(alts), (" (closest: %s)" % deepest) if deepest else ""))
    if "const" in schema:
        if value != schema["const"] or isinstance(value, bool) != isinstance(schema["const"], bool):
            raise SchemaError(path, "must be %s" % _short(schema["const"]))
        return
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(path, "must be one of %s" % ", ".join(_short(v) for v in schema["enum"][:12]))
    kind = schema.get("type")
    if kind is not None:
        kinds = kind if isinstance(kind, list) else [kind]
        if not any(_TYPES.get(k, lambda v: True)(value) for k in kinds):
            raise SchemaError(path, "must be of type %s" % "/".join(kinds))
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", ()):
            if name not in value:
                raise SchemaError(path, "missing required field '%s'" % name)
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(props))
            if extra:
                raise SchemaError(path, "unexpected field '%s'" % extra[0])
        if "maxProperties" in schema and len(value) > schema["maxProperties"]:
            raise SchemaError(path, "too many fields")
        for name, sub in value.items():
            if name in props:
                check(sub, props[name], root, path + "." + name, depth + 1)
    elif isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaError(path, "needs at least %d items" % schema["minItems"])
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaError(path, "allows at most %d items" % schema["maxItems"])
        if "items" in schema:
            for i, sub in enumerate(value):
                check(sub, schema["items"], root, "%s[%d]" % (path, i), depth + 1)
    elif isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise SchemaError(path, "is too short")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise SchemaError(path, "is longer than %d characters" % schema["maxLength"])
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise SchemaError(path, "does not match the required pattern")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaError(path, "must be at least %s" % schema["minimum"])
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaError(path, "must be at most %s" % schema["maximum"])


def is_valid(value, schema):
    try:
        check(value, schema)
        return True
    except SchemaError:
        return False
