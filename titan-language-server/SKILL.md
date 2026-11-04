---
name: titan-language-server
description: Configure, run, and query the standalone Titan language server through omp's lsp tool or over stdio, including multi-root workspaces, per-slice SDK selection with compiler_root and titan-config.local.lua, trustedRoots policy, titan/workspaceStatus, and interpreting diagnostics, hover, definition, references, and raw completion results. Use when querying Titan code intelligence from an agent session; use titan-completion instead when changing compiler completion contexts or language-server completion internals.
---

# Titan language server in omp

Use this skill when configuring or querying the standalone Titan language server
(`titan-language-server`) from omp's `lsp` tool, particularly across multiple
Titan worktrees and per-slice SDK installations. Load
[`titan-programmer`](../titan-programmer/SKILL.md) before reading, writing, or
reviewing any `.titan` source, and [`titan-tester`](../titan-tester/SKILL.md)
for native Titan tests. If you are changing compiler completion contexts,
detached descriptors, or the server's completion implementation itself, load
[`titan-completion`](../titan-completion/SKILL.md) (and `vscode-titan`'s
repository-local `.agents/skills/vscode-titan-development/SKILL.md` when editing
the `vscode-titan` repository).

In `vscode-titan`, user settings and standalone setup live in `README.md`,
configuration inputs and router/worker data flow in `docs/server-data-flow.md`,
SQLite cache and header provenance in `docs/sqlite-backend-storage.md`, unsaved
completion and private hover in `docs/completion.md`, and native build rules in
`docs/native-build.md`.

## What the server does and does not do

The Titan language server is a native Titan executable that communicates over
stdio using `Content-Length`-framed JSON-RPC. Stdout is reserved exclusively for
LSP frames; structured logs and diagnostics go to stderr.

- **Saved-file features:** `definition`, `references`, `rename`, `foldingRange`,
  and published `diagnostics` operate on saved disk files discovered under the
  project's `include` roots (configured in `titan-config.lua`, default
  `{ "./src" }`) and resolved through `source_module_roots` (default
  `{ "./src" }`). Save edited `.titan` files to disk before querying these
  operations.
- **Buffer-based completion and private hover:** `textDocument/completion`
  (triggered by `.` and `:` or explicit request) analyzes captured open/changed
  document buffers (`didOpen`/`didChange` using full document sync, `change = 1`)
  against the committed saved-file dependency baseline. `textDocument/hover`
  reads the saved generation until a completion request activates private
  per-document analysis for that module; once active, hover follows edits to
  that module across untouched tokens and queues a 200 ms debounced refresh.
- **Out-of-scope navigation:**
  - **C FFI declarations:** `foreign import "header.h"` contributions to `ffi`
    and unqualified `foreign` types support hover and within-module references,
    but have **no** definition or rename target.
  - **External source and binary modules:** paths listed in
    `source_module_roots` outside `include` are external sources—the compiler
    resolves them for typechecking, but they are not watched, indexed, or
    definition-navigation targets. Standard-library modules backed by embedded
    or static archive metadata provide hover and completion without source
    definition locations unless their `.titan` sources are part of the root's
    own `include` set (as in a Titan compiler/stdlib checkout).
- **LSP is an exploratory aid, not verification proof:** language-server answers
  never replace running `titanc`, native `titan.test` executables, or Busted
  suites required by your assignment.

## Router and per-root worker architecture

One `titan-language-server` executable runs in two modes:

1. **Router (default mode):** launched by every client (`omp`, VS Code, Codex).
   It speaks LSP on stdio, manages the workspace root registry, tracks open
   document overlays, evaluates root trust and SDK settings, routes requests and
   notifications by document URI without re-encoding message payloads, and
   supervises per-root worker processes. The router never loads the Titan
   compiler into its own process.
2. **Worker (`titan-language-server --worker --root <canonical-root>`):** an
   internal single-root server spawned by the router with its working directory
   set to `<canonical-root>`. Because the compiler Lua modules, native Lua C
   modules, driver state, SQLite database, and C probe cache are process-wide,
   each root gets its own isolated worker process.

Key lifecycle rules:

- **Activation and worker cap:** roots supplied during `initialize` activate at
  `initialized`, up to `maxWorkers` (default `4`; configurable via
  `initializationOptions.maxWorkers` or `TITAN_LS_MAX_WORKERS`). Folders added
  later and lazily discovered roots activate on their first routed message.
- **Idle eviction:** a worker is idle when it has no open documents and no
  pending requests. Idle workers exit after `idleTimeoutSeconds` (default `600`)
  and are evicted least-recently-used first when activating a new root would
  exceed `maxWorkers`. Workers with open documents or pending requests are never
  evicted; if all `maxWorkers` slots are busy, requests to an additional root
  fail with `RequestFailed` (`-32803`) naming the worker cap.
- **Overlay replay and crash recovery:** the router retains the latest full text
  and version of every open document and replays `didOpen` whenever a worker
  respawns after idle eviction, settings/SDK reload, or an unexpected exit. An
  unexpected worker exit fails its in-flight requests with `RequestFailed` and
  respawns on the next routed message; three crashes within 60 seconds mark the
  root `failed` until its settings change or an explicit reload occurs.

## Obtaining a server binary and SDK compatibility

Build the standalone server from a `vscode-titan` checkout (or a disposable
copy) against an installed, read-only Titan SDK:

```sh
make -C /path/to/vscode-titan -j2 server TITAN_PREFIX=/path/to/titan-sdk
```

This produces `/path/to/vscode-titan/bin/titan-language-server` (add
`BUILD_PROFILE=validation` for an unoptimized validation build, or use
`make install-server INSTALL_PREFIX=/path/to/install` to install the binary and
license notices). Building `server` requires GNU Make 4.2 or newer, a C
toolchain, the installed Titan SDK, and (for a system-OpenSSL SDK) OpenSSL 3
development files with `pkg-config`; it does not require `npm ci` or building
the VS Code extension bundle. Never modify or rebuild a shared or maintainer SDK
prefix unless your task explicitly owns that prefix.

### One executable serves every SDK via `compiler_root`

You do **not** need to compile a separate `titan-language-server` binary for
each slice worktree:

- **Default roots (no `compiler_root`):** the worker inherits the router's
  `TITAN_ROOT`, `TITAN_LS_LUA_PATH`, and `TITAN_LS_LUA_CPATH` and uses the
  build-time embedded standard-library interface provider.
- **Roots with `compiler_root`:** the router validates that the prefix contains
  `share/lua/5.5/titan-compiler/driver.lua`, `lib/lua/5.5`, and
  `lib/titan/0.6/titan.a`, then spawns its own executable (`os.exepath()`) with
  `--compiler-root <prefix>`. Before loading any compiler module, that worker:
  1. sets `TITAN_ROOT` to `<prefix>` and configures `package.path` /
     `package.cpath` from `<prefix>/share/lua/5.5` and `<prefix>/lib/lua/5.5`
     (ignoring `TITAN_LS_LUA_*`);
  2. neutralizes inherited `TITAN_PATH_0_6`, `TITAN_PATH`, and
     `TITAN_SOURCE_PATH` so another SDK's providers cannot leak in;
  3. verifies `TITAN_ABI_VERSION == "2"`, `LANGUAGE_SERVER_API_VERSION == 1`,
     and every required driver entry point;
  4. skips the build-time embedded interface provider (which describes the
     server's build SDK) and sets the driver's `prefer_static = true` so
     standard-library interfaces come from parsing `<prefix>/lib/titan/0.6/titan.a`
     without `dlopen`ing foreign `.so` providers into the server process.

**Support-table boundary:** the only C surface that compiler Lua modules call in
the host executable is the `titan` support table (`luaopen_titan`). If a slice
SDK changes that C support surface and calls a function that the running
`titan-language-server` binary lacks, that root fails with a root-scoped error.
Only in that case must you build `titan-language-server` against the newer SDK.

## Configuring omp (`lsp.json`)

Omp loads LSP configuration per launch `cwd` (merging user config such as
`~/.omp/agent/lsp.json` with project overrides at `<cwd>/.omp/lsp.json` and
`<cwd>/lsp.json`). Do not create or modify user or project `lsp.json` files
unless authorized by the maintainer or task instructions.

Omp's `ServerConfig` schema has **no `env` field**. Supply environment variables
through `/usr/bin/env` in `command` and `args`, and clear ambient variables that
could contaminate SDK or probe-cache selection:

```json
{
  "servers": {
    "titan": {
      "command": "/usr/bin/env",
      "args": [
        "-u", "TITAN_PREFIX",
        "-u", "TITAN_PATH_0_6",
        "-u", "TITAN_PATH",
        "-u", "TITAN_SOURCE_PATH",
        "-u", "LUA_PATH",
        "-u", "LUA_CPATH",
        "-u", "LUA_PATH_5_5",
        "-u", "LUA_CPATH_5_5",
        "TITAN_ROOT=/path/to/default-sdk",
        "TITAN_LS_LUA_PATH=/path/to/default-sdk/share/lua/5.5/?.lua;/path/to/default-sdk/share/lua/5.5/?/init.lua",
        "TITAN_LS_LUA_CPATH=/path/to/default-sdk/lib/lua/5.5/?.so",
        "/path/to/bin/titan-language-server"
      ],
      "fileTypes": [".titan"],
      "languageId": "titan",
      "rootMarkers": ["titan-config.lua", "titan-config.local.lua", ".git", "."],
      "initOptions": {
        "trustedRoots": [
          "/tmp/titan-session",
          "/home/user/Code"
        ],
        "insertCallSnippets": false
      },
      "warmupTimeoutMs": 30000
    }
  }
}
```

Configuration rules to keep straight:

- **`TITAN_ROOT` vs `TITAN_PREFIX`:** in the language server, `TITAN_ROOT`
  selects the default SDK installation root (headers, Lua sources, default
  providers). `TITAN_PREFIX` is **not** the server's SDK selector—when set in
  the server's environment, `TITAN_PREFIX` only redirects the C probe cache
  (which otherwise defaults to `<root>/.titan-ls`, or
  `<TITAN_PREFIX>/roots/<sha256-prefix>` when the router inherits a nonempty
  `TITAN_PREFIX`). Unset `TITAN_PREFIX` in the server launch args so each root
  keeps its probe cache under `<root>/.titan-ls`.
- **Complete Lua templates:** `TITAN_LS_LUA_PATH` and `TITAN_LS_LUA_CPATH` are
  used verbatim by default roots. Never use `;;` or rely on ambient `LUA_PATH` /
  `LUA_CPATH`. On macOS, native Lua modules in `lib/lua/5.5` still use `.so`; on
  Windows they use `.dll`.
- **`rootMarkers`:** omp checks `rootMarkers` in the launch `cwd` only and does
  not walk parent directories at startup. Including `"."` allows the server to
  start even when omp was launched in a parent workspace directory above the
  Titan checkouts.
- **`initOptions` (`initializationOptions`):**
  - `trustedRoots`: array of absolute directory paths whose contained roots are
    allowed to use `compiler_root` (can also be supplied via
    `TITAN_LS_TRUSTED_ROOTS` using the OS path-list separator).
  - `insertCallSnippets`: set `false` if you want completion items to carry
    plain callable names instead of parameter-placeholder snippets.
  - `maxWorkers` (default `4`) and `idleTimeoutSeconds` (default `600`).
  - When a project `.omp/lsp.json` overrides a user `~/.omp/agent/lsp.json`, omp
    replaces top-level object fields such as `initOptions` as a whole rather
    than deep-merging them; repeat the complete `initOptions` object in any
    override.
- **Reloading config:** omp caches `lsp.json` per process and `cwd`. After
  editing `lsp.json`, run `lsp(action="reload", file="*")` (or omit `file`) so
  omp invalidates its config cache and restarts clients whose configuration
  changed.

## Per-slice SDK selection (`compiler_root`, `titan-config.local.lua`, and trust)

In multi-agent workflows where each slice has a source worktree
(such as `/tmp/titan-NNN/<slice>/source`) and its own installed SDK prefix
(`/tmp/titan-NNN/<slice>/prefix`):

1. **Never edit the tracked `titan-config.lua` to set `compiler_root`.** The
   tracked `titan-config.lua` owns repository-wide settings (`include`,
   `exclude`, `source_module_roots`, `binary_modules_root`,
   `extra_ffi_include_dirs`, `extra_ffi_cppflags`) and must remain clean for
   commits and diffs.
2. **Create an untracked `titan-config.local.lua` in the slice root** that
   assigns **only** `compiler_root`:
   ```lua
   compiler_root = "/tmp/titan-NNN/slice-a/prefix"
   ```
   - `titan-config.local.lua` is loaded after `titan-config.lua` in an empty
     Lua environment.
   - It may assign **only** `compiler_root` (an absolute path, or a path
     resolved relative to that root). Assigning any other key (`include`,
     `source_module_roots`, `extra_ffi_cppflags`, etc.) or returning a value is
     rejected as a configuration error.
   - Remove `titan-config.local.lua` before finishing if the repository's
     `.gitignore` does not ignore it; never stage or commit it.
3. **Ensure the slice root is trusted:**
   - A root is trusted only when its canonical path (`realpath`) is equal to or
     inside a canonical entry of `initializationOptions.trustedRoots` or
     `TITAN_LS_TRUSTED_ROOTS`.
   - If an **untrusted** root sets `compiler_root` (in either
     `titan-config.lua` or `titan-config.local.lua`), the router refuses to
     spawn a worker for that root, publishes a diagnostic on the config file
     that set `compiler_root`, and fails every request for that root with
     `RequestFailed` (`-32803`) naming the root, `compiler_root`, and the trust
     option.
   - **No silent fallback:** neither an untrusted `compiler_root`, a missing
     prefix, an incomplete prefix layout, nor an ABI/API mismatch ever falls
     back to the router's default SDK. Fix the trust list or the slice prefix
     rather than assuming queries used the default compiler.

## Multi-root routing, folder addition, and lazy discovery

A single router session can serve multiple independent Titan checkouts and
application roots simultaneously:

- **Workspace folders:** initial folders come from `initialize.workspaceFolders`
  (or `rootUri` / `rootPath` / launch `cwd`), canonicalized with `realpath` and
  refcounted. When you query a `.titan` file in a sibling git checkout or
  worktree outside omp's launch `cwd`, omp automatically sends
  `workspace/didChangeWorkspaceFolders` before `didOpen` to register that
  checkout with the router.
- **Most-specific root wins:** the router canonicalizes each document path
  (using the deepest existing ancestor's `realpath` when a file does not exist
  yet) and routes the request to the **most specific** known root that contains
  it. For nested roots, even if an outer root's `include` globs cover an inner
  root's files, requests for inner files go to the inner worker, and the router
  forwards `publishDiagnostics` for a URI **only** from that URI's owning
  worker.
- **Lazy ancestor discovery:** if a document lies outside every registered
  workspace folder, the router walks upward from the document's directory to the
  filesystem root looking for `titan-config.lua`. The nearest ancestor containing
  `titan-config.lua` becomes a discovered root. (`titan-config.local.lua` alone
  does not mark a root for discovery; a root without a tracked
  `titan-config.lua` must either have one or be registered as a workspace
  folder.)
- **Unowned files:** if a document is outside every known workspace folder and
  has no `titan-config.lua` ancestor, notifications for it are dropped and
  requests fail with `RequestFailed` (`-32803`) naming the file and stating that
  it is outside every Titan root and has no `titan-config.lua` ancestor.

## Reinstalling a slice prefix and reloading

Workers load compiler Lua modules (`titan-compiler.*`, `c-parser.*`) and
standard-library interfaces from the selected SDK prefix (`compiler_root` or
`TITAN_ROOT`), **not** from uncommitted compiler Lua or `.titan` edits sitting
in the source checkout:

1. After editing compiler Lua or standard-library sources in a slice worktree,
   reinstall them into that slice's SDK prefix first.
2. The router tracks each active root's settings fingerprint (`compiler_root`
   and trust status) and SDK identity (device, inode, size, and mtime of
   `share/lua/5.5/titan-compiler/driver.lua`, `lib/titan/0.6/titan.a`, and
   `lib/titan/0.6/sdk-digests`). It re-checks an active root at most once per
   second when routing to it, on a periodic timer, and immediately for every
   root when it receives `workspace/didChangeConfiguration`.
3. When the router detects a changed `compiler_root`, trust state, or reinstalled
   SDK identity, it gracefully drains pending requests on that root's worker,
   shuts it down, spawns a fresh worker against the updated prefix, and replays
   open-document overlays. Other roots keep running untouched. (Edits to tracked
   `titan-config.lua` keys other than `compiler_root` are picked up by the
   worker's own file watcher without restarting the worker process.)
4. To trigger immediate revalidation of all roots without waiting for the
   periodic check, run:
   ```text
   lsp(action="reload", file="*")
   ```

## Inspecting router state with `titan/workspaceStatus`

Before debugging unexpected diagnostics, empty navigation, or SDK mismatches,
inspect the router's live root table with a raw `titan/workspaceStatus` request:

```text
lsp(action="request", query="titan/workspaceStatus")
```

The response lists every known root with:

- its canonical `root` path and `origin` (`"folder"` or `"discovered"`);
- `trusted` (`true` or `false`);
- effective `compiler_root` (or absence when using the router's default SDK);
- `state` (`"inactive"`, `"starting"`, `"ready"`, `"failed"`, or `"evicted"`);
- `error` / failure message when `state == "failed"`;
- current worker `pid` and restart generation counter.

Check `titan/workspaceStatus` right after adding a slice or changing
`titan-config.local.lua` to confirm that `trusted` is `true`, `compiler_root`
points to your slice's prefix, and `state` is `"ready"` (or `"inactive"` before
its first routed file request), not `"failed"`.

## Querying the server from omp

### Position conventions

- **Standard omp actions (`diagnostics`, `hover`, `definition`, `references`,
  `symbols`, `rename`):** pass 1-based `line` and the `symbol` name on that
  line. Use `symbol="name#2"` to select the second occurrence of `name` on
  `line` (1-based occurrence index). On project-aware servers, `definition`,
  `references`, and `rename` **require** `symbol` whenever `line` is given;
  omitting `symbol` fails immediately with a `ToolError`.
- **Raw `lsp(action="request", ...)` calls:** when you supply a JSON `payload`,
  LSP positions use **zero-based `line` and zero-based UTF-16 `character`**
  offsets. Always compute UTF-16 positions from the current saved text of the
  file immediately before the query; never reuse coordinates computed for an
  earlier revision of the file. (If you omit `payload` on `action="request"` and
  supply a concrete `file`, 1-based `line`, and `symbol`, omp resolves the
  column and builds `{"textDocument":{"uri":"..."},"position":{"line":...,"character":...}}`
  automatically.)

### Common query calls

```text
# 1. Check that omp sees the configured Titan server
lsp(action="status")
lsp(action="capabilities", file="/tmp/titan-NNN/slice-a/source/titan/string.titan")

# 2. Inspect router roots, trust, compiler_root, and worker health
lsp(action="request", query="titan/workspaceStatus")

# 3. Query saved-file diagnostics (use a concrete .titan file or .titan glob,
#    never file="*", which runs omp's built-in Rust/TS/Go/Python CLI checkers)
lsp(action="diagnostics",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    timeout=60)

# 4. Hover, definition, and references on a saved file
lsp(action="hover",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    line=42, symbol="split")
lsp(action="definition",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    line=42, symbol="split")
lsp(action="references",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    line=42, symbol="split#1")

# 5. Folding ranges via raw request (omp builds {"textDocument":{"uri":...}})
lsp(action="request",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    query="textDocument/foldingRange")

# 6. Completion via raw request (omp has no named completion action;
#    supply zero-based line and UTF-16 character in payload)
lsp(action="request",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    query="textDocument/completion",
    payload='{"textDocument":{"uri":"file:///tmp/titan-NNN/slice-a/source/titan/string.titan"},"position":{"line":41,"character":14}}')

# 7. Rename preview (ALWAYS pass apply=false unless authorized to edit files;
#    omp's rename action defaults to apply=true)
lsp(action="rename",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    line=42, symbol="split", new_name="split_bytes", apply=false)
```

## Interpreting results, caches, and failure modes

1. **Empty or incomplete results are inconclusive:**
   - Before a worker finishes its initial saved-file index publication, read-only
     queries (`hover`, `definition`, `references`, `foldingRange`, `completion`)
     can return empty results (`No definition found`, `No hover information`, or
     `isIncomplete: true`). While a background refresh runs after a disk edit,
     read-only queries read the preceding completed generation.
   - A `diagnostics` timeout (for example when initial indexing of a full
     checkout exceeds the call timeout or when no new diagnostic publication
     arrives during omp's wait window) is **not** a clean `OK` result and does
     not prove the file is error-free.
   - Never treat `No definition found` or `No references found` alone as proof
     that a declaration is dead code or missing; verify with `grep` and the
     compiler (`titanc`).
2. **Check config and C headers when stdlib or FFI modules fail to index:**
   - If a module fails checking (for instance because `titan-config.lua` is
     missing required `extra_ffi_include_dirs` or `extra_ffi_cppflags` for a C
     header), that module and its dependency closure publish no reusable
     semantic interfaces for that generation, even though independent valid
     modules still publish theirs.
3. **Per-root `.titan-ls` caches and worktree hygiene:**
   - Each worker persists its SQLite index at `<root>/.titan-ls/index.sqlite3`
     and (by default) its C compiler probe cache under
     `<root>/.titan-ls/var/cache/titan-probes/2`, with a `<root>/.titan-ls/.gitignore`
     containing `*`.
   - Querying a worktree creates `<root>/.titan-ls/`. If a repository does not
     ignore `.titan-ls/` at the top level or your task requires a clean
     `git status`, remove your own worktree's `.titan-ls/` and
     `titan-config.local.lua` before committing.
   - **Never delete another agent's `.titan-ls/` directory** or touch a sibling's
     worktree to force a cache rebuild. In your own worktree, if a changed C
     toolchain or environment makes raw-C probe cache entries stale, stop or
     reload the worker after removing your own `.titan-ls/`.
4. **Never mutate files through `lsp` without authority:**
   - In omp, `lsp(action="rename", ...)` and `lsp(action="rename_file", ...)`
     apply edits to disk by default (`apply !== false`). In read-only reviews or
     when previewing a refactor, always pass `apply=false`.
