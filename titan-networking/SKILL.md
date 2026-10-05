---
name: titan-networking
description: Write, review, and test Titan TCP, TLS, HTTP/1.1, and URL code with the exact net, ssl, http, url, io, async, and timer contracts. Use for clients, servers, byte streams, certificate verification, HTTP framing, URL normalization, network cancellation, or network-resource cleanup. API-provided network timeouts are covered here; add titan-async for asynchronous networking behavior tests or when directly designing Task, timer, cancellation, or Runtime mechanics.
---

# Titan networking

Use this skill for application code and reviews involving `net`, `ssl`, `http`,
`url`, or a network value viewed through an `io` Interface. Titan networking is
**direct-style asynchronous Titan code**: an operation looks like a blocking
method call, but it suspends only its current `async.Task` and resumes from a
libuv callback. It is not LuaSocket, Go's `net/http`, Node promises, or a
thread-per-connection API.

This cartridge is self-contained for the public networking surface, including
an API's own timeout/deadline contract. Read `titan-programmer` first for every
`.titan` change, and load every applicable peer: `titan-async` for asynchronous networking behavior tests or when directly
designing Task/timer/cancellation or Runtime ownership, `titan-tester` for native
behavior tests, `titan-pegs` when changing the URL grammar, and `titan-ffi` when
changing the standard library's native boundary. Normal applications use these high-level APIs. Low-level adapters may import
public `uv`; only `titan.uv` may import libuv headers/types/helpers. Keep
OpenSSL and llhttp FFI inside their established library boundaries.

## Evidence labels used here

Examples are deliberately labeled so an attractive sketch is not mistaken for
a checked-in contract:

- **REPOSITORY-VERIFIED** means the pattern or complete example is present in a
  current manual, source module, or native Titan behavior test named beside it.
  A quoted manual example is reproduced as written. A shortened test pattern
  keeps the same public calls but is not claimed to be a byte-for-byte fixture.
- **COMPOSITION SKETCH** means every named API and semantic rule is current, but
  the whole snippet is newly composed for this skill and was not separately
  built as a repository fixture. Compile it in the target source tree and add a
  focused test before shipping it.

Do not infer an API from a sketch. The API inventories below are the boundary.

## Route to the narrow authority

| Work | Read first | Then inspect |
| --- | --- | --- |
| TCP/DNS/byte streams | [`doc/language/standard-library-net.md`](../../../doc/language/standard-library-net.md) | [`titan/net.titan`](../../../titan/net.titan), [`spec/stdlib/titan/net/tests.titan`](../../../spec/stdlib/titan/net/tests.titan), [`doc/implementation/libuv-networking.md`](../../../doc/implementation/libuv-networking.md) |
| TLS/trust/certificates | [`doc/language/standard-library-ssl.md`](../../../doc/language/standard-library-ssl.md) | [`titan/ssl.titan`](../../../titan/ssl.titan), [`spec/stdlib/titan/ssl/tests.titan`](../../../spec/stdlib/titan/ssl/tests.titan), [`doc/implementation/ssl-library.md`](../../../doc/implementation/ssl-library.md) |
| HTTP client/server | [`doc/language/standard-library-http.md`](../../../doc/language/standard-library-http.md) | [`titan/http/`](../../../titan/http), [`spec/stdlib/titan/http/tests/`](../../../spec/stdlib/titan/http/tests), [`doc/implementation/http-library.md`](../../../doc/implementation/http-library.md) |
| URL validation/normalization | [`doc/language/standard-library-url.md`](../../../doc/language/standard-library-url.md) | [`titan/url.titan`](../../../titan/url.titan), [`spec/stdlib/titan/url/tests.titan`](../../../spec/stdlib/titan/url/tests.titan), [`doc/implementation/url-library.md`](../../../doc/implementation/url-library.md) |
| Stream abstraction | [`doc/language/standard-library-io.md`](../../../doc/language/standard-library-io.md) | [`titan/io.titan`](../../../titan/io.titan), [`doc/language/interfaces.md`](../../../doc/language/interfaces.md) |
| Tasks, deadlines, cancellation | [`doc/language/async-io.md`](../../../doc/language/async-io.md) | [`doc/implementation/libuv-runtime.md`](../../../doc/implementation/libuv-runtime.md), [`titan/async.titan`](../../../titan/async.titan) |
| Cleanup/error/option spelling | [`doc/style-guide.md`](../../../doc/style-guide.md), [`doc/language/defer.md`](../../../doc/language/defer.md), [`doc/language/error-handling.md`](../../../doc/language/error-handling.md), [`doc/language/option-types.md`](../../../doc/language/option-types.md) | Adjacent code and tests |
| Native tests | [`doc/language/standard-library-test.md`](../../../doc/language/standard-library-test.md) | Existing owner under [`spec/stdlib/titan/`](../../../spec/stdlib/titan), repository commands in [`AGENTS.md`](../../../AGENTS.md) |

The public language chapters define behavior. Source confirms declarations and
layering; the mechanically extracted current provider schema in
[`spec/fixtures/stdlib/titan_stdlib_types.lua`](../../../spec/fixtures/stdlib/titan_stdlib_types.lua)
confirms which fields, generated constructors, methods, functions, and aliases
are actually public. Tests show supported use and ownership. Implementation
chapters are authority for private callback/lifetime invariants, not permission
to use private names in application code.

## The runtime model that makes the APIs make sense

1. Async owns one non-reentrant libuv loop on the Lua main thread. Top-level
   `async.loop()` or the generated standalone bootstrap drives that loop.
   Callback-only public UV clients may drive their own explicit loops with
   `uv.run`, following the same main-thread and non-reentry restrictions.
2. A Task runs synchronously until it returns, raises, or invokes an operation
   that yields to the runtime. Libuv does not preempt ordinary Titan statements.
   Explicit low-level calls that invoke synchronous callbacks (such as
   `uv.walk`, or Windows TTY read startup) follow their documented contract;
   do not confuse that direct call with unrelated event-loop preemption.
3. `async.run` schedules a new Task and returns before its function starts. It
   does not run the function inline.
4. Operation callbacks resume the Task waiting for that exact operation through
   its public generic await settlement or subscription delivery. Public `Task:resume(token)` is only
   for the exact explicit `async.suspend(token, ...)` that stored the same
   nominal token; it is never a general native-wait wake and is not how
   application code completes reads, accepts, writes, DNS, TLS, or HTTP.
5. An accepted native request and everything libuv borrows remain owned until
   its terminal callback. Task cancellation is logical before it is physical;
   it never makes the callback owner or write bytes disposable early.
6. A standalone program that imports this async constellation gets the automatic
   bootstrap: generated `main` already runs as a Task and the entrypoint drives
   the loop until all Tasks finish. Do not wrap `async.loop()` inside `main`, a
   handler, a callback, or another Task.
7. A Lua host schedules work with `async.run` and drives it with one top-level
   `async.loop`. A program or test compiled with `--no-uv-bootstrap` must do the
   same explicitly and finish Runtime-bound Tasks/handles inside that session.
8. CPU-heavy Titan code blocks all I/O until it returns or explicitly calls
   `async.yield()`/`timer.yield()`.

These are verified by
[`doc/language/async-io.md`](../../../doc/language/async-io.md) and
[`doc/implementation/libuv-runtime.md`](../../../doc/implementation/libuv-runtime.md).
Reject designs that add locks, generations, callback fences, ready queues, or
snapshot rollback to defend against imagined same-thread callback preemption.
Tasks can interleave only at real suspension boundaries; ownership still must
be correct across those boundaries.

## Exact public API inventory

### TCP: `net`

```text
local net = import "net"

record Connection       -- opaque; no public constructor or handle
record Server           -- opaque; no public constructor or handle

function connect(host: string, port: integer): Connection
function listen(host: string, port: integer,
                backlog: integer?): Server

function Connection:read(): string?
function Connection:read_until(delimiter: string,
                               chop: boolean?): string?
function Connection:write(data: string)
function Connection:shutdown()
function Connection:close()

function Server:accept(): Connection
function Server:close()
```

This is the complete current TCP surface. There is no UDP, Unix-domain socket,
socket-option, local/peer-address, selected-ephemeral-port, read-size,
`read_all`, per-operation timeout, or connection-pool API.

### TLS: `ssl`

```text
local ssl = import "ssl"

record Error
  code: integer
  name: string
  message: string
  operation: string
end
function Error.new(code: integer, name: string,
                   message: string, operation: string): Error

record Connection       -- opaque
record Server           -- opaque

function connect(host: string, port: integer,
                 ca_file: string?): Connection
function listen(host: string, port: integer,
                certificate_file: string,
                private_key_file: string?,
                backlog: integer?): Server

function Connection:handshake()
function Connection:read(): string?
function Connection:read_until(delimiter: string,
                               chop: boolean?): string?
function Connection:write(data: string)
function Connection:shutdown()
function Connection:close()

function Server:accept(): Connection
function Server:close()
```

`ssl.Error(...)` calls the ordinary generated `ssl.Error.new` constructor for
this public-field record; applications normally receive an Error from a failed TLS operation
rather than manufacturing one.

There is no insecure flag, CA-directory argument, client-certificate/mTLS
surface, ALPN selector, cipher/session/key-log control, raw `net.Connection`
accessor, or simultaneous-read/write mode.

### URLs: `url`

```text
local url = import "url"

record Url
  scheme: string
  host: string
  port: integer
  path: string
  query: string?
  target: string
  authority: string
end

record Error
  position: integer
  kind: string
  message: string
end

-- Public-field records receive their ordinary generated constructors.
function Url.new(scheme: string, host: string, port: integer,
                 path: string, query: string?, target: string,
                 authority: string): Url
function Error.new(position: integer, kind: string,
                   message: string): Error

function parse(source: string): (Url?, Error?)
function parse_request(scheme: string, authority: string,
                       target: string): (Url?, Error?)
function Url:host_header(): string
```

Both parse functions are synchronous and nonthrowing for malformed input. They
return exactly one populated tuple position. The generated `Url.new` and
`Error.new` constructors exist because every field is public, but application
input should go through `parse`/`parse_request` so its normalization and policy
are enforced. The `http` layer deliberately turns the returned `url.Error` into
a raised value when a request cannot proceed.

### HTTP/1.1: `http`

```text
local http = import "http"

record Header
  name: string
  contents: string
end
function Header.new(name: string, contents: string): Header

record Headers

function headers(initial: {Header}?): Headers
function Headers:add(name: string, contents: string)
function Headers:set(name: string, contents: string)
function Headers:get(name: string): string?
function Headers:values(name: string): {string}
function Headers:remove(name: string)
function Headers:all(): {Header}

record ClientResponse
  status: integer
  reason: string
  version: string
  headers: Headers
end

function request(method: string, source_url: string,
                 supplied_headers: Headers?, body: string?,
                 ca_file: string?): ClientResponse
function get(source_url: string, supplied_headers: Headers?,
             ca_file: string?): ClientResponse
function ClientResponse:read(): string?
function ClientResponse:read_until(delimiter: string,
                                   chop: boolean?): string?
function ClientResponse:close()

type Handler = function(Request, Response): ()

record Request
  method: string
  target: string
  url: url.Url
  version: string
  headers: Headers
end

function Request:read(): string?
function Request:read_until(delimiter: string,
                            chop: boolean?): string?

record Response
function Response:set_status(status: integer, reason: string?)
function Response:add_header(name: string, contents: string)
function Response:set_header(name: string, contents: string)
function Response:headers(): Headers
function Response:send_headers()
function Response:write(data: string)
function Response:close()

record Server
function listen(host: string, handler: Handler,
                port: integer?, backlog: integer?,
                idle_timeout: integer?): Server
function listen_tls(host: string, certificate_file: string,
                    handler: Handler, private_key_file: string?,
                    port: integer?, backlog: integer?,
                    idle_timeout: integer?): Server
function Server:idle_timeout(timeout: integer?): integer
function Server:serve()
function Server:close()
```

`Header(...)` calls the public generated constructor because Header has only
public fields; passing an Array
through `headers(initial)` validates and copies those records. `Headers`,
`Response`, and `Server` are opaque. `ClientResponse` and `Request` expose the
listed public fields but also own private transport/parser state, so neither has
a public generated constructor. Use `headers`, `request`/`get`, and
`listen`/`listen_tls`.

This is an HTTP/1.1-only, one-request client and serial keep-alive server. There
is no `Router`, request builder, streaming request-body Writer, response `body`
field, redirect policy, decompressor, cookie jar, proxy mode, connection pool,
WebSocket/Upgrade, HTTP/2, endpoint getter, or generic middleware API.

### The stream Interfaces used by networking

`net.Connection` and `ssl.Connection` satisfy all seven exact method-shape
Interfaces. `http.ClientResponse` satisfies `io.ReaderCloser`, `http.Request`
satisfies `io.Reader`, and `http.Response` satisfies `io.WriterCloser`.
Servers satisfy `io.Closer` incidentally.

```text
local io = import "io"

interface Reader
  function read(): string?
  function read_until(delimiter: string, chop: boolean?): string?
end
interface Writer
  function write(data: string)
end
interface Closer
  function close()
end
interface ReaderWriter
  function read(): string?
  function read_until(delimiter: string, chop: boolean?): string?
  function write(data: string)
end
interface ReaderCloser
  function read(): string?
  function read_until(delimiter: string, chop: boolean?): string?
  function close()
end
interface WriterCloser
  function write(data: string)
  function close()
end
interface ReaderWriterCloser
  function read(): string?
  function read_until(delimiter: string, chop: boolean?): string?
  function write(data: string)
  function close()
end

function lines(reader: ReaderCloser):
    (function (ReaderCloser): (string?), ReaderCloser, nil,
     function (ReaderCloser): ())
```

Interface satisfaction is structural at an explicit conversion site. It is not
inheritance, does not duplicate a resource, and does not recursively convert a
method result, Array, Map, or function type. Several Interface wrappers still
own the same one socket/parser. Concrete concurrency, cancellation, and close
rules do not become uniform merely because method shapes match.

### Networking-relevant Task/timer subset

This is not the complete `async` API; it is the subset needed to understand the
patterns in this skill. The `async` module owns these public data shapes:

```text
record ResumeToken
  const source: string?
end

record Error
  error: value
  traceback: string
end
record OperationError
  code: integer
  name: string
  message: string
  operation: string
end
union CancellationReason<|B|>
  simple(string)
  complex(B)
end
union TaskStatus<|A, B|>
  ready()
  running()
  waiting()
  succeeded(A)
  failed(Error)
  cancelled(CancellationReason<|B|>)
end
record Task<|A, B|>  -- opaque
```

These nominal types and their constructors are declared by `async` itself.
Its networking-relevant functions form this surface:

```text
local async = import "async"
local timer = import "timer"

-- Shown unqualified as inside async; callers use async.*.
type SuspendCancelAction = function(): ()

function run<|A, B|>(func: function (): (A)): Task<|A, B|>
function loop()
function yield()
function running(): Task<|value, value|>
function suspend(token: ResumeToken,
                 cancel_action: SuspendCancelAction?)
function join<|A, B|>(task: Task<|A, B|>): TaskStatus<|A, B|>
function join_two<|A1, B1, A2, B2|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>):
    (TaskStatus<|A1, B1|>, TaskStatus<|A2, B2|>)
function any_two<|A1, B1, A2, B2|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>):
    AnyTwoResult<|A1, A2|>
function race_two<|A1, B1, A2, B2|>(
    first: Task<|A1, B1|>, second: Task<|A2, B2|>):
    RaceTwoResult<|A1, B1, A2, B2|>

function Task:cancel(reason: CancellationReason<|B|>?)
function Task:status(): TaskStatus<|A, B|>
function Task:add_terminal_listener(
    listener: function (TaskStatus<|A, B|>): ()): function (): ()
function Task:resume(token: ResumeToken)
function TaskStatus:as_string(): string
function TaskStatus:has_finished(): boolean
function TaskStatus:has_succeeded(): (boolean, A?)
function TaskStatus:has_failed(): (boolean, Error?)
function TaskStatus:has_cancelled(): (boolean, CancellationReason<|B|>?)

-- These declarations are inside timer; callers use timer.sleep/yield.
function sleep(milliseconds: integer)
function yield()
```

`ResumeToken` compares by nominal record identity; its optional source is only
diagnostic. A wrong token raises synchronously in the caller with this exact
message: `Task resume token mismatch (expected source: <source>)`, using
`unknown source` when the Task has no stored source. That includes every wrong-
time call, because a Task outside the matching explicit suspension expects no
token. Correct-token calls coalesce and wake on a deferred Task-owned timer.
Cancellation first runs the optional detach action, then wakes with the token
captured by `suspend`.

The facade's aliases preserve the underlying public constructors and union
variants, including `CancellationReason.simple/complex`, every `TaskStatus`
variant, and `Error.new`/`OperationError.new`; applications normally receive the
error/status records rather than manufacturing them. The fixed-arity `any_*`,
`race_*`, `all_*`, and `join_*` families extend from two through five operands;
only `join` has a unary form. They never cancel losers. Consult the async
skill/manual for exact result unions and arities.

## Titan spelling rules that matter in network code

### Omit trailing optional arguments; do not invent option records

Titan fixed calls nil-fill omitted positions, and every optional position here
accepts nil. These are valid public calls:

```text
net.listen("127.0.0.1", 8080)          -- backlog 128
ssl.connect("example.com", 443)         -- default OpenSSL trust paths
ssl.listen("127.0.0.1", 8443, "server.pem") -- combined cert/key PEM
http.get("https://example.com/")        -- no headers, default TLS trust
http.listen("127.0.0.1", handler)       -- port 80, backlog 128, no deadline
response:set_status(404)                 -- default reason phrase
connection:read_until("\n")             -- delimiter retained
```

Do not replace these with guessed option tables, named `Config` records, or
Go-style functional options.

### Options auto-unwrap at their use; `value` does not

Preserve normal absence with `local item?`. After a presence check, use the
option directly where the bare value is required. Field access, method calls,
arguments, indexing, operators, and ordinary inferred initializers perform the
checked unwrap. A guard makes that check known-safe; it does not flow-change the
variable's static type.

```text
local parsed?, problem? = url.parse(source)
if problem then
  return nil
end
return parsed:host_header()  -- correct: method receiver unwraps Url?
```

Do **not** write `(parsed as url.Url):host_header()` merely because `parsed` is
an option. A few older implementation/test spellings still contain such casts;
the normative option chapter and current style guide require the direct form.

By contrast, catch-local `error` has type `value`. After an `is` test, an
explicit cast is appropriate because this is a dynamic-value projection, not
an option unwrap:

```text
do
  risky_network_call()
catch
  if error is async.OperationError then
    local failure = error as async.OperationError
    log(failure.operation .. ": " .. failure.name)
  else
    raise       -- preserve the original error and traceback
  end
end
```

### Acquire, then defer immediately

```text
local connection = net.connect(host, port)
defer connection:close()
```

One statement after `defer` is enough. Its scope is the current function, loop,
`if`/`case` arm, or explicit `do` block, and same-block defers run LIFO on
fallthrough, return, break, or error. Use `defer do ... end` only for several
cleanup statements. Do not add a `do/end` solely because cleanup exists.

Titan has no `try`. `catch` attaches directly to any block, including a function
body. Use `do ... catch ... end` only when a deliberately narrower region must
be protected. A deferred cleanup error can replace the pending result/error; if
best-effort cleanup must preserve a caught primary failure, catch the cleanup
and use bare `raise` from the original catch.

## Byte-stream behavior shared across TCP, TLS, and HTTP bodies

- Payloads and delimiters are binary Titan strings. Embedded NUL is valid.
  Hosts, PEM paths, and other C text inputs reject embedded NUL.
- `read()` returns one timing-dependent chunk or `nil` EOF. Never treat a chunk
  as a message boundary, a TLS record, or a complete HTTP body.
- `read_until(delimiter, chop)` requires a nonempty delimiter and matches it
  across underlying chunks, and retains bytes after the first match. Omitted or
  false `chop` includes the delimiter; true removes it. A delimiter at the
  beginning with `chop == true` returns `""`, which is not EOF.
- EOF after a nonempty unterminated tail returns that tail once, then nil.
- The generic `io.Reader` contract permits an empty chunk. Concrete `net` and
  `ssl` reads deliver nonempty data chunks; only nil is EOF.
- `io.lines(reader)` repeatedly calls `read_until("\n", true)` and transfers
  responsibility for closing a `ReaderCloser` to the generic-for iterator. Do
  not separately consume or close it while the iterator owns it.
- A successful/terminal `close()` is safe to repeat. That shared Interface rule
  does not imply shared post-close writes, concurrent-operation behavior, or
  cancellation policy.

**COMPOSITION SKETCH — generic body drain through the real Interface:**

```titan
local stream = import "io"
local str = import "string"

function read_all(reader: stream.Reader): string
  local output = str.writer()
  while true do
    local chunk? = reader:read()
    if not chunk then return output:drain() end
    output:write(chunk) -- argument context unwraps string?
  end
  return ""
end
```

`read_all` is an application helper, not a missing method on `net.Connection`
or `http.ClientResponse`. Bound memory remains application-owned; impose a
size limit for untrusted input rather than collecting without bound.

## TCP clients and servers

### Endpoint and buffering contract

- `connect` accepts ports `1..65535`. It resolves asynchronously, tries IPv4
  and IPv6 candidates in resolver order, and closes a failed candidate before
  moving on without waiting for that close callback.
- `listen` accepts ports `0..65535`; zero asks the OS for an ephemeral port, but
  the current `Server` exposes no way to retrieve it. Backlog defaults to 128
  and, when supplied, must be `1..2147483647`.
- A read watcher starts lazily at the first read and keeps buffering chunks even
  with no waiter. There is no high-water mark. Do not leave a peer producing
  indefinitely while the application does not drain. Buffered chunks are
  returned before a stored read error; after they drain, that error remains
  sticky until close. Returned chunks are immutable copies. Private TCP receive
  scratch retains at most 64 KiB per active reader; this bound does not limit
  queued application bytes. A Connection retained after raw Runtime teardown
  can retain that scratch until explicit close, a closed read, or collection.
- A listener likewise retains already accepted clients when no Task is waiting;
  there is no application buffer cap beyond the native listen backlog.
- There may be at most one suspended reader on a Connection and one suspended
  acceptor on a Server. A second waiter raises; no queue is created.
- Cancelling a reader detaches only that waiter and leaves the connection/read
  watcher reusable. Cancelling an accept waiter leaves the server listening.
- Every nonempty write uses one `uv_write_t`; libuv orders them. Do not add
  another write queue. The call returns after its callback and keeps the exact
  immutable input rooted for the entire native borrow. An empty write validates
  state and returns without submitting a request.
- `shutdown()` is idempotent, waits behind earlier writes, closes the write side,
  and leaves reads open. `close()` is idempotent and closes both directions.
- Closing a Connection discards buffered/excess input, wakes a blocked reader
  with nil on a later turn, makes later reads EOF, and rejects new output.
  Closing a Server closes buffered unaccepted clients and wakes a blocked
  accept with an error.
- Runtime shutdown eventually finds leaked handles through `uv_walk`, but
  explicit close is still the application contract and reports errors at the
  right site.

**REPOSITORY-VERIFIED — manual TCP client**
([`doc/language/standard-library-net.md`](../../../doc/language/standard-library-net.md)):

```titan
local net = import "net"
local async = import "async"

function client(): value
  local connection = net.connect("127.0.0.1", 8080)
  defer connection:close()
  connection:write("hello\0world\n")
  connection:shutdown()
  return connection:read_until("\n", false)
end

function main(args: {string}): integer
  async.run<|value, value|>(client)
  return 0
end
```

The generated standalone runtime waits for the scheduled client Task after
`main` returns. In a main that performs the network calls directly, do not add
`async.run` merely to make them legal: `main` is already the bootstrap Task.
Use `async.run` for actual concurrency or a separately observable operation.

**COMPOSITION SKETCH — accept concurrently, handle each client serially:**

```titan
local async = import "async"
local net = import "net"

local function start_client(connection: net.Connection): async.Task<|nil, value|>
  return async.run<|nil, value|>(function (): nil
    defer connection:close()
    local line? = connection:read_until("\n", true)
    if line then connection:write(line .. "\n") end
    connection:shutdown()
    return nil
  end)
end

function serve(host: string, port: integer)
  local server = net.listen(host, port)
  defer server:close()
  while true do
    local connection = server:accept()
    start_client(connection)
  end
end
```

The Runtime roots spawned Tasks, and an uncaught client error ends/logs only
that Task. A production server still needs an intentional stop policy and, if
shutdown must await handlers, its own bounded registry of application Tasks.
Do not confuse such application ownership with a private Runtime scheduler or
make `net.Server:close()` promise to join clients—it does not.

## TLS without weakening verification or ownership

### Trust and endpoint identity

- `ssl.connect` establishes TCP, performs the client handshake, requires TLS
  1.2+, verifies the certificate chain, and verifies the requested `host` as
  the identity before returning. There is no insecure mode.
- DNS hosts are checked as DNS identities and sent as SNI. Textual IPv4/IPv6
  hosts are checked as IP identities and do not send SNI. An IPv6 `%zone`
  remains in the TCP destination but is removed only for X.509 matching.
- Omitted `ca_file` uses one module-wide OpenSSL context configured from
  OpenSSL's compiled default verify paths and recognized environment
  overrides. That is not a portable abstraction over the operating system's
  native trust store; bundled OpenSSL may synchronously consult its default CA
  file/directory. Pass an explicit CA file for deployment-independent trust.
- An explicit PEM `ca_file` **replaces**, rather than augments, default roots.
  The high-level async `fs` module reads it before TCP is opened. Empty,
  certificate-free, or malformed PEM is rejected. There is no CA-directory
  parameter.

### TLS servers and serialized connections

- `ssl.listen` reads one PEM chain and an unencrypted key through high-level
  `fs`. The first certificate is the leaf and later certificates are sent as
  its chain. Omit `private_key_file` to use one combined cert/key PEM.
- `Server:accept()` accepts TCP and creates TLS state, but deliberately does
  **not** wait for ClientHello. Start a Task per accepted connection and call
  `handshake()` there when handshake failure should be explicit. Otherwise the
  first read/write drives it. Never perform the handshake serially in the main
  accept loop if a stalled peer must not block later accepts.
- One `ssl.Connection` admits exactly one active operation across handshake,
  read, write, shutdown, and close. Do not run a reader Task and writer Task on
  the same TLS connection. The single OpenSSL state machine may need both
  network directions for any nominal operation.
- Cancelling a TLS operation terminalizes the TLS engine and best-effort closes
  its TCP transport. The Connection is not reusable afterward.
- `shutdown()` emits `close_notify`, drains it, and half-closes TCP output while
  leaving the read side available. Authenticated peer `close_notify` becomes
  nil EOF. FIN/RST without it becomes `ssl.Error` named
  `TLS_TRUNCATED_EOF`.
- `close()` best-effort performs TLS shutdown when possible, frees the engine,
  and closes TCP. It is idempotent after terminal close. Do not concurrently
  call close while another TLS operation owns the busy state; cancel and join
  that operation instead.
- Closing an `ssl.Server` stops only the listener/context reference. Already
  accepted Connections retain their TLS state and remain independently owned.

**REPOSITORY-VERIFIED — manual verified TLS client**
([`doc/language/standard-library-ssl.md`](../../../doc/language/standard-library-ssl.md)):

```titan
local async = import "async"
local ssl = import "ssl"

function fetch_head(): value
  local connection = ssl.connect("example.com", 443, nil)
  defer connection:close()
  connection:write(
    "HEAD / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n")
  return connection:read_until("\r\n\r\n", false)
end

function main(args: {string}): integer
  async.run<|value, value|>(fetch_head)
  return 0
end
```

For local TLS tests, the repository's supported pattern is a checked-in CA,
leaf certificate, and unencrypted key, an explicit `ca_file` on the client, and
loopback connections. It does not disable verification; see
[`spec/stdlib/titan/ssl/tests.titan`](../../../spec/stdlib/titan/ssl/tests.titan).

## URLs: validate once and use the right field

The URL module accepts only absolute HTTP/HTTPS URLs with a nonempty authority.
It deliberately rejects user information and fragments. It accepts registered
names, IPv4, bracketed IPv6, and bracketed IPvFuture; explicit ports are
`1..65535`. It performs no DNS or I/O.

Normalization is byte-oriented:

- `scheme` and registered-name hosts are lowercase;
- `host` is the unbracketed connection/TLS-identity spelling;
- `port` is explicit or the effective 80/443 default;
- empty path becomes `/`;
- `query` distinguishes absent nil from present empty `""`;
- `target` is normalized origin-form path plus optional query;
- `authority`/`host_header()` is normalized Host spelling, including brackets
  and an explicitly supplied canonical decimal port;
- unreserved percent escapes decode, retained escapes use uppercase hex; and
- IPv6 zone `%25` is decoded to `%` in `host` but retained URI-encoded in
  `authority`.

Use `Url.host` and `Url.port` to connect, `Url.target` in an HTTP request line,
and `Url.authority`/`host_header()` for Host. Do not split URLs with string
operations or send unbracketed IPv6 as Host.

**COMPOSITION SKETCH — nonthrowing URL validation with idiomatic options:**

```titan
local url = import "url"

function normalized_authority(source: string): string?
  local parsed?, problem? = url.parse(source)
  if problem then return nil end
  return parsed:host_header()
end
```

If callers need diagnostics, return both positions rather than converting the
ordinary parse failure into a string:

```titan
local url = import "url"

function inspect_url(source: string): (url.Url?, url.Error?)
  return url.parse(source)
end
```

`url.Error.position` is one-based in bytes. For `parse_request`, it refers to
the virtual absolute string `scheme .. "://" .. authority .. target`.
`kind` is the stable branch key; `message` is display text. The complete current
kind set is `scheme`, `scheme_separator`, `authority_separator`, `userinfo`,
`ipv6_brackets`, `ip_literal`, `ipv6_close`, `zone`, `host`, `port`,
`percent_escape`, `authority_tail`, `origin_form`, `fragment`, `url_tail`, and
the generic `url`. HTTP calls `url.parse`/`parse_request` internally and raises
that same structured record before opening a network connection when validation
fails.

## HTTP clients

### Request construction

- `request` validates `method` as an HTTP token. Method names are
  case-sensitive; exact `HEAD` selects no-body response framing.
- The source URL must be the `url` module's HTTP/HTTPS subset. HTTPS forwards
  `ca_file` exactly to `ssl.connect`; plain HTTP ignores it.
- Supplied `Headers` are copied. Header names compare with ASCII case folding,
  but original spelling, duplicates, and insertion order are retained.
  `get` returns the first; `values` returns all; `set` removes all matches and
  appends one replacement; `all` returns copied records.
- Header names must be nonempty HTTP tokens. Values reject forbidden controls
  and DEL, including NUL/CR/LF; this prevents injection.
- There may be at most one Host. An absent Host is generated from
  `Url.authority`; a supplied Host is separately validated as one complete
  authority and is preserved on the wire.
- The optional request body is one in-memory binary string. The client creates
  or checks exact Content-Length, rejects request Transfer-Encoding, and
  rejects Expect because it has no staged `100-continue` client state.
- The client always sends `Connection: close`. It has no reuse pool.

### Response ownership

`request`/`get` returns after final response headers, after consuming any 1xx
responses. The body remains streaming. Content-Length, chunked, no-body, and
connection-close framing are decoded; chunk framing is not returned.
Trailers are appended to `response.headers` only as parsing reaches them.

Always register `response:close()` immediately. Reading EOF closes it for you,
but a caller that stops early owns explicit close. Close discards the remainder,
closes the one-use transport, is idempotent, and completes transport cleanup
before pending Task cancellation is published. Redirects and content codings
are returned unchanged; the caller owns those policies.

**COMPOSITION SKETCH — one-request client with a bounded body policy:**

```titan
local http = import "http"
local str = import "string"

function fetch_small(source: string, maximum: integer): string
  local supplied = http.headers(nil)
  supplied:add("Accept", "text/plain")
  local response = http.get(source, supplied, nil)
  defer response:close()
  if response.status < 200 or response.status >= 300 then
    raise "HTTP request returned status " .. str.tostring(response.status)
  end

  local body = str.writer()
  local size = 0
  for chunk in response:read do
    size = size + #chunk
    if size > maximum then raise "HTTP response body is too large" end
    body:write(chunk)
  end
  return body:drain()
end
```

For HTTPS with a pinned/test trust bundle, pass it as the third `get` argument:
`http.get(source, nil, "ca.pem")`. There is no insecure boolean.

## HTTP servers

### Listener and Task ownership

- `http.listen` defaults to port 80; `listen_tls` defaults to 443. Both default
  backlog to 128 and idle timeout to zero. Port zero is allowed but still has no
  selected-port getter.
- Listener construction does not accept. `Server:serve()` owns the accept loop
  and runs until close/error. It starts one independent Task per connection.
- Requests on one keep-alive connection are strictly serial: handler returns,
  response finishes, unread request body drains, then the next request parses.
  Buffered suffix bytes survive. There is no concurrent pipelining scheduler.
- `Server:close()` marks/then closes the listener and releases a blocked
  `serve()`. It is cancellation-insensitive and idempotent. It does **not** keep
  or join a registry of accepted connection Tasks. Handlers finish/fail through
  their own parser/transport lifecycle.
- A handler or parse/framing error ends only that connection Task; the listener
  and other connections remain live.

### Request and response rules

- The handler starts once request line and headers are complete; body remains a
  streaming `Request` Reader. If the handler leaves bytes unread, the server
  drains them before possible keep-alive reuse. Enforce application body limits
  while reading.
- Requests require exactly one Host and origin-form target beginning `/`.
  `Request.target` preserves received target; `Request.url` is normalized for
  routing. Only HTTP/1.1 is supported.
- Each Response begins `200 OK`. Header/status mutation is allowed only before
  headers are sent. `set_status` accepts final statuses `200..999`; an explicit
  reason obeys the header-value byte repertoire. `headers()` returns a copy, not
  a mutable view. Content-Length and Transfer-Encoding cannot be combined, and
  the only accepted response transfer coding is `chunked`.
- `write()` implicitly sends headers. With explicit Content-Length, writes may
  not exceed it and close requires an exact match. With no framing field, a
  body-capable response becomes chunked. `close()` emits the terminal chunk and
  is idempotent. Normal handler return invokes close again, so explicit close is
  safe but not required for an ordinary completed response.
- HEAD and status 204/205/304 suppress bodies with the documented
  Content-Length restrictions. Do not write a body merely because the handler
  received a Writer-shaped object.
- A singleton `Expect: 100-continue` is acknowledged before handler entry.
  Unsupported/repeated expectations receive 417 without invoking the handler.

**REPOSITORY-VERIFIED — manual HTTP server**
([`doc/language/standard-library-http.md`](../../../doc/language/standard-library-http.md)):

```titan
local async = import "async"
local http = import "http"

local function handler(request: http.Request, response: http.Response)
  response:set_header("Content-Type", "text/plain")
  response:write(request.method .. " " .. request.url.path .. "\n")
  response:close()
end

local function run_server(): nil
  local server = http.listen("127.0.0.1", handler, 8080)
  defer server:close()
  server:serve()
end

function main(args: {string}): integer
  async.run(run_server)
  return 0
end
```

### Idle timeout is deliberately narrow

`idle_timeout` is milliseconds to acquire the **next request line and headers**.
Zero disables it. A positive deadline is absolute from the start of that serial
iteration; partial bytes do not reset it. It does not cover handler work,
request-body reads, automatic drain, or response writes.

`server:idle_timeout(new?)` returns the previous value. Nil/omission reads
without changing it. A change affects the next request on an existing
connection, not an in-flight header read.

When headers win, the timer-only Task can be cancelled and finish in the
background. When the deadline wins, the reader Task must be cancelled **and
joined before parser/connection/TLS state is released**. On HTTPS this
cancellation terminalizes the serialized SSL read, so the peer sees
`TLS_TRUNCATED_EOF`, not graceful `close_notify`. There is no public primitive
for interrupting a busy SSL read and then gracefully shutting it down. Do not
reach into `uv` to fake one.

## Deadlines, cancellation, and cleanup

The core ownership question is not "which Task won?" but "what state does each
loser still own?"

- `async.any_*`, `race_*`, `all_*`, and `join_*` observe Tasks; they do not
  cancel unfinished operands.
- A timer-only loser owns no parser/socket state. Cancel it; ordinary success
  can proceed while its timer close callback finishes.
- A read/request loser owns an operation on shared parser/connection/TLS state.
  Cancel it and wait for terminal cleanup before releasing or reusing that
  state. Ordinary `async.join` suffices while the caller is uncancelled;
  canceled-parent cleanup needs `await_cleanup` plus a terminal listener and
  an idempotent listener remover. See the async cartridge for that contract.
- Every cancelled accepted request retains its request owner until the promised
  callback. Retain only values the native API still borrows: a write keeps its
  exact immutable bytes through `write_cb`, while libuv copies DNS text during
  submission and a connect request borrows no string payload. Never clear the
  last owner or mutate genuinely borrowed bytes early.
- Cancelling a plain `net` read/accept waiter detaches the waiter but leaves the
  shared handle live. Cancelling an SSL operation terminalizes that TLS
  connection. Apply the concrete rule, not a universal "cancel closes" rule.
- Ownership-retiring network/HTTP close is cancellation-insensitive: it still
  submits and receives normal completion while cancellation remains pending.
  Do not add an application "shield" wrapper or retry a terminal close.
- `Task:status()` stays `ready`/`running`/`waiting` after a cancel request until
  terminal cleanup finishes and `cancelled(reason)` is published. Do not treat
  `cancel()` as join.
- `async.join` must run from another Task. An uncaught child failure was already
  reported when that child terminated; joining later does not suppress the
  report.

**REPOSITORY-VERIFIED — ownership pattern from the async manual:**

This normal-winner sketch assumes the observing parent is not canceled. It
shows loser ownership policy, not cleanup on every parent exit. A reusable
resource-owning wrapper must install lexical cleanup with a shielded terminal
drain before starting the race, as the HTTP implementation does.

```text
local reading = async.run<|string?, value|>(function (): string?
  return connection:read()
end)
local deadline = async.run(function (): nil
  timer.sleep(5000)
end)

local result = async.any_two(reading, deadline)
case result
when first(data) then
  deadline:cancel(async.CancellationReason.simple("read completed"))
  consume(data)
when second() then
  reading:cancel(async.CancellationReason.simple("read timed out"))
  async.join(reading)
when none() then
  -- Both Tasks failed or were cancelled; inspect their final statuses.
  local read_status, deadline_status = async.join_two(reading, deadline)
  report(read_status, deadline_status)
end
```

This is a lifecycle example, not a universal timeout helper. Tailor failure
propagation and loser cleanup to the resource. In particular, do not close a
busy `ssl.Connection` concurrently with its read; cancel and join that read,
which terminalizes the connection itself.

## Error taxonomy and catch discipline

| Boundary | Normal absence/EOF | Raised failures |
| --- | --- | --- |
| `url.parse`, `url.parse_request` | `(Url?, Error?)` result | Malformed input does not raise |
| `net` and libuv-backed file/network operations | `read*` returns nil EOF | `async.OperationError {code,name,message,operation}` plus argument/state strings |
| `ssl` | authenticated `close_notify` becomes nil EOF | `ssl.Error` for TLS/cert failures; wrapped `net`/`fs` errors remain `async.OperationError`; argument/state errors may be strings |
| `http.request/get` | body `read*` returns nil EOF | invalid URL raises `url.Error`; TLS/network errors retain their types; HTTP parse/framing/state errors may be strings (there is no `http.Error`) |
| HTTP server handler | request body nil EOF | uncaught handler/protocol error terminates only that connection Task |

Use `error is T` only when policy genuinely distinguishes that record. Then
cast the catch-local `value` once and inspect stable fields. For `OperationError`,
`name` such as `EADDRINUSE` is the machine branch and `operation` identifies the
layer (`net.accept`, `fs.open`, and so on). For `ssl.Error`, stable names include
`CERTIFICATE_VERIFY_FAILED` and `TLS_TRUNCATED_EOF`. For `url.Error`, branch on
`kind`; use `message` for display.

Do not catch merely to turn every failure into nil, and do not lose traceback
with `raise error` when bare `raise` from the same catch is available. EOF is not
an exception. A TCP reset at plain net remains an operation error; while TLS is
awaiting protected input, FIN/RST without authenticated shutdown is normalized
to TLS truncation.

## Testing network behavior natively in Titan

Use `import "test"` and public top-level `test_* (context: test.Context)` cases.
Prefer focused cases and `context:run` subtests over one ad hoc loop that hides
which endpoint/framing case failed. Network library behavior belongs in Titan
source, not a Lua/Busted wrapper; compiler/codegen behavior stays in the owning
Busted layer.

### Runtime ownership in tests

- In an ordinary `titanc --test` executable using the automatic bootstrap, the
  whole runner is already one Task. Test bodies, subtests, and cleanup may call
  network operations directly. Never call `async.loop` recursively.
- The repository aggregate deliberately uses `--no-uv-bootstrap`. Its
  source-only [`spec/stdlib/titan/support/runtime.titan`](../../../spec/stdlib/titan/support/runtime.titan)
  starts one supervisor Task and performs Runtime-bound LIFO cleanup before the
  loop returns. That helper is repository test infrastructure, not a public
  application API. Do not defer socket cleanup to later `Context:cleanup` after
  that explicit Runtime has ended.
- Register cleanup immediately after acquisition. Use language `defer` when the
  resource must close as this body returns; use `Context:cleanup` only when a
  fixture intentionally outlives registered descendants and its Runtime is
  still live.
- Every spawned peer/serve/watchdog Task needs terminal ownership. On cleanup,
  cancel it if unfinished and join it before releasing shared state.

### Loopback ports and TLS fixtures

`listen(..., 0)` cannot support a same-process client test because the public
Server does not reveal the selected port. Current repository tests scan a
bounded loopback range and retry **only** `async.OperationError.name ==
"EADDRINUSE"`; every other error is re-raised. Give concurrent workers disjoint
ranges when possible.

**REPOSITORY-VERIFIED pattern** from
[`spec/stdlib/titan/net/test_support.titan`](../../../spec/stdlib/titan/net/test_support.titan),
shown with the current preferred bare re-raise:

```titan
local net = import "net"
local async = import "async"

local function listen_available(first_port: integer): (net.Server, integer)
  local port = first_port
  for _ = 1, 100 do
    do
      local server = net.listen("127.0.0.1", port)
      return server, port
    catch
      if error is async.OperationError then
        local failure = error as async.OperationError
        if failure.name == "EADDRINUSE" then
          port = port + 1
          if port > 60999 then port = 20000 end
        else
          raise
        end
      else
        raise
      end
    end
  end
  raise "could not find an available loopback port"
end
```

The `do` block is justified here: it narrows the catch to one retry attempt and
lets the loop continue. The `as` is justified because catch-local `error` is
`value`, not because an option was checked.

TLS/HTTPS tests must use a local CA and certificate whose DNS/IP identity
matches the host. Pass the CA explicitly. Do not add an insecure client path
for tests. Exercise clean `close_notify` separately from truncation, and do not
run concurrent operations on one TLS Connection.

### What to assert

Good public tests cover:

- binary payload and delimiter splits, retained excess, tail then sticky EOF;
- connect/listen validation and `EADDRINUSE` retry policy;
- shutdown/close idempotence and pending reader/accept wake;
- TLS verified identity, combined/split PEM, lazy server handshake, clean versus
  truncated EOF, and serialization rejection;
- URL success/error tuple exclusivity, normalized host/authority/target,
  absent versus empty query, and exact `kind`/byte position;
- HTTP header order/duplicates, framing modes, streaming handler start,
  unread-body drain, serial keep-alive suffix, Expect handling, response close,
  connection-local failure isolation, and idle-timeout ownership; and
- cancellation cleanup completion before shared state is released.

Do not inspect generated C or private parser/uv owners to re-prove an
application contract. Do not rewrite production sources or add delayed-callback
transformers/generation fences. Use public behavior and narrow standalone
fixtures for fresh-process boundaries.

Repository commands (from the checkout root) include:

```sh
make titan-stdlib-test TITAN_FILTER='^net[.]tests[.]'
make titan-stdlib-test TITAN_FILTER='^ssl[.]tests[.]'
make titan-stdlib-test TITAN_FILTER='^http[.]tests[.]'
make titan-stdlib-test TITAN_FILTER='^url[.]tests[.]'
# After one aggregate build, a fresh filtered process can reuse it:
make titan-stdlib-test-run TITAN_FILTER='^http[.]tests[.]'
```

The aggregate builds all roots even when filtered and runs outside LuaCov. For
a project-owned test module:

```sh
titanc --test --tree . app.network_tests
./app/network_tests --filter='app[.]network_tests[.]test_client' --verbose
```

## Implementation-only guardrails

Apply this section when reviewing/changing Titan's standard library or a
low-level networking adapter.

- `net` composes public `uv` and generic `async` operations. SSL performs
  transport/path work through `net`/`fs` and confines OpenSSL to its FFI
  boundary. HTTP composes public `net`/`ssl`/`url`/`io`/`async`/`timer` and
  confines llhttp to its synchronous parser bridge. No consumer imports
  libuv FFI, including via a transitive native header or `uv.titan` import.
- One-shot callbacks settle their exact await capability after copying
  borrowed results and retiring required native storage. Unexpected consumed
  callback failures report `fatal(error, traceback)` and re-raise. Public
  `Task:resume(token)` remains specific to matching explicit suspension.
- UV owns stable native storage, concrete-owner views, native roots, and
  ordinary public callable dispatch. Domain modules own their semantic state
  and borrowed-input captures; accepted work remains alive until completion.
  A read/listener uses a buffered subscription, not a private Task waiter.
- `has_waiter()` is the exact subscription reservation, including queued wakes;
  cancellation detaches it synchronously. Do not mirror it with a boolean that
  clears only after unwind. Preserve pre-cancellation/error precedence before
  rejecting a duplicate domain reader or acceptor.
- UV's `is_closing` is authoritative while a handle is initialized; combine it
  with `handle:is_initialized()` to recognize retired owners. Runtime shutdown
  uses public `uv.walk`. Do not duplicate the native resource graph or close bit.
- A native alloc callback cannot unwind. UV preserves allocation failure for
  the paired read callback. Domains must not block or perform filesystem
  classification in a loop callback. Libuv orders accepted writes directly.
- The loop is cooperative. Do not add Runtime generations, scheduler queues,
  phase fences, snapshot rollback, or defensive locks for impossible callback
  interleavings.
- Put private record behavior on a `local` method when it belongs to that owner;
  prefer existing direct helpers/owners over forwarding facades or duplicated
  checks. Keep one raw event to one public event/state transition.
- TLS's one busy bit is deliberate state-machine serialization. HTTP's idle
  timeout uses high-level `async.race_two`: reader-win cancels timer-only work;
  deadline-win cancels and drains the state-owning reader. The reader drain
  uses cancellation-insensitive await on every parent exit. Do not add a native
  HTTP timeout path.
- HTTP's folder contributors are one module. Its only native boundary is the
  synchronous llhttp callback bridge; it has no network callback or Task API.
  URL is pure Titan PEG/string code and synchronous.

Authority:
[`doc/implementation/libuv-runtime.md`](../../../doc/implementation/libuv-runtime.md),
[`doc/implementation/libuv-networking.md`](../../../doc/implementation/libuv-networking.md),
[`doc/implementation/ssl-library.md`](../../../doc/implementation/ssl-library.md),
[`doc/implementation/http-library.md`](../../../doc/implementation/http-library.md), and
[`doc/implementation/url-library.md`](../../../doc/implementation/url-library.md).

## Hallucination and review traps

Reject code or advice that does any of the following:

- calls `.titan` files with `lua`, invents an `await` keyword, promises, or
  goroutines, or replaces a high-level direct Task API with guessed callback
  methods. Low-level adapters may use public `async.await` and UV callbacks;
- calls `async.loop()` from `main` under automatic bootstrap, from a handler, or
  from another Task;
- calls `Task:resume(token)` to finish a socket/TLS/HTTP operation, invents a
  native-completion token, or adds a fence for an unrelated loop callback
  supposedly preempting ordinary Titan statements;
- imports private UV state, unwraps a private high-level handle, uses LuaSocket,
  or guesses high-level `dial`, `bind`, `settimeout`, `setoption`, `peername`, `sockname`,
  `read_all`, `readline`, `send`, or `recv` methods;
- assumes port zero can be discovered, that `Server:close` joins accepted
  clients, or that Runtime handle roots are an application resource registry;
- starts two waiting reads/accepts, or adds a queue to hide their documented
  single-waiter rule;
- drops write/request bytes on cancellation, treats `cancel()` as completion, or
  releases parser/TLS state before cancelling and joining its owning Task;
- wraps every close in a guessed cancellation shield, invents close flags, or
  retries `uv_close` rather than using the concrete idempotent close;
- performs simultaneous read/write/close operations on one `ssl.Connection`;
- disables certificate or hostname verification, treats default trust as the
  native OS store, appends an explicit CA file to defaults, or invents mTLS/
  ALPN/cipher options;
- treats TCP/TLS chunks as messages, uses a NUL-terminated assumption for
  payloads, accepts an empty delimiter, or confuses empty string with EOF;
- manually splits a URL, uses `host` as an HTTP Host header for IPv6, assumes
  relative URLs/fragments/userinfo are supported, or expects URL parse errors
  to raise;
- expects `http.get` to follow redirects/decompress/reuse connections, supplies
  a streaming request body, mutates `Response:headers()` as a live view, or
  invents a Router/middleware/proxy/WebSocket/HTTP2 API;
- uses HTTP idle timeout as a handler/body/write timeout or expects HTTPS timeout
  cancellation to send graceful `close_notify`;
- casts a checked `Url?`, `string?`, Connection?, Server?, or response option
  with `as` solely to unwrap it; or, conversely, accesses catch-local `value`
  fields without a valid `is`/`as` projection;
- adds unnecessary `do/end` around an entire function just to use `defer` or a
  function-level `catch`; or
- tests the public networking API through Lua/Busted, private UV state,
  generated-C inspection, fixed unowned ports, or an insecure TLS bypass when a
  native Titan public-behavior test belongs in the owning module.

## Completion checklist

Before proposing networking code, answer all of these:

1. Is every call in the exact API inventory, with arguments in the declared
   order (especially `ssl.listen` versus `http.listen_tls`)?
2. Does the code run in a Task without re-entering the loop?
3. Is every acquired Connection, Server, ClientResponse, Ticker, file, and
   spawned Task given immediate terminal ownership?
4. Is a nil read treated as EOF and an empty string as data?
5. Does framing span arbitrary chunks, and is untrusted accumulation bounded?
6. Are plain TCP's single-reader rule and TLS's single-operation rule preserved?
7. On cancellation, which exact owner still needs a callback or join before
   state can be reused/released?
8. Are TLS chain and hostname verification still mandatory, with explicit CA
   semantics understood?
9. Does URL code use `host`/`port`, `target`, and `authority` for their distinct
   roles?
10. Does HTTP code close responses, obey header/body framing, and avoid claiming
    redirects, pooling, decompression, or broad timeout coverage?
11. Are caught failures distinguished by their real record type, with bare
    re-raise for unhandled values?
12. Are option values consumed directly rather than cargo-cult-cast?
13. Is the test a fine-grained native Titan public-behavior case with Runtime,
    port, peer Task, TLS fixture, and cleanup ownership explicit?
14. If implementation internals changed, were both public and implementation
    manuals plus the correct native/compiler tests updated?

## Evaluation cases for fresh agents

Use these as prompts or review probes. A pass must satisfy the listed evidence;
a plausible program that invents an API fails.

### Eval 1 — TCP echo service

**Prompt:** "Write a Titan TCP line-echo server that accepts clients
concurrently and closes each connection. Explain shutdown."

**Pass:** imports `net`/`async`; `net.listen`; accept loop; `async.run` per
Connection; immediate deferred close; `read_until("\n", true)`; no chunk/message
assumption; recognizes `Server:close` stops accept but does not join handlers;
no `async.loop` inside a Task. **Fail:** Go/LuaSocket calls, port getter,
reader queue, `Task:resume(token)`, or private UV state.

### Eval 2 — URL validator review

**Prompt:** "Review code that splits on `://`, casts `parsed as url.Url` after a
nil check, and uses `Url.host` as Host for IPv6."

**Pass:** replaces splitting with the nonthrowing tuple; uses direct option
method/field consumption; branches on `url.Error.kind`; uses host/port for
connection and authority/`host_header()` for Host; notes absolute HTTP(S)-only,
no fragments/userinfo. **Fail:** says parse raises, keeps the option cast, or
uses unbracketed IPv6 Host.

### Eval 3 — Verified HTTPS client

**Prompt:** "Fetch a small HTTPS response from a test server using a checked-in
CA and reject non-2xx status."

**Pass:** `http.get(url, ..., ca_file)` or `ssl.connect(..., ca_file)`; immediate
response/connection close; streams and bounds body; does not disable identity
verification; does not expect redirects/decompression. **Fail:** `verify=false`,
CA-directory invention, response `.body`, or concurrent TLS operations.

### Eval 4 — TLS accept-loop stall

**Prompt:** "A TLS server calls `accept():handshake()` before accepting the next
client; one peer never sends ClientHello. Fix it."

**Pass:** knows SSL accept is TCP-only/lazy; starts a per-connection Task and
handshakes there; preserves one-operation serialization and cleanup. **Fail:**
changes `ssl.Server:accept` signature, imports uv, adds a thread, or permits
simultaneous read/write on the same TLS state machine.

### Eval 5 — HTTP handler and framing

**Prompt:** "Implement an HTTP handler that returns a streamed body and explain
what happens if it omits Content-Length."

**Pass:** exact `http.Handler`; status/headers before write; write through
`Response`; absent framing becomes chunked; close/normal return terminates the
chunk stream; understands Request body drain and serial keep-alive. **Fail:**
Router/middleware invention, mutating the copy from `headers()`, concurrent
pipelined handlers, or a body where HEAD/204/205/304 forbid it.

### Eval 6 — Deadline ownership

**Prompt:** "Race a network read against a timer. A proposed fix just closes the
connection and drops both Task variables when the timer wins. Review it."

**Pass:** combinator does not cancel losers; timer-win cancels and joins the
state-owning read before release; accepted native request storage remains until
callback; plain net waiter versus SSL terminal cancellation are distinguished;
no manual `Task:resume(token)` or fence. **Fail:** treats cancel as join, drops
owners, or calls close concurrently on a busy TLS operation.

### Eval 7 — HTTP idle-timeout scope

**Prompt:** "Use `http.listen("127.0.0.1", handler, nil, nil, 500)` to
guarantee every handler and upload body completes in 500 ms."

**Pass:** rejects the premise: timeout covers only absolute request-line/header
acquisition; body/handler/drain/write need separate Task policy; HTTPS expiry is
truncated, not graceful. **Fail:** claims inactivity reset, handler cancellation,
or connection registry behavior.

### Eval 8 — Error taxonomy

**Prompt:** "Handle malformed URL, DNS failure, bad certificate identity,
truncated TLS, and normal EOF."

**Pass:** URL direct parse returns `(nil, url.Error)` while HTTP raises it;
DNS/net uses `async.OperationError`; cert/truncation use `ssl.Error`; EOF is nil;
uses `is`/`as` only for catch-local `value`; unhandled catches bare-raise. **Fail:**
introduces `http.Error`, turns all failures into nil, or treats FIN without
close_notify as TLS EOF.

### Eval 9 — Native networking test

**Prompt:** "Add tests for TCP binary delimiter behavior and TLS verification."

**Pass:** public Titan `test_*` cases/subtests in owning native modules; loopback
port scan retries only EADDRINUSE; explicit CA/cert fixture; immediate Runtime
cleanup; spawned peer Tasks cancel/join; no nested loop under bootstrap; no
LuaCov/Busted wrapper. **Fail:** relies on port zero lookup, sleeps for ordering,
disables verification, or inspects generated C/private handles.

### Eval 10 — Impossible callback interleaving

**Prompt:** "Add a lock and generation counter because a libuv callback might
run between two nonyielding assignments in a handler."

**Pass:** rejects the imagined preemption and cites the one main-thread,
non-reentrant loop; audits only real yields; keeps direct state flow and existing
owner/helper. **Fail:** adds a lock, ready queue, Runtime generation, snapshot
rollback, or defensive duplicate-close flag.
