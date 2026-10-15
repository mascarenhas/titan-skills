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

Pass an application-owned output directory to every compiler invocation, such
as `titanc --output build main`. Titan creates missing directories and writes
generated C, objects, headers, runners, and final native outputs there,
preserving the source hierarchy relative to the selected source root. `--tree`
selects the original authored source tree independently of `--output`; output
isolation needs no source copies. Keep generated files outside the installed
SDK.

Use the same output directory for incremental object compilation and final
linking. Application and test builds can share unchanged production objects
when native flags, SDK, and resolved provider bindings match. Test mode alone
does not require separate production objects. Use separate output directories
for incompatible native flags or SDKs/toolchains.

The compiler separates coverage objects from ordinary objects in `.coverage`
subdirectories inside the output tree. Independent coverage executables or
processes need separate output roots when their counter lifetimes overlap:
each execution resets its own counters. See the tester skill's
[native coverage guidance](../titan-tester/SKILL.md#opt-in-native-production-coverage).
Only delete output directories that the build owns; authored sources stay
outside them.

Pair `--incremental` with build-system dependency tracking for imports, foreign
headers, folder-module inventories, compiler/SDK/provider changes, native
payloads, and flags. The compiler's object cache covers only its documented
local conditions. Compile affected owning modules before linking their
consumers, and clean an owned output tree when a configuration change is not
covered by the invalidation graph. See
[incremental compilation](../../../doc/language/incremental-compilation.md)
for the existing compile/link contract and Make pattern.

## Create the initial `.gitignore`

For the output layout above, start with:

```gitignore
# All configured build modes and their generated outputs.
/build/

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

Add native `titan.test` roots and a repeatable `titanc --output build --test`
command using the project's selected source tree. The first requested root
determines the runner's logical output path on POSIX; copy or name the
deliverable explicitly instead of guessing it from the common namespace. Read the tester skill's
[project build guidance](../titan-tester/SKILL.md#9-compile-run-and-filter-a-project-suite)
for synthetic modules, filters, and installed provider selection. Run a known
test and inspect the selected count: a successful empty filtered run is not
test evidence.

The generated runner uses the same compiled `titan.test` provider as ordinary
imports, through public `Case.new` and `run`; it needs no private test source
installation. On Linux/macOS, `--static` prefers Titan archives and can fall
back to DSOs; it does not request a fully static system executable. Validate
the delivery claim with a relocated application in a temporary directory and
an environment without compiler or SDK search paths. Check its native dependencies and whether
it can still locate Titan providers at their original paths; clearing `PATH`
alone does not rule out embedded absolute paths. Use a bounded smoke test that
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
