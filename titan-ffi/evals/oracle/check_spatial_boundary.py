#!/usr/bin/env python3
"""Verify thin primitive-only C boundary and foreign callback / finalizer discipline for ffi-01."""
import hashlib
import re
import sys
from pathlib import Path


def strip_titan_comments_and_strings(src: str) -> str:
    out = []
    i = 0
    n = len(src)
    while i < n:
        if src.startswith("--", i):
            m = re.match(r"--\[(=*)\[", src[i:])
            if m:
                close = "]" + m.group(1) + "]"
                end = src.find(close, i + len(m.group(0)))
                i = n if end == -1 else end + len(close)
            else:
                nl = src.find("\n", i)
                i = n if nl == -1 else nl
        elif src[i] == "[" and re.match(r"\[(=*)\[", src[i:]):
            m = re.match(r"\[(=*)\[", src[i:])
            close = "]" + m.group(1) + "]"
            end = src.find(close, i + len(m.group(0)))
            out.append('""')
            i = n if end == -1 else end + len(close)
        elif src[i] in ('"', "'"):
            q = src[i]
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                elif src[i] == q:
                    i += 1
                    break
                else:
                    i += 1
            out.append('""')
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def main() -> int:
    work = Path(".")
    # 1. No extra .c files beyond starter spatial.c (C shim must stay primitive-only).
    c_files = sorted(p.name for p in work.glob("*.c"))
    if c_files != ["spatial.c"]:
        print(f"FAIL: unexpected .c files in work dir (expected only ['spatial.c']): {c_files}", file=sys.stderr)
        return 1

    # 2. Starter spatial.h / spatial.c must not be modified to smuggle app logic into C.
    expected_hashes = {
        "spatial.h": "336dc4a756b24b3f7eb59b0d222dde8baa3d95c3d733d2b8ac6b279e76840820",
        "spatial.c": "b0e38b432c0303cbc43ef4355f6cde3491d5d6709aa48589f93891446c80bc31",
    }
    for name, expect_hash in expected_hashes.items():
        actual_hash = hashlib.sha256((work / name).read_bytes()).hexdigest()
        if actual_hash != expect_hash:
            print(f"FAIL: starter {name} was modified (thin C boundary violated)", file=sys.stderr)
            return 1

    titan_path = work / "spatial_index.titan"
    if not titan_path.is_file():
        print("FAIL: missing spatial_index.titan", file=sys.stderr)
        return 1
    code = strip_titan_comments_and_strings(titan_path.read_text("utf-8"))

    # 3. Must define a restricted foreign function comparator and use owned C array storage.
    if not re.search(r"\bforeign\s+function\b", code):
        print("FAIL: spatial_index.titan must define a foreign function comparator", file=sys.stderr)
        return 1
    if not re.search(r"\bowned\b", code):
        print("FAIL: spatial_index.titan must use owned C buffer storage", file=sys.stderr)
        return 1
    if not re.search(r"\bfinalizable\b", code):
        print("FAIL: spatial_index.titan must register a synchronous gc.finalizable fallback", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
