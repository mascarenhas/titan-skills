#!/usr/bin/env python3
"""Static + runtime safety check for stdlib-01 (async fs.File defer, zero gc.finalizable)."""
import re
import sys
from pathlib import Path


def strip_titan_comments_and_strings(src: str) -> str:
    """Strip Titan comments (--[[...]], --...) and string literals to inspect code tokens only."""
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        # Long comment --[=*[ ... ]=*]
        if src[i : i + 2] == "--":
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                eq = m.group(1)
                end_tok = "]" + eq + "]"
                end_pos = src.find(end_tok, i + len(m.group(0)))
                i = n if end_pos == -1 else end_pos + len(end_tok)
                out.append(" ")
                continue
            nl = src.find("\n", i)
            i = n if nl == -1 else nl
            out.append(" ")
            continue
        # Long string [=*[ ... ]=*]
        if src[i] == "[":
            m = re.match(r"\[(=*)\[", src[i:])
            if m:
                eq = m.group(1)
                end_tok = "]" + eq + "]"
                end_pos = src.find(end_tok, i + len(m.group(0)))
                i = n if end_pos == -1 else end_pos + len(end_tok)
                out.append('""')
                continue
        # Quoted string
        if src[i] in ('"', "'"):
            q = src[i]
            i += 1
            while i < n and src[i] != q:
                if src[i] == "\\":
                    i += 2
                else:
                    i += 1
            i += 1
            out.append('""')
            continue
        out.append(src[i])
        i += 1
    return "".join(out)


def main() -> int:
    journal_path = Path("journal.titan")
    stderr_path = Path("oracle_journal.stderr")
    if not journal_path.is_file():
        print("FAIL: missing journal.titan", file=sys.stderr)
        return 1

    code = strip_titan_comments_and_strings(journal_path.read_text("utf-8"))

    # Critical safety invariant: NEVER attach gc.finalizable to async fs.File / fs.Watcher handles
    if re.search(r"\bfinalizable\b", code):
        print(
            "FAIL: journal.titan calls gc.finalizable; async fs.File/fs.Watcher handles MUST NOT use finalizers",
            file=sys.stderr,
        )
        return 1

    # Must use lexical defer cleanup
    if not re.search(r"\bdefer\b", code):
        print("FAIL: journal.titan does not use lexical `defer` cleanup", file=sys.stderr)
        return 1

    # Must not emit Lua GC/finalizer warnings during oracle execution
    if stderr_path.is_file():
        err_text = stderr_path.read_text("utf-8", errors="replace")
        if "Lua warning:" in err_text or "cannot yield" in err_text:
            print(f"FAIL: runtime warning/error on stderr:\n{err_text}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
