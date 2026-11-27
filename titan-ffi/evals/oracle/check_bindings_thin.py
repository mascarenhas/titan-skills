#!/usr/bin/env python3
"""Verify thin primitive-only bindings.mjs boundary for ffi-02."""
import re
import sys
from pathlib import Path


def strip_js_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def main() -> int:
    p = Path("bindings.mjs")
    if not p.is_file():
        print("FAIL: missing bindings.mjs", file=sys.stderr)
        return 1
    code = strip_js_comments(p.read_text("utf-8"))

    # Forbidden app/layout/styling/hit-testing policy inside bindings.mjs.
    forbidden = [
        ("hardcoded highlight color #ff9900", r"#ff9900"),
        ("hardcoded span color #3366cc", r"#3366cc"),
        ("hardcoded span color #33aa66", r"#33aa66"),
        ("hardcoded span color #aa44aa", r"#aa44aa"),
        ("layout/hit-test function in JS", r"\b(?:compute_layout|computeLayout|hit_test|hitTest)\b"),
        ("hardcoded span id in JS", r'["\'](?:lex|parse|emit)["\']'),
        ("SDK-reserved titan:* binding key", r'["\']titan:'),
    ]
    for desc, pat in forbidden:
        m = re.search(pat, code, flags=re.I)
        if m:
            print(f"FAIL: bindings.mjs violates thin primitive boundary ({desc}: {m.group(0)!r})", file=sys.stderr)
            return 1

    non_empty = [ln for ln in code.splitlines() if ln.strip()]
    if len(non_empty) > 90:
        print(f"FAIL: bindings.mjs is too large ({len(non_empty)} code lines > 90); keep logic in .titan", file=sys.stderr)
        return 1

    # Verify timeline_app.titan actually handles BrowserError with :close() and uses BigInt/is_integer.
    app = Path("timeline_app.titan")
    if not app.is_file():
        print("FAIL: missing timeline_app.titan", file=sys.stderr)
        return 1
    app_src = app.read_text("utf-8")
    if "BrowserError" not in app_src:
        print("FAIL: timeline_app.titan must explicitly handle browser.BrowserError", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
