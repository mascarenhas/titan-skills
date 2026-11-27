# HTTP & TLS Deep-Dive: Redirects, Pools, Browser Fetch, Framing & Handoff

Read alongside `skill://titan-networking` for HTTP redirects/pools/drains, browser `fetch` edge cases, HTTP server framing/upgrades, TLS deadlines/state-close/static linking, or cross-state handoff.

## 1. Native HTTP Redirects, Pools & Abandoned-Body Drains

- **Redirects (`301`, `302`, `303`, `307`, `308`):**
  - `manual()` *(native default)* returns 3xx as-is; `error()` closes response and raises `async.OperationError("EIO", "http.request")`.
  - `follow()` resolves `Location` per RFC 3986 §5.2 (strips `#fragment`, validates via `url.parse`, then removes dot segments), allows **<= 20 hops**, checks cancellation per hop, and closes intermediate responses. Missing `Location` returns the 3xx; multiple `Location`s, hop 21, or non-HTTP(S)/userinfo target raise `OperationError("EIO", "http.request")`.
  - `301`/`302` after `POST` and `303` after non-`GET`/`HEAD` rewrite to bodyless `GET` stripping `Content-*`; `307`/`308` keep method/body. Cross-origin hops (normalized `scheme`/`host`/`port`, incl. `https`→`http`) stickily strip `Authorization`, `Proxy-Authorization`, `Cookie`, `Cookie2`, `Host`. `ca_file` applies on every HTTPS hop.
- **Native option policies:** `only_if_cached()` (requires explicit `RequestMode.same_origin()`) raises `OperationError("EIO", "http.request")` pre-dial; `no_cors()` allows only `GET`/`HEAD`/`POST` (case-insensitive) else raises string.
- **Pools & drains:**
  - Keyed by `(scheme, normalized host, port, effective Host, ca_file path)` (plain HTTP ignores `ca_file`). Close pool (`close_idle_connections()`/`client:close()`) before rotating a CA file in place.
  - Bounds: **100** idle total, **2** per key, **90 s** idle expiry (checked on activity, no timer Task); idle input listeners abort unsolicited bytes/EOF. Stale reused sockets retry **at most once** only for bodyless `GET`/`HEAD` with zero bytes received (incl. 1xx) on close/reset.
  - Early `ClientResponse:close()` marks closed immediately and background-drains up to **50 ms** and **256 KiB** to reclaim persistent sockets (larger known `Content-Length`, nonpersistent, EOF-framed, or active-read responses retire immediately). `close_idle_connections()` runs 50 ms TLS `close_notify` on healthy idle TLS sockets.

## 2. Browser `fetch` Client Edge Cases (`--target browser`)

- **Pre-network checks:** Requires owner `async` Runtime (`"async Runtime is not active"` in `lua.new()`, though building `Headers`/`RequestOptions`/`Client()` works). Rejects pre-fetch: bad method tokens, `CONNECT`/`TRACE`/`TRACK`, non-`GET`/`HEAD`/`POST` under `no_cors()`, bad/non-HTTP(S) URLs (`url.Error`), any `ca_file`, any `GET`/`HEAD` body (even `""`), and forbidden headers:
  - `Host`: matching normalized URL host+port auto-stripped; any other raises `"HTTP custom Host header is unavailable on the browser target"`.
  - `Content-Length`: exact match to `#body` auto-stripped; mismatch raises. `Transfer-Encoding` and `Expect` raise.
  - Forbidden names (`"HTTP request header '<name>' is forbidden on the browser target"`): `Accept-Charset`, `Accept-Encoding`, `Access-Control-Request-Headers`, `Access-Control-Request-Method`, `Connection`, `Cookie`, `Cookie2`, `Date`, `DNT`, `Keep-Alive`, `Origin`, `Referer`, `Set-Cookie`, `TE`, `Trailer`, `Upgrade`, `Via`, plus `Proxy-*` and `Sec-*`.
  - `X-HTTP-Method`, `X-HTTP-Method-Override`, `X-Method-Override`: rejected if any unquoted comma element is `CONNECT`/`TRACE`/`TRACK` (quoted lists pass Titan, though Firefox/WebKit drop them).
- **Engine quirks & responses:**
  - `redirect` defaults to `follow()`. `CacheMode.default()` uses browser cache (`no_store()`/`reload()` bypass). Node has no cache (`only_if_cached()` raises `"EIO"`); WebKit `only_if_cached()` hits network. `CredentialsMode.include()` forbids server `Access-Control-Allow-Origin: *`.
  - `manual()` yields opaque-redirect (`status == 0`, empty `reason`/`headers`, `url == requested`, `read() == nil`). Cross-origin `no_cors()` + `follow()` yields `url == nil` (with `manual()`/`error()` raises `"EIO"`). On `follow()` + 3xx without `Location`, browsers deliver body while Node may fail reads with `"http.read"`.
  - `headers` are lowercase, sorted, comma-joined, without trailers or `Set-Cookie`/`Set-Cookie2`. Host decodes `Content-Encoding` while keeping original `Content-Encoding`/`Content-Length`—**never decompress again or bound reads by `Content-Length`**.
  - `close()`/cancel abort immediately without yielding; `close_idle_connections()` is a no-op; `Client` closes with its Runtime and cannot migrate.

## 3. HTTP/1.1 Server Framing, Coalescing, `Expect` & Upgrades

- **Commitment & coalescing:** `Response:is_committed()` flips `true` immediately **before** the first final-header write (`send_headers`, `write`, `close`, `upgrade`, `reject_upgrade`) and stays readable after failure/end. `100 Continue` does not commit. Unsent headers coalesce with the first valid `write(data)` when `#data <= 64 KiB` (or with `"0\r\n\r\n"` on uncommitted empty chunked `close()`); call `send_headers()` to flush ahead of body.
- **Framing & keep-alive:** Omitted `Content-Length` → `Transfer-Encoding: chunked`; declared `Content-Length` rejects overflow and requires exact match at `close()`. `HEAD`, `204` (forbids `Content-Length`), `205` (enforces `Content-Length: 0`), `304` forbid nonempty bodies. Setting `response:set_header("Connection", "close")` skips unread request-body draining after `response:close()`. Idle `EOF`/`ECONNRESET`/`TLS_TRUNCATED_EOF` before next-request bytes closes quietly.
- **`Expect` & upgrades (native):** Singleton `Expect: 100-continue` (non-upgrade) emits `100 Continue` pre-handler; invalid `Expect` sends `417`. Bad upgrade openings (any `Expect`, bad/missing/duplicate `Host`, bad URL, non-1.1) send `400` pre-handler.
  - Client: `http.request_upgrade_on(conn, abort_fn, url, protocol, headers?)` (`plain:close` or `secure:abort`; 64 KiB cap, `<= 16` interims); claim `101` once via `response:take_upgrade()` (`defer stream:close()`).
  - Server: `response:upgrade(req, protocol, headers?)` validates live pair, unsent output, and protocol (case-insensitive name, case-sensitive `/version`), emits `101` (64 KiB cap), and transfers stream ownership. `response:reject_upgrade(req, status, headers?)` emits bodyless `400..599` (`Content-Length: 0`, `Connection: close`) without draining body and retires transport.

## 4. TLS Deadlines, State Close & Static OpenSSL Linking

- **Deadlines:** Race an owned child I/O Task against `timer.sleep(ms)` (`async.race_two`), then cancel and `async.join` the loser (`skill://titan-async`). On `ssl.Connection`, call `conn:abort()` **before** joining a blocked accepted write child (`close()` is exclusive; cancelling admitted TLS I/O terminalizes the engine).
- **Lua-state close:** State teardown frees open `ssl.Connection` engines and `ssl.Server` contexts synchronously while the abandoned Runtime closes TCP sockets without `close_notify`. During unwind, `ssl.Connection:close()` and `abort()` complete synchronously so `defer conn:close()` does not raise.
- **Static linking (`--static`):** Bundled OpenSSL links automatically in `titan.a`; system-OpenSSL providers require:
  ```sh
  TITAN_EXTRA_CPPFLAGS="$(pkg-config --cflags openssl)" \
  TITAN_EXTRA_LDFLAGS="$(pkg-config --libs openssl)" \
    titanc --static -o out --exe out/app app.main
  ```

## 5. Cross-State Handoff (`net`, `ssl`, `http.Exchange`, `http.UpgradedStream`)

All four implement `to_transfer_payload()`, `.from_transfer_payload(payload)`, and `.discard_transfer_payload(payload)` (`skill://titan-thread`): detach pre-delivery, adopt **exactly once** in an active non-closing Runtime, and recover failed delivery via `.discard_transfer_payload(payload)` without a Runtime (consumes ownership even on error).

- **Idle gate & Windows:** Rejects active readers, writers, handshakes, shutdowns, input listeners, half-closed sockets, and pending native requests (source stays usable). On Windows, set `read_ahead(false)` (or `server:read_ahead(false)` pre-`serve()`) and call `async.yield()` after `connect`/last I/O before encoding.
- **Preserved state:** `net`/`ssl` preserve unread buffers, `read_ahead`, and OS `TCP_NODELAY` (destination `:local_address()`/`:peer_address()`/`:set_no_delay()` query the live socket). `http.Exchange(request, response)` preserves parser/headers/keep-alive suffix; destination finishes with `exchange:close()` or loops via `exchange:serve(handler, idle_timeout?)` (`idle_timeout` defaults `0`, independent of origin server). `http.UpgradedStream` transfers only `net`/`ssl` transports.
