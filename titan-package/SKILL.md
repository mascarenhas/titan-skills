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
  it). On Linux/macOS a library publishes its own `.so`/`.a` pair, and on
  Windows its `.dll` only, carrying only its authored `--tree` modules (plus
  any explicit non-Titan `-X` payloads) without incorporating external compiled
  Titan dependencies or external installed source-only dependencies; declare
  package dependencies in `dependencies` instead. On `--target browser`, a
  library publishes `.a` only, likewise leaving external installed source-only
  dependencies external while retaining browser's preexisting separate archive
  composition for compiled browser dependencies. `--static` is rejected on
  every final no-main library output, including canonical bundles (`-c
  --static` still compiles individual objects for a later executable, not a
  linked library). Dynamic/default applications may still fall back to an
  archive-only dependency or compile source; on Linux/macOS, `--static`
  standalone and `--test` executables embed the full reached Titan dependency
  closure from `.a` archives plus source compiled in the application (including
  any external dependencies recorded by reached members of imported prebuilt
  libraries, satisfied by `.a` archives or compiled source), with no fallback
  to shared Titan providers (a missing archive for an external prebuilt
  dependency—including a DSO-only replacement for a formerly source-only
  dependency—not satisfied by application-compiled source is a build error).
  `--static` governs Titan module archives and does not force
  `libc`, OS support, or external native libraries to link statically (nor
  forbid external linker flags that request it).
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
that fallback—even when a library build only checks it—requires `-o`/`--output`
so generated files stay in the caller's output tree and `titanc` neither
writes nor locks in the implicit SDK root.

A compiled library can depend on an installed source-only module without owning
it, and each consuming application supplies one chosen owner for that
dependency without rebuilding the library when the dependency's distribution
changes:

- **Library builds and plain `-c`:** In a library build—including plain
  non-`main`, non-`--test`, non-`--static` `-c` (prospective library mode) and
  `--source-first`—an ordinary public `import` resolved from
  `<root>/lib/titan/0.6` is checked for its public interface and public layouts
  and stays external (neither it nor its private helpers/native dependencies
  enter the library provider; plain non-`main` `-c` writes only owned library
  objects, with no orphan object for the installed source). Declare the
  dependency rock in `dependencies` and stage only your library's own provider
  files—no new package format, manifest, config, or compiler flag is needed.
  Even a private or initializer-only import of an installed source-only module
  is tracked automatically without appearing in the library's public API;
  wrapper libraries check reached external dependencies without owning them and
  forward those obligations cleanly. Explicit `.titan` private collaboration
  (`import "dep.titan"`) remains strictly source-only and is rejected across
  the installed-source library boundary—use an ordinary public `import` or an
  authored `--tree` checkout (explicit `.titan` collaboration remains valid
  within authored `--tree` roots and inside applications and `--test` builds).
- **Ordinary single-owner selection in consumers:** For each external
  dependency recorded by a reached logical member of an imported prebuilt
  library, `titanc` resolves that logical module through **ordinary
  single-owner election** for the current build mode and target—the same
  candidate, claim, and preference order as a written `import`, with no
  redundant `import` required in the application and no broad filesystem or
  runtime plugin scan for arbitrarily named non-prefix DSOs:
  - **Source or compiled provider:** default ordinary lookup tries compiled
    providers before source (so a compatible compiled provider can win even
    when source also exists), while `--test` and `--source-first` try source
    first; within source lookup, authored `--tree` roots precede the read-only
    `<root>/lib/titan/0.6` fallback. Eligible compiled providers are a
    standalone provider (`.so`/`.a` on Unix, `.dll` on Windows, `.a` on
    `--target browser`), a canonical common-prefix bundle claiming that logical
    module (such as `pkg.so`/`pkg.a`/`pkg.dll` supplying `pkg.meter`), or an
    already-carried member of a selected archive/bundle.
  - **Targets and `--static`:** When source is chosen, default Unix, Unix
    `--static`, Windows (via the companion application provider DLL behind the
    launcher), and `--target browser` compile that source **once** into the
    application; `--output` is required only when the build actually selects
    installed fallback `.titan` source (or on `--target browser`), not when a
    compiled provider or authored `--tree` source satisfies it. When a compiled
    provider is chosen, a selected shared DSO or DLL (default Unix or Windows)
    loads lazily through the application at run time, whereas a selected `.a`
    archive (default Unix archive-only fallback, Unix `--static`, or
    `--target browser`) links its reached member into the executable or
    WebAssembly image rather than opening a DSO at run time. Unix `--static`
    accepts only `.a` archives or compiled source and rejects a DSO-only
    provider; `--target browser` accepts only eligible WebAssembly `.a`
    archives or `.browser.titan`/shared `.titan` source (never native host
    binaries or dynamic loading). Every library shares the application's single
    chosen owner and state lazily in written import order through the checked
    public ABI; a dormant sibling in a multi-module library imposes no
    additional logical source or build demand merely by being dormant (physical
    symbol/container rules still apply).
- **Diagnostics, ABI checks, and conflicts:** Missing all eligible owners fails
  the build naming both the requesting library and the missing dependency. An
  incompatible ABI or used public interface, a malformed claimed provider,
  genuinely conflicting independent physical owners for the same logical
  module, or a cross-boundary cycle remains a compile/link or load error—never
  weakened or silently skipped.
- **Upgrades, existing apps, editors, and bare Lua hosts:** An already-built
  application whose selected owner was compiled from source retains that
  app-compiled module and continues running unchanged if the dependency on disk
  is later replaced by a compiled provider or removed. A later application
  rebuilt against the **same** prebuilt library (without rebuilding that
  library) accepts a compatible compiled provider—standalone or canonical
  prefix bundle—when ordinary election chooses it, with no source codegen for
  that dependency. Compatible implementation or private-dependency edits to an
  installed source likewise require rebuilding only the consuming application;
  if a compiled intermediate library changes which external modules it
  requires, rebuild compiled libraries that forward those obligations
  (`--incremental` detects the change). Editors and the language server lazily
  recover exposed types from a prebuilt library's recorded dependencies on
  demand using the same ordinary module selection (checking nothing for purely
  private requirements with no exposed-type demand until a build runs). In a
  bare Lua host (which has no Lua-side Titan compiler and no Titan application
  binding table), loading a prebuilt library **built against that dependency as
  installed source** requires the dependency to be already initialized or
  registered via Titan's native preload machinery in that Lua state—for example
  by `require`-ing an independently installed compiled provider first—rather
  than relying on an arbitrary Lua `package.preload` function (ordinary
  compiled imports and directly `require`-ing an installed compiled provider
  keep their normal Titan searcher behavior).

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
3. **Installed source-only module:** `.titan` files in `<tree>/lib/titan/0.6/`.
   Compiled libraries can typecheck against them and publish without owning
   them; each consuming Titan application or `--test` executable supplies one
   chosen owner through ordinary module selection—compiling the source once
   (under `--output` whenever installed fallback source is selected or on
   `--target browser`) or binding a later compatible compiled provider or
   canonical prefix bundle without rebuilding the library. In a bare Lua state,
   loading a library built against that dependency as source requires it to be
   already initialized or natively preloaded first.

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
