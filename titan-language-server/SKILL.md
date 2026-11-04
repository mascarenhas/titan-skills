---
name: titan-language-server
description: Configure, run, and query the standalone Titan language server through omp's lsp tool or over stdio, including multi-root workspaces, per-slice SDK selection with compiler_root and titan-config.local.lua, trustedRoots policy, titan/workspaceStatus, and interpreting diagnostics, hover, definition, references, and raw completion results. Use when querying Titan code intelligence from an agent session; use titan-completion instead when changing compiler completion contexts or language-server completion internals.
---

# Titan language server in omp

Use this skill when configuring or querying `titan-language-server` through omp's
`lsp` tool, including across multiple Titan worktrees and per-slice SDK
installations. Load [`titan-programmer`](../titan-programmer/SKILL.md) before
reading, writing, or reviewing `.titan` source, and
[`titan-tester`](../titan-tester/SKILL.md) for native Titan tests. Load
[`titan-completion`](../titan-completion/SKILL.md) instead when changing
compiler completion contexts, detached descriptors, or language-server
completion internals (and `vscode-titan`'s `.agents/skills/vscode-titan-development/SKILL.md`
when working in `vscode-titan`).

In `vscode-titan`, user settings and multi-root behavior live in `README.md`,
router/worker data flow and SDK compatibility in `docs/server-data-flow.md`,
SQLite cache rules in `docs/sqlite-backend-storage.md`, completion in
`docs/completion.md`, and build rules in `docs/native-build.md`.

## What the server does and does not do

`titan-language-server` is a native Titan executable speaking `Content-Length`-framed
JSON-RPC over stdio (stdout is reserved for LSP frames; logs go to stderr).

- **Implemented operations:**
  - **Saved-file features (`definition`, `references`, `rename`,
    `textDocument/foldingRange`, `diagnostics`):** operate on saved disk files
    under the root's `include` directories (`titan-config.lua`, default
    `{ "./src" }`) resolved through `source_module_roots` (default
    `{ "./src" }`). Save files to disk before querying them.
  - **Work-done progress and pull diagnostics (`$/progress`,
    `textDocument/diagnostic`):** when the client advertises
    `window.workDoneProgress` (as omp does), each worker wraps initial indexing
    and every saved refresh in `window/workDoneProgress/create`
    (`titan-progress/<pid>/<n>`) and `$/progress` `begin` / `report` / `end`,
    sending `end` only after the completed generation and its diagnostics are
    published so omp waits for indexing automatically. `textDocument/diagnostic`
    (`diagnosticProvider`) answers from the same published rows as push, carries
    a `resultId` (`unchanged` when `previousResultId` matches), and waits for a
    refresh whenever the completed generation does not yet cover the file's
    current saved bytes—including a newly created or deleted project source, or a
    repair after a failed pass (a `.titan` file outside `include`, excluded, or
    an inactive target variant answers an empty report without re-indexing).
  - **Buffer-based completion and private hover (`textDocument/completion`,
    `hover`):** completion (triggered by `.` and `:` or raw request) analyzes
    captured open/changed editor buffers against the committed saved-file
    dependency baseline. `hover` reads the saved generation until completion
    activates private per-document analysis on that module; afterward, hover
    follows edits to that module across untouched tokens with a 200 ms debounced
    refresh.
  - **Router inspection (`titan/workspaceStatus`):** returns the live root
    registry and each worker's observed SDK and probe prefix.
- **Unimplemented LSP methods:** the server does **not** implement
  `textDocument/documentSymbol`, `workspace/symbol`, `textDocument/typeDefinition`,
  `textDocument/implementation`, `textDocument/codeAction`, or
  `workspace/willRenameFiles`. In omp, `lsp` actions `symbols`,
  `type_definition`, `implementation`, and `code_actions` fail with
  `MethodNotFound` (`-32601`); never interpret that failure as "no symbols" or
  missing types.
- **Out-of-scope navigation:**
  - **C FFI declarations (`foreign import`, `ffi.*`, `foreign` types):** support
    hover and within-module references, but have **no** definition or rename
    target.
  - **External source and binary modules:** paths in `source_module_roots`
    outside `include` are resolved for typechecking, not watched, indexed, or
    definition targets. Standard-library modules backed by embedded or static
    archive metadata provide hover and completion without source definition
    locations unless their `.titan` sources are in the root's `include` set.
- **Exploratory aid only:** LSP answers never replace running `titanc`, native
  `titan.test` executables, or Busted suites required by your assignment.

## Multi-root router and per-root workers

The server runs as a session router that starts one isolated worker process per
Titan root:

- **Workspace folders and lazy discovery:** initial folders come from
  `initialize.workspaceFolders` (else `rootUri`, `rootPath`, or launch `cwd`),
  canonicalized with `realpath`. When you query a `.titan` file in a sibling git
  checkout or worktree outside omp's launch `cwd`, omp finds its nearest `.git`
  ancestor and sends `workspace/didChangeWorkspaceFolders` before `didOpen` to
  add that checkout as a workspace folder. Each document routes by canonical
  path to the **most specific** known root containing it (and `publishDiagnostics`
  is forwarded only from that owning root). A document outside every known
  folder walks upward for the nearest
  ancestor `titan-config.lua` and registers it as a discovered root; if none
  exists, the file is unowned and requests fail with `RequestFailed` (`-32803`)
  naming the file and `titan-config.lua`.
- **Worker cap, idle eviction, and crash limit:** at `initialized`, initial
  roots activate up to `maxWorkers` (default `4`; set via
  `initializationOptions.maxWorkers` or `TITAN_LS_MAX_WORKERS`); remaining and
  later roots activate on their first routed message. A worker is idle when its
  root has no open documents, no request in flight, and no active indexing pass;
  idle workers stop after `idleTimeoutSeconds` (default `600`, fractional values
  accepted) or are evicted least-recently-used first when a new root needs a
  slot. If all `maxWorkers` slots are busy, activating another root fails with
  `RequestFailed` naming the cap. Open document buffers are replayed when a
  worker respawns after eviction, reload, or crash. Three crashes within 60
  seconds mark the root `failed` until its settings change or `lsp(action="reload")`.

## Obtaining a server binary and serving multiple SDKs

Build the server from a `vscode-titan` checkout (or disposable copy) against an
installed, read-only Titan SDK (requires GNU Make 4.2+, a C toolchain, the SDK,
and OpenSSL 3 + `pkg-config` for system-OpenSSL SDKs; does not need `npm ci`):

```sh
make -C /path/to/vscode-titan -j2 server TITAN_PREFIX=/path/to/titan-sdk
```

This produces `bin/titan-language-server` (or use `make install-server INSTALL_PREFIX=...`).
Never modify or rebuild a shared or maintainer SDK prefix.

**One executable serves every SDK:** you do not need to build a separate
`titan-language-server` per slice. A root without `compiler_root` uses the
router's `TITAN_ROOT` and `TITAN_LS_LUA_*`. A root that sets `compiler_root`
loads that prefix's compiler Lua modules, native Lua modules, SDK headers, and
static standard-library archive in its own worker process. The only component
fixed by the server binary is the linked `titan` C support table: if a slice SDK's
compiler calls a new C support function that the running server binary lacks,
that root fails with a clear error, fixed by building `titan-language-server`
against a matching SDK (see `vscode-titan` `README.md` and
`docs/server-data-flow.md#compiler-compatibility`).

## Configuring omp (`lsp.json`)

Omp loads LSP config per launch `cwd` (merging `~/.omp/agent/lsp.json` with
`<cwd>/.omp/lsp.json` and `<cwd>/lsp.json`). Do not edit user or project
`lsp.json` without authorization. Because omp's `ServerConfig` has **no `env`
field**, pass environment variables via `/usr/bin/env` and clear contaminating
ambient variables:

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
      "rootMarkers": ["titan-config.lua", "titan-config.local.lua", ".git"],
      "initOptions": {
        "trustedRoots": ["/tmp/titan-session", "/home/user/Code"],
        "insertCallSnippets": false
      },
      "warmupTimeoutMs": 30000
    }
  }
}
```

- **`TITAN_ROOT` vs `TITAN_PREFIX`:** `TITAN_ROOT` selects the default SDK.
  `TITAN_PREFIX` in the server environment only moves the C probe cache
  (default `<root>/.titan-ls`, or `<TITAN_PREFIX>/roots/<digest>` when inherited);
  unset `TITAN_PREFIX` so each root uses `<root>/.titan-ls`.
- **Lua paths:** `TITAN_LS_LUA_PATH` and `TITAN_LS_LUA_CPATH` are used verbatim
  by default roots; never use `;;` or ambient `LUA_PATH`/`LUA_CPATH`.
- **`rootMarkers`:** checked in omp's launch `cwd` only. Adding `"."` makes the
  entry eligible in every `cwd` where the config loads, so a user-level entry
  would start the server in any project with `.titan` files; prefer project
  scope or omit `"."` when that is unwanted.
- **`initOptions`:** `trustedRoots` (array of absolute paths; also configurable
  via `TITAN_LS_TRUSTED_ROOTS` using the OS path-list separator), `insertCallSnippets`, `maxWorkers`, and
  `idleTimeoutSeconds`. Leave `pullDiagnostics` unset/enabled in omp
  (`pullDiagnostics: false` omits `diagnosticProvider` and is used by the VS
  Code extension to avoid duplicate push/pull collections). Project overrides
  replace `initOptions` as a whole, so repeat the full object in any override.
  Run `lsp(action="reload", file="*")` after editing `lsp.json`.

## Per-slice SDK selection, trust, and reload

For a slice worktree `/tmp/titan-NNN/<slice>/source` with installed prefix
`/tmp/titan-NNN/<slice>/prefix`:

1. **Keep tracked `titan-config.lua` untouched.** Write an untracked
   `titan-config.local.lua` in the slice root assigning **only** `compiler_root`:
   ```lua
   compiler_root = "/tmp/titan-NNN/slice-a/prefix"
   ```
   Relative paths resolve from the root. `titan-config.local.lua` may assign
   only `compiler_root` (any other key, non-string/empty value, or syntax error
   fails the root). Remove `titan-config.local.lua` before committing if
   `.gitignore` does not ignore it.
2. **Trust and no-fallback rule:** a root is trusted only when its canonical
   path is equal to or inside `initOptions.trustedRoots` or
   `TITAN_LS_TRUSTED_ROOTS`. An untrusted root that sets `compiler_root` publishes
   a `configuration` diagnostic on the config file, starts no worker, and fails
   requests with `RequestFailed` (`-32803`) naming `trustedRoots` /
   `TITAN_LS_TRUSTED_ROOTS`. Likewise, a missing prefix, incomplete SDK layout,
   unreadable override, or ABI/API mismatch fails that root and **never** falls
   back to the default SDK.
3. **Reinstalling a slice prefix:** workers load compiler Lua and stdlib
   interfaces from the installed prefix, not from uncommitted source edits. After
   reinstalling into `<slice>/prefix` or editing `titan-config.local.lua`, the
   router detects the changed settings or SDK identity (within ~1 s or on the
   next routed request) and restarts only that root's worker. Run
   `lsp(action="reload", file="*")` to force immediate revalidation across all
   roots.

## Inspecting state and querying from omp

- **Position rules:** standard omp actions (`diagnostics`, `hover`,
  `definition`, `references`, `rename`) take 1-based `line` and `symbol`
  (`symbol="name#2"` selects the 2nd occurrence on `line`). On project-aware
  servers, `definition`, `references`, and `rename` **require** `symbol` when
  `line` is given. Raw `lsp(action="request", ...)` payloads take **zero-based
  `line` and UTF-16 `character`** computed from the current saved text (never
  reused from an earlier file revision).
- **`titan/workspaceStatus`:** returns `{ "roots": [ ... ] }` where each root
  reports `root`, `origin` (`"folder"` | `"discovered"`), `trusted`,
  `compilerRoot` (string | `null`), `state` (`"inactive"` | `"starting"` |
  `"ready"` | `"failed"` | `"evicted"`), optional `failure`, `workerPid`
  (integer | `null`), `generation`, and the worker's self-reported `titanRoot`
  and `probePrefix` (string | `null`). Pass a concrete `.titan` `file` when
  calling `titan/workspaceStatus` through omp (so omp reconciles and registers
  that file's checkout before querying); a file-less call also works for
  already-registered roots.

```text
# Inspect live roots, trust, compilerRoot, titanRoot, probePrefix, workerPid, and failure messages
lsp(action="request", query="titan/workspaceStatus",
    file="/tmp/titan-NNN/slice-a/source/titan/string.titan")
# Saved-file diagnostics (always pass a concrete .titan file or .titan glob;
# file="*" runs omp's Rust/TS/Go/Python CLI checkers, not Titan)
lsp(action="diagnostics", file="/tmp/titan-NNN/slice-a/source/titan/string.titan", timeout=60)

# Hover, definition, references, and folding ranges
lsp(action="hover", file="/tmp/titan-NNN/slice-a/source/titan/string.titan", line=42, symbol="split")
lsp(action="definition", file="/tmp/titan-NNN/slice-a/source/titan/string.titan", line=42, symbol="split")
lsp(action="references", file="/tmp/titan-NNN/slice-a/source/titan/string.titan", line=42, symbol="split#1")
lsp(action="request", file="/tmp/titan-NNN/slice-a/source/titan/string.titan", query="textDocument/foldingRange")

# Raw completion (zero-based line and UTF-16 character in payload)
lsp(action="request", file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    query="textDocument/completion",
    payload='{"textDocument":{"uri":"file:///tmp/titan-NNN/slice-a/source/titan/string.titan"},"position":{"line":41,"character":14}}')

# Rename preview (ALWAYS pass apply=false unless authorized to mutate files)
lsp(action="rename", file="/tmp/titan-NNN/slice-a/source/titan/string.titan",
    line=42, symbol="split", new_name="split_bytes", apply=false)
```

## Interpreting results and `.titan-ls` hygiene

- **Modules that fail checking publish no semantic facts (`hover`, `definition`,
  `references`):** when a module fails checking (for example because of a syntax
  or type error inside that file, or missing `extra_ffi_include_dirs` /
  `extra_ffi_cppflags` in `titan-config.lua`), `diagnostics` reports the
  compiler error, while `hover`, `definition`, and `references` for symbols in
  that failed module (and its dependents) return nothing (`No hover information`
  / `No definition found`) for that generation; independently valid modules in
  the same project still answer both.
- **Empty, incomplete, or timed-out results are inconclusive:** omp waits for
  `$/progress` and pulls `textDocument/diagnostic` for current saved bytes, but
  a `diagnostics` timeout (when indexing exceeds omp's call `timeout`) is **not**
  a clean `OK` result. Read-only requests (`hover`, `foldingRange`, `completion`)
  issued before initial indexing finishes can still return empty results or
  `isIncomplete: true`, and read the preceding completed generation while a
  background refresh runs.
- **Per-root `.titan-ls` caches:** each worker writes `<root>/.titan-ls/index.sqlite3`
  and (by default) `<root>/.titan-ls/var/cache/titan-probes/2`. Remove your own
  worktree's `.titan-ls/` and `titan-config.local.lua` before committing if a
  clean worktree is required. **Never delete another agent's `.titan-ls/`
  cache** or touch a sibling's worktree.
- **Never mutate files without authority:** `rename` and `rename_file` default
  to `apply=true` in omp; always pass `apply=false` for read-only work.
