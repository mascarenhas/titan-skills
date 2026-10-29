---
name: titan-application
description: Start or organize a standalone Titan application repository, including source and test layout, build artifact ownership, initial .gitignore, installed SDK use, and executable delivery checks. Use alongside titan-programmer for application scaffolding and build setup; compiler and standard-library development use their existing repository workflows.
---

# Titan application startup

Use this skill when creating an application from scratch or repairing its build
and repository layout. Load [titan-programmer](../titan-programmer/SKILL.md)
before writing or reviewing Titan source, and
[titan-tester](../titan-tester/SKILL.md) for native Titan tests. Add the relevant
API skills as the application needs them; this skill owns project setup, not
language or protocol contracts.

## Choose the application boundary

Use a prepared, ABI-matched Titan SDK and its Lua/native toolchain. Inspect the
available installation and the user's deployment target before choosing build
commands. An application consumes that installation; building a new compiler
prefix or changing Titan itself is separate work. The compiler is a build-time
tool, not an application runtime dependency.

An illustrative layout is:

```text
project/
  .gitignore
  README.md
  main.titan
  app/
    service.titan
  tests/
    service_test.titan
  build/                 # generated sources, objects, runners, and payloads
```

Choose names and a build tool to fit the project. A single-module experiment
can use `titanc` directly; a maintained application needs repeatable build and
test commands, but does not inherently require Make or this exact tree.

The program entry point is exactly `main(args: {string}): integer`, exported
from one selected root. Compile logical module names such as `main` or
`tests.service_test`, without filename extensions. See the base skill's
[compilation examples](../titan-programmer/SKILL.md#compile-with-titanc) and
the [module manual](../../../doc/language/modules.md) for source lookup and
entry-point semantics. Keep the entry point focused on configuration and
resource ownership; reusable application modules can be tested separately.
Programs that transitively import `titan.async` receive the compiler's Runtime
bootstrap by default; importing `titan.uv` alone does not enable it. Consult
[titan-async](../titan-async/SKILL.md) before choosing `--no-uv-bootstrap`,
custom Runtime ownership, or shutdown behavior.

## Establish output ownership before compiling

Always invoke `titanc --incremental --output build` for the application and
its `--test` build. Titan owns the source import graph, dependency-order
scheduling, object certification, and final-link reuse; a build tool that skips
the invocation cannot detect changes through the compiler. Do not maintain
per-module `.o` rules, import/header inventories, or compiler/SDK/configuration
stamps to decide whether Titan needs to run.

Titan creates missing output directories and writes generated C, objects,
headers, and native outputs there, preserving the selected source hierarchy.
`--tree` selects authored sources independently; no source copies are needed.
It takes an ordered, semicolon-separated list of roots, quoted for the shell:
`--tree 'src;tests'` looks up each logical module in `src` first, then in
`tests`, so a runner under `tests/` imports `src` modules by their usual names
(`demo.main`) while keeping its own (`runner`). Omitting `--tree` means `.`;
there is no source-path environment variable.
Keep generated files outside the installed SDK. Target-specific runner and
entrypoint files live under `build/.titan-links/<key>/synthetic/`; native C
helpers live under `build/.native/`. Treat these as compiler-owned inventories,
not paths to reconstruct or glob. Split outputs reserve `<stem>.partN.c` and
`<stem>.partN.o` for `1 <= N < --c-parts`, even when fewer parts are emitted;
do not place authored files or other targets at those paths. On native
Windows, links also stage each launcher and provider DLL in a sibling
`<file>.stage.tmp.<suffix>` directory. A later link removes a leftover one, but
fails with `refusing to retire stale Windows staging` and deletes nothing if it
holds a build input or if Titan cannot identify every native input and tool
(an uncertified compiler or uninterpretable linker flags). Keep authored files
out of those directories, and inspect and delete a reported leftover yourself.

Application and test builds can share this output tree safely on local
filesystems: `titanc` locks it through certification and publication. Unchanged
production objects are shared when native flags, SDK, and resolved provider
bindings match. Use separate output directories for incompatible configurations.
Keep source-path spelling stable too: changing `--tree src` to an absolute
spelling can legitimately miss because source paths appear in generated code
and diagnostics, even when the files are the same.

Reinstalling or republishing a byte-identical Titan compiler and SDK is a hit
for an otherwise cacheable build whose outputs and certificates are still valid,
when the SDK's headers and providers resolve to the same paths and all other
inputs, options, and the native toolchain are unchanged: every object, native
C node, and final link is reused, and `titanc` compiles and links nothing
despite new timestamps and inodes. The digest cache may rehash those files
first. Moving the SDK so its headers or providers resolve to a different
physical path, or retargeting a symlink, can legitimately miss. Opaque native
mechanisms (`@file` arguments, `-fplugin`, `-specs`, `-wrapper`, `-Xclang` or
`-Xlinker`) or an uncertified toolchain make the affected native C nodes or
final link uncacheable, so they run on every build, republished or not.

Titan keeps a disposable digest cache at `build/.titan/digests`. It reuses
hashes only when precise device/inode, size, mode, and nanosecond mtime/ctime
observations match; otherwise it reads and hashes the input again. Missing or
malformed cache data is ignored. The coordinator loads and atomically saves
this hint under the output lock; no persistent digest cache is used without
`--output`. This is separate from object and final-link certificates.

The compiler separates coverage objects from ordinary objects in `.coverage`
subdirectories inside the output tree. Independent coverage executables or
processes need separate output roots when their counter lifetimes overlap:
each execution resets its own counters. See the tester skill's
[native coverage guidance](../titan-tester/SKILL.md#opt-in-native-production-coverage).
Only delete output directories that the build owns; authored sources stay
outside them.

Use `--exe build/app` and `--exe build/app-tests` for exact executable
destinations, relative to the working directory, rather than moving a compiler
output afterward. Windows appends `.exe` when absent and keeps the application
provider DLL under the output tree; preserve the documented payload layout.

Pass native inputs directly: `-I DIR` and `-D NAME=VALUE` for headers/defines,
`-L DIR` and `-l LIB` for linking, and repeatable single-argument
`--cflag=ARG` / `--ldflag=ARG` for other native switches. Translate other
`pkg-config` tokens through those phase-specific switches, not as bare
`titanc` options. Pass app-owned C helpers with `--c-source app/native_helper.c`;
Titan compiles and certifies them and their header inputs. If a Make rule needs
the actual object path for a copy or another tool, capture stdout from
`titanc -c --incremental --output build --c-source app/native_helper.c --print-c-objects`.
The flag requires `-c` and at least one `--c-source`; it prints one absolute
certified object path per C-source argument, in argument order, one per line.
`-c` rejects link-phase options (`-l`, `-L`, `--ldflag`, `-X`, `--exe`, and
`--no-uv-bootstrap`), so give that capture only the compile-phase switches
(`-I`, `-D`, `--cflag`) and add the link switches to the final image commands;
do not reuse one complete native argument list for both. Do not glob
`build/.native/*.o`: that cache can retain nodes from older source locations
and holds one node per C source. Prefer passing `--c-source` directly to the
final Titan build when no external object consumer is needed. Capturing an
object links nothing by itself: every image that needs the helper still gets
it, either through its own `--c-source` or by linking the captured object with
`-X`.

`titanc` parses `CC` as shell words, so a valid value can quote an executable
path that contains spaces, such as `CC='"C:/Program Files/LLVM/bin/clang.exe"'`.
Forward a caller-configurable compiler unchanged with `export CC` rather than
re-quoting it as `CC="$(CC)"` inside a recipe.

Custom generators, third-party native-library builds, environment checks,
packaging, test execution, and coverage output-root policy remain build-tool
work.

A short Linux/macOS Makefile can follow this shape. Here another tool also
reads the C helper's object, so the rule captures it once and both images link
those bytes:

```make
TITANC ?= titanc
TITAN_JOBS ?= 4
BUILD_FLAGS = --incremental --output build --static -j $(TITAN_JOBS)
NATIVE_COMPILE = -I native -D APP_HELPER=1
NATIVE_LINK = -l m
HELPER = build/c-objects/helper.o
DELIVERY_PATH ?= /usr/bin:/bin
SMOKE_ARGS ?= --self-test

.PHONY: all $(HELPER) build/app build/app-tests test package check-delivery
all: build/app

$(HELPER):
	+@object=$$($(TITANC) -c --incremental --output build -j $(TITAN_JOBS) \
	  $(NATIVE_COMPILE) --c-source native/helper.c --print-c-objects) && \
	mkdir -p $(@D) && { cmp -s "$$object" $@ || cp -p "$$object" $@; }

build/app: $(HELPER)
	+$(TITANC) $(BUILD_FLAGS) $(NATIVE_COMPILE) $(NATIVE_LINK) \
	  -X $(HELPER) --exe $@ main

build/app-tests: $(HELPER)
	+$(TITANC) $(BUILD_FLAGS) $(NATIVE_COMPILE) $(NATIVE_LINK) \
	  --test --tree . --test-dir tests -X $(HELPER) --exe $@

test: build/app build/app-tests
	build/app-tests

# Also copy any provider DSO the image selected to dist/bin or dist/lib/titan/0.6.
package: build/app
	rm -rf dist && mkdir -p dist/bin && cp -p build/app dist/bin/

# Run after `make package`; no prerequisites, so it never runs titanc or lua.
check-delivery:
	@test -x dist/bin/app || { echo 'run make package first' >&2; exit 1; }
	@if env -i PATH='$(DELIVERY_PATH)' sh -c 'command -v titanc || command -v lua'; \
	then echo 'DELIVERY_PATH must not reach titanc or lua' >&2; exit 1; fi
	@tmp=$$(mktemp -d) && cp -Rp dist/. "$$tmp" && \
	env -i HOME="$$tmp" PATH='$(DELIVERY_PATH)' "$$tmp/bin/app" $(SMOKE_ARGS); \
	status=$$?; rm -rf "$$tmp"; exit $$status
```

The phony image targets always ask the compiler to certify; unchanged links
are reused. The helper rule is phony too: it always asks `titanc` for the
certified object, captures only stdout, and copies the object only when its
bytes change. `-X` takes several payloads, so give it the object and then
another option (`--exe`) before any module name. The final-link certificate
digests `-X` payloads, so an unchanged helper still hits.
The `+` recipes pass GNU Make's jobserver. GNU Make 4.4 or newer's
FIFO jobserver shares its pool with Titan's frontend/native jobs. Older pipe
jobservers that cannot be shared, including stock macOS Make, use Titan's own
`-j` / `TITAN_JOBS` cap; Linux can also share privately reopened pipe
descriptors. Native Windows uses the local cap and omits `--static`.
Keep `TITANC` a single program name or path: compiled programs and Lua hosts
read an environment variable of the same name for their SDK fallback, start it
without a shell as `$TITANC --print-root`, and GNU Make exports a command-line
`TITANC` into recipes such as `build/app-tests`. Give a compiler command with
arguments or a wrapper another variable name.
Add `-v` to see native command echoes and object/native/link hits and miss
reasons on stderr; worker output and diagnostics also go there, leaving
`--print-c-objects` stdout as paths only. Capture both streams for a build log
(`2>&1`), but leave stderr separate when capturing object paths. Consult
[incremental compilation](../../../doc/language/incremental-compilation.md)
for certification boundaries and
[output directories](../../../doc/language/output-directory.md) for native
switches, executable destinations, and locking.

`check-delivery` must not depend on the phony images, a generator, or
`package`: each would invoke `titanc` or the SDK's `lua`, which the check
keeps out of reach. It runs the packaged copy from a temporary directory under
`env -i`, which clears `TITAN_ROOT`, `TITANC`, `TITAN_PATH_0_6`, `TITAN_PATH`,
`LUA_PATH`, `LUA_CPATH`, and dynamic-loader variables such as
`LD_LIBRARY_PATH`, and it refuses a
`DELIVERY_PATH` that still finds `titanc` or `lua`. `SMOKE_ARGS` selects a
bounded mode of the application, so the check finishes on its own.

## Create the initial `.gitignore`

For the output layout above, start with:

```gitignore
# All configured build modes and their generated outputs.
/build/

# Packaged delivery copy made by `make package`.
/dist/

# Workspace language-server cache.
.titan-ls/

# Local environment files; public templates can be committed.
.env
.env.*
!.env.example
!.env.*.example
```

Adapt these paths to the actual project. Add narrow rules for repository-local
runtime state only when the application creates it: for example, an application
using a root `state.sqlite3` can ignore `/state.sqlite3` and `/state.sqlite3-*`
for its SQLite sidecars. Keep databases, logs, credentials, and live-test
receipts in explicitly owned local paths or outside the repository. An ignored
environment file is only a storage convention; document how the application
actually receives its configuration. Example files contain public placeholders.

Avoid blanket `*.c`, `*.h`, `*.lua`, `*.sqlite3`, `*.json`, or `*.log` rules:
authored FFI helpers, Lua utilities, and test fixtures may use those extensions.
For a legacy build that omits `--output`, enumerate the generated paths beside
the selected module stems, including executable/provider/loader output and
synthetic entry-point/test files. Do not copy Titan's compiler-repository ignore
file into an application; its source trees and dependency builds differ.

Check the initial rules against both generated/private and authored candidates:

```sh
git check-ignore --no-index build/main.c .env.local .env.example \
  main.titan app/native_helper.c scripts/helper.lua tests/fixtures/sample.sqlite3
git status --short --ignored
git ls-files
```

Only the build output and local environment file should be printed by that
`check-ignore` example. An illustrative candidate need not exist for the
command to check its rule. Repeat with the application's actual executable,
Windows payload if relevant, runtime state, and legitimate fixture paths.
Review tracked files as well: `.gitignore` does not remove anything already
tracked, and an already committed secret needs separate remediation rather
than an ignore rule.

## Connect native tests and delivery

Use `--test-dir tests` instead of maintaining a root list when test owners
follow the naming rule: their final logical component is `test`, `tests`,
`spec`, `specs`, or ends in `_test`, `_tests`, `_spec`, or `_specs`. The directory
must lie inside a `--tree` root, and the first listed root containing it
supplies the logical prefix: with `--tree .`, `tests/` retains the `tests.*`
namespace; with `--tree 'src;tests'`, its modules are top-level names such as
`router_test`. Add explicit logical roots for other names.
`--test-exclude tests.platform_test` removes an exact automatic root, not an
explicit root or a module imported by another selected root. `--exe` keeps the
runner destination independent of root order. Read the tester skill's
[project build guidance](../titan-tester/SKILL.md#9-compile-run-and-filter-a-project-suite)
for discovery, synthetic modules, filters, and installed provider selection.
Run a known test and inspect the selected count: a successful empty filtered
run is not test evidence.

The generated runner uses the same compiled `titan.test` provider as ordinary
imports, through public `Case.new` and `run`; it needs no private test source
installation. On Linux/macOS, `--static` prefers Titan archives and can fall
back to DSOs; it does not request a fully static system executable. Validate
the delivery claim with a relocated application in a temporary directory and
an environment without compiler or SDK search paths: unset `TITAN_ROOT`,
`TITANC`, `TITAN_PATH_0_6`, and `TITAN_PATH`, and keep `titanc` and the SDK's
`lua` off `PATH`. Run the check against an already packaged copy, with no
build step in it, as `check-delivery` above does.
A program searches its selected DSOs only in its own directory and in
`../lib/titan/0.6` beside it, then asks the installed SDK (through `TITAN_ROOT`
or `titanc --print-root`) once per Lua state, so a passing run with `titanc`
still reachable can hide a missing provider. Deploy dynamic providers in one of
those two directories. Check its native dependencies; clearing `PATH` alone
does not rule out embedded absolute paths. Use a bounded smoke test that
exercises the application's entry point and representative functionality.

When Windows is part of the requested target, follow the
[Windows build guide](../../../doc/implementation/windows-build.md).
Windows has no Titan `--static` mode: retain the EXE launcher, application and
standard provider DLLs, controlled Lua DLL, native dependency DLLs, and required
licenses in their documented layout. Use a separate native Windows build tree
and validate the delivered payload from an ordinary shell with build-tool/SDK
paths removed. A Unix static build or successful Windows compilation alone
does not prove that payload runs independently of the SDK.

The project README should give the required SDK capabilities, build/test/run
commands, output location, configuration defaults and secrets, runtime state,
and intended deployment layout. Record actual platform checks and limitations.
Keep environment-specific compiler paths and private validation artifacts out
of the committed project. Follow the user's commit, review, and CI instructions
for delivery; application startup does not itself authorize CI dispatch or
changes to the compiler repository.
