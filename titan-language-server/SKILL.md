---
name: titan-language-server
description: Use to configure, run, or query Titan LSP (diagnostics, completion, hover, definition, refs, rename). Covers titan-language-server via omp lsp/stdio, textDocument/completion, multi-root workspaces, compiler_root/titan-config.local.lua, trustedRoots, target="browser", workspaceStatus; never load titan-completion when querying LSP (only for editing compiler completion.lua).
---

# Titan Language Server (`omp lsp` & Workspaces)

Configure, run, and query `titan-language-server` (`Content-Length`-framed JSON-RPC over stdio; logs on stderr; **`shutdown` takes no `params` field**—`-32602` if `params` is sent) via omp's `lsp` tool or stdio. **All LSP queries including `textDocument/completion` stay in this skill** (do NOT load `skill://titan-completion` unless editing compiler Lua `completion.lua`; inside `vscode-titan`, see `docs/{server-data-flow,sqlite-backend-storage,completion,native-build}.md`). Pair with `skill://titan-programmer` for `.titan` edits and `skill://titan-tester` for native tests.

## Non-negotiable invariants

1. **Saved-file baseline & unsupported methods:** `diagnostics`, `definition`, `references`, `rename`, and `textDocument/foldingRange` read **saved disk files** under `include` (`titan-config.lua`, default `{"./src"}`) via `source_module_roots` (default `{"./src"}`)—save before querying. `symbols`, `type_definition`, `implementation`, and `code_actions` are **unimplemented** (`MethodNotFound` `-32601`; never read as empty).
2. **Exploratory aid & read-only `apply=false`:** LSP never replaces `titanc`, `titan.test`, or Busted. `rename`/`rename_file` default to `apply=true` in omp—**always pass `apply=false`** unless authorized to edit. Timeouts, early empty reads, or `isIncomplete: true` are inconclusive, never `OK`.
3. **Failed modules & out-of-scope targets:** Modules failing checking (or missing `extra_ffi_include_dirs`/`extra_ffi_cppflags`) emit `diagnostics` but **no** `hover`/`definition`/`references` for that generation (valid siblings still answer). C FFI (`foreign import`/`ffi.*`/`foreign` types) has hover + in-module refs only (no def/rename); `source_module_roots` outside `include` and binary/stdlib providers give hover/completion without source defs.
4. **Per-slice SDK (`compiler_root`), trust & no fallback:** Never edit tracked `titan-config.lua` for local pins; put **only** `compiler_root = "/path/to/prefix"` in untracked `titan-config.local.lua` (any other key, empty/non-string, or syntax error fails the root). Root must match `initOptions.trustedRoots` or `TITAN_LS_TRUSTED_ROOTS`, else fails (`-32803`) with **zero fallback** to the default SDK.
5. **Browser projects (`target = "browser"`):** Type-check against `<PREFIX>/lib/titan-browser/0.6/{titan.a,analysis-target,absent-modules}` (`driver.browser_analysis_target`) with no `wasi-sdk`/Binaryen unless a source uses `foreign import` C probes (native embedded inventories never participate).
6. **Worktree `.titan-ls/` & `lsp.json` hygiene:** Workers write `<root>/.titan-ls/{index.sqlite3,var/cache/titan-probes/2}`. Never touch another agent's `.titan-ls/` or edit user/project `lsp.json` without authorization; remove your own `.titan-ls/` and `titan-config.local.lua` before committing if unignored.

## LSP capability matrix

| Feature | omp `lsp` action / method | Baseline & rules |
| --- | --- | --- |
| Diagnostics (pull + push) | `diagnostics` (`textDocument/diagnostic`, `$/progress`) | Saved files; always pass concrete `.titan` file/glob (`file="*"` runs non-Titan checkers). Pull refreshes saved state (`resultId`); unowned `.titan` returns empty. |
| Nav & Rename | `definition`, `references`, `rename` | Saved files under `include`; 1-based `line` + required `symbol` (`name#N`). Pass `apply=false` to preview. |
| Folding | `request` `textDocument/foldingRange` | Saved files under `include`. |
| Completion & hover | `request` `textDocument/completion`, `hover` | Handled here (never load `titan-completion` to query LSP). Completion (`.`/`:` or raw 0-based `line` + UTF-16 `character`) checks unsaved buffer vs saved deps; once active, `hover` tracks edits (200 ms debounce). |
| Router status | `request` `titan/workspaceStatus` | Live roots: `root`, `origin`, `trusted`, `compilerRoot`, `state`, `failure`, `workerPid`, `generation`, `titanRoot`, `probePrefix`. |
| **Unimplemented** | `symbols`, `type_definition`, `implementation`, `code_actions`, `willRenameFiles` | Fail with `MethodNotFound` (`-32601`). |

## Multi-root router, server binary, and `lsp.json`

- **Routing & worker pool:** Initial roots come from `initialize.workspaceFolders` (`realpath`). Documents route to the **most specific** claimed root or nearest ancestor `titan-config.lua` (`discovered`); unowned files fail `RequestFailed` (`-32803`). When omp's mux drops a sibling folder, the root becomes `origin: "released"` with its warm worker retained (`file=` re-adds as `"folder"`). Caps: `maxWorkers` (default `4`, `TITAN_LS_MAX_WORKERS`), idle LRU eviction (`idleTimeoutSeconds`, default `600`), open buffers replayed on respawn, 3 crashes in 60 s -> `failed` until settings change/`reload`.
- **One binary serves every SDK:** Build from `vscode-titan` against a read-only SDK: `make -C /path/to/vscode-titan -j2 server TITAN_PREFIX=/path/to/sdk` -> `bin/titan-language-server` (never rebuild a maintainer SDK). Default roots use `TITAN_ROOT` + `TITAN_LS_LUA_*`; roots with `compiler_root` load that prefix's compiler Lua, native modules, headers, and static stdlib archive per worker. Rebuild only if a slice compiler needs a newer linked `titan` C support symbol.
- **`lsp.json`:** Merged from `~/.omp/agent/lsp.json`, `<cwd>/.omp/lsp.json`, and `<cwd>/lsp.json`. Omp's `ServerConfig` has **no `env` field**—invoke via `/usr/bin/env` unsetting `TITAN_PREFIX` (only relocates probe cache to `<TITAN_PREFIX>/roots/<digest>`), `TITAN_PATH*`, `TITAN_SOURCE_PATH`, and `LUA_*`. Set `TITAN_ROOT` + verbatim `TITAN_LS_LUA_PATH`/`TITAN_LS_LUA_CPATH` (no `;;`). Avoid user-scope `rootMarkers: ["."]`; project overrides replace `initOptions` whole; leave `pullDiagnostics` unset in omp. Run `lsp(action="reload", file="*")` after edits.

```json
{
  "servers": {
    "titan": {
      "command": "/usr/bin/env",
      "args": [
        "-u", "TITAN_PREFIX", "-u", "TITAN_PATH_0_6", "-u", "TITAN_PATH", "-u", "TITAN_SOURCE_PATH",
        "-u", "LUA_PATH", "-u", "LUA_CPATH", "-u", "LUA_PATH_5_5", "-u", "LUA_CPATH_5_5",
        "TITAN_ROOT=/path/to/sdk",
        "TITAN_LS_LUA_PATH=/path/to/sdk/share/lua/5.5/?.lua;/path/to/sdk/share/lua/5.5/?/init.lua",
        "TITAN_LS_LUA_CPATH=/path/to/sdk/lib/lua/5.5/?.so",
        "/path/to/bin/titan-language-server"
      ],
      "fileTypes": [".titan"], "languageId": "titan",
      "rootMarkers": ["titan-config.lua", "titan-config.local.lua", ".git"],
      "initOptions": { "trustedRoots": ["/tmp/titan-session", "/home/user/Code"], "insertCallSnippets": false },
      "warmupTimeoutMs": 30000
    }
  }
}
```

## Per-slice SDKs, omp queries, LDoc hover, and compiler LS API

- **Slice pin & refresh:** Put `compiler_root = "/tmp/titan-NNN/slice/prefix"` in `<slice>/source/titan-config.local.lua` (relative paths resolve from root). Workers read installed prefixes, not uncommitted edits; after reinstalling or editing, the router auto-restarts that worker (~1 s or next request), or force via `lsp(action="reload", file="*")`.

```text
lsp(action="request", query="titan/workspaceStatus", file="/tmp/slice/source/titan/string.titan")
lsp(action="diagnostics", file="/tmp/slice/source/titan/string.titan", timeout=60)
lsp(action="hover", file="/tmp/slice/source/titan/string.titan", line=42, symbol="split")
lsp(action="definition", file="/tmp/slice/source/titan/string.titan", line=42, symbol="split")
lsp(action="references", file="/tmp/slice/source/titan/string.titan", line=42, symbol="split#1")
lsp(action="rename", file="/tmp/slice/source/titan/string.titan", line=42, symbol="split", new_name="split_bytes", apply=false)
lsp(action="request", file="/tmp/slice/source/titan/string.titan", query="textDocument/completion",
    payload='{"textDocument":{"uri":"file:///tmp/slice/source/titan/string.titan"},"position":{"line":41,"character":14}}')
```

- **LDoc comments (`doc/language/modules.md`, `doc/implementation/documentation-comments.md`):** `---` + `--` continuations (or `--[[-- ... ]]`). Blank lines terminate a block; empty `--` separates paragraphs. `@module` before first token documents the module (main file in folder modules); owner `@field` provides field doc fallback; stdlib uses `@usage <file.md>[#<anchor>]`. Serialized via `types.Documented` / `Type.Module._type_documentation` (invalidating `.titan` source-import facts on edit) and stripped by `types.serialize_semantic` (no runtime ABI/reflection effect).
- **Compiler LS API (`doc/implementation/driver.md#language-server-compiler-api`):** `driver.LANGUAGE_SERVER_API_VERSION = 1` prerelease (clients reject mismatches). Core APIs: `driver.compiler_root()`/`titanc --print-root`, `driver.new_resolver_context{ analysis_only = true, target = ..., browser_analysis_target = ..., io = ..., cache_adapter = ... }`, `compact`/`encode`/`decode_project_entry`, `project_entries_registry`, `restat_c_header_dependencies`, `classify_source_filename`/`target_selection_labels`, `resolve_external_modules`.

```titan
--- Counter helpers for hover docs.
--
-- Supports bounded increments.
-- @module counts

--- Counter with an immutable label.
-- @field label Counter name.
record Counter
  const label: string
  value: integer
end

--- Increment counter by one.
-- @param counter Target counter.
-- @return Updated count.
function step(counter: Counter): integer
  counter.value = counter.value + 1
  return counter.value
end
```

## Pre-delivery verification checklist

- [ ] Saved `.titan` files to disk before querying `diagnostics`, `definition`, `references`, or `rename`.
- [ ] Passed concrete `.titan` path/glob to `diagnostics` (never `file="*"`) and `apply=false` on read-only `rename`.
- [ ] Checked root trust, `compilerRoot`, `titanRoot`, `probePrefix`, and `state == "ready"` via `titan/workspaceStatus` when debugging SDK/FFI errors.
- [ ] Treated `MethodNotFound`, timeouts, and failed-module empty hover as inconclusive; verified with `titanc` / tests.
- [ ] Removed only your own worktree's `.titan-ls/` and `titan-config.local.lua` before committing.
