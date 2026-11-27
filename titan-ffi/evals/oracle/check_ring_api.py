#!/usr/bin/env python3
"""Verify trusted Lua C API guard-rails for ffi-04."""
import hashlib
import re
import sys
from pathlib import Path

EXPECTED_RING_EXT_H_SHA256 = "41287a1ef3d0a18944549744cf240b424cd74ee2dc6ec492d1abdbcdb2782a7d"


def strip_c_comments_and_strings(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    src = re.sub(r"'(?:\\.|[^'\\])*'", "''", src)
    return src


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
    hdr = Path("ring_ext.h")
    cfile = Path("ring_ext.c")
    tfile = Path("ring.titan")
    for p in (hdr, cfile, tfile):
        if not p.is_file():
            print(f"FAIL: missing {p}", file=sys.stderr)
            return 1

    if hashlib.sha256(hdr.read_bytes()).hexdigest() != EXPECTED_RING_EXT_H_SHA256:
        print("FAIL: starter ring_ext.h was modified", file=sys.stderr)
        return 1

    c_code = strip_c_comments_and_strings(cfile.read_text("utf-8"))
    t_code = strip_titan_comments_and_strings(tfile.read_text("utf-8"))

    # Guard-rails: no luaL_ref, no lua_pcall/lua_pcallk for plain C work, no raw TValue write bypasses.
    for label, pat, text in [
        ("luaL_ref in ring_ext.c", r"\bluaL_ref\b", c_code),
        ("luaL_ref in ring.titan", r"\bluaL_ref\b", t_code),
        ("lua_pcall/lua_pcallk in ring_ext.c", r"\blua_pcallk?\b", c_code),
        ("lua_pcall/lua_pcallk in ring.titan", r"\blua_pcallk?\b", t_code),
    ]:
        if re.search(pat, text):
            print(f"FAIL: forbidden {label}", file=sys.stderr)
            return 1

    # C helper must use Lua 5.5 public uservalue APIs (emitting write barriers).
    for req in ("lua_newuserdatauv", "lua_setiuservalue", "lua_getiuservalue"):
        if not re.search(rf"\b{req}\b", c_code):
            print(f"FAIL: ring_ext.c must use {req}", file=sys.stderr)
            return 1

    # Titan side must follow stack-transaction discipline (lua_gettop + defer lua_settop + lua_checkstack + lua_totvalue).
    for req in ("lua_gettop", "lua_settop", "lua_checkstack", "lua_totvalue", "defer"):
        if not re.search(rf"\b{req}\b", t_code):
            print(f"FAIL: ring.titan must follow stack transaction discipline ({req} missing)", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
