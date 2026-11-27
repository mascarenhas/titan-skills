---
name: titan-application
description: Use when building, organizing, or deploying standalone Titan executables or browser WebAssembly apps. Covers titanc -o/--incremental/--tree/--exe/--static, target variants, Makefiles, .gitignore, Windows payloads, and .mjs/.wasm deployment; use titan-package for LuaRocks libraries and titan-ffi for C FFI or titan.browser JS bridges.
---

# Titan applications: layout, native builds, and browser deployment

Scaffold, build, organize, or deploy standalone native and WebAssembly browser Titan applications. Pair with `skill://titan-programmer` for `.titan` code, `skill://titan-tester` for native tests/`--coverage`, `skill://titan-async` for Tasks/`--no-uv-bootstrap`, `skill://titan-ffi` for C helpers and `titan.browser`/`bindings.js`, and `skill://titan-protobuf` for `titan-protobuf.mjs`. Use `skill://titan-package` for reusable LuaRocks libraries.

## Non-negotiable invariants

1. **Compiler-owned incremental builds & output isolation:** Always run `titanc --incremental --output <dir>` (`-o`). Never write per-module Make `.o` rules, header inventories, or compiler/SDK stamps; `titanc` tracks imports, C headers, flags, `--c-source`, and final links. Keep incompatible flags, build profiles (`TITAN_BUILD_PROFILE=production` vs `validation`), and targets (`--target browser` writes `<out>/.titan-target`) in **separate** `-o` dirs.
2. **Output locks & reserved paths:** `titanc` serializes concurrent runs sharing `-o` (or `dirname(--exe)`) via permanent `<dir>/.titan-build.lock` on local POSIX/NTFS filesystems (network shares unsupported). Never place authored files at `<out>/.titan/`, `.native/`, `.titan-links/`, `.coverage/`, `.titan-target`, `<stem>.{c,o,priv.h,ffi.h,titan.h}`, or split `<stem>.partN.{c,o}` (`1 <= N < --c-parts`).
3. **`--tree`, positional roots & SDK source fallback:** Positional roots and `--test-dir` resolve **only** under authored `--tree` roots (default `.`, semicolon-separated `'src;tests'`), never `<root>/lib/titan/0.6`. Ordinary `import`s fall back to read-only `<root>/lib/titan/0.6` (requiring `-o` whenever installed source is selected).
4. **Entry point, `--exe` vs `--static`, and Windows:** Export exact `function main(args: {string}): integer` in one requested root (`args[1]` is first user arg). `--exe PATH` is relative to CWD, not `-o`. Unix `--static` embeds reached Titan `.a` archives + app-compiled source with zero `.so` fallback (rejects DSO-only providers and no-main library links; never implies system `-static`). Windows has **no** `--static`: it emits `<exe>.exe` + `<out>/lib/titan/0.6/<logical-root>.dll` on the same volume.
5. **Browser builds & deployment:** `--target browser` requires `-o`, **`wasi-sdk` 34** (any `34.x`, LLVM 23.1), exact **Binaryen `version_133`**, Node 26+ JSPI (`TITAN_NODE`), and matching `TITAN_BUILD_PROFILE` against `make browser-sdk`. Deploy `.mjs`, `.wasm`, and `.wasm.trace` from **one** build over HTTP (`text/javascript`, `application/wasm`, CSP `script-src 'wasm-unsafe-eval'`; never `file://`) and always `await instance.dispose()`.
6. **Delivery checks & `TITANC` hygiene:** Keep `TITANC` a single executable name/path (never flags/wrappers)—runtime SDK fallback runs `$TITANC --print-root` without a shell. Prove standalone delivery in a relocated temp dir under `env -i` with `titanc`/`lua` off `PATH`.

## Target and build-mode matrix

| Mode | Command | Output & provider resolution |
| --- | --- | --- |
| Unix dynamic | `titanc --incremental -o build --exe build/app app.main` | Links source (`.a` fallback); loads `.so` via `!;!/../lib/titan/0.6`, then SDK fallback. |
| Unix `--static` | `titanc --incremental --static -o build-s --exe build-s/app app.main` | Embeds reached Titan `.a` closure + source; rejects DSO-only providers; system libs stay dynamic. |
| Windows native | `titanc --incremental -o build --exe build/bin/app.exe app.main` | DLL-only (MSYS2 CLANG64); emits `<exe>.exe` + `build/lib/titan/0.6/<root>.dll`. |
| Browser Wasm | `titanc --target browser --incremental -o build-web --exe build-web/app.mjs app` | Self-contained `.mjs`, `.wasm`, `.wasm.trace`, `.wasm.map` (`--exe` must end in `.mjs`). |
| Compile-only | `titanc -c --incremental -o build ...` | Owned `.o`/headers only; rejects `--exe`, `-l`, `-L`, `--ldflag`, `-X`, `--no-uv-bootstrap`. |

## Repository layout, target variants, and `.gitignore`

```text
project/
  .gitignore  README.md  main.titan    # function main(args: {string}): integer
  app/service.titan                    # reusable modules
  tests/service_test.titan             # native tests (--test-dir tests)
  build/  build-browser/               # separate -o trees (ignored)
```

Compile logical dotted names (`main`, `app.service`), never file paths. Transitive `async` imports auto-enable Runtime bootstrap (`uv` alone does not); see `skill://titan-async` before `--no-uv-bootstrap`.

**Target-specific source variants:** Any flat file, folder main, or contributor `name.titan` supports `name.<label>.titan` using lowercase labels `linux`, `darwin`, `windows`, `browser`, `native`:
- Native selects `<host>` -> `native` -> default; `--target browser` selects `browser` -> default (omitting native-only files).
- Stacked (`x.linux.native.titan`) or mis-cased (`x.Linux.titan`) names error. Folder contributors sort by logical name (label stripped); a main variant replaces the default main and its `do ... end` initializer.
- `-T`/`--target` (overriding `TITAN_TARGET`) accepts host OS or `browser` (`native` and cross-OS error). Labels never enter generated `.c`/`.o`/executable names.

```titan
-- file: platform.native.titan
function label(): string
  return "native"
end

-- file: platform.browser.titan
function label(): string
  return "browser"
end

-- file: main.titan
local io = import "io"
local platform = import "platform"

function main(args: {string}): integer
  local target = args[1] or platform.label()
  io.print("hello from " .. target)
  return 0
end
```

**Initial `.gitignore`:** Ignore generated outputs and local secrets narrowly; **never** add blanket `*.c`, `*.h`, `*.lua`, `*.sqlite3`, `*.json`, or `*.log` rules (they hide authored helpers/fixtures).

```gitignore
/build/
/build-browser/
/dist/
/site/
.titan-ls/
.env
.env.*
!.env.example
!.env.*.example
```

Verify with `git check-ignore --no-index build/main.c .env.local .env.example main.titan app/helper.c tests/fixtures/sample.sqlite3`.

## Native flags, `--c-source`, Make integration, and delivery

**Flag order:** (1) `TITAN_BUILD_PROFILE` (`production`: `-O3`, Linux `-flto=auto -ffat-lto-objects`, `-g1`/`-gline-tables-only`; `validation`: `-O0 -fno-lto -g`) -> (2) shell-word-split `TITAN_EXTRA_CPPFLAGS`/`CFLAGS`/`LDFLAGS` -> (3) CLI `-I`, `-D`, `--cflag`, `-L`, `-l`, `--ldflag` in written order -> (4) SDK `-I` dirs last. Forward `CC` via `export CC` (not `CC="$(CC)"`; quote spaced paths as `CC='"C:/.../clang.exe"'`). For debugger builds on a `production` SDK, set `TITAN_EXTRA_CFLAGS='-Og -g -fno-lto' TITAN_EXTRA_LDFLAGS='-Og -g -fno-lto'`.

**C helpers:** Pass `--c-source native/helper.c` directly to the final link (`<out>/.native/`). If another tool needs the `.o` path, capture stdout of `titanc -c --incremental -o build <compile-flags-only> --c-source native/helper.c --print-c-objects` (never glob `build/.native/*.o`) and link via `-X <obj>` before `--exe` and module names.

**GNU Makefile (`+` shares Make 4.4+ FIFO / Linux pipe jobservers; macOS stock 3.81 uses local `-j`/`TITAN_JOBS`):**

```make
TITANC ?= titanc
TITAN_JOBS ?= 4
BUILD_FLAGS = --incremental --output build --static -j $(TITAN_JOBS)
DELIVERY_PATH ?= /usr/bin:/bin
SMOKE_ARGS ?= --self-test

.PHONY: all app app-tests test package check-delivery
all: app

app:
	+$(TITANC) $(BUILD_FLAGS) --exe build/app main

app-tests:
	+$(TITANC) $(BUILD_FLAGS) --test --tree . --test-dir tests --exe build/app-tests

test: app app-tests
	./build/app-tests

package: app
	rm -rf dist && mkdir -p dist/bin && cp -p build/app dist/bin/

check-delivery:
	@test -x dist/bin/app || { echo 'run make package first' >&2; exit 1; }
	@if env -i PATH='$(DELIVERY_PATH)' sh -c 'command -v titanc || command -v lua'; \
	then echo 'DELIVERY_PATH must not reach titanc or lua' >&2; exit 1; fi
	@tmp=$$(mktemp -d) && cp -Rp dist/. "$$tmp" && \
	( cd "$$tmp" && env -i HOME="$$tmp" PATH='$(DELIVERY_PATH)' \
	  "$$tmp/bin/app" $(SMOKE_ARGS) ); status=$$?; rm -rf "$$tmp"; exit $$status
```

- **Tests & delivery:** App and `--test` share `build/` via `.titan-build.lock`. `--test-dir` must lie inside a `--tree` root (first containing root sets logical prefix; discovers `test(s)`, `spec(s)`, `*_test(s)`, `*_spec(s)`; filter with `--test-exclude`). Keep `check-delivery` prerequisite-free; for dynamic builds also ship provider `.so` files in `dist/bin/` or `dist/lib/titan/0.6/`.
- **Logs, cache & splits:** Keep default stderr progress in Makefiles; use `-q` in scripts and `-v` for commands and miss reasons (`source-set`, `source-content`, `configuration`, `c-input`, `import-interface`, `import-binding`). Opaque flags (`@file`, `-fplugin`, `-specs`, `-wrapper`, `-Xclang`, `-Xlinker`) disable caching on affected nodes/links. Disposable digest cache: `<out>/.titan/digests`. `--c-parts` defaults to `4` on Linux, `1` elsewhere.
- **Provider lookup & stock Lua:** Runtime searches `TITAN_PATH_0_6` -> `TITAN_PATH` -> `!;!/../lib/titan/0.6` (`;;` splices default, `!` = exe dir; `.` is never searched at runtime) -> once-per-state SDK fallback (`TITAN_ROOT` or `$TITANC --print-root`). Never put `lib/titan/0.6` on `package.cpath`. `ldd`/`otool -L` miss lazily `dlopen`'d Titan providers; rely on `check-delivery`. Stock Lua 5.5.1 hosts set `LUA_CPATH_5_5="$ROOT/lib/lua/5.5/?.so;;"` + `TITAN_ROOT`/`TITAN_PATH_0_6` (checkout `--lua` needs `MYCFLAGS=-fPIC`).

## Windows deployment and platform deltas

Build from MSYS2 **CLANG64** (`LC_ALL=C.UTF-8`, `PREFIX == ROCKS_TREE`): `mingw32-make -f Makefile.win lua|luarocks|compiler PREFIX=/c/Titan/sdk`. Direct `luarocks.exe` needs `LUAROCKS_CONFIG="<sdk>/etc/luarocks/config-5.5.lua"`. `bin/titanc.exe` ignores `LUA_INIT`/`LUA_PATH`/`LUA_CPATH`.

- **Payload layout:** Ship `bin/<app>.exe`, `bin/lua55.dll`, native DLLs (`libuv-1.dll`, `libllhttp-9.4.dll`, `libsqlite3-0.dll`, and matched `libcrypto*.dll`/`libssl*.dll`, e.g. `-4-x64` MSYS2 OpenSSL 4 or `-3-x64` bundled 3.5.7), plus `lib/titan/0.6/<logical-root>.dll` and `titan.dll`. Use separate `-o` dirs if two test binaries share a first root.
- **Traps:** Close processes holding mapped DLLs before rebuild/uninstall. Leftover `<file>.stage.tmp.<suffix>` dirs auto-retire on the next certified link (refused if holding inputs or uncertified—delete manually). `--c-source` helpers omit `LUAI_FUNC` dllimports (define `LUA_LIB` or `__declspec(dllexport)` to export `luaopen_*`). Raw C worker threads start in 53-bit x87 mode (call `_fpreset()` for `long double`). Validate in a plain Windows shell without SDK `PATH` on local NTFS.

## Browser (`--target browser`) builds, loader, and deployment

**Setup:** Linux, macOS, or Windows MSYS2 CLANG64 (`make -f Makefile.win lua-browser` & `browser-sdk`). Configure `WASI_SDK_PATH` (or `PATH`; `CC`/`AR`/`RANLIB` ignored), `BINARYEN_ROOT`/`WASM_OPT`, `TITAN_NODE`, and Chrome 137+ / Firefox 153+ / Safari 27+. Run `make lua-browser PREFIX="$PREFIX"` then `make browser-sdk PREFIX="$PREFIX"`. Clear native `TITAN_PATH_0_6` and native flags (`-fPIC`, `-flto`, `-march=...`, `-O*`, `-g*`, `--no-line-directives`).

```sh
titanc --target browser --incremental -o build-browser --exe build-browser/app.mjs app
mkdir -p site
cp index.html build-browser/app.mjs build-browser/app.wasm build-browser/app.wasm.trace site/
cp "$PREFIX/lib/titan-browser/0.6/titan-protobuf.mjs" site/   # only if using protobuf.portable
```

- **Hosting & bundlers:** Serve `.mjs`, `.wasm`, and `.wasm.trace` from one build (mismatches fail `TITAN_BROWSER_PROTOCOL`; `.wasm.map` is DevTools-only). Cross-origin needs CORS; Vite needs `build: { assetsInlineLimit: 0 }`; moved assets or `blob:`/`data:` modules need `create({ locateFile })`. For local dev, build `doc/language/http-dev-server.titan` natively in a separate `-o` dir.
- **Loader (`create(options)`):** `.mjs` embeds loader/factory (zero external imports). Options: `stdin`/`stdout`/`stderr` (`+ *Kind`/`*End`), `locateFile`, `requireTrace`, `bindings`, `imports`, `env`, `onNotificationError`, `requestDrain`, `onEngineFailure`. Methods: `initialize()`, `run(args)` (once -> `{ kind, status, bytes, trace }`), `call`, `callTask(cb, args, { signal })`, `notify`, `drain`, `dispose()`. Reverse calls inside bindings/sinks reject `TITAN_BROWSER_REENTRY` (use `notify()`). See `skill://titan-ffi` for thin primitive-only `bindings`/`imports` and `doc/language/browser-app/`.
- **Stdlib subset & limits:** 21 modules (14 complete: `coroutine`, `gc`, `io`, `iteration`, `json`, `math`, `path` [POSIX], `peg`, `protobuf`, `reflect`, `string`, `test`, `transfer`, `url`; 6 browser-adapted: `async`, `timer`, `os`, `lua`, `http`, `websocket`; browser-only `browser`). **6 absent at compile time:** `fs`, `net`, `sqlite3`, `ssl`, `thread`, `uv`. Limits: `LUAI_MAXCCALLS = 100` (native 200), 1 MiB main / 256 KiB coroutine C stacks, 16 MiB–2 GiB linear memory, 7,654,321 B max function / 1 GiB `.wasm`, 128-level protobuf/transfer nesting, no `--coverage`, cross-heap JS/Lua cycles uncollected, Safari traces omit line numbers, `production` inlining merges frames (`--test` keeps test frames; `validation` keeps all).
- **CLI runner:** `"$PREFIX/lib/titan-browser/0.6/titan-browser-run"` (not in `bin/`) `[--engine node|chromium] [--imports FILE] [--root DIR] [--timeout MS] build-browser/tests.mjs -- --filter='...'` (`TITAN_BROWSER_ROOT_NO_SANDBOX=1` for root container Chromium).

## Pre-delivery verification checklist

1. Native and `--test` builds pass via `titanc --incremental -o <dir>` with non-zero reported cases; separate `-o` per target/profile.
2. `git check-ignore --no-index` ignores build/dist/site/cache/`.env.*` while keeping authored `.c`/`.h`/`.lua`/fixtures tracked.
3. Relocated `check-delivery` passes in a temp copy under `env -i` with `TITAN_*`/`LUA_*`/`LD_LIBRARY_PATH` unset and `titanc`/`lua` off `PATH`.
4. Windows targets pass in a plain Windows shell with `bin/lua55.dll`, native/OpenSSL DLLs, and `lib/titan/0.6/*.dll`, without SDK `PATH`.
5. Browser targets bundle `.mjs`/`.wasm`/`.wasm.trace` from one matching-profile build, pass `titan-browser-run` (enforces `requireTrace: true` by default), and verify HTTP MIME/CORS/CSP + `dispose()`.
