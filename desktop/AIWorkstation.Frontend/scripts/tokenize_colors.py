#!/usr/bin/env python3
"""One-off helper: rewrite the hard-coded light-theme colours in a stylesheet into theme variables (--c-*).
Usage: tokenize_colors.py FILE  (rewrites in place). Idempotent: already-tokenised values contain no hex literals."""
import colorsys, re, sys

def parse(h):
    h = h.lstrip("#")
    if len(h) == 3: h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

def hue_name(h):
    d = h * 360
    if d < 25 or d >= 330: return "red"
    if d < 70: return "amber"
    if d < 170: return "green"
    return "blue"

def token(hexv, prop):
    r, g, b = parse(hexv)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    tinted = s > 0.28 and 0.08 < l < 0.97 and not (s < 0.45 and l < 0.36 and hue_name(h) == "blue")
    name = hue_name(h)
    if prop.startswith("border") or prop == "outline":
        if l > 0.97: return "var(--c-surface)"
        if l > 0.72:
            return "var(--c-border)" if not (tinted and name in ("red", "green", "amber")) else "var(--c-border-%s)" % name
        return "var(--c-accent)" if name == "blue" and tinted else "var(--c-muted)"
    if prop.startswith("background") or prop == "fill":
        if l < 0.3 and s < 0.5: return hexv                      # dark chrome (kept: dead legacy sidebar)
        if tinted and l > 0.84: return "var(--c-%s-bg)" % name
        if tinted: return "var(--c-accent)" if name == "blue" else "var(--c-%s)" % name
        if l > 0.985: return "var(--c-surface)"
        if l > 0.935: return "var(--c-surface-2)"
        if l > 0.86: return "var(--c-surface-3)"
        return "var(--c-border)"
    if prop == "color" or prop == "stroke":
        if l > 0.93: return hexv                                  # white text on accent buttons
        if tinted: return "var(--c-%s)" % ("accent" if name == "blue" else name)
        return "var(--c-text)" if l < 0.3 else "var(--c-muted)"
    return hexv

HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")
WHITE = re.compile(r"\bwhite\b")
DECL = re.compile(r"([a-z-]+)(\s*:\s*)([^;{}]+)")

def rewrite(css):
    def decl(m):
        prop, sep, val = m.group(1), m.group(2), m.group(3)
        if "gradient" in val or prop in ("box-shadow",):
            return m.group(0)
        val = WHITE.sub("#ffffff", val)
        return prop + sep + HEX.sub(lambda x: token(x.group(0), prop), val)
    return DECL.sub(decl, css)

if __name__ == "__main__":
    path = sys.argv[1]
    text = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8").write(rewrite(text))
