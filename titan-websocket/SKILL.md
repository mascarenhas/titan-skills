---
name: titan-websocket
description: Write, review, and test Titan WebSocket clients and HTTP/TLS upgrade handlers with message framing, origin/subprotocol policy, Ping/Close, cancellation, and owned session cleanup. Use for titan.websocket work; ordinary TCP/TLS/HTTP uses titan-networking.
---

# Titan WebSocket

Load `titan-programmer` before any .titan work. Add `titan-networking` for
opening/TCP/TLS/HTTP, `titan-async` for lifecycle/concurrency, `titan-tester` for
native tests and `titan-ffi` when changing the synchronous crypto/byte boundary.

The module is message-oriented, direct Task-blocking RFC 6455 version 13 over
HTTP/1.1. Import `websocket`; never substitute a Node event emitter, LuaSocket
API or private UV/HTTP/TLS fields. Ordinary `http.Handler` owns routing/auth
before `websocket.accept`; the same handler works in `http.listen_tls`.

## Public contract

```text
union MessageType: text(), binary()
const TEXT, BINARY: MessageType
record Connection -- opaque; no public constructor
DialOptions(headers:http.Headers?, ca_file:string?, subprotocols:({string})?,
            read_limit:integer?, handshake_timeout:integer?)
AcceptOptions(subprotocols:({string})?, allowed_origins:({string})?,
              read_limit:integer?, handshake_timeout:integer?)
connect(source_url:string, options:DialOptions?):Connection
accept(request:http.Request,response:http.Response,options:AcceptOptions?):Connection
Connection:read():(MessageType?,string?)
Connection:write(kind:MessageType,data:string)
Connection:ping(timeout_ms:integer?)
Connection:shutdown(code:integer?,reason:string?,timeout_ms:integer?)
Connection:close()
Connection:subprotocol():string?
Connection:close_status():(integer?,string?)
```

Constructor options are validated copied snapshots. Incoming limit defaults
1 MiB; opening 10 s; Ping/shutdown/control progress 5 s. Limits/deadlines are finite
positive integers. Deadlines initiate abort, with actual native retirement
possibly later. Public error data is:

```text
Error(kind:string,operation:string,message:string,close_code:integer?)
HandshakeError(message:string,status:integer?,headers:http.Headers?)
```

Preserve underlying `ssl.Error`, `async.OperationError`, URL and cancellation
identities; do not turn transport loss into clean EOF or manufacture 1006.

## Application decisions

- Immediately `defer connection:close()` after connect/accept. `close` is
  idempotent, cancellation-insensitive abort/retirement. `shutdown` is bounded
  graceful WebSocket closing and does not replace lexical cleanup.
- Read one complete message with `local kind?, data? = connection:read()`.
  `(nil,nil)` means valid peer Close and reciprocal handling. Empty strings are
  data, binary permits NUL, and previous strings stay immutable after later
  reads/GC. There is no streaming message Reader/Writer or JSON convenience.
- One application reader and one data writer may progress simultaneously on
  ws/wss. Duplicate same-kind operations fail. Large output is fragmented at
  16 KiB with frame-level control priority; never interleave two data messages.
- **Ping requires a concurrent application reader.** `read` services controls;
  no perpetual session-reader Task or decoded-message queue exists. A write-only
  client must deliberately keep reading. Unmatched Pong is ignored.
- Shutdown stops data admission. Existing read may deliver one message, then
  its nonyielding release hands receive progress to shutdown, which discards
  further data while servicing controls. New reads cannot steal that owner.
- Cancellation before transport/protocol admission detaches reservations.
  Once admitted, even idle ws/wss reads terminalize on cancellation. Timeout
  is catchable without cancelling the caller; genuine Task cancellation stays
  sticky. The first terminal failure is an async.Error carrier: preserve its
  exact value and captured origin traceback through cleanup and later valid
  operations. Never join a blocked native writer before initiating transport abort.
- After HTTP transfers the stream, its handler can return only after establishing
  session ownership. Listener close does not close/registry-manage sessions.

Default Origin accepts absent Origin or normalized same HTTP(S) scheme/host/
effective port. Exact `allowed_origins` adds explicit public origins for proxy
setups; no wildcards/implicit forwarded trust. Reject multiple/malformed/null
origins. Origin is browser cross-site policy, not native-client authentication.

Subprotocols match **case-sensitively**, server preference first; no intersection
means no selected protocol. HTTP token/name case folding does not apply to
subprotocols. Ignore empty HTTP Upgrade/Connection list elements within the
header bound; keep subprotocol offers strict. Do not override reserved handshake/body framing fields with
application headers. Once HTTP invokes accept: malformed opening 400,
origin 403, unsupported version 426;
rejection finishes one response and raises HandshakeError. Invalid options or
already committed output fail before protocol response. HTTP pre-handler
validation is separate: an upgrade indication plus Expect receives 400 with no
handler call; complete upgrade attempts with missing/duplicate/invalid Host,
invalid request URLs, or unsupported HTTP version receive 400 before the handler. Invalid HTTP syntax fails in parsing.
These paths do not produce a server accept HandshakeError.

TLS always verifies the original URL hostname and chain. `ca_file` replaces
default trust per SSL. Dial already-resolved numeric endpoints without changing
Host/SNI/cert identity. No insecure mode, redirects, proxies, cookies/reconnect
policy, automatic heartbeat, extensions/compression or HTTP2/3 support exists.
Valid extension offers are syntactically checked and ignored; clients reject
unsolicited extension negotiation and all nonzero RSV bits.

## Implementation review

Keep one folder module; UV alone owns libuv FFI, SSL owns its engine, HTTP owns
llhttp/prefix transfer. Only the tiny EVP digest/base64 bridge and portable
rooted byte access belong here. Nonces/masks use public synchronous uv.random;
every client frame including empty/control gets fresh 4-byte entropy. Do not
use math.random or add an unreviewed asynchronous entropy pool.

Opening admission is keyed by semantic IP bytes/port/effective IPv6 scope in an
ephemeron runtime bucket; mapped IPv6 converges with IPv4. Resolve once, reserve
only the current candidate until validated Upgrade/retirement, and preserve
original URL identity. Contenders never own/cancel the incumbent. Only TCP
failure permits resolver-order fallback.

Validate frame opcode/RSV/FIN/mask and minimal length before allocating.
Reject 64-bit high-bit lengths and cumulative overflow/limit. Controls have 125
bytes independently of data budget. Continuation requires active fragmentation;
text scalar UTF8 state spans every split and validates FIN, overlong/surrogate/
>U+10FFFF rejection. Outgoing text validates before bytes. Close permits empty
payload or code plus UTF8 reason (123 bytes); codes 1000..1003,1007..1014,3000..4999.
Servers cannot send 1010 and answer client 1010 with 1000. Never emit reserved codes.

Operation supervisors are per public I/O call, with cancellation-aware parents
and accepted-ownership-retiring children. One shared terminal owner aborts
before draining scopes, preserving first cause. Never join arbitrary caller
Tasks or resurrect terminal TLS. Controls have bounded progress behind stalled
output. No codec Task per frame, but nested TLS writes add workers per fragment:
count actual allocation costs. Buffered parse/mask work needs explicit yields;
checkpoint alone is not scheduling fairness.

The decoded-message cap does not bound inherited net queues. Do not claim
bounded memory for paused application readers, zero-copy messages or zero
fragment-proportional Task allocation without measured evidence.

## Tests and evidence

Native behavior belongs in `spec/stdlib/titan/websocket/tests/`, using installed
public APIs, source-only `support.runtime`, owned peer Tasks and checked-in CA
fixtures. Retry loopback ports only on EADDRINUSE. Establish pending states
with acknowledgments/suspension, not timing sleeps. Compile shared Windows
fixtures before considering platform skips. Reinstall current source first:

```sh
make titan-stdlib-test-build
make titan-stdlib-test-run TITAN_FILTER='^websocket[.]tests[.]'
make titan-stdlib-test-run TITAN_FILTER='^ssl[.]tests[.]'
make titan-stdlib-test-run TITAN_FILTER='^http[.]tests[.]'
make titan-stdlib-test-run TITAN_FILTER='^net[.]tests[.]'
make titan-stdlib-test-run TITAN_FILTER='^url[.]tests[.]'
```

Use both pinned Autobahn roles and strict exact nonempty case/agent reports;
check behaviorClose too, and reject NON-STRICT/UNCLEAN/unknown/missing results.
Only audited INFORMATIONAL cases qualify. Do not copy upstream UTF8/Close
exclusions. Compression 12/13 alone are explicit outside the uncompressed
profile. A zero process exit is not conformance. Native tests retain opening,
TLS, limits, cancellation, shutdown takeover and role-mask oracles regardless
of Autobahn coverage. Keep separate WebSocket benchmarks from issue196's
frozen matrix. Record source/provider/image/platform identity with results.

Authority: [human manual](../../../doc/language/standard-library-websocket.md),
[implementation](../../../doc/implementation/websocket-library.md),
[source](../../../titan/websocket), [native tests](../../../spec/stdlib/titan/websocket/tests),
and [conformance harness](../../../spec/conformance/websocket/README.md).
