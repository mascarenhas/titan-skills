#!/usr/bin/env python3
"""Verify Wasm C helper, browser.pin/call_sync hygiene, and import rules for ffi-05."""
import hashlib
import re
import sys
from pathlib import Path

EXPECTED_CRC_WASM_H_SHA256 = "461ff9314349a6430095856c2f63f3059f63ba182d606a38e62a61d80255e4cb"


def strip_c_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"//[^\n]*", "", src)
    return src


def main() -> int:
    hdr = Path("crc_wasm.h")
    cfile = Path("crc_wasm.c")
    tfile = Path("crc_app.titan")
    jfile = Path("wasm_imports.mjs")
    for p in (hdr, cfile, tfile, jfile):
        if not p.is_file():
            print(f"FAIL: missing {p}", file=sys.stderr)
            return 1

    if hashlib.sha256(hdr.read_bytes()).hexdigest() != EXPECTED_CRC_WASM_H_SHA256:
        print("FAIL: starter crc_wasm.h was modified", file=sys.stderr)
        return 1

    c_code = strip_c_comments(cfile.read_text("utf-8"))
    t_code = tfile.read_text("utf-8")
    j_code = strip_c_comments(jfile.read_text("utf-8"))

    for req in ("titan_browser_call_sync", "free"):
        if not re.search(rf"\b{req}\b", c_code):
            print(f"FAIL: crc_wasm.c must call {req}", file=sys.stderr)
            return 1

    if not re.search(r"\bbrowser\.pin\b|\bpin\s*\(", t_code):
        print("FAIL: crc_app.titan must pin the callback with browser.pin", file=sys.stderr)
        return 1
    if not re.search(r"\bdefer\b", t_code):
        print("FAIL: crc_app.titan must use defer to unpin/close the BrowserPin", file=sys.stderr)
        return 1

    # Must not wrap synchronous C callback dispatcher in WebAssembly.Suspending.
    if re.search(r"WebAssembly\.Suspending", j_code):
        print("FAIL: wasm_imports.mjs must not wrap synchronous C callbacks in WebAssembly.Suspending", file=sys.stderr)
        return 1
    if re.search(r"\b(?:wasi_snapshot_preview1|titan_browser_|titan_mco_)\b", j_code):
        print("FAIL: wasm_imports.mjs references reserved Wasm import namespace/prefix", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
