#!/usr/bin/env python3
"""Create a disposable writable Titan + LuaRocks tree at /verify/rock-tree without touching base/prefix."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def copy_fast(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    # Prefer btrfs reflink for instant zero-copy regular files; fall back to normal copy2.
    r = subprocess.run(["cp", "--reflink=auto", "-p", str(src), str(dst)])
    if r.returncode != 0:
        shutil.copy2(src, dst)


def setup_rock_tree(target_str: str = "/verify/rock-tree") -> Path:
    sdk_root = Path(
        subprocess.check_output(["titanc", "--print-root"], text=True).strip()
    )
    target = Path(target_str)
    try:
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        target = Path("/tmp/verify-rock-tree")
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

    old = str(sdk_root)
    new = str(target)

    # 1. Copy bin/ (rewrite text wrappers pointing to sdk_root -> target; copy real lua binary)
    (target / "bin").mkdir(parents=True, exist_ok=True)
    for item in (sdk_root / "bin").iterdir():
        dst = target / "bin" / item.name
        if item.name in ("lua", "luac"):
            copy_fast(item, dst)
        else:
            raw = item.read_bytes()
            if old.encode("utf-8") in raw:
                dst.write_bytes(raw.replace(old.encode("utf-8"), new.encode("utf-8")))
                dst.chmod(item.stat().st_mode)
            else:
                copy_fast(item, dst)

    # 2. Copy etc/ (rewrite luarocks config to point to target)
    shutil.copytree(sdk_root / "etc", target / "etc")
    for cfg in (target / "etc/luarocks").glob("*.lua"):
        txt = cfg.read_text("utf-8")
        cfg.write_text(txt.replace(old, new), "utf-8")

    # 3. Copy include/, share/, and src/ (Lua 5.5.1 internal headers)
    shutil.copytree(sdk_root / "include", target / "include")
    shutil.copytree(sdk_root / "share", target / "share")
    if (sdk_root / "src").is_dir():
        shutil.copytree(sdk_root / "src", target / "src")
    # 4. Copy lib/lua, lib/*.a, and lib/titan/0.6/* (reflink-fast for big archives)
    shutil.copytree(sdk_root / "lib/lua", target / "lib/lua")
    for afile in (sdk_root / "lib").glob("*.a"):
        copy_fast(afile, target / "lib" / afile.name)
    for item in (sdk_root / "lib/titan/0.6").iterdir():
        copy_fast(item, target / "lib/titan/0.6" / item.name)

    # 5. Copy lib/luarocks/rocks-5.5/ (skip titan's bulky archived dist/ copy; rewrite location.lua)
    rocks_src = sdk_root / "lib/luarocks/rocks-5.5"
    rocks_dst = target / "lib/luarocks/rocks-5.5"
    rocks_dst.mkdir(parents=True, exist_ok=True)
    for entry in rocks_src.iterdir():
        if entry.is_file():
            copy_fast(entry, rocks_dst / entry.name)
        elif entry.name == "titan":
            for ver_dir in entry.iterdir():
                v_dst = rocks_dst / "titan" / ver_dir.name
                v_dst.mkdir(parents=True, exist_ok=True)
                for sub in ver_dir.iterdir():
                    if sub.name == "dist":
                        continue
                    if sub.is_dir():
                        shutil.copytree(sub, v_dst / sub.name)
                    else:
                        copy_fast(sub, v_dst / sub.name)
                loc = v_dst / "installer/location.lua"
                if loc.is_file():
                    loc.write_text(loc.read_text("utf-8").replace(old, new), "utf-8")
        else:
            shutil.copytree(entry, rocks_dst / entry.name)

    return target


if __name__ == "__main__":
    dest = sys.argv[1] if len(sys.argv) > 1 else "/verify/rock-tree"
    out = setup_rock_tree(dest)
    print(f"ROCK TREE READY: {out}")
