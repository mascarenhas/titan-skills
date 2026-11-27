---
name: titan-package
description: Use when packaging, publishing, testing, or uninstalling reusable Titan libraries as LuaRocks rocks. Covers format 3.0 rockspecs, titan-install/titan-uninstall, dist/{modules,include,lib} staging, common-prefix providers, source-only vs compiled rocks, and DSO binary compatibility; use titan-application for standalone native or browser apps.
---

# Titan library packaging and distribution

Package, test, publish, and uninstall reusable Titan libraries as LuaRocks rocks. Pair with `skill://titan-programmer` for `.titan` code, `skill://titan-tester` for native tests, and `skill://titan-ffi` for C headers/callbacks. Use `skill://titan-application` for standalone native or browser apps. No Makefile is required.

## Non-negotiable invariants

1. **Rock name vs logical name & common-prefix providers:** Keep lowercase rock names (`titan-cui`) separate from logical module names (`cui`, `cui.box`). Neither rock name nor `package.cpath` controls Titan lookup—**never** add `lib/titan/0.6` to `package.cpath`. Multi-root builds (`titanc pkg.a pkg.b`) emit one provider named for the **longest common dotted prefix** (`pkg.so`/`.a` Unix, `pkg.dll` Windows, `pkg.a` browser); unrelated roots fail. Bare `titan` is reserved for Lua's support module.
2. **No `--static` on libraries; never embed external Titan deps:** Build libraries in ordinary mode with explicit roots (Unix `.so`+`.a`, Windows `.dll` only, browser `.a` only—refusing native companions). `--static` is **rejected** on every final no-main library (`-c --static` compiles executable-bound objects only). Declare external Titan packages in `dependencies` (`"lua ~> 5.5"`, `"titan ~> 0.6"`).
3. **`$(PREFIX)` vs `$PREFIX`, `dist/` staging & `titan-install`:** In format `3.0` rockspecs, `$(PREFIX)` is the rock's private version dir (`<tree>/lib/luarocks/rocks-5.5/<rock>/<ver>`), **not** shell `$PREFIX` or SDK root; `$(SCRIPTS_DIR)` is `<tree>/bin`. Stage only final regular files under `$(PREFIX)/dist/{modules,include,lib}` (no `build/`, `.c`/`.o`/`.titan`/`.titan-links`, `dist/bin/`, symlinks, or `dist/include/titan/`) and run `titan-install --path "$(PREFIX)"` (`titan-install.bat` Windows; no `--module`). Rockspecs run in empty `_ENV` (`table` is `nil`; use literals and `..`).
4. **Removal & physical ownership (`titan-uninstall`):** Remove rocks with `titan-uninstall <rock> [version]`, never plain `luarocks remove` (leaves published files behind; follow with `titan-uninstall <rock>`). Bare `titan-uninstall` removes Titan itself! Ownership tracks physical files only: keep one rock per logical namespace so rocks cannot shadow via `.titan` vs `.so` or flat vs folder layouts.
5. **Source-only dependency boundary:** Positional `titanc` roots resolve **only** under authored `--tree` roots. Ordinary `import`s fall back to read-only `<root>/lib/titan/0.6` (needs `-o` when selected). Compiled libraries check installed source imports and leave them external (explicit `.titan` imports error across that boundary); consuming apps elect one owner without rebuilding the library.
6. **DSO binary compatibility:** Replacing `.so`/`.dll` without rebuilding consumers requires unchanged used public signatures (incl. param names), ordered public record fields/union variants, Interface members, and public aliases; check safe/breaking rules below before editing `local` fields/variants or `new`.

## Staging (`$(PREFIX)/dist/`) mapping

| Staged under `$(PREFIX)/dist/` | Published to | Contents & constraints |
| --- | --- | --- |
| `dist/modules/` | `<tree>/lib/titan/0.6/` | Unix `<prefix>.so`+`.a`, Windows `<prefix>.dll` only, or `.titan` source; keep subpaths (`cui/box.so`). |
| `dist/include/` *(opt)* | `<tree>/include/` | Public `.titan.h`/FFI headers in package subdir (`dist/include/cui/`); `include/titan/` is SDK-reserved. |
| `dist/lib/` *(opt)* | `<tree>/lib/` | Optional native C `.a`/Windows `.lib` link inputs; not Titan providers (`lib/luarocks`, `lua`, `titan`, `titan-browser` refused). |

Relative paths under `dist/` must use portable ASCII ordinary components (spaces ok; Windows reserved names, symlinks, and ASCII case aliases rejected; does not apply to absolute SDK/checkout roots).

## Complete minimal library package

Layout (ignore `/build/` and `.titan-ls/` in `.gitignore`; ignore `/dist/` **only** when build-generated, **never** in a source-only repo checking in `dist/modules/`):

```text
titan-cui/  (.gitignore, titan-cui-0.1.0-1.rockspec, src/cui.titan, tests/cui_test.titan)
```

1. **Library (`src/cui.titan`, no `main`) and native test (`tests/cui_test.titan`):**

```titan
-- file: src/cui.titan
local strings = import "string"

function box(text: string): string
  local edge = strings.rep("=", #text + 4)
  return edge .. "\n= " .. text .. " =\n" .. edge
end

-- file: tests/cui_test.titan
local cui = import "cui"
local test = import "test"

function test_box(context: test.Context)
  test.assert(cui.box("Titan") == "=========\n= Titan =\n=========")
end
```

```sh
(cd titan-cui &&
  titanc --incremental --test --tree "src;tests" --test-dir tests -o build --exe build/cui-tests &&
  ./build/cui-tests)   # confirm non-zero case count
```

2. **Format `3.0` rockspec (`titan-cui-0.1.0-1.rockspec`):** `~>` is a prefix match (`TITAN_ABI_VERSION` tracked separately). Windows `platforms.windows` uses `cmd.exe` `\\`, `.exe`/`.bat`, double quotes, and `(if not exist ... mkdir ...) && copy /Y ...`.

```lua
rockspec_format = "3.0"
package = "titan-cui"
version = "0.1.0-1"
source = { url = "git+https://example.invalid/titan-cui.git", tag = "v0.1.0" }
description = { summary = "Minimal console UI box helper for Titan", license = "MIT" }
dependencies = { "lua ~> 5.5", "titan ~> 0.6" }
build = {
   type = "command",
   build_command = '"$(SCRIPTS_DIR)/titanc" --incremental --tree src --output build cui',
   install_command = 'mkdir -p "$(PREFIX)/dist/modules" && cp -p build/cui.so build/cui.a "$(PREFIX)/dist/modules/"',
   platforms = {
      windows = {
         build_command = '"$(SCRIPTS_DIR)\\titanc.exe" --incremental --tree src --output build cui',
         install_command = '(if not exist "$(PREFIX)\\dist\\modules" mkdir "$(PREFIX)\\dist\\modules") && copy /Y build\\cui.dll "$(PREFIX)\\dist\\modules\\cui.dll"'
      }
   }
}
hooks = {
   post_install = '"$(SCRIPTS_DIR)/titan-install" --path "$(PREFIX)"',
   platforms = {
      windows = {
         post_install = '"$(SCRIPTS_DIR)\\titan-install.bat" --path "$(PREFIX)"'
      }
   }
}
```

3. **Install locally (`luarocks make`) and verify from an outside `demo/` dir (no `--tree`/`TITAN_PATH_0_6`):**

```text
-- demo/main.titan (outside titan-cui/ so src/ and build/ cannot resolve)
local cui = import "cui"
local io = import "io"

function main(args: {string}): integer
  io.print(cui.box("Titan"))
  return 0
end
```

```sh
(cd titan-cui && luarocks make titan-cui-0.1.0-1.rockspec)
(cd demo &&
  titanc -o build --exe build/demo main && ./build/demo &&
  titanc --static -o build-static --exe build-static/demo main && ./build-static/demo &&
  lua -e 'require "titan"; print(require("cui").box("Titan"))')
titan-uninstall titan-cui   # Windows: skip --static; run build\demo.exe
```

## Multi-module providers, folder modules, and `-X` payloads

- **Prefix bundles:** `titanc --tree src -o build a.b.left a.b.right` emits `build/a/b.so`+`.a` (`a/b.dll` Windows; `a/b.a` browser). Modules keep separate state, exports, and init guards (`require "a.b.left"` initializes only `a.b.left` + its imports). Authored `--tree` helpers link in without changing the prefix, but aren't independently discoverable unless named as roots.
- **Folder modules:** `pkg/name/name.titan` + immediate sibling `*.titan` contributors form **one** logical module (`pkg.name`), one `luaopen_*`, and shared `local` scope. Contributors sort bytewise, cannot be imported directly, and cannot hold `do ... end` initializers (main only).
- **Native deps & `-X`:** Native library links require external compiled Titan deps to supply a `.so`/`.dll` (`.a`-only external deps fail). Non-Titan `-X` `.o`/`.a` payloads carry into `.so` and `.a` in CLI order (child C archives flattened; metadata-bearing Titan `.o` rejected on `-X`). Browser libraries run structural + Node 26+ executing protocol checks.

## Source-only rocks and cross-library obligations

Replace only `build` to ship `.titan` source: stage `src/cui.titan` into `$(PREFIX)/dist/modules/` via `type = "command"`, or check in `dist/modules/cui.titan` (don't ignore `/dist/`) with `build = { type = "none", copy_directories = { "dist" } }`.

- **Compiled library importing installed source:** Public `import`s from `<root>/lib/titan/0.6` (even private/initializer-only, and under plain non-`main`/non-`--test`/non-`--static` `-c` or `--source-first`) are checked and recorded in `source_requirements` without entering the library. Declare the rock in `dependencies`; stage only own providers. Explicit `.titan` imports error across this boundary.
- **Consumer single-owner election:** Apps/`--test` builds satisfy reached obligations once by logical name (no redundant `import`) via ordinary lookup—authored `--tree`, installed source (needs `-o`), standalone provider, or canonical prefix bundle:
  - **Unix default:** `.so` (lazy), `.a` fallback (linked), or compile source once. **Unix `--static`:** `.a` or compile source once (rejects DSO-only).
  - **Windows:** `.dll` (lazy) or compile into app DLL. **`--target browser`:** Wasm `.a` or `.browser.titan`/shared `.titan` (never native binaries).
  Duplicate independent physical providers (`meas/meter.so` + `meas.a` carrying `meas.meter`) are diagnosed; paired `.so`/`.a` at one stem are one distribution.
- **Upgrades & bare Lua:** Built apps keep app-compiled source if disk changes; rebuilt apps bind a compatible compiled provider without rebuilding intermediate libraries. Compatible source edits rebuild only the app; changing *which* source modules a library requires means rebuilding forwarding libraries (`--incremental` detects it). In bare Lua `require`, loading a library built against a dependency as source requires that dependency to be initialized or natively preloaded first (e.g., `require` a compiled provider first).

## Packing, DSO compatibility, and removal

- **Source vs prebuilt rocks:** `luarocks pack <rockspec>` builds `<pkg>.src.rock`; `luarocks upload <rockspec>` publishes to LuaRocks (never locally). `luarocks pack titan-cui 0.1.0-1` archives `$(PREFIX)` (incl. `dist/`) and may label it `.all.rock`—rename to `.<arch>.rock` (`luarocks config arch`) before sharing (tied to OS, arch, Lua, ABI, profile).
- **DSO replacement rules:** First initialized provider per Lua state is canonical (no hot-reload; cannot override app-linked copies). Load-time ABI/compatibility checks enforce:
  - **Safe:** unused export add/remove, function/var reorder, generic param rename (`T`->`U`), `local` field/variant edits (except breaking cases below).
  - **Breaking:** used function/method/static/`foreign function` erased types or param names; module var type/`const`; ordered public record fields/`const`; ordered public union variants/payload names; Interface members; referenced public aliases. Adding `local` fields or overriding `new` breaks raw `{...}` literals, fused native storage, or initializer own-callable construction; adding any union variant breaks closed-union `case` non-fallthrough without a terminating `else`.
- **Upgrades & removal:** One active version per rock. `titan-install` preflights destinations and rejects collisions with foreign files, SDK paths (`include/titan/`), or protected `lib/` subtrees before writing; succeeding reinstall/upgrade retires stale owned files and prunes empty dirs. `titan-uninstall <rock> [version]` preserves files if LuaRocks' dep check fails; removing an inactive older version leaves the active one intact (no switch-back); absent-rock cleanup is a no-op. Close Windows consumers holding mapped DLLs first.

## Pre-delivery verification checklist

1. Native tests pass via `titanc --incremental --test --tree "src;tests" --test-dir tests` with non-zero cases.
2. Format `3.0` rockspec is empty-`_ENV`-safe, stages portable ASCII files under `$(PREFIX)/dist/{modules,include,lib}`, has Windows `cmd.exe` overrides, and hooks `titan-install --path "$(PREFIX)"`.
3. `luarocks make` installs cleanly; an **outside** `demo/` consumer (no `--tree`/`TITAN_PATH_0_6`) passes dynamic, Unix `--static`, and `lua -e 'require "titan"; ...'`.
4. Libraries depending on installed source verify consumer single-owner compilation under `-o` (and bare-Lua preload order if relevant).
5. `titan-uninstall <rock>` removes the rock and all published files under `lib/titan/0.6/`, `include/`, and `lib/`.
