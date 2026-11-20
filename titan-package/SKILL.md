---
name: titan-package
description: Package, publish, test, and uninstall reusable Titan library modules as LuaRocks rocks using titan-install and titan-uninstall. Covers library repository layout, logical module naming and common-prefix providers, native tests, format 3.0 rockspecs, dist/{modules,include,lib} staging, compiled vs source-only rocks, .src.rock vs prebuilt packing, separate consumer checks, and removal rules. Use alongside titan-programmer for reusable libraries; use titan-application for standalone native or browser applications.
---

# Titan module packaging

Use this skill for reusable Titan libraries packaged with LuaRocks. Load
[titan-programmer](../titan-programmer/SKILL.md) before writing or reviewing
`.titan` code and [titan-tester](../titan-tester/SKILL.md) for native tests.
Use [titan-application](../titan-application/SKILL.md) for standalone native or
browser applications. No Makefile is required.

## Quickstart: layout, code, test, rockspec, verify, remove

Keep the rock name (`titan-cui`) separate from the logical Titan module name
(`cui`, or a dotted prefix like `cui.box` and `cui.text`). Neither the rock
name nor `package.cpath` affects Titan's binary lookup: provider filenames
follow the logical module name or longest common dotted prefix.

Illustrative layout (ignore `/build/` and `.titan-ls/` in `.gitignore`; ignore
`/dist/` **only** if a build step generates it—never ignore `/dist/` in a
source-only repo that checks in `dist/modules/`):

```text
titan-cui/
  .gitignore
  titan-cui-0.1.0-1.rockspec
  src/
    cui.titan
  tests/
    cui_test.titan
```

1. Write `titan-cui/src/cui.titan` (no `main`, so `titanc` builds a provider):

```titan
local strings = import "string"

function box(text: string): string
  local edge = strings.rep("=", #text + 4)
  return edge .. "\n= " .. text .. " =\n" .. edge
end
```

2. Write and run a native test in `titan-cui/tests/cui_test.titan`:

```titan
local cui = import "cui"
local test = import "test"

function test_box(context: test.Context)
  test.assert(cui.box("Titan") == "=========\n= Titan =\n=========")
end
```

```sh
(cd titan-cui &&
  titanc --incremental --test --tree "src;tests" --test-dir tests --output build --exe build/cui-tests &&
  ./build/cui-tests)
```

Verify the reported case count is non-zero.

3. Write `titan-cui/titan-cui-0.1.0-1.rockspec` (replace `source.url` and `tag`
   with your own release before packing a `.src.rock`):

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

4. Build and install locally (`luarocks make` does not fetch `source.url`):

```sh
(cd titan-cui && luarocks make titan-cui-0.1.0-1.rockspec)
```

5. Verify from a separate `demo/` directory outside `titan-cui/` (so nothing
   can resolve `titan-cui/src` or `titan-cui/build`). Write `demo/main.titan`:

```titan
local cui = import "cui"
local io = import "io"

function main(args: {string}): integer
  io.print(cui.box("Titan"))
  return 0
end
```

Compile and run with no `--tree` and no `TITAN_PATH_0_6` override:

```sh
(cd demo &&
  titanc --output build --exe build/demo main &&
  ./build/demo &&
  titanc --static --output build-static --exe build-static/demo main &&
  ./build-static/demo &&
  lua -e 'require "titan"; print(require("cui").box("Titan"))')
```

On Windows (no `--static` mode):

```cmd
titanc --output build --exe build\demo.exe main
build\demo.exe
```

6. Remove the installed rock and its published files:

```sh
titan-uninstall titan-cui
```

## Rockspec and `dist/` staging rules

| Staged under `$(PREFIX)/dist/` | Published to | Contents |
| --- | --- | --- |
| `dist/modules/` | `<tree>/lib/titan/0.6/` | Unix `<prefix>.so` + `<prefix>.a`, Windows `<prefix>.dll` only, or `.titan` source files; preserve logical subpaths (`cui/box.so` for `cui.box`). |
| `dist/include/` *(optional)* | `<tree>/include/` | Public C headers (`.titan.h`, companion FFI headers); `include/titan/` is reserved for SDK headers, so use a package-specific directory such as `dist/include/cui/`. |
| `dist/lib/` *(optional)* | `<tree>/lib/` | Optional native link inputs (C archives or Windows import `.lib`); not stand-alone Titan providers. |

- **`$(PREFIX)` vs shell `$PREFIX`:** Inside a rockspec, `$(PREFIX)` is the
  installing rock's private version dir (e.g.
  `<tree>/lib/luarocks/rocks-5.5/titan-cui/0.1.0-1`), not the SDK root, shell
  `$PREFIX`, or `dist/`. `$(SCRIPTS_DIR)` is `<tree>/bin/`. Pass `--path
  "$(PREFIX)"` (no `--module` alias or extra flags).
- **Dependencies:** In LuaRocks, `~>` is a prefix match (`"lua ~> 5.5"`
  matches `5.5.*`; `"titan ~> 0.6"` matches Titan `0.6.*` releases—`TITAN_ABI_VERSION`
  is tracked independently of package version).
- **Libraries vs bundles vs executables:** Build a single library module or a
  related canonical bundle in ordinary library mode with explicit logical roots
  (the standard library names all of its own roots; no other package embeds
  it), publishing only its own `.so`/`.a` pair on Linux/macOS (`.dll` only on
  Windows) without incorporating external Titan dependencies; declare
  dependencies in `dependencies` instead. `--static` is rejected on every final
  no-main library output, including canonical bundles (`-c --static` still
  compiles individual objects for a later executable, not a linked library).
  Dynamic/default applications may still fall back to an archive-only
  dependency or compile source; on Linux/macOS, `--static` standalone and
  `--test` executables embed the full reached Titan dependency closure from
  `.a` archives plus source compiled in the application, with no fallback to
  shared Titan providers (a missing archive for an external prebuilt dependency
  not satisfied by application-compiled source is a build error). `--static`
  governs Titan module archives and does not force `libc`, OS support, or
  external native libraries to link statically (nor forbid external linker
  flags that request it).
- **Clean staging:** Stage only exact final regular files—no `build/` copy, no
  `.c`/`.o`/`.titan`/`.titan-links`, no `dist/bin/`, no symlinks, no direct
  SDK writes. Relative paths under `dist/` must use portable ASCII ordinary
  file components (spaces allowed; Windows reserved names, symlinks, and
  path/case aliases refused; this portable-entry naming rule does not apply to
  the absolute SDK or checkout path).
- **Windows `platforms.windows`:** Use native `cmd.exe` commands with `\\`,
  explicit `.exe`/`.bat`, double-quoted paths, and parenthesized
  `(if not exist ... mkdir ...) && copy /Y ...` so `&&` stays outside the `if`.

## Source-only packages

Keep the same rockspec metadata, dependencies, and `hooks`, and replace only
`build`. Stage `src/cui.titan` into `$(PREFIX)/dist/modules/` at install time:

```lua
build = {
   type = "command",
   install_command = 'mkdir -p "$(PREFIX)/dist/modules" && cp -p src/cui.titan "$(PREFIX)/dist/modules/"',
   platforms = {
      windows = {
         install_command = '(if not exist "$(PREFIX)\\dist\\modules" mkdir "$(PREFIX)\\dist\\modules") && copy /Y src\\cui.titan "$(PREFIX)\\dist\\modules\\cui.titan"'
      }
   }
}
```

Or check `dist/modules/cui.titan` directly into the repo (without ignoring
`/dist/`) and use `build = { type = "none", copy_directories = { "dist" } }`.

Positional `titanc` build roots—for a library, program, `-c`, explicit
`--test`, or `--exe` build—resolve **only** from authored `--tree` roots
(default `.`), never from the implicit installed source fallback: build a
library from its checkout with `--tree` (as the rockspec does for `cui`),
never by naming an installed dependency as a positional root. Ordinary
`import` statements inside a valid authored root search authored `--tree`
roots first before falling back to the read-only implicit SDK root
`<root>/lib/titan/0.6` on both native and browser targets (browser uses it for
`.titan` source only, selecting `.browser.titan`/shared variants; native
providers there are never eligible). Selecting an installed source through
that fallback requires `-o`/`--output` so generated files stay in the
consumer's output tree and `titanc` neither writes nor locks in the implicit
SDK root. Separately from the positional-root rule, compiling an ordinary
binary library fails if a dependency is selected from the implicit installed
source fallback (including under `--source-first` when a paired compiled
provider is also installed) rather than copying another rock's module into the
library's provider: install or use that dependency's compiled provider
(building without `--source-first` if one is already installed), or publish
your library as source-only until
[titan#427](https://github.com/mascarenhas/titan/issues/427) allows an
external installed-source dependency to be compiled once by the final program.
(Without `-o`/`--output`, the generic missing-`--output` diagnostic can appear
first; passing `-o` does not permit vendoring an installed source into a binary
library.) Same-repo authored sources under `--tree` (or default `.`) still
compile together into a library, and ordinary/`--static` applications and
`--test` builds still compile installed fallback sources into `--output`. Ordinary Lua
`require` loads compiled providers, not uncompiled `.titan` sources.

## Publishing, packing, and removal

Distinguish three concepts:

1. **Source distribution (`.rockspec` / `.src.rock`):** `luarocks pack
   titan-cui-0.1.0-1.rockspec` fetches the pinned `source` URL/tag and packs
   rockspec + sources into `titan-cui-0.1.0-1.src.rock`. To publish through
   your LuaRocks account, run `luarocks upload titan-cui-0.1.0-1.rockspec`
   (which packs a `.src.rock` by default; pass a prepacked
   `titan-cui-0.1.0-1.src.rock` only as the optional second argument—do not
   run `upload` during local verification).
2. **Package-built native provider:** Compiled during `luarocks install` /
   `luarocks make` into `<tree>/lib/titan/0.6/`; usable from Titan and Lua.
3. **Installed source-only module:** `.titan` files in `<tree>/lib/titan/0.6/`;
   compiled into each Titan consumer's `--output` directory (not Lua `require`).

Packing an installed native rock (`luarocks pack titan-cui 0.1.0-1`) archives
`$(PREFIX)` (including `dist/`) and may label it `.all.rock` because `dist/`
is outside LuaRocks' `lib` deployment. Rename it to `.<arch>.rock` (`luarocks
config arch`) before sharing; it is tied to OS, arch, Lua version, Titan ABI,
and build profile.

- **Removal:** `titan-uninstall titan-cui` removes the active published
  version; `titan-uninstall titan-cui 0.1.0-1` removes one exact version
  (removing an inactive older version leaves the active one untouched, with no
  automatic switch-back). Plain `luarocks remove` leaves published files
  behind; follow with `titan-uninstall ROCK [VERSION]` to clean them (repeat
  cleanup of an absent rock is a no-op). When LuaRocks' dependency check fails,
  published files are preserved.
- **Reinstalls, upgrades & collisions:** One active published version per
  rock. Preflight checks all destinations first: a collision with any foreign
  file, Titan SDK-owned path (including the reserved `include/titan/` header
  subtree), or protected `lib/` subtree refuses the install before changing
  any published files (separate from mid-copy I/O failures; there is no
  blanket transaction guarantee). Ownership is tracked per physical
  destination file with no compiler or DSO metadata introspection on publish:
  keep one rock per logical module/namespace and distinct author prefixes (as
  with Lua module rocks), because two rocks shipping different physical
  representations of the same logical module (for example `.titan` source
  versus prebuilt `.so`/`.a`/`.dll`, or flat versus folder files) are not
  rejected by logical name and can shadow each other. On a succeeding
  same-version reinstall or upgrade, `titan-install` retires only stale files
  owned by that rock and prunes shared directories only when empty.
- **No arguments:** `titan-uninstall` alone requests whole-Titan removal
  (also subject to LuaRocks' dependency check). On Windows, close consumers
  holding a module's DLL before upgrading or removing it.

References:
[Packaging and distributing modules with LuaRocks](../../../doc/language/modules.md#packaging-and-distributing-modules-with-luarocks),
[Toolchain](../../../doc/language/toolchain.md),
[Windows](../../../doc/language/windows-build.md), and
[Module rock publication and removal](../../../doc/implementation/build-script-audit.md#module-rock-publication-and-removal).
