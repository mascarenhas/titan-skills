---
name: titan-websocket
description: Use when writing Titan WebSocket clients or HTTP/TLS upgrade handlers (websocket, ws/wss, RFC 6455 framing). Covers DialOptions/AcceptOptions, Origin/subprotocol policy, reader duty, Ping/Pong/Close, browser WebSocket, and session handoff; use titan-networking for ordinary URL/TCP/TLS/HTTP, titan-async for Tasks/timers, titan-stdlib for fs/io.
---

# Titan WebSocket

Message-oriented RFC 6455 (v13) over HTTP/1.1 (`local websocket = import "websocket"`; Lua `require "titan.websocket"`). Native provides `ws`/`wss` clients and HTTP/TLS upgrades; `--target browser` provides the host-`WebSocket` client. Pair with `skill://titan-programmer`, `skill://titan-networking`, `skill://titan-async`, `skill://titan-thread`, and `skill://titan-tester`.

## Non-negotiable invariants

1. **Immediate `defer conn:close()` & upgrade handoff:** Always `defer conn:close()` after `connect`/`accept` (even with `shutdown()`). Auth/route in `http.Handler` before `websocket.accept(req, res, opts?)` (works under `http.listen` and `http.listen_tls`). Closing `http.Server` never closes sessions; `Connection:close()` needs a Task (warns during abandoned Lua-state unwind).
2. **Reader duty (`ping` requires a concurrent `read()`):** No background reader Task or decoded-message queue exists. `conn:read()` services incoming Ping (auto-Pong), Pong, and Close. **`conn:ping()` times out unless another Task calls `read()`**; write-only clients must run a reader Task.
3. **Duplex, 16 KiB framing & shutdown takeover:** One reader + one writer run concurrently on `ws`/`wss` (duplicate same-kind ops raise). Outgoing data fragments at **16 KiB** with control priority (Close > Pong > Ping > data; data never interleaves); text checks UTF-8 both ways. `shutdown(code?, reason?, timeout_ms?)` stops writes, lets an active `read()` finish one message/Close, then takes receive ownership (new `read()` raises `state`).
4. **Clean EOF vs loss:** `local kind?, data? = conn:read()` returns `(nil, nil)` **only** after valid peer Close + reciprocal reply (`""` valid; binary keeps NULs). Transport loss raises `Error("abnormal", ...)` with `close_status() == (nil, nil)`—never synthesize `1006`.
5. **Browser subset (`--target browser`):** `accept`, `AcceptOptions`, `ping`, and transfer hooks are absent at compile time. `connect` rejects non-empty `headers` or any `ca_file`, fails if offered `subprotocols` go unselected (native allows `nil`), maps pre-open failures to `HandshakeError(msg, nil, nil)`, and permits only `1000` and `3000..4999` in `shutdown`.
6. **Fairness & memory caveats:** Native buffered work yields every **64 KiB** or **32** control/empty frames and between **16 KiB** outgoing fragments—**no generic starvation bound**. `read_limit` (default **1 MiB**) caps decoded bytes, not `net` receive buffers or browser unread queues.

## Native vs. browser behavior & error table

| Failure / behavior | Native targets | `--target browser` |
| --- | --- | --- |
| Malformed URL | `url.Error` | `url.Error` |
| Non-`ws`/`wss`, bad opts, no Runtime, browser `headers`/`ca_file` | `string` | `string` (`lua.new()` → `"async Runtime is not active"`) |
| Opening timeout (default 10 s) | `Error("timeout", "websocket.open", ...)` | Same |
| HTTP reject, bad response, unoffered subprotocol | `HandshakeError(msg, status?, headers?)` | `HandshakeError(msg, nil, nil)` |
| Subprotocols offered, none selected | Succeeds (`subprotocol() == nil`) | Fails: `HandshakeError(msg, nil, nil)` |
| Pre-open DNS / TCP / TLS failure | `async.OperationError` or `ssl.Error` | `HandshakeError(msg, nil, nil)` |
| Outgoing invalid UTF-8 (`write`/`shutdown`) | `Error("utf8", op, ..., nil)` | Same |
| Closed/dup op/bad code/reason > 123 B | `Error("state", ...)` (`1000..1003`, `1007..1014`, `3000..4999`; no server `1010`) | Same, but `shutdown` allows **only** `1000`, `3000..4999` |
| Incoming message > `read_limit` (1 MiB) | `Error("limit", "websocket.read", ..., 1009)` | Same (decompressed length, pre-copy) |
| Post-open loss or peer violation | `Error("abnormal" \| "protocol" \| "utf8", ...)` | `Error("abnormal", op, "transport ended before WebSocket Close", nil)` |
| `ping`/`shutdown` timeout (5 s) / cancel | `Error("timeout", ...)` / `CancellationReason` | `shutdown` timeout / `CancellationReason` |

## Opening policy, framing & loopback example

- **Options (copied snapshots):** `DialOptions { headers, ca_file, subprotocols, read_limit, handshake_timeout }` and native `AcceptOptions { subprotocols, allowed_origins, read_limit, handshake_timeout }` (defaults: 1 MiB, 10 s open, 5 s controls).
- **Origin, subprotocols & rejections:** Absent `Origin` passes for native clients; browser `Origin` must match normalized scheme/host/port or an exact `allowed_origins` entry (no wildcards; rejects `"null"`/multiple/malformed). Subprotocols match **case-sensitively** (server order first). Reserved headers (`Host`, `Connection`, `Upgrade`, `Content-Length`, `Transfer-Encoding`, `Expect`, `Sec-WebSocket-*`) cannot be overridden. Inside `accept`: malformed `400`, origin `403`, version `426` → `HandshakeError`; pre-handler HTTP errors (`Expect`, bad `Host`/URL, non-1.1) send `400` pre-dispatch.
- **TLS, cancellation & kinds:** `connect` verifies original URL hostname (`ca_file` replaces defaults; no insecure mode, redirects, proxies, or native extensions/compression; masks use `uv.random`). Pre-admission cancel detaches reservations; admitted ops (incl. idle `read()`) terminalize. Timeouts are catchable without cancelling caller; first terminal error latches as `async.Error`. `MessageType` exports singletons `TEXT`/`BINARY`—use `case` (never `== MessageType.text()`).

```titan
local async = import "async"
local http = import "http"
local websocket = import "websocket"

local function handle(req: http.Request, res: http.Response)
  if req.url.path ~= "/ws" then res:set_status(404); return end
  local conn = websocket.accept(req, res, websocket.AcceptOptions { subprotocols = {"echo.v1"} })
  defer conn:close()
  while true do
    local kind?, msg? = conn:read()
    if kind == nil then break end
    conn:write(kind, msg)
  end
end

function main(args: {string}): integer
  local server = http.listen("127.0.0.1", handle, 0)
  defer server:close()
  local serving = async.run(function (): nil server:serve(); return nil end)
  defer do
    server:close()
    if not serving:status():has_finished() then serving:cancel() end
    async.join(serving)
  end

  local conn = websocket.connect("ws://127.0.0.1:" .. server:local_address().port .. "/ws",
    websocket.DialOptions { subprotocols = {"echo.v1"}, read_limit = 65536 })
  defer conn:close()
  if conn:subprotocol() ~= "echo.v1" then raise "subprotocol" end

  local replies: {string} = {}
  local reader = async.run(function (): nil
    for _ = 1, 2 do
      local kind?, data? = conn:read()
      if kind == nil then break end
      case kind
      when text() then replies[#replies + 1] = data
      when binary() then replies[#replies + 1] = "bin:" .. #data
      end
    end
    return nil
  end)
  defer do
    if not reader:status():has_finished() then reader:cancel() end
    async.join(reader)
  end

  conn:ping(2000) -- reader Task services Pong
  conn:write(websocket.TEXT, "hello")
  conn:write(websocket.BINARY, "a\0b")
  async.join(reader) -- drain replies before shutdown takes receive ownership
  conn:shutdown(1000, "done", 2000)
  local code?, _ = conn:close_status()
  if code ~= 1000 or replies[1] ~= "hello" or replies[2] ~= "bin:3" then raise "echo" end
  return 0
end
```

## Browser client & cross-state transfer

- **Browser specifics:** Host owns TCP/TLS, trust, cookies, `Origin`, fragmentation, Pong, and `permessage-deflate`. `write` checks UTF-8, yields once, pauses > 256 KiB until <= 64 KiB (return = host-queued; Node/WebKit loss can lag drainage). `close()` retires sync (host queues empty Close); Firefox/Node may hold cancelled/rejected opening sockets until peer/browser closes. Valid Close + reset still yields `(nil, nil)` and `close_status()` (never `1005`/`1006`/`1015`). Sessions close with Runtime.
- **Native transfer:** Set `server:read_ahead(false)` pre-`serve()`, require idle open session (no active ops/partial message), and `async.yield()` post-I/O on Windows. `to_transfer_payload()` detaches without Close; `from_transfer_payload()` adopts once; `discard_transfer_payload()` frees unadopted bytes without Runtime (`skill://titan-thread`). Closed native endpoints reclaim over multiple GC cycles (`Coroutine` finalizers).

```titan
-- Cross-target (native & --target browser) WebSocket client helper
local websocket = import "websocket"

function send_and_receive(endpoint: string, payload: string): string?
  local conn = websocket.connect(endpoint, websocket.DialOptions {
    subprotocols = {"chat.v1"}, read_limit = 65536, handshake_timeout = 5000,
  })
  defer conn:close()
  conn:write(websocket.TEXT, payload)
  local kind?, reply? = conn:read()
  if kind == nil then return nil end
  conn:shutdown(1000, "bye")
  case kind
  when text() then return reply
  when binary() then return nil
  end
end
```

## Pre-delivery verification checklist

- [ ] `defer conn:close()` follows `connect`/`accept`; auth in `http.Handler` before `accept` (closing `Server` never closes sessions).
- [ ] Every `conn:ping()` runs with a concurrent `conn:read()` Task; finish/coordinate reads before `shutdown()`.
- [ ] `local kind?, data? = conn:read()` preserves options and separates `(nil, nil)` Close EOF from `Error("abnormal", ...)`.
- [ ] Browser clients omit `accept`/`AcceptOptions`/`ping`/transfer/`headers`/`ca_file`, handle unselected-subprotocol `HandshakeError`, and use `1000`/`3000..4999` in `shutdown`.
- [ ] Transfer sets `server:read_ahead(false)` + `async.yield()` (Windows) and recovers via `Connection.discard_transfer_payload`.
