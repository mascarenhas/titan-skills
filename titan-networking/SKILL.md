---
name: titan-networking
description: Use when writing Titan URL, TCP, TLS, or HTTP clients and servers (url, net, ssl, http, browser fetch). Covers DNS, sockets, HTTPS/TLS certificates, HTTP/1.1 framing, RequestOptions, redirects, pools, Exchange handoff, and deadlines; use titan-websocket for WebSocket framing/upgrades, titan-async for Tasks/timers/uv, titan-stdlib for fs/io/os.
---

# Titan networking

Covers `url`, `net`, `ssl`, and `http` (native HTTP/1.1 client/server and browser `fetch` client). Pair with `skill://titan-programmer` (syntax/`T?`/`defer`/`raise`), `skill://titan-websocket` (WS/WSS framing & upgrades), `skill://titan-async` (Tasks/timers/cancellation/libuv), `skill://titan-stdlib` (`io`/`string.writer()`/`fs`), `skill://titan-thread` (cross-state `transfer`), and `skill://titan-tester` (tests).

## Non-negotiable invariants

1. **Direct-style async Tasks & target split:** Import `"url"`, `"net"`, `"ssl"`, `"http"` (Lua: `require "titan.<m>"`). Network calls suspend only the current `async.Task` (Go-style direct async over libuv/Fetch—not LuaSocket or promises); `main` auto-bootstraps, Lua needs `async.run`+`async.loop`. On `--target browser`, **only `url` (full) and `http` client (subset)** exist; `net` and `ssl` fail at compile time.
2. **Nonthrowing `url.parse` vs throwing `http`:** `url.parse`/`url.parse_request` synchronously return mutually exclusive `(Url?, Error?)` (bind `local u?, err? = ...`; never split URLs with strings). Rejects userinfo (`user@`) and `#fragment`; keeps `ws`/`wss`; `Url.host` is unbracketed for dialing/TLS while `Url.authority`/`Url:host_header()` keeps brackets and explicit ports. `http` raises `url.Error` pre-dial.
3. **`net` ownership, `TCP_NODELAY`, & deadlines:** Immediately `defer conn:close()` / `defer server:close()`. `Connection` satisfies all 7 `io` Interfaces; `Server` satisfies `io.Closer`. Dialed/accepted sockets default to `TCP_NODELAY = true` (`set_no_delay(enabled)` toggles); `listen(host, 0)` + `Server:local_address()` gets ephemeral OS ports. `net` has no built-in timeouts—race with `timer.sleep`, cancel and join losers, and abort blocked TLS/accepted ops before draining.
4. **`ssl` TLS 1.2+ strict limits:** Always TLS 1.2+ with strict chain + DNS/IP verification. **Absent by design:** insecure mode, CA-directory param, OS-native trust store, encrypted keys/passwords, ALPN, mTLS, cipher/session/key-log controls, raw `net.Connection` getter. Explicit `ca_file` **replaces** defaults (required on Windows, which ships no CA bundle). `ssl.Server:accept()` is TCP-only (lazy handshake—spawn a Task per client). One reader + one writer concurrently; cancellation terminalizes the engine; bare TCP EOF/RST without `close_notify` raises `ssl.Error` `TLS_TRUNCATED_EOF`.
5. **`http` client (`RequestOptions`, browser `fetch` vs native pools/redirects):** `RequestOptions` is an immutable copied snapshot; mode unions (`CacheMode`, `CredentialsMode`, `RequestMode`, `RedirectMode`) compare by identity—inspect with **`case`**, never `==`. `redirect` defaults to **`manual()` natively** and **`follow()` on browser**. `http.get` rejects any `body` (even `""`). Always `defer response:close()`; stream via `for chunk in response:read do` + `strings.writer()` (no `.body` field). Browser rejects `ca_file`, custom `Host`, and Fetch forbidden headers pre-network and decodes `Content-Encoding` automatically.
6. **HTTP/1.1 server (`Server`, `Request`, `Response`, `Exchange`):** Serial keep-alive per connection Task; no built-in Router or HTTP/2. Watch arg order: `http.listen(host, handler, port?, ...)` puts `handler` 2nd (`net`/`ssl.listen` put `port` 2nd). `Server:idle_timeout(ms)` is an **absolute** per-request header-acquisition deadline only (no partial-header reset; excludes handler/body/write; HTTPS expiry yields `TLS_TRUNCATED_EOF` at peer). Cross-state handoff bundles `http.Exchange(request, response)` (`server:read_ahead(false)` + `async.yield()` on Windows).
7. **Conditional reference read:** **MUST read `skill://titan-networking/references/http-and-tls-details.md`** before implementing: HTTP redirect chains/pools/abandoned-body drains, browser `fetch` forbidden headers/cache/CORS/opaque responses, HTTP `Response` framing/coalescing/`100-continue`/`upgrade`, `ssl.client` adoption/deadlines/state-close/static OpenSSL linking, or cross-state `net`/`ssl`/`http.Exchange`/`UpgradedStream` handoff.

## Module, target & error matrix

| Module | Targets | Primary surface |
| --- | --- | --- |
| `url` | Native & Browser | `parse`, `parse_request`, `Url` (`scheme`/`host`/`port`/`path`/`query`/`target`/`authority`, `:host_header()`), `Error` (`position`/`kind`/`message`) |
| `net` | Native only | `resolve`, `connect`, `Connection()`+`connect_address`, `listen`, `Address`, `local_address`/`peer_address`, `read`/`read_until`/`write`/`set_no_delay`/`shutdown`/`close` |
| `ssl` | Native only | `connect`, `client`, `listen`, `accept`, `handshake`, `local_address`/`peer_address`, `read`/`read_until`/`write`/`set_no_delay`/`shutdown`/`abort`/`close`, `Error` |
| `http` client | Native & Browser | `headers`/`Headers`, `RequestOptions` + 4 mode unions, `Client`/`get`/`request`, `ClientResponse` (`status`/`reason`/`headers`/`url`/`redirected`, `io.ReaderCloser`) |
| `http` server | Native only | `listen`/`listen_tls`, `Handler`, `Request`/`Response`, `request_upgrade_on`/`take_upgrade`, `Exchange`, `UpgradedStream` |
| `websocket`/`uv` | See peers | WS/WSS framing & upgrades → `skill://titan-websocket`; UDP/pipes/raw sockets → `skill://titan-async` |

| Boundary | Normal EOF / absence | Raised failure (branch on exact type & stable field) |
| --- | --- | --- |
| `url.parse` / `parse_request` | `(nil, url.Error)` | Never raises on malformed URL (`Error.kind`, 1-based byte `position`) |
| `net` | `read*` → `nil` | `async.OperationError` (`name` e.g. `EADDRINUSE`/`EAI_*`, `operation`); arg/state `string` |
| `ssl` | Authenticated `close_notify` → `nil` | `ssl.Error` (`name`: `CERTIFICATE_VERIFY_FAILED`, `TLS_TRUNCATED_EOF`, `TLS_INTERRUPTED`, `SSL_ERROR_*`); wrapped `net`/`fs` keep `OperationError` |
| `http` (native) | Body `read*` → `nil` | Bad URL/Host → `url.Error`; policy (`only_if_cached`, redirect error/loop) → `OperationError("EIO", "http.request")`; net/TLS keep types; framing/arg → `string` (no `http.Error`) |
| `http` (browser) | Body `read*` → `nil` | Bad URL/Host → `url.Error`; forbidden header/`ca_file`/arg → `string`; all host/TLS/CORS/policy failures → `OperationError("EIO", "http.request" \| "http.read")` |

## URLs (`url`)

- **Normalization:** Lowercases `scheme`, registered `host`, IPv6 hex, and IPvFuture version; supplies default `port` (`80` `http`/`ws`, `443` `https`/`wss`); maps empty `path` to `"/"`; distinguishes absent `query` (`nil`) from empty `""`; builds `target` = `path` + optional `"?" .. query`; decodes unreserved `%XX` (`%5f` → `_`) and uppercases retained escapes (`%2F`). IPv6 `%25zone` decodes to `%zone` in `host` while staying `%25zone` in `authority`. No IDNA/DNS/redirects.
- **`parse_request(scheme, authority, target)`:** Validates separate server parts (rejects `/`, `?`, `#` in `authority` with `authority_tail`, requires origin-form `/` `target` else `origin_form`, indexes `Error.position` into `scheme .. "://" .. authority .. target`). Connect with `Url.host`/`Url.port`; send `Url.target` and `Url:host_header()`.

## TCP & DNS (`net`)

- **Dialing & listening:** `resolve(host, port)` returns owned IPv4/IPv6 `{uv.sockaddr_t}` (`port` `1..65535`; cancel still awaits callback). `connect(host, port)` tries candidates in resolver order. `Connection()` + `connect_address(addr)` exposes a pre-dial abortable handle (`set_no_delay`, `close`, `has_pending_input` valid pre-dial; `set_no_delay` rejected while connecting). `listen(host, port, backlog?, reuse_port?)` accepts `port = 0` (ephemeral), `backlog` default `128`, `reuse_port` Linux-only (`ENOTSUP` on macOS/Windows).
- **Addresses:** `Server:local_address()`, `Connection:local_address()`, `Connection:peer_address()` return cached immutable `net.Address { const ip, const port, const ipv6, const scope_id }` snapshots (readable after close; require live endpoint + active Task on owning Runtime; reset peer may raise `OperationError` `"net.peer_address"`).
- **Streams:** Lazy read watcher starts on first `read`/`read_until`. Single reader at a time (cancelling waiter leaves `Connection` usable). `read_until(delim, chop?)` requires nonempty `delim`, matches across chunks, keeps excess, returns `""` for empty chopped match (distinct from `nil` EOF) and unterminated tail once before sticky `nil`. `read_ahead(false)` (only before first read) stops watcher per callback for transfer; `has_pending_input()` is a pure snapshot; `add_input_listener(fn)` runs non-yielding outside Tasks. Overlapping `write(data)` calls stay ordered and retain strings across cancellation. `shutdown()` half-closes writes; `close()` wakes waiting reader with `nil`.

```titan
local async = import "async"
local net = import "net"

local function serve_one(server: net.Server): nil
  local peer = server:accept()
  defer peer:close()
  local line? = peer:read_until("\n", true)
  if line ~= nil then peer:write("echo:" .. line .. "\n") end
  peer:shutdown()
  return nil
end

function main(args: {string}): integer
  local server = net.listen("127.0.0.1", 0)
  defer server:close()
  local port = server:local_address().port
  local worker = async.run(function (): nil return serve_one(server) end)
  defer do
    if not worker:status():has_finished() then worker:cancel() end
    async.join(worker)
  end
  local conn = net.connect("127.0.0.1", port)
  defer conn:close()
  conn:write("ping\n")
  conn:shutdown()
  local reply? = conn:read_until("\n", true)
  if reply ~= "echo:ping" then raise "unexpected reply" end
  async.join(worker)
  return 0
end
```

## Verified TLS (`ssl`)

- **Clients & trust:** `ssl.connect(host, port, ca_file?)` dials TCP (`TCP_NODELAY = true`) and finishes verified TLS 1.2+. `ssl.client(transport, host, ca_file?)` adopts a connected `net.Connection` lazily (keeps `TCP_NODELAY`, preserves SNI/cert `host` separately from numeric TCP IP; strips IPv6 `%zone` only for X.509 IP match). Explicit `ca_file` reads PEM via async `fs` and replaces defaults; omitted `ca_file` shares one OpenSSL context from compiled defaults + `SSL_CERT_FILE`/`SSL_CERT_DIR`.
- **Servers & duplex:** `ssl.listen(host, port, cert_file, key_file?, backlog?, reuse_port?)` loads leaf-first PEM chain + unencrypted key (omitted `key_file` reads `cert_file`). `Server:accept()` accepts TCP only—spawn a Task per client and drive `handshake()`/I/O there. `local_address()`/`peer_address()`/`set_no_delay()` delegate to `net` without touching the TLS engine.
- **Shutdown vs abort:** One reader + one writer run concurrently (duplicate same-direction raises safely); `handshake()`/`shutdown()`/`close()` are exclusive. `shutdown()` sends `close_notify` + TCP write half-close; `close()` best-effort shuts down and closes TCP; `abort()` immediately closes TCP without `close_notify` and interrupts siblings with `ssl.Error` `TLS_INTERRUPTED` (safe during active I/O/cancellation). See `skill://titan-networking/references/http-and-tls-details.md` for deadlines, state close, static OpenSSL linking, and transfer.

```titan
local async = import "async"
local ssl = import "ssl"

function fetch_head(host: string, port: integer, ca_file: string?): string?
  local conn = ssl.connect(host, port, ca_file)
  defer conn:close()
  conn:write("HEAD / HTTP/1.1\r\nHost: " .. host .. "\r\nConnection: close\r\n\r\n")
  return conn:read_until("\r\n\r\n", false)
catch
  if error is ssl.Error then
    local err: ssl.Error = error
    if err.name == "TLS_TRUNCATED_EOF" then return nil end
  end
  raise
end

function accept_tls(server: ssl.Server, on_conn: function (ssl.Connection): ())
  while true do
    local conn = server:accept()
    async.run(function (): nil
      defer conn:close()
      conn:handshake()
      on_conn(conn)
      return nil
    end)
  end
end
```

## HTTP/1.1 client, server & browser `fetch` (`http`)

- **Headers & options:** `http.headers(initial?)` is an insertion-ordered, ASCII case-folded list (`add`/`set`/`get`/`values`/`remove`/`all`; rejects CR/LF/NUL/controls). Build reusable `http.RequestOptions { headers, body, ca_file, cache, credentials, mode, redirect }`. `CacheMode.only_if_cached()` requires explicit `RequestMode.same_origin()`. Inspect mode unions with `case`, never `==`.
- **Client:** `http.get`/`http.request` share a per-Runtime default pool; `http.Client()` isolates its pool (`defer client:close()`). `ClientResponse` exposes `status`, `reason`, `headers`, `url` (`string?`), `redirected` and streams via `read()`/`read_until()` (`defer response:close()`). Request `Transfer-Encoding`/`Expect` and `ws`/`wss` URLs are rejected (`skill://titan-websocket`).
- **Server:** `http.listen(host, handler, port?, backlog?, idle_timeout?, reuse_port?)` (default `80`) and `http.listen_tls(host, cert, handler, key?, port?, backlog?, idle_timeout?, reuse_port?)` (default `443`). `Handler = function (Request, Response): ()`. `Request` has `method`, raw `target`, normalized `url`, `version`, `headers`, `read`/`read_until`, `local_address()`/`peer_address()`. `Response` starts at `200 OK`; mutate status/headers before commitment (`is_committed()`, `send_headers()`, `write()`, `close()`, `abort()`). `Server:header_limit` defaults to **64 KiB**; `Server:idle_timeout` defaults to `0` (header acquisition only); `Server:close()` stops accepts without cancelling active handlers.
- **Browser & deep-dive:** `--target browser` provides `url` + `http` client over `fetch` (`follow()` default; no `ca_file`, custom `Host`, forbidden headers, servers, upgrades, or handoff). Read `skill://titan-networking/references/http-and-tls-details.md` for redirects, pools/drains, full browser quirks, server framing/upgrades, and `Exchange`/`UpgradedStream` handoff.

```titan
local async = import "async"
local http = import "http"
local strings = import "string"
local url = import "url"

local function read_all(res: http.ClientResponse): string
  local out = strings.writer()
  for chunk in res:read do out:write(chunk) end
  return out:drain()
end

local function handle(req: http.Request, res: http.Response)
  local body = strings.writer()
  for chunk in req:read do body:write(chunk) end
  local payload = req.method .. " " .. req.url.path .. ":" .. body:drain()
  res:set_status(200)
  res:set_header("Content-Type", "text/plain")
  res:set_header("Content-Length", "" .. #payload)
  res:set_header("Connection", "close")
  if req.method ~= "HEAD" then res:write(payload) end
end

function main(args: {string}): integer
  local server = http.listen("127.0.0.1", handle, 0)
  defer server:close()
  local port = server:local_address().port
  local serving = async.run(function (): nil server:serve(); return nil end)
  defer do
    server:close()
    if not serving:status():has_finished() then serving:cancel() end
    async.join(serving)
  end

  local parsed?, err? = url.parse("http://127.0.0.1:" .. port .. "/items?v=1")
  if err then raise err.message end
  local target = parsed.scheme .. "://" .. parsed:host_header() .. parsed.target

  local client = http.Client()
  defer client:close()
  local h = http.headers()
  h:set("Content-Type", "text/plain")
  local res = client:request("POST", target, http.RequestOptions {
    headers = h, body = "ok", redirect = http.RedirectMode.manual(),
  })
  defer res:close()
  if res.status ~= 200 or read_all(res) ~= "POST /items:ok" then raise "mismatch" end
  return 0
end
```

```titan
-- Cross-target (native & --target browser) HTTP client helper
local async = import "async"
local http = import "http"
local strings = import "string"

function redirect_name(mode: http.RedirectMode): string
  case mode
  when follow() then return "follow"
  when error() then return "error"
  when manual() then return "manual"
  end
end

function fetch_api(endpoint: string): (integer, string)
  local h = http.headers()
  h:set("Accept", "application/json")
  local res = http.get(endpoint, http.RequestOptions {
    headers = h,
    cache = http.CacheMode.no_store(),
    credentials = http.CredentialsMode.same_origin(),
    redirect = http.RedirectMode.follow(),
  })
  defer res:close()
  local out = strings.writer()
  for chunk in res:read do out:write(chunk) end
  return res.status, out:drain()
catch
  if error is async.OperationError then
    local op_err: async.OperationError = error
    if op_err.name == "EIO" and op_err.operation == "http.request" then
      return 0, op_err.message
    end
  end
  raise
end
```

## Pre-delivery verification checklist

- [ ] Every `net`/`ssl`/`http` `Connection`, `Server`, `Client`, `ClientResponse`, and `Exchange` has immediate `defer :close()`; spawned Tasks are cancelled and joined on teardown.
- [ ] `url.parse`/`parse_request` binds `(u?, err?)`; `Url.host` dials/verifies TLS while `Url:host_header()` sets `Host`.
- [ ] `ssl` never assumes OS trust stores, CA dirs, encrypted keys, or insecure bypasses; `ssl.Server:accept()` moves handshakes to per-client Tasks; blocked TLS cancellation uses `abort()`.
- [ ] `http` inspects mode unions via `case` (never `==`), handles `manual()` native vs `follow()` browser redirect defaults, and never passes `body` to `http.get`.
- [ ] Browser builds omit `net`/`ssl`/servers/`ca_file`/custom `Host`/Fetch forbidden headers and do not re-decompress `Content-Encoding` or bound reads by `Content-Length`.
