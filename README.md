# Titan Agent Skills

Curated coding-agent skills for the [Titan](https://github.com/mascarenhas/titan) programming language, its standard library, C/Lua/Browser FFI, native and WebAssembly toolchains, and compiler/LSP tooling.

## Topology (17 Skills + 5 On-Demand References)

Load `titan-programmer` before writing, editing, compiling, or reviewing `.titan` source, plus every applicable peer skill for the task's domain. Skills with multi-layer specialist material keep core rules in `SKILL.md` and gate deep references under `<skill>/references/` via explicit `skill://<name>/references/<file>.md` triggers.

| # | Skill | On-Demand `references/` | Scope |
| ---: | --- | --- | --- |
| 1 | `titan-programmer` | — | Core language, types, `T?`/`value`, `#arr` holes, `const`/`local` records, unions, interfaces, generics, `defer`/`catch`/`gc.finalizable`, modules, basic `titanc`. |
| 2 | `titan-stdlib` | — | Everyday stdlib: `string` (`writer()`, `pack`, `Regex`), `math`, `iteration`, `io`, `path`, `fs`, `os`, `gc`. |
| 3 | `titan-ffi` | `runtime-lua-c-api.md`, `browser-wasm-c-imports.md` | Thin native C FFI (`foreign import`, `owned`, `foreign function`), thin browser JS bridge (`titan.browser`, `bindings.js`), Lua interop & `titan.lua`. |
| 4 | `titan-async` | `uv-and-native-adapters.md` | Cooperative `async` Tasks, cancellation, `join*`/`all*`/`race*`/`any*`, `timer`, `async.channel`, `async.Receiver`, `coroutine`, browser async; `uv` adapters in reference. |
| 5 | `titan-networking` | `http-and-tls-details.md` | `url`, `net` DNS/TCP, `ssl` TLS 1.2+, `http` client (native + browser `fetch`) & HTTP/1.1 server (`Exchange`). |
| 6 | `titan-tester` | `titan-repo-suites.md` | Native `test_*(context: test.Context)`, assertions, `context:run`/`cleanup`, async tests, `titanc --test`/`--test-dir`/`--coverage`; Titan repo suites in reference. |
| 7 | `titan-pegs` | — | `titan.peg` byte parsers, Relabel grammars, typed captures, anchored vs search matching, labeled recovery, combinators. |
| 8 | `titan-thread` | — | OS threads (`titan.thread`), bounded MPMC channels, `thread.Group`, `titan.transfer` (`TransferValue`, closure snapshots, manual resource handoff). |
| 9 | `titan-application` | — | Standalone native & `--target browser` app layout, `titanc` `-o`/`--incremental`/`--exe`/`--static`, target variants, browser `.mjs`/`.wasm` deployment, Windows payloads. |
| 10 | `titan-package` | — | Reusable LuaRocks Titan library rocks (`titan-install`, `titan-uninstall`, format `3.0` rockspecs, `dist/` staging, common-prefix providers, DSO compatibility). |
| 11 | `titan-protobuf` | — | `titan.protobuf` Proto3 wire codecs for records/unions, anonymous messages, `protobuf.portable` (`titan-protobuf.mjs`), cross-state use. |
| 12 | `titan-sqlite3` | — | `titan.sqlite3` native async SQLite connections, prepared statements, `Blob` binding, cursors, `Row:fill`/factories, transactions, `Connection` handoff. |
| 13 | `titan-json` | — | `titan.json` encoding/decoding, null & schema policies, typed record/union mapping, diagnostics, nesting limits. |
| 14 | `titan-language-server` | — | Configuring and querying `titan-language-server` via `omp lsp`/stdio, multi-root workspaces, `compiler_root`/`titan-config.local.lua`, `trustedRoots`, `target="browser"`, LDoc hover. |
| 15 | `titan-websocket` | — | `titan.websocket` native & browser WS/WSS clients, HTTP/TLS server upgrades, framing, Ping/Close, reader duty, cleanup. |
| 16 | `titan-reflect` | — | `titan.reflect` runtime inspection, nominal type descriptors, generic views, dynamic field access & construction. |
| 17 | `titan-completion` | — | Compiler caret-transform completion (`completion.lua`), checker observation points, `analysis_only`, closed-world catalogs, LS completion internals. |

## Mounting into `titan`

In the main `titan` repository, `titan-skills` is mounted as a git submodule at `.agents/skills`. Agent harnesses such as `omp` scan `<skills-root>/<skill-name>/SKILL.md` non-recursively:
- Root files (`README.md`, `AGENTS.md`, `scripts/`) and nested `<skill>/references/` or `<skill>/evals/` directories are never registered as top-level skills.
- Because `omp`'s `AGENTS.md` walker skips hidden `.agents/` directories, this repository's `AGENTS.md` applies only when working directly inside `titan-skills`.

## Verification (`scripts/check_skills.lua`)

Run the mechanical gate with Titan's Lua 5.5 interpreter and an installed Titan SDK prefix (matching the target Titan release):

```sh
# Full check (frontmatter, line/byte caps, links, git diff --check, and native + browser compile/run)
"$PREFIX/bin/lua" scripts/check_skills.lua --prefix "$PREFIX"

# Metadata, size caps, link, eval-suite hygiene (--evals), and diff checks without compiling code blocks
"$PREFIX/bin/lua" scripts/check_skills.lua --skip-compile --evals

# Check specific skill(s) only (with compile+run and eval validation)
"$PREFIX/bin/lua" scripts/check_skills.lua --prefix "$PREFIX" --evals titan-sqlite3 titan-language-server titan-completion
```

Browser `--target browser` code blocks require the browser SDK (`<PREFIX>/lib/titan-browser/0.6/`) plus `WASI_SDK_PATH`, `BINARYEN_ROOT` (or `WASM_OPT`), and `TITAN_NODE` (Node 26+ with JSPI) in the environment when compiling and executing via `titan-browser-run`.

## Prompt-Blind Evaluations

Structured authoring evaluation suites live in `<skill-name>/evals/evals.json` with starter fixtures under `<skill-name>/evals/files/` and verification harnesses under `<skill-name>/evals/oracle/`. Pass `--evals` to `scripts/check_skills.lua` to verify schema, unique IDs, declared files, zero symlinks/PEMs, author-visible zero-leak rules (`prompt` and `evals/files/**`), and blind-judge hygiene (`assertions[].check` and `judge_rubric`). Historical evaluation run logs are kept out of git in GitHub Release validation archives (`issue-<N>-validation-archive`).

See [`AGENTS.md`](AGENTS.md) before editing or adding skills.
