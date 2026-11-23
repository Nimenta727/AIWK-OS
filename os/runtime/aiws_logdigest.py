"""Deterministic log reading: turn a huge log into a short, faithful, numbered list. No model is involved here.

Why: in the 2026-11-22 benchmark, a plain keyword grep found the root cause of only 6 of 12 logs (the others hid it behind
harmless "error" decoys), while a 9B model that was shown THIS compressed form found all 12, and a 2B model 8. The compression is
what makes a long log readable for a model at all, and it is the only part that cannot be wrong in a surprising way, so it
is plain code.

What it does
  * Every message is reduced to a template (timestamps, numbers, hex ids and UUIDs become '#').
  * Identical templates are merged. Each entry keeps the FIRST line number where it appeared and how many times it repeated.
    "First" is the point: the root cause is nearly always the first sign, and the line number lets anyone open the real log there.
  * When the result is too long, rare messages are kept first (a message that happened once is more informative than one that
    happened 4000 times), then the entries are put back in line order.
  * Text is quoted VERBATIM (cut at 400 characters), never paraphrased. Level counts (ERROR, WARN ...) are counted from the raw lines.

Everything is bounded: file size, distinct templates, output size, range size. The file is read as a stream; binary files are refused.
"""
import re

MAX_FILE = 64 * 1024 * 1024
MAX_LINE_CHARS = 400
MAX_GROUPS = 20000
BUDGET_CHARS = 7000
MAX_RANGE = 200
LEVELS = ("FATAL", "CRITICAL", "ERROR", "WARN", "WARNING", "INFO", "DEBUG", "TRACE")

_TS = re.compile(r"^\s*(?:\[?\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?\]?|\[?\d\d:\d\d:\d\d(?:[.,]\d+)?\]?|[A-Z][a-z]{2}\s+\d{1,2}\s+\d\d:\d\d:\d\d|\d{10,13})\s*")
_VAR = re.compile(r"0x[0-9a-fA-F]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8,}|\d+")
_LEVEL = re.compile(r"\b(" + "|".join(LEVELS) + r")\b")


class LogError(ValueError):
    pass


def template(message):
    return _VAR.sub("#", message)


def strip_timestamp(line):
    return _TS.sub("", line, count=1)


def _lines(path):
    """Yield (number, text) from a file as a stream. Refuses binary content and oversized files."""
    try:
        size = path.stat().st_size
    except OSError:
        raise LogError("Cannot read that file")
    if not path.is_file():
        raise LogError("Not a regular file")
    if size > MAX_FILE:
        raise LogError("File is larger than %d MiB: use log.lines with a range or code.search" % (MAX_FILE // 1048576))
    with open(path, "rb") as fh:
        head = fh.read(4096)
        if b"\x00" in head:
            raise LogError("This looks like a binary file, not a text log")
        fh.seek(0)
        for number, raw in enumerate(fh, 1):
            yield number, raw.decode("utf-8", "replace").rstrip("\r\n")


def digest(lines, budget_chars=BUDGET_CHARS):
    """`lines` yields (number, text). Returns the compressed view as a plain dict (see the module doc)."""
    groups, order, total, other = {}, [], 0, 0
    levels = {}
    for number, text in lines:
        total = number
        for level in _LEVEL.findall(text[:300]):
            levels[level] = levels.get(level, 0) + 1
            break                                               # the first level word on the line is its level
        if not text.strip():
            continue
        message = strip_timestamp(text)
        key = template(message)
        entry = groups.get(key)
        if entry is not None:
            entry[1] += 1
        elif len(groups) < MAX_GROUPS:
            groups[key] = [number, 1, message]
            order.append(key)
        else:
            other += 1                                          # templates beyond the cap are counted, not lost silently
    items = [groups[k] for k in order]

    def render(item):
        return "L%d%s %s" % (item[0], (" x%d" % item[1]) if item[1] > 1 else "", item[2][:MAX_LINE_CHARS])

    used = sum(len(render(i)) + 1 for i in items)
    omitted = 0
    if used > budget_chars:
        keep, used = [], 0
        for item in sorted(items, key=lambda i: (i[1], i[0])):
            cost = len(render(item)) + 1
            if used + cost > budget_chars:
                break
            used += cost
            keep.append(item)
        omitted = len(items) - len(keep)
        items = sorted(keep, key=lambda i: i[0])
    return {"totalLines": total, "distinct": len(order), "levels": levels, "otherUncounted": other, "omittedFrequent": omitted,
            "entries": [{"line": i[0], "count": i[1], "text": i[2][:MAX_LINE_CHARS]} for i in items],
            "note": "Each entry shows the FIRST line where the message appeared (numbers ignored when merging) and how often it repeated. "
                    "Open the real lines around a number with log.lines."}


def digest_file(path, budget_chars=BUDGET_CHARS):
    return digest(_lines(path), budget_chars)


def _line_number(value):
    """A line number from what a model or a person typed: `352`, `L352`, `line 352`, `L352 WARN ...` (a real 9B copied a whole digest entry).
    The first whole number is used. Read-only and bounded, so being forgiving here is harmless."""
    if isinstance(value, bool):
        raise LogError("start and end must be whole numbers")
    if isinstance(value, int):
        return value
    m = re.search(r"\d{1,9}", str(value if value is not None else ""))
    if not m:
        raise LogError("start and end must be line numbers such as 340 and 360 (the number after L in a log.digest entry)")
    return int(m.group(0))


def line_range(path, start, end):
    """Numbered lines start..end (1-based, inclusive), at most MAX_RANGE of them, each cut at 400 characters."""
    start, end = _line_number(start), _line_number(end)
    if start < 1 or end < start:
        raise LogError("Need 1 <= start <= end")
    if end - start + 1 > MAX_RANGE:
        end = start + MAX_RANGE - 1
    out = []
    for number, text in _lines(path):
        if number > end:
            break
        if number >= start:
            out.append({"line": number, "text": text[:MAX_LINE_CHARS]})
    return {"start": start, "end": out[-1]["line"] if out else start, "lines": out,
            "note": "" if out else "The file has fewer lines than the start of this range."}


def render_digest(result):
    """The compact text form shown to a model: one line per entry, verbatim."""
    head = "%d lines, %d distinct messages; levels: %s" % (
        result["totalLines"], result["distinct"], ", ".join("%s=%d" % kv for kv in sorted(result["levels"].items())) or "none")
    if result["omittedFrequent"]:
        head += "; %d frequent messages left out to fit (rare ones are kept)" % result["omittedFrequent"]
    return head + "\n" + "\n".join("L%d%s %s" % (e["line"], (" x%d" % e["count"]) if e["count"] > 1 else "", e["text"]) for e in result["entries"])
