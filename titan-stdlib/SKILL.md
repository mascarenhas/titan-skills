---
name: titan-stdlib
description: Use for Titan stdlib (string, math, iteration, io, path, fs, os, gc): text, files, I/O, paths, OS, GC. Covers regex/pack/writer, random/numerals, ipairs/pairs, Reader/Writer/lines, watchers, spawn/popen/signals/clocks, weak Maps & finalizers; use titan-programmer for syntax, titan-async for Tasks/timers/uv, titan-networking for net/http, titan-json/protobuf/sqlite3 for data.
---

# Titan everyday standard library

Covers `string`, `math`, `iteration`, `io`, `path`, `fs`, `os`, `gc`. Pair with `titan-programmer` for syntax/types/`T?`/`defer`/`raise`.
Peers: `titan-async` (`async`/`timer`/`coroutine`/`uv`), `titan-thread`, `titan-networking`, `titan-websocket`, `titan-pegs`, `titan-json`, `titan-protobuf`, `titan-sqlite3`, `titan-reflect`, `titan-ffi`, `titan-tester`.

## Non-negotiable invariants

1. **Short imports:** Import `"string"` (alias `strings`), `"math"`, `"iteration"`, `"io"`, `"path"`, `"fs"`, `"os"`, `"gc"`. Lua uses `require "titan.<name>"` without touching `_G`/string metatables.
2. **Linear strings:** Construct `string.StringWriter` via `strings.writer()` (never `string.Writer` or `StringWriter.new()`) + `:write()` + `:drain()`—never loop `..` or chunk arrays.
3. **Hole-safe iteration:** `iteration.ipairs(arr)` visits `1..#arr` across `nil` holes (`for i, v?`); mutable `{T}` only—use numeric `for i = 1, #xs` for `const`/`const?` Arrays.
4. **Structural `io` & owned `io.lines`:** `io.Reader`/`Writer`/`Closer` satisfy structurally; `close()` is idempotent, closed readers return `nil`, raw reads use `for chunk in src:read do`. `io.lines(r)` owns closing `r`—never read/close separately.
5. **Async Tasks & `defer :close()`:** `fs` (except sync path/transfer), `os` streams/`spawn`/`popen`/`wait_signal`/`exit`, and async `io` need a Task (`main` auto-bootstraps; Lua: `async.run`+`async.loop`). Immediately `defer :close()`/`w:clear()`: `os.exit`/Runtime close never close `fs.File` or kill/reap children.
6. **Sync-only `gc.finalizable`:** Only for tables/full userdata owning external OS/C handles—never GC data and **never** yielding ops (`fs.File:close()`): yields/`gc.*` raise; errors warn. Shared `__gc`: use param, never capture instance, stay sync/idempotent, prefer `finalizable<|value|>` on hot types.
7. **`os.spawn` vs `os.popen` & browser:** `os.spawn` for direct argv, split `stdout`/`stderr`, or inherited fds; `os.popen` only for merged shell commands; drain pipes concurrently with `stdin`/`wait()`. Browser: no `fs`, POSIX `/` `path`, `string.pack` `l`/`L`/`T`=4B (`wasm32`), `os` subset.
8. **Pure lexical `path`:** Sync byte-string ops (Go `filepath`-style); never inspects disk/symlinks (`fs.realpath`). `path.separator` is `string?` (non-`nil` after init, auto-unwraps).

## Lua-to-Titan stdlib delta

| Lua habit | Titan idiom | Key delta |
| --- | --- | --- |
| `import "titan.string"` | `local strings = import "string"` | Short imports; Lua uses `titan.*`. |
| Loop `s = s .. x` | `strings.writer()` + `:drain()` | Linear join; `drain()` resets. |
| `string.find` patterns / `%1` | `strings.find` / `compile_regex` | Literal `find`; `gsub` passes whole match, verbatim return. |
| Global `pairs`/`ipairs` | `iteration.pairs`/`ipairs` | No globals; `ipairs` crosses holes (`v?`); `const`: numeric `for`. |
| `math.abs` int / `random(6)` | Float ops; `v is integer`; `random(6) as integer` | Float returns; no `math.type`; `random` -> `value`. |
| `format("%d","7")` / `tonumber("inf")` | `format("%d",7)` / `math.tonumber` | Reject numeric strings in `format`/`pack`, `nan`/`inf` in `tonumber`. |
| `os.clock()` wall / `io.open` | `os.time()` / `fs.open` + `defer :close()` | `clock()` is CPU (native); files in async `fs`. |
| `setmetatable(__mode/__gc)` | `gc.weak`, `gc.ephemeron`, `gc.finalizable` | Raw metatable update + mark; sync finalizers only. |

## `string`, `io` & `path` — Bytes, regex, streams & lexical paths

- **Bytes & 200-cap (`string`):** 1-based bytes, process C locale (`lower`/`upper`; `"C"` for ASCII), NUL safe except modified `%s`/`z`. Cap **200** on variadic/flex lists (`byte`, `char`, `format`, `pack`, regex groups; `unpack` <=199 + next-pos).
- **Byte quirks:** `byte(s, first?, last?)` defaults `last` to raw `first` before clamp (`byte("abc", 0)`->0 values). `find` is literal (empty `needle`->`last==first-1`). `tostring(v)` honors `__tostring`, ignores `_G.tostring`, 1 `value` (`tostring()`->`"nil"`).
- **Format & pack:** Dynamic `value` args use `as integer`/`as float`/`as string` (`c[n]`/`s[n]`/`z`)—integral floats ok, numeric strings rejected. `%q`: integral floats->int, fractional->hex float; unmodified `%s` keeps NUL, modified rejects; Windows rejects flags/width/prec on `%a`/`%A`.
- **Pack sizing:** `packsize` rejects `s[n]`/`z`. `unpack(fmt, data, init?)` returns `(value, ...: value)` with next-pos last (`init==#data+1` ok; `>` raises). `wasm32`: `l`/`L`/`T`=4B, `j`/`J`=8B LE.
- **Regex (`compile_regex`, weak-cached):** ASCII classes (`\s` excludes `\f`), `\<`/`\>`, outer-only `^`/`$` anchoring whole alternation (`^a|b$` anchors both), left-biased `a|ab`, greedy backtracking, `\1`..`\9`. Rejects `\v`, `\b`, hex/octal, multi-digit backrefs, nullable unbounded repeats (`*`,`+`,`{n,}`). Limits: 200 groups, 512 depth, stack via `peg.set_max_stack`.
- **Regex loops & `gsub`:** Use `gmatch` (`RegexMatch`) if group 1 is optional (`matches` yields `values()`, so `nil` group 1 ends `for`). `split(s, nil)` yields bytes; regex delim keeps empty fields. `gsub` passes `whole()` only, inserting return verbatim.
- **In-memory streams:** Construct via `strings.reader(s)` / `strings.writer()` (never `string.Writer` or `StringWriter.new()`); `StringReader`/`StringWriter` satisfy `io.ReaderCloser`/`WriterCloser` sync without importing `io` (`read_until` raises on empty `delim` with unread bytes, returns unterminated tail once before `nil`; `StringReader:close()` drops unread bytes; `StringWriter:close()` no-op).
- **`io` contracts:** 7 type-only Interfaces (`Reader`, `Writer`, `Closer`, `ReaderWriter`, `ReaderCloser`, `WriterCloser`, `ReaderWriterCloser`; absent on Lua `titan.io`). `fs.File` uses adjusted dispatch; `os.InputStream`/`OutputStream` follow caller direction (`proc.stdin`=`OutputStream`). Windows libuv caps single file-read/stream-write at `2^32-1` B.
- **`io.print` & `io.lines`:** `print(...: value)` converts L->R via `string.tostring`, joins `"\t"`, appends `"\n"`, writes `os.stdout`. `lines(rc: ReaderCloser)` calls `read_until("\n", true)` (never `read()`), yields `""` for empty lines; creating tuple neither reads nor closes.
- **Lexical `path`:** POSIX `/` on Linux/macOS/Browser (`volume`=`""`, `to_slash`/`from_slash` no-ops); Windows takes `/` & `\`, emits `\`, knows `C:`, UNC `\\srv\share`, device `\\.\`/`\\?\`/`\??\`. `normalize("")`->`"."`; `join()`->`""`; `join("w","/o")`->`"w/o"`; `split(p)` raw (`dir..file==p`), `dirname` normalized; `extension` keeps `.` (`".profile"`, `"a.tar.gz"`->`".gz"`). Windows: `is_absolute` needs volume+root (`\w`/`C:w` false); `join("C:","w")`->`"C:w"` (`"C:\\"` for root).

```titan
local io = import "io"
local path = import "path"
local strings = import "string"

local tag_re = strings.compile_regex([[(\w+)(?::(\d+))?]])

local function copy_all(src: io.Reader, dst: io.Writer): integer
  local n = 0
  for chunk in src:read do
    dst:write(chunk)
    n = n + #chunk
  end
  return n
end

function main(args: {string}): integer
  local v, l, p = strings.unpack(">BH", strings.pack(">BH", 2, 1024))
  if (v as integer) ~= 2 or (l as integer) ~= 1024 or (p as integer) ~= 4 then raise "pack" end
  local out = strings.writer()
  defer out:close()
  for m in tag_re:gmatch("api:8080 health") do
    local port? = m:group(2)
    out:write(strings.format("%s=%s\n", m:group(1) or "", port or "-"))
  end
  local s, hits = strings.gsub(out:drain(), [[\d+]], function (d) return strings.rep("#", #d) end)
  local n = copy_all(strings.reader(s), out)
  local lines = 0
  for _ in io.lines(strings.reader(out:drain())) do lines = lines + 1 end
  local d, f = path.split("a//b.txt")
  if hits ~= 1 or n ~= #s or lines ~= 2 or d .. f ~= "a//b.txt"
     or path.extension(path.normalize("a//b/../c.tar.gz")) ~= ".gz"
     or path.to_slash(path.join("w", "/o", "x.o")) ~= "w/o/x.o" then raise "io/path" end
  return 0
end
```

## `math` & `iteration` — Typed numerics, RNG & hole-safe loops

- **Numerics (`math`):** `pi`, `huge`, `const maxinteger` (`2^63-1`), `const mininteger` (`-2^63`). Float ops (`abs`, `ceil`, `floor`, `fmod`, `modf`, `min`, `max`, trig, `exp`, `sqrt`, `log`/`log2`/`log10`) return `float` (`log(x,b)`=`ln(x)/ln(b)`—prefer `log2`/`log10`). `ldexp` exp fits C `int`; `min`/`max` skip `<` metamethods; `ult(a,b)` compares 64b unsigned (`ult(0,-1)==true`).
- **RNG:** xoshiro256** (non-crypto, per-state). `random(l?, u?): value`: `()`->`float` `[0,1)`, `(0)`->64b `integer`, `(u)`->`[1,u]`, `(l,u)`->`[l,u]` (cast `as float`/`as integer`; rejects `l>u` or `u` without `l`). `randomseed(s1?, s2?)` returns both ints (`s2` defaults `0`; `s2` without `s1` raises).
- **Numerals:** `tonumber(v, base?)` without base keeps int/float, checks full bytes (no NUL/trailing/`"nan"`/`"inf"`), locale-independent `.`, decimal overflow->`float`, hex wraps mod `2^64`; with `base` (`2..36`), raises on non-`string` `v`/bad `base`, bad digits->`nil`, wraps mod `2^64`. `tointeger(v)` takes int, exact integral float, or matching string, else `nil`.
- **Iteration:** `next<|K,V|>(m, k?)` is O(1) empty test; absent non-`nil` key raises `invalid key to 'next'`; insert mid-loop unspecified (update/delete current safe); `K` non-`nil`/non-option. `pairs` stops only on `nil` (visits `false` keys). Erased generics check element types on typed reads.

```titan
local iteration = import "iteration"
local math = import "math"

local function count_const(xs: const? { string }): integer
  local n = 0
  for i = 1, #xs do
    local x? = xs[i]
    if x ~= nil then n = n + 1 end
  end
  return n
end

function main(args: {string}): integer
  local p? = math.tonumber(" 42 ")
  math.randomseed(7)
  local die = math.random(6) as integer
  if p == nil or (p as integer) ~= 42 or math.tointeger("3.0") ~= 3
     or die < 1 or die > 6 or not math.ult(0, -1) then raise "math" end
  local slots: {string} = { "a", "b", "c" }
  slots[2] = nil
  local holes = 0
  for _, x? in iteration.ipairs(slots) do if x == nil then holes = holes + 1 end end
  local flags: {boolean: integer} = { [false] = 10, [true] = 5 }
  local sum = 0
  for _, v in iteration.pairs(flags) do sum = sum + v end
  if holes ~= 1 or count_const(slots) ~= 2 or sum ~= 15 or iteration.next(flags, nil) == nil then raise "iter" end
  return 0
end
```

## `fs` & `os` — Async files, watchers, processes & browser subset

- **`fs` files & `async.OperationError` (Native):** Sync: `tmpdir`, `homedir`, `pwd`, `chdir`, transfer hooks. Errors raise `async.OperationError` (`code: integer`, `name: string`, `message: string`, `operation: string`—**cannot concatenate with `..`**; format via `err.message` or `err.operation .. ": " .. err.message`), except `stat`/`lstat` (`nil` on `ENOENT`; dangling symlink: `stat`->`nil`, `lstat`->`"symlink"`) and `WatcherEvent.error`. `open(p, mode)`: `r`/`w`/`a`/`r+`/`w+`/`a+` (+`b`, binary, `0666`&~umask, no NUL). `read(max?)` (64 KiB default, drains `read_until` excess, EOF non-sticky); `write` loops short writes; `flush`=`fsync`; `close` idempotent; `read_file` ignores `stat.size`.
- **`fs` metadata & transfer:** `Stat.(device,inode)` opaque signed-int pair; `list` omits `.`/`..`; `tmpname()` creates+closes empty file (caller `unlink`s); `chdir` process-wide (`defer` restore). State close sync-closes idle `File`s. `File:to/from_transfer_payload` move idle fds sync (no `discard_transfer_payload`—adopt & close; `titan-thread`).
- **`fs.Watcher`:** Bound to Runtime (raises after stop). `watch(p)` canonicalizes via `realpath` (idempotent; dirs watch immediate children; macOS FSEvents async). Single `poll()` waiter (`{}` unwatched; cancel detaches; after `stop`/`clear` removes last watch, let awakened `poll()` return first). `union WatcherEvent`: `created(value: string)`, `deleted(value: string)`, `modified(value: string)`, **`error(value: async.OperationError)`** (part `value`, NOT `message`; format `when error(err)` via `err.message`, never `".." .. err`); paths are canonical absolute; OS may coalesce/duplicate/omit.
- **`os` time/env/host:** Sync: `clock` (CPU, native), `difftime`, `date`, `time`, `setlocale`, `getenv`/`setenv`/`unsetenv` (`""` vs `nil`, no NUL), native `cwd`/`chdir`/`homedir`/`tmpdir`/`hostname`/`exepath` (compiled Titan only)/`pid`/`ppid` (process-global C state, not thread-safe). `date(fmt?, ts?)`->`value` (`"*t"`/`"!*t"`->`os.Date` `wday` 1..7, `yday` 1+, `isdst: boolean?`; else `string`; `"!"`=UTC). `time { year, month, day, ... }` needs all 3 if any arg given (`hour`=12).
- **`os` signals & exit:** `wait_signal` (native, one-shot): `"hup"|"int"|"quit"|"term"|"usr1"|"usr2"` (Windows omits `usr1`/`usr2`; `"kill"` rejected). `os.exit(code?)` starts graceful Runtime shutdown (first code wins, runs `defer`s, sticky cancel on caller; browser raises outside Task).
- **`os` processes (native):** `spawn(file, args, ...opts)` captures all 3 pipes; opts L->R (`with_stdin`/`stdout`/`stderr`, `with_parent_*`->`nil`, `with_merged_output` shares one `InputStream`, `with_env(k,v)`). `wait()` single-waiter, caches `ExitStatus`; cancel won't kill child; `kill(sig)` takes `"kill"`, raises if exited (`is_running()`). `popen(cmd)` runs `/bin/sh -c`/`cmd.exe /d /s /c` (`InputOutputStream`, all 7 `io` Interfaces); `close()` closes stdin, sends `"term"` to shell, waits, closes output.
- **`os` stdio & transfer:** `os.stdin`/`stdout`/`stderr` are mutable lazy per-Runtime vars (no-op `close()`); backings `"tty"`, `"pipe"` (`TITAN_STDIO_PIPE_FDS=0,1,2`), `"file"`, Unix connected `"tcp"` (`OutputStream:shutdown()`=`SHUT_WR`, `ENOTSUP` elsewhere—close `proc.stdin` for child EOF). `InputStream`/`OutputStream` have `to/from/discard_transfer_payload`; `InputOutputStream` omits `discard_transfer_payload`, dest `wait()` raises, Windows live shell pipes fail (`EBUSY`).
- **Browser `os` subset:** Present: `Date`, `date`, `time`, `difftime`, `setlocale` (C/UTF-8 musl; JS host TZ, `TZ` ignored), instance `getenv`/`setenv`/`unsetenv` (`create({ env })`), Task-only `exit`, embedding `stdin`/`stdout`/`stderr` (missing `stdin`/undeclared `kind`->`OperationError` `ENOSYS`; undeclared `is_tty()`=`false`; `shutdown()` only for `"tcp"`). Absent: `clock`, `cwd`..`ppid`, `spawn`, `popen`, `with_*`, `wait_signal`, `ExitStatus`, `SpawnConfig`, `SpawnOption`, `Process`, `InputOutputStream`.

```titan
local async = import "async"
local fs = import "fs"
local os = import "os"
local strings = import "string"

local function drain(s: os.InputStream): string
  local out = strings.writer()
  defer out:close()
  for chunk in s:read do out:write(chunk) end
  return out:drain()
end

function run_command(prog: string, args: {string}): (integer, string, string)
  local p = os.spawn(prog, args, os.with_parent_stdin, os.with_env("LC_ALL", "C"))
  local so, se = p.stdout, p.stderr
  defer so:close()
  defer se:close()
  local o, e = async.all_two(
    async.run(function (): string return drain(so) end),
    async.run(function (): string return drain(se) end))
  return p:wait().code, o, e
end

function main(args: {string}): integer
  local tmp = fs.tmpname()
  defer fs.unlink(tmp)
  local f = fs.open(tmp, "w")
  defer f:close()
  f:write("hello\n")
  f:flush()
  f:close()
  local info? = fs.stat(tmp)
  local ev = os.date("!*t", 0)
  if info == nil or info.kind ~= "file" or info.size ~= 6 or not (ev is os.Date) then raise "fs" end
  local ep: os.Date = ev
  local t1 = os.time { year = 2026, month = 7, day = 31 }
  local t2 = os.time { year = 2026, month = 7, day = 31, hour = 13 }
  if ep.year ~= 1970 or os.difftime(t2, t1) ~= 3600.0 then raise "cal" end
  return 0
end
```

## `gc` — Weak Maps, finalizers & collector control

- **Weak Maps:** `gc.weak(m)` (`__mode="v"`) & `gc.ephemeron(m)` (`__mode="k"`) take `{value: value}`, mutate raw `__mode` in place (shared metatable peers see it), collecting collectable objects only (numbers/strings never weak keys).
- **Finalizers (`gc.finalizable<|T|>(v, f)`):** Table/full userdata only (record, union, Interface, Array, owned foreign); `nil`/scalars/functions/threads/light userdata raise. Reinstalling metatable marks `v` and replaces raw `__gc` for marked peers. In finalizers & abandoned-coroutine `defer`, `gc.*` raises `garbage collector operation is unavailable`, `coroutine.is_yieldable()`=`false`, state close ignores new `finalizable`. Non-`function(value)` callbacks wrap per call.
- **Collector control:** `pause()` (`defer gc.resume()`), `resume()`, `paused()`, `collect()`, `step(size?)` (>=0, default `0`), `incremental()`/`generational()` (true if already in mode), `count()` (live bytes `integer`). Tuning (`0..100000`, omit to query, returns prior compressed value): `minormul`, `majorminor`, `minormajor`, `pause_percent`, `stepmul`, `stepsize`.

```titan
local gc = import "gc"
local released = 0

record ExternalSlot -- placeholder for OS/C handle
  local const id: integer
  local closed: boolean
end

function ExternalSlot:close()
  if self.closed then return end
  self.closed = true
  released = released + 1
end

local function finalize_slot(raw: value)
  local slot: ExternalSlot = raw
  slot:close()
end

function open_slot(id: integer): ExternalSlot
  local slot = ExternalSlot(id, false)
  gc.finalizable<|value|>(slot, finalize_slot)
  return slot
end

local function alloc_temp(c: {string: ExternalSlot}) c["tmp"] = open_slot(2) end

function main(args: {string}): integer
  local c: {string: ExternalSlot} = {}
  gc.weak(c)
  local kept = open_slot(1)
  defer kept:close()
  c["kept"] = kept
  alloc_temp(c)
  gc.collect()
  gc.collect()
  if c["tmp"] ~= nil or c["kept"] == nil or released ~= 1 then raise "gc" end
  kept:close()
  if released ~= 2 then raise "close" end
  return 0
end
```

## Pre-delivery verification checklist

- [ ] Short imports (`local strings = import "string"`); multi-piece strings use `strings.writer()` (never `string.Writer`/`StringWriter.new()`).
- [ ] `iteration.ipairs` binds `v?` on holed Arrays; `const`/`const?` Arrays use numeric `for`.
- [ ] `fs.File`, `fs.Watcher`, `os.Process` pipes, `InputOutputStream` use `defer` close (never `gc.finalizable`/double-closed with `io.lines`), draining pipes concurrently; format `OperationError` via `err.message`.
- [ ] `gc.finalizable` wraps external handles only (sync, non-yielding, non-capturing, idempotent; `finalizable<|value|>` on hot types).
- [ ] Browser omits `fs`/native `os`, avoids 8B `string.pack` `l`/`L`/`T`, handles `stdin`/`kind` `ENOSYS`.
