# Titan Repository Test Suites, Make Lanes & CI Gates

Read only when developing or testing inside the Titan compiler/stdlib repository itself. For general `titan.test` authoring, project `--test`/`--test-dir` builds, browser `titan-browser-run`, and `--coverage`, use `skill://titan-tester`.

## 1. Regression Layer Placement

The **subject under test**—never fixture language—picks the suite (`doc/implementation/test-runner.md#regression-placement`). Keep stdlib behavior **outside LuaCov** (LuaCov measures the Lua compiler only; add a small compiler spec for any uncovered compiler gap).

| Behavior under test | Owning layer | Contract |
| --- | --- | --- |
| Tokens, grammar, AST, preprocessor, pure type/metadata/driver logic | Root `spec/*_spec.lua` | Pure Busted; no C build (`cpp_spec.lua` bounds macro recursion). |
| Typechecking, plans, visibility, semantic rejection | `spec/checker/<topic>_spec.lua` | `helpers.run_checker`; never generate/run C. |
| Codegen, native runtime, Lua boundary, DSO/archive/incremental ABI | `spec/coder/<topic>_spec.lua` | Compile/run via `spec/support/helpers.lua`; DSO tests exclude source & `.a`. |
| Public stdlib API & observable runtime/host behavior | `spec/stdlib/titan/` (`TITAN_STDLIB_TEST_ROOTS`) | Native aggregate outside LuaCov; never wrap in Busted or inspect generated C. |
| Browser stdlib portable & target-specific cases | `TITAN_STDLIB_BROWSER_TEST_ROOTS` | Shared owners + `.native.titan`/`.browser.titan` contributors; host-only (`test.host_tests`, `{reflect,json}.lua_tests`, `protobuf.resource_tests`), live net (`{http,websocket}.browser_tests`), embedding (`{os,async}.browser_tests`) stay separate. |
| Native deps, provider ownership, rockspec | `spec/libuv_build_spec.lua`, `spec/rockspec_spec.lua` | Build/packaging ownership gates; separate from API tests. |

## 2. Isolated SDKs, Profiles & Clean Environment

- **SDK & profiles:** Use an absolute isolated `PREFIX` (`ROCKS_TREE == PREFIX`, `PATH="$PREFIX/bin:$PATH"`) against the pinned Lua **5.5.1** fork (`git submodule update --init --recursive`). Ordinary builds default to `production`; repo test goals select `validation` (defaulting to `.lua-validation` when `PREFIX` is unset). Keep `production`/`validation` prefixes separate (`etc/titan/build-profile`). Warm `make lua`/`make luarocks` ignore native input changes.
- **Clean env for canonical runs:** Unset `ROCKS_TREE`, `TITAN_ROOT`, `TITANC`, `TITAN_PATH_0_6`, `TITAN_PATH`, `TITAN_EXTRA_CPPFLAGS`, `TITAN_TARGET`, `TITAN_NO_LINE_DIRECTIVES`, and `LUA_PATH`, `LUA_CPATH`, `LUA_PATH_5_5`, `LUA_CPATH_5_5`. Make pins `TITAN_ROOT` internally for native launches to `TEST_LUA`'s install root; never inherit an ambient one.
- **Read-only shared outputs:** Never mutate `titan-runtime/libtitan.a`, `out/titan.{so,a}`, installed providers, or native dep trees from test helpers. Use separate worktrees for concurrent repo builds (`PREFIX`/`-o` alone do not isolate checkout-owned native trees).

## 3. Repository Make & Busted Commands (from Repo Root)

| Command | Purpose & constraints |
| --- | --- |
| `make test` | Prepare SDK, `luarocks make --force`, run full mixed suite (`TITAN_JOBS=8 TITAN_ROCK_TEST_JOBS=7 make -j8 test` widens the default 4-slot Make >= 4.2 pool). |
| `make rock-test` / `luarocks test` | Mixed Busted + native aggregate on **already installed** snapshot (`luarocks test` does **not** reinstall). |
| `make busted-test [BUSTED_FILTER='pat']` | Installed compiler Busted only; unfiltered partitions via `ci_compiler_test_groups.txt` across `TITAN_ROCK_TEST_JOBS=4` private checkouts, then `EXCLUSIVE_SPECS` alone. |
| `TITAN_ROOT="$PREFIX" TITAN_PROBE_CACHE_DISABLE=1 busted --run=checkout spec/parser_spec.lua [--filter='...']` | Run edited checkout compiler Lua against installed SDK without reinstalling (needs `TITAN_ROOT`; does not refresh runtime/providers/aggregate). |
| `make titan-stdlib-test-build` | Incrementally builds `out/tests/test/tests` (`--no-uv-bootstrap`, `--test-dir spec/stdlib/titan`, explicit first root `test.tests`, 3 `--c-source` helpers + fixed C fixtures). Identical `luarocks make --force` produces 0 recompiles/relinks (`TITAN_VERBOSE=1` prints `Titan object/native/link hit`). |
| `make titan-stdlib-test` | Build aggregate, then run `titan-stdlib-test-run-parallel` (or serial `titan-stdlib-test-run` if `TITAN_FILTER` set). |
| `make titan-stdlib-test-run-parallel TITAN_TEST_JOBS=4` | LPT-balanced ordinary owner groups in parallel, then timing-guarded owners (`timer`, `net`, `ssl`, `http`, `websocket`, `os`) alone, audited by `check_stdlib_test_output.lua --union`. Rejects `TITAN_FILTER`. |
| `make titan-stdlib-test-run TITAN_FILTER='^ssl[.]tests[.]'` | Serial filtered run of existing aggregate (never filters compilation; `TITAN_TEST_TIMEOUT=600`, timeout exit `124`). Unix concurrent filtered runs share one build with distinct `TMPDIR` + `TITAN_TEST_RUN_LOG`. |
| `make stdlib-test` | Retained runtime/packaging Busted specs, then native aggregate (no compiler specs/coverage). |
| `make titan-native-coverage` (`-build`/`-run`) | Serial source-linked aggregate (`out/coverage`, `--coverage-module 'titan.*'`, `-rdynamic` on Linux; never parallel). Windows: `Makefile.win` + `scripts/windows_native_coverage.sh` on local NTFS. |
| `make titan-stdlib-browser-test` | Builds all browser-portable stdlib owners into one `--target browser --test` image, checks closure/imports/subset parity gate, runs Node 26+ & Chromium (`TITAN_FILTER`, `TITAN_BROWSER_TEST_ENGINES`, `TITAN_BROWSER_TEST_RUNNER`). |

`BUSTED_FILTER` and `TITAN_FILTER` are independent (`make rock-test BUSTED_FILTER='...' TITAN_FILTER='...'` runs both domains).

## 4. Native Aggregate Conventions (`--no-uv-bootstrap`, Fixtures & Busted Hygiene)

- **Per-case Runtime (`--no-uv-bootstrap`):** Wrap async cases in source-only `support.runtime.run(function() ... end)` and register Runtime-bound Tasks/handles immediately via `support.runtime.cleanup` / `support.async.cleanup_task`. `Context:cleanup` runs **after** that Runtime ends—use only for non-Runtime cleanup (e.g., removing a parent-compiled fixture). Never import `uv.titan` or inspect private Task/Runtime internals.
- **Expected diagnostics & fresh processes:** Bracket deliberate uncaught Task logs with `context:log("BEGIN expected uncaught async Task diagnostics")` / `END ...`. Launch child processes from the owning native test via `support.command` (C fixtures in `spec/fixtures/stdlib/native/`, Titan children in `spec/fixtures/stdlib/titan/`).
- **Output audit & skip prefixes (`check_stdlib_test_output.lua`):** Unfiltered runs must execute every manifest owner with 2-decimal timings, zero duplicates, and classified skips: `platform: ` (other-OS semantics), `capability: ` (probed host limit), `unsupported: ` (unimplemented documented API), `portability: ` (unfinished fixture—**deliberately fails validation gates**).
- **Busted hygiene:** Use `spec.support.helpers` (`helpers.verbose = true`), require `luassert` explicitly in helpers, reset `types.registry`/`driver.imported`, use `restrict` + `assert_is_subset`, and **never** set unlimited `TableFormatLevel` globally on checked self-referential ASTs. Add a measured row to `spec/support/ci_compiler_test_groups.txt` (`titan-busted-timings-v2`) for every new `spec/**/*_spec.lua`, and tag heavy tests `#stress` with a covered companion.
- **Artifact cleanup:** Remove only test-owned files (incl. paired `.a`). `make clean` / `clean_generated_test_artifacts.sh` use `.titan.source` metadata & exact banners—never delete `spec/**/*.c`, `*.a`, or `out/titan.{so,a}` broadly. On POSIX, `os.tmpname()` ignores `TMPDIR` (`/tmp/lua_XXXXXX`), so concurrent workers share `/tmp`.

## 5. Browser Validation, Windows & CI Lanes

- **Real-toolchain browser gates:** Require `wasi-sdk` 34 (`WASI_SDK_PATH`), Binaryen `version_133` (`BINARYEN_ROOT`), Node 26+ JSPI (`TITAN_NODE`), Chromium (`TITAN_CHROME`), `make lua-browser`, `make browser-sdk`. Real cases are pending when tools are absent; set `TITAN_REQUIRE_BROWSER_TOOLCHAIN=1` (`TITAN_REQUIRE_BROWSER_DEPLOYMENT=1` for Vite/Playwright doc checks) to fail instead.
- **Linux CI (`ci.yml`, 14 push jobs):** `build-compiler` (compiler SDK only), `browser-packaging` (`doc_check.lua --clean-checkout` on `HEAD`), and serial `sanitizer` (ASan+UBSan GCC, fake-stack probe, shadow `.text` mapper) start independently; `build-compiler` fans out to:
  - `test-linux-compiler` (2 shard pairs, LuaCov `compiler`, `#stress` split) and `native-coverage` (`stdlib-busted-test`, 2 installed-stdlib shards, `titan-native-coverage` LCOV `native-stdlib`, bundled/system OpenSSL smokes; `TITAN_COVERAGE_TEST_REQUIRED=1`);
  - `browser-toolchain` (5 Busted specs + loader/runner/trace-adapter/Node trace gates), `browser-stdlib` (`sdk`: `titan-stdlib-browser-test` + 8 specs; `scheduler`: semantic pack unittest + 7 specs + `playground-sdk`), and `browser-playwright` (5 Chromium/Firefox/WebKit × `validation`/`production` cells: trace/degraded, bridge/counter/responsive, live net, delivery, docs, production pins, records, core stdlib).
- **macOS (`macos.yml`) & Windows (`windows.yml`):** Push-triggered (`validation`, no browser/coverage/sanitizer). macOS (`macos-15` arm64) uses Homebrew GNU Make >= 4.4 and proves universal x86_64/arm64 Mach-O archives; **never trigger manual macOS `full` dispatch without express maintainer approval**. Windows uses MSYS2 CLANG64/UCRT (`mingw32-make -f Makefile.win`), short local NTFS paths, serial aggregate under Job Object supervisor (`OPENSSL_MODE=bundled` vs `system`); fs/SQLite/watcher tests require local NTFS (never shared folders). Hosted CI and local runs are separate evidence—record commit, OS/arch, profile, and dependency modes.
