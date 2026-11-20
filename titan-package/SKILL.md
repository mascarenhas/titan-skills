---
name: titan-package
description: Package, publish, test, and uninstall reusable Titan library modules as LuaRocks rocks using titan-install and titan-uninstall. Covers library repository layout, logical module naming and common-prefix providers, native tests, format 3.0 rockspecs, dist/{modules,include,lib} staging, compiled vs source-only rocks, binary-rock packing caveats, separate consumer import checks, and ownership/removal rules. Use alongside titan-programmer for reusable libraries; use titan-application for standalone native or browser applications.
---

# Titan module packaging

Use this skill when creating, packaging, testing, or removing a reusable Titan
library distributed through LuaRocks. Load
[titan-programmer](../titan-programmer/SKILL.md) before writing or reviewing
any `.titan` source, and [titan-tester](../titan-tester/SKILL.md) for native
tests. For standalone native or browser applications, use
[titan-application](../titan-application/SKILL.md) instead.

## Choose the library layout and logical module names

A Titan library rock publishes its built providers (or `.titan` source files)
into the installed Titan tree so separate applications and Lua programs can
import it without custom `TITAN_PATH_0_6` settings.

Keep the LuaRocks package name (`titan-cui`) distinct from the Titan logical
module name (`cui`, or a dotted prefix such as `cui.box` and `cui.text`).
Neither the rock name nor Lua's `package.cpath` changes Titan's provider lookup:
provider filenames always follow the logical module name or the longest common
dotted prefix of the roots passed to `titanc`.

An illustrative library repository layout is:

```text
titan-cui/
  .gitignore
  titan-cui-0.1.0-1.rockspec
  src/
    cui.titan
  tests/
    cui_test.titan
  build/                       # compiler outputs (ignored; never staged whole)
```

Start `.gitignore` with:

```gitignore
/build/
/dist/
.titan-ls/
```

Avoid blanket `*.c`, `*.h`, or `*.lua` ignores so authored FFI headers, C
helpers, and rockspecs stay trackable.

A library module omits `main` so `titanc` emits a provider instead of an
executable. Write `titan-cui/src/cui.titan`:

```titan
--- Minimal console UI formatting helpers.
-- @module cui

local strings = import "string"

--- A framed single-line text banner.
record Banner
  const title: string
  const border: string
end

--- Render the banner with matching top and bottom borders.
-- @return A multi-line bordered string.
function Banner:render(): string
  local width = #self.title + 4
  local edge = strings.rep(self.border, width)
  return edge .. "\n" .. self.border .. " " .. self.title .. " " .. self.border .. "\n" .. edge
end

--- Frame `text` with a single-character border (defaults to `"="`).
-- @param text The line to frame.
-- @param border Optional border string.
-- @return The rendered banner.
function box(text: string, border: string?): string
  local mark = border or "="
  return Banner(text, mark):render()
end
```

## Write and run native library tests first

Test the library before packaging it. Write `titan-cui/tests/cui_test.titan`:

```titan
local cui = import "cui"
local test = import "test"

function test_box_formatting(context: test.Context)
  context:run("default_border", function(_)
    test.assert(cui.box("Titan") == "=========\n= Titan =\n=========")
  end)

  context:run("custom_border", function(_)
    local banner = cui.Banner("Hi", "*")
    test.assert(banner:render() == "******\n* Hi *\n******")
    test.assert(cui.box("Hi", "*") == banner:render())
  end)
end
```

Compile and run with `--tree "src;tests"` so tests import `cui` by its normal
logical name while `--test-dir tests` discovers `cui_test`:

```sh
titanc --incremental --test --tree "src;tests" --test-dir tests --output build --exe build/cui-tests
./build/cui-tests
```

Verify the reported case count is non-zero; an empty filtered run is not test
evidence. See [titan-tester](../titan-tester/SKILL.md#9-compile-run-and-filter-a-project-suite)
for filters and fixtures.

## Write the format 3.0 rockspec and stage `dist/`

Installing Titan places `titan-install` and `titan-uninstall` beside `titanc`
in `<tree>/bin/` (`titan-install.bat` and `titan-uninstall.bat` on Windows).
Use a format `3.0` rockspec with the `command` build backend, stage only the
exact final providers under `$(PREFIX)/dist/modules/`, and invoke
`titan-install --path "$(PREFIX)"` in `hooks.post_install`:

```lua
rockspec_format = "3.0"
package = "titan-cui"
version = "0.1.0-1"
source = {
   url = "git+https://github.com/example/titan-cui.git",
   tag = "v0.1.0"
}
description = {
   summary = "Minimal console UI formatting helpers for Titan",
   license = "MIT"
}
dependencies = {
   "lua ~> 5.5",
   "titan ~> 0.6"
}
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

Follow these exact rockspec and staging rules:

- **`$(PREFIX)` vs shell `$PREFIX`:** Inside a rockspec, `$(PREFIX)` is the
  *installing rock's private version directory* (for example
  `<tree>/lib/luarocks/rocks-5.5/titan-cui/0.1.0-1`), not the Titan SDK root,
  not shell `$PREFIX`, not your checkout directory, and not `dist/`.
  `$(SCRIPTS_DIR)` is the selected tree's public `bin/` directory. Pass
  `--path "$(PREFIX)"` directly (there is no `--module` alias and no extra
  prefix/release flags).
- **LuaRocks `~>` constraints:** In LuaRocks, `~>` is a **prefix match**, not
  Ruby's pessimistic operator. `"lua ~> 5.5"` matches Lua `5.5.*`, and
  `"titan ~> 0.6"` matches any `0.6.*` release in Titan's `0.6` ABI line while
  rejecting `0.7.0` and `0.7.0alpha`. `"titan ~> 0.6.0"` locks to `0.6.0-*`
  only and rejects `0.6.1`. Combine with `>=` if you need a minimum patch floor
  (`"titan ~> 0.6, >= 0.6.0"`). Pin `source` to a Git tag or checksummed
  archive for releases; local `luarocks make` builds from the current working
  directory without fetching `source.url`.
- **Three staged namespaces under `$(PREFIX)/dist/`:**
  - `dist/modules/` -> `<tree>/lib/titan/0.6/` (required for modules: on Linux
    and macOS stage both `<prefix>.so` and `<prefix>.a`; on Windows stage
    `<prefix>.dll` only; preserve logical subpaths such as `cui/box.so` for
    `cui.box`).
  - `dist/include/` *(optional)* -> `<tree>/include/` (public C headers such as
    generated `.titan.h` or companion FFI headers).
  - `dist/lib/` *(optional)* -> `<tree>/lib/` (optional native link inputs such
    as C static libraries or Windows import `.lib` files; never treat a `.lib`
    or `.dll.a` as a stand-alone Titan provider).
- **Stage only exact final files:** Never copy `build/` wholesale, never stage
  compiler intermediates (`.c`, `.o`, `.titan/`, `.titan-links/`), never use
  `dist/bin/`, never stage symlinks, and never write directly into the SDK from
  `build_command` or `install_command`. Alternatively, a build step may
  recreate a fresh local `dist/` directory and declare
  `build.copy_directories = { "dist" }`, but staging directly into
  `$(PREFIX)/dist/modules` avoids carrying stale local files.
- **Portable relative names:** Entries under `dist/` must use ordinary regular
  files with portable ASCII relative path components (spaces are allowed;
  Windows reserved or ambiguous spellings, symlinks, and path/case aliases are
  refused; ownership keys compare ASCII case-insensitively). Absolute checkout
  and SDK roots are not restricted by this rule.
- **Windows commands:** In `platforms.windows`, use native `cmd.exe` commands
  with backslashes (`\\` in Lua strings), explicit `.exe`/`.bat` extensions,
  and double-quoted paths; never put POSIX `mkdir -p` or `cp` in a Windows
  override. Keep `(if not exist ... mkdir ...)` parenthesized before `&&` so
  `cmd.exe` does not bind `copy` inside the `if`.

## Source-only packages and installed source lookup

A package may ship `.titan` source files under
`dist/modules/<logical/path>.titan` instead of prebuilt native providers. With
`dist/modules/cui.titan` in the repository, `build.type = "none"` and
`copy_directories = { "dist" }` stage the files without compiling at install
time:

```lua
rockspec_format = "3.0"
package = "titan-cui"
version = "0.1.0-1"
source = {
   url = "git+https://github.com/example/titan-cui.git",
   tag = "v0.1.0"
}
description = {
   summary = "Minimal console UI formatting helpers for Titan (source-only)",
   license = "MIT"
}
dependencies = {
   "lua ~> 5.5",
   "titan ~> 0.6"
}
build = {
   type = "none",
   copy_directories = { "dist" }
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

When compiling a consumer, `titanc` searches every authored root from `--tree`
(default `.`) and then falls back to the read-only installed module directory
`<root>/lib/titan/0.6` on both native and browser targets (passing `--tree`
replaces `.` without disabling this fallback; on `--target browser`,
`<root>/lib/titan/0.6` is searched for `.titan` source only, selecting
`.browser.titan` and shared `.titan` variants normally, and native providers
there are never eligible). Whenever a build actually selects an installed
`.titan` source through that fallback, `-o`/`--output` is **required** so
generated C, objects, and build locks stay in the consumer's output directory
rather than the installed SDK; omitting `--output` fails with an error naming
the logical module and asking for `--output DIR`. Lua's `require` loads
compiled providers (`.so`/`.dll`), not uncompiled `.titan` sources.

## Source rocks versus prebuilt packed rocks

Distribute **source rocks** (a rockspec with a pinned tag or checksummed
archive) as the default path so `luarocks install titan-cui` compiles for each
consumer's OS, CPU architecture, Lua installation, Titan ABI, and build
profile.

If you run `luarocks pack titan-cui 0.1.0-1` on an installed native rock,
LuaRocks packs the retained `$(PREFIX)` directory (including `dist/`), and
installing that `.rock` runs `hooks.post_install` without compiling. Because
files under `dist/modules/` are outside LuaRocks' `lib` deployment, `luarocks
pack` can label the output `.all.rock` even though it holds native binaries.
Never ship a prebuilt native Titan rock as `.all.rock`: rename it to the host
architecture from `luarocks config arch` (such as `linux-x86_64`) and treat it
as coupled to that OS, architecture, Lua version, Titan ABI, and build profile.

## Verify from a distinct consumer and uninstall cleanly

Install locally from the package directory:

```sh
(cd titan-cui && luarocks make titan-cui-0.1.0-1.rockspec)
```

Create a separate consumer directory (`demo/`) outside `titan-cui/` so nothing
can resolve against `titan-cui/src` or `titan-cui/build`. Write
`demo/main.titan`:

```titan
local cui = import "cui"
local io = import "io"

function main(args: {string}): integer
  io.print(cui.box(args[1] or "Titan"))
  return 0
end
```

Compile and run from `demo/` with no `--tree` and no `TITAN_PATH_0_6`
override (testing both dynamic and `--static` on Linux/macOS, plus Lua's
`require` for compiled providers):

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

Then remove the module rock with `titan-uninstall`:

```sh
titan-uninstall titan-cui
```

Pass an explicit full rock version (`titan-uninstall titan-cui 0.1.0-1`) to
remove one exact version (including an inactive older version without touching
the active published one; there is no automatic switch-back). Follow these
ownership and removal rules:

- **Never rely on plain `luarocks remove` alone:** `luarocks remove` has no
  uninstall hook and leaves published files under `lib/titan/0.6/`, `include/`,
  and `lib/`. If `luarocks remove titan-cui` already ran, follow it with
  `titan-uninstall titan-cui` (or `titan-uninstall titan-cui 0.1.0-1`) to
  clean up the remaining published files; repeating cleanup for an absent rock
  is a no-op.
- **Dependency refusals preserve files:** `titan-uninstall` removes the rock
  through LuaRocks before deleting published files, so if another rock depends
  on `titan-cui`, nothing is torn down.
- **Upgrades and collisions:** Each rock has one active published version.
  Reinstalling or upgrading retires only stale files owned by that rock;
  foreign files, Titan SDK files, and protected `lib/` subtrees are never
  overwritten, and shared directories are pruned only when empty.
- **No arguments removes Titan itself:** Plain `titan-uninstall` (without a
  rock name) uninstalls Titan. On Windows, close processes holding a module's
  mapped DLL before upgrading or removing it.

For the full language guide and publication contract, see
[Packaging and distributing modules with LuaRocks](../../../doc/language/modules.md#packaging-and-distributing-modules-with-luarocks),
[The `titanc` toolchain](../../../doc/language/toolchain.md),
[Installing and using Titan on Windows](../../../doc/language/windows-build.md),
and [Module rock publication and removal](../../../doc/implementation/build-script-audit.md#module-rock-publication-and-removal).
