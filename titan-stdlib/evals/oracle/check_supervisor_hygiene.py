#!/usr/bin/env python3
"""Static hygiene check for stdlib-04: use os.spawn/os.popen/os.clock, never raw uv."""
import re
import sys
from pathlib import Path


def strip_comments(src: str) -> str:
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        if src[i : i + 2] == "--":
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                end_tok = "]" + m.group(1) + "]"
                end_pos = src.find(end_tok, i + len(m.group(0)))
                i = n if end_pos == -1 else end_pos + len(end_tok)
                out.append(" ")
                continue
            nl = src.find("\n", i)
            i = n if nl == -1 else nl
            out.append(" ")
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def main() -> int:
    sup_path = Path("supervisor.titan")
    if not sup_path.is_file():
        print("FAIL: missing supervisor.titan", file=sys.stderr)
        return 1
    code = strip_comments(sup_path.read_text("utf-8"))
    if re.search(r'import\s+["\'](?:titan\.)?uv["\']', code):
        print("FAIL: supervisor.titan must use os.spawn/os.popen, not raw uv", file=sys.stderr)
        return 1
    if not re.search(r"\bclock\s*\(", code):
        print("FAIL: supervisor.titan must measure process CPU time via os.clock()", file=sys.stderr)
        return 1
    if not re.search(r"\bdefer\b", code):
        print("FAIL: supervisor.titan must use defer cleanup for process streams", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
