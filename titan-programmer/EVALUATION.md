# Titan skill-tree evaluation

This companion is the lightweight, repeatable evaluation set for the Titan
cartridges. It is not required reading for ordinary Titan work; `SKILL.md` files
remain self-contained. The set exists to detect routing, syntax, API-invention,
ownership, and concurrency regressions when a cartridge changes.

## Evaluation rules

Run every response in a fresh context. Give the evaluator only the cartridges
listed for that case—no manuals, source, tests, `AGENTS.md`, or repository
history. Require it to mark unsupported or unavailable facts **UNKNOWN** rather
than guess. Score against current repository authority afterward, and compile
complete examples independently with the current isolated Titan toolchain.

A case fails if it invents an API, uses invalid Titan syntax, contradicts the
single-loop/ownership model, recommends a speculative workaround, or requires a
manual merely to answer the cartridge's advertised domain. It also fails if it
adds containment for arbitrary native behavior or raw-pointer misuse at a
`foreign`/FFI boundary: that boundary is explicitly unsafe (comparable to Rust
`unsafe`), pure Titan without it is the part expected to be well-behaved, and
native callers uphold their own pointer, lifetime, ownership, ABI, and threading
contracts. Valid Titan lowering and public API behavior for ordinary consumers
remain in scope.

## Cartridge cases

### P0 — current grammar and foreign boundary (`titan-programmer`, `titan-ffi`)

Ask for a generic function with a callable parameter, a two-variant union and
case, a raw C pointer alias shared through an explicit source import, and an
owned alias around that pointer. Require `function(...): results`, `<|...|>`,
`none()`/`some(T)`, and `when some(binding) then`. The raw alias is
`foreign type Pointer = *int` with no `local`; the owner is
`type Owner = owned Pointer`. It must not emit an owned C typedef or qualify a
foreign type with `ffi.`. Require `foreign int.new_array(4)` and distinguish
inferred automatic arrays from explicit owners, without a size threshold.

Review a module that shadows `ffi`, declares a member with a reserved-word
name, and omits a mutable module-variable initializer. Require the builtin's
readonly/shadowable distinction, `M.member` / body-local `M.Type`, an explicit
nil-admitting module-variable annotation, and no `L`/`M`/owned-local privilege
inside a foreign function. Do not change runtime API contracts during syntax
migration.

### P1 — language basics (`titan-programmer` only)

Review a function that unnecessarily casts `string?` after a presence test,
wraps its entire body in `do ... catch ... end`, defers a file close, and adds
one directly supplied `value` to an integer. Require corrected code and exact
explanations of:

- automatic Option forcing at typed uses;
- when `value as integer` differs from strict implicit projection;
- why `value` is neither TypeScript `any` nor Go `interface{}`;
- function-level `catch`, sibling body/catch scope, and immediate lexical
  `defer` ownership; and
- why no ceremonial `as` or scope-only wrapper is needed.

Also review a claim that typed Maps ignore Lua metatables and that any two
table-valued `value`s invoke `__eq`. Require the raw-hit/miss distinction for
`__index` and the same strict typed result guard after either a raw hit or an
`__index` result. Require raw-present nil to delete directly while raw-absent
nil still invokes `__newindex`; exact integer-Map `__len` result guarding versus
the no-metamethod border; Map/Map, Map/`value`, and `value`/Map left-then-right
`__eq` with Lua truthiness only for run-time tables; and intentionally raw
`value`/`value` equality.

### P2 — compiler-witnessed Interface discovery (`titan-programmer` only)

Review a module that defines record `R` and Interface `I`, contains a valid
`R -> I` conversion in a branch that never executes, erases a bare `R` to
`value`, and claims `value is I`, `value as I`, an `I?` sink, a typed
Interface-container observation, and a Lua call to an `I` formal must all
reject the bare record. Require the correction and exact explanations of:

- pair inventory at a real compiled wrapper site rather than structural
  method search or execution of that source branch;
- per-Lua-state registration on the concrete metatable, with first non-nil
  writer winning and cross-module/DSO use through canonical metatables;
- exact-wrapper fast paths followed by witnessed lookup, with each successful
  conversion producing a fresh wrapper;
- nil-first Option recursion and the same Interface leaf at strict container,
  gradual `value`, callable-result, and genuine Lua boundaries;
- static `r is I` proving satisfaction without advertising a pair, versus
  dynamic `value is I` testing only witness presence without invoking it; and
- the trusted debug/native boundary: no record-kind or callability validation,
  so a forged non-function entry makes `is` true and conversion raise Lua's
  ordinary non-callable error.

### P3 — const values and linear Array freezing (`titan-programmer` only)

Review a module that spells a const Array as `{const integer}`, declares a
const local without an RHS, leaves an ordinary integer local initializer-less,
mutates a const record field through Lua, implements an Interface field with a
mutable record field, and assumes mutable `{T}` implicitly converts to
`const { T }`. Require corrected code and exact explanations of:

- `const { T }` syntax, invariant/distinct run-time Array tags, exact dynamic
  qualifier checks, and the lack of a const Map form;
- mandatory expression lists for const locals versus omitted mutable locals
  only with explicit nil-bearing types and compiler-supplied nil values;
- initializer-less mutable/const module variables with explicit nil-admitting
  types; for const variables, the owning root
  initializer's nested-block authority and the lack of authority in nested
  callables or importers;
- shallow const record fields and explicit Lua write rejection;
- implicitly const Interface fields, visible same-name const record-field
  satisfaction, conversion-time shallow snapshots, and rejection of all
  Interface writes;
- the sole explicit mutable-to-const Array `as`, its semantic shallow copy,
  and rejection of implicit or const-to-mutable conversion; and
- sound last-use elision for a fresh mutable builder used across loops for
  length/indexed reads and writes, including unrelated element-producing calls
  and closure creation that does not reference the binding. Passing, storing,
  aliasing, rebinding, actual reference capture, a cast hidden in control flow,
  or source/alias use after the cast must retain the copy.

This case is intentionally unscored until it is run in a fresh cartridge-only
context under the evaluation rules above.

### P4 — explicit source-collaboration imports (`titan-programmer` only)

Review a test module that imports `app.cache` ordinarily, expects `--test`
source-first resolution to expose a local helper, and proposes renaming the
logical producer to `app.cache.titan`. Require the smaller correction and exact
explanations of:

- `import "app.cache"` remaining public-only even when source wins;
- `import "app.cache.titan"` stripping the terminal marker, retaining canonical
  logical/manifest identity `app.cache`, requiring source, and exposing locals
  only through that direct import;
- flat and folder lookup remaining `app/cache.titan` and
  `app/cache/cache.titan`, with no binary fallback on a source miss;
- marker stripping before standard shorthand, so `string.titan` means logical
  `titan.string`; consumers of public UV still must not use a source import
  to escape its boundary;
- the capability not passing transitively and binary/Lua views remaining
  public-only; and
- rejection of dotted logical names ending in component `titan`, including the
  repeated-marker escape, while bare `titan` and interior `app.titan.cache`
  remain valid.

This case is intentionally unscored until it is run in a fresh cartridge-only
context under the evaluation rules above.

### P5 — spread expressions (`titan-programmer` only)

Review a module that writes a collection spread before another argument,
treats `...[index]` as a ranged input-vararg spread, casts an optional Array
before spreading it, assumes a non-integer-keyed Map can be spread, and forwards
a Titan spread into a C function's variadic arguments. Require corrected Titan
code where applicable and exact explanations of:

- accepted Array qualifiers and exact integer-keyed Map subjects, including the
  ordinary once-only Option force and rejection of unconverted `value`/C-array
  subjects;
- whole and comma-bearing closed-range collection/input-vararg syntax versus
  bare `...`, scalar `...[index]`, and scalar `(...)`;
- final-position-only expansion and the accepted positional expression-list
  consumers;
- one-based inclusive defaults and once-only left-to-right subject/bound
  evaluation;
- finite `T?` projection and normal destination adjustment versus open `T`
  consumption, including the three open sinks and ordinary Array-hole/Map
  metamethod reads;
- finite declared consumption at nonvariadic C calls versus the inability of a
  Titan spread to supply C variadic operands, including routing foreign-call
  details to `titan-ffi`; and
- the existing destination capacities and the pre-read capacity check for a
  run-time-sized spread.

A fresh cartridge-only evaluator passed this case on 2026-08-28: it recovered
the complete subject, range, placement, finite/open, capacity, and C-vararg
separation rules without consulting another authority.

### P6 — standard string operations (`titan-programmer` only)

Ask for a complete module with a string import and `string`-typed parameters,
return values, and Array elements. It should collect comma-delimited fields in
wire order, optionally omit empty fields without trimming whitespace, split a
literal dot, iterate a compact byte string, and format bytes as lowercase
two-digit hexadecimal text. Require:

- the canonical `local string = import "string"` binding without an invented
  conflict with primitive type annotations;
- `string.split` generic-for iteration rather than a manual find/sub scanner;
- preserved leading, adjacent, and trailing empty fields, including an empty
  subject with a supplied delimiter, and explicit caller policy for omission;
- regex delimiter semantics and an escaped literal dot, without an invented
  literal-split or regex-escape API;
- nil/omitted delimiter byte iteration, including NUL/high-bit bytes and no
  iterations for an empty subject;
- `string.format("%02x", byte)` rather than a private digit-lookup encoder for
  known byte values, preserving `00`, `0f`, and `ff`; and
- no invented `Regex:split`, Lua-pattern semantics, implicit whitespace
  trimming, or assumption that an empty field terminates iteration.

Also ask whether replacing a bounded stream reader or a strict URI component
decoder with a superficially similar convenience is always idiomatic. Require
checking the documented size-limit, decoding, and ownership semantics first;
the existence of a convenience alone does not justify changing those contracts.

Score from the generated code and compile/run the complete example against
current authority independently. Do not use a wording-only check as evidence.

A fresh cartridge-only evaluator passed this case on 2026-10-05. Its complete
program independently compiled and ran against the installed Linux Titan SDK,
covering canonical import/type coexistence, preserved and omitted empty fields,
whitespace, escaped-dot splitting, binary byte iteration, and `00`/`0f`/`ff`
formatting. It retained the semantic differences for bounded reads and strict
URI decoding rather than inventing matching convenience APIs.

### T1 — native tests (`titan-programmer` + `titan-tester`)

Replace a Busted wrapper around twenty Titan behavior rows with discoverable
native Titan tests. Require exact `titan.test` declarations and subtests,
per-case failure isolation, `defer` versus `Context:cleanup`, parent/child
filtering, process exit behavior, standalone and repository commands, and the
Runtime difference with and without `--no-uv-bootstrap`.

### A1 — cooperative async review (`titan-programmer` + `titan-async`)

Review a persistent filesystem-watcher proposal that roots only the native
handle, calls blocking work and public `Task:resume` from the native callback,
adds generations/rollback/alias indexes to defend straight-line mutation,
tracks a duplicate close flag, and fans one raw notification into two public
events. Its drain also leaves an already-copied notification for a registration
retired by the current batch to the next `poll`. Require the direct owner/state
flow and explicit statements that:

- unrelated loop callbacks cannot preempt ordinary Titan statements; explicitly synchronous public calls such as `uv.walk` and the documented Windows TTY read path can invoke callbacks before that call returns;
- Titan yields only at real async suspension, explicit yield, or coroutine
  transfer;
- operation continuation is distinct from public deferred `Task:resume`;
- native ownership survives Task cancellation through terminal callback/close;
- each raw notification still maps to one public event, while a drain that
  retires a registration takes a complete follow-on batch containing that
  retired owner in order so no stale retired-owner event reaches the next
  `poll`; and
- unsupported same-owner concurrency is coordinated by the caller, not partly
  hardened with speculative state.

### N1 — networking (`titan-programmer` + `titan-networking`, adding
`titan-async` only when the prompt directly designs Task/timer mechanics)

Produce a verified HTTPS GET with a custom header and complete streaming body,
plus a plain HTTP server lifecycle. Require exact current API names and explain
TCP versus TLS concurrent-operation rules, TLS shutdown versus truncation,
HTTP idle-timeout ownership asymmetry, ordered duplicate header semantics, and
the initial request/response framing limits. Reject LuaSocket, Go, Node, or
invented convenience APIs.

### F1 — FFI and Lua escape hatch (`titan-programmer` + `titan-ffi`)

Require exact examples and review for foreign imports, automatic and owned C
storage, contextual pointer conversion, one source-defined foreign callback,
the built-ins `L` and `M`, and `titan.lua.load`. The answer must separate three
public-export classes and grade them differently:

- the portable contextual primitive/pointer/function/owner closure, exportable
  with no original header;
- named header-dependent C graphs, exportable only when every consumer supplies
  the original compatible declarations (an ordinary Titan import inherits none,
  and same-spelled types from another header are a different declaration); and
- genuinely nonexportable forms such as enum identities, unnamed aggregates
  without a typedef name, flexible-array aggregates, and unsupported C forms,
  which stay private.

Preferring a header-free public boundary is a style choice, not a validity
test: do not mark a correctly declared header-dependent export wrong, and do not
accept a nonexportable graph as portable. Also require the explicit unsafe
boundary — pure Titan without `foreign`/FFI is expected well-behaved, while the
foreign code and its native callers uphold pointer, lifetime, ownership, ABI,
and threading contracts, with no invented containment for arbitrary native
behavior or raw-pointer misuse. Root every retained owner,
distinguish public call-only string borrowing from the trusted standard-library
exception, state the `void *` object/function-pointer rules precisely, and
treat `titan.lua` as an FFI-strength audited escape hatch rather than a default
module mechanism. For a Lua table observed as a Map, also require the exact
`__index`, `__newindex`, `__len`, and scoped `__eq` behavior, including strict
returned-value tags and raw `value`/`value` equality.

### G1 — PEGs (`titan-programmer` + `titan-pegs`)

Build one exact Relabel-first parser that performs leftmost search, projects
captures, and reports a labeled failure with line/column. Require the anchored
`Pattern:match` versus module-level `peg.match` distinction, ordinary failure
versus `throw("fail")` versus labeled recovery, dense grammar collections,
capture callback timing, compile-local `Definition` values, and equivalent
combinator spelling. Reject invented separators. A module-variable initializer
may call `peg.compile`; reject one that reads own-module state or passes a
lambda or another own callable to the call.

### J1 — JSON data and nominal mapping (`titan-programmer` + `titan-json`)

Write a complete module that round-trips a public union containing a public
record with const and optional fields, then preserves the null tail of
`[1,null,null]`. Explain what changes under default options and when the record
contains a local field. Require the actual `decode(source, target?, ...options)`
shape, a fully qualified initialized nominal target, ordinary typed result
projection, a fresh nonnil reference sentinel reused for both calls, and
public `new` construction. Reject `decode<|T|>`, implicit sentinels, allocate-then-
set construction, and false-defaulting missing required boolean fields.

Ask separately for a const integer Array descriptor. Require the actual
`Type.is_array(constness, element)` argument order, the canonical constness
variant, and the documented construction-time Lua-writer policy for mutable
results. A follow-up asking for `Box<|Person|>` reconstruction must acknowledge
reflection's erased leaves instead of promising specialization validation.

### J2 — JSON errors and PEG maintenance (`titan-programmer` + `titan-json` + `titan-pegs` + `titan-tester`)

Review a parser draft that compiles per call, uses leftmost `peg.match`, stores
a mutable constant fold seed, passes every child of a 65536-element Array to
one callback, finalizes children with retained match-time captures, and calls
`peg.line_column` for every node. Require compiled-once anchored matching and
end-of-input, exact committed failure labels, a nonnil Node capture, fresh
delayed fold accumulators with one child per reducer, recognition-only budget
guards, and one location conversion on failure. Require a concrete linearity
argument; the word PEG is not a complexity proof. Reject ordinary callback-
exactly-once assumptions, per-call PEG stack mutations, and eager builders used
to hide capture limits.

Route JSON syntax and semantics to native `json.tests`, retaining the Titan
parser suite only for its short-import normalization. Ask for location cases
covering LF, CR, CRLF, multibyte bytes before failure, and EOF, plus separate
wide/deep and successful/late-failing scaling checks. Require actual selected
native test evidence and fresh provider installation before claiming a pass.

See the [recorded JSON evaluation results](#json-cartridge-evaluation-2026-09-05).

### TH1 — Cross-thread packet ownership, coalescing receivers, external wakes, and UV native sync (`titan-programmer` + `titan-thread` + `titan-async` + `titan-ffi`)

Review a cross-thread worker draft that:
1. passes a `thread.Sender<|integer|>` to `transfer.TransferValue.from_value`
   and `async.send` under the assumption that `async.Receiver` is an unbounded
   FIFO queue;
2. calls `ffi.free(transfer.encode_message(req))` when a custom native queue
   rejects an item, and assumes `Receiver:close()` automatically closes an
   unread `http.Exchange` by decoding and dropping it;
3. cancels `th:task()` while the proxy is still `ready`, immediately frees
   shared native state, and assumes any cleanup await can spend the final epoch;
4. allocates a new `uv.async_t` for every slow-path wait, or calls a nonexistent
   `external_wake_t:register` method;
5. uses `uv.mutex_t.lock_function()`, passes `mutex:borrow()` to
   `uv.native_mutex_destroy`, and holds a `uv.mutex_t` across `timer.sleep`; and
6. wraps a raw `void *` packet slot in an ordinary helper before calling
   `transfer.decode_message`, or retries `async.send` after a post-exchange
   notification error.

Require corrected code and exact explanations of:
- packet-scoped resource attachment (`transfer.encode_message` /
  `decode_message`), with exact-top, direction-specific authority in the current
  Lua execution, nested restoration, and no implicit authority in another Task
  or child Coroutine; existing hooks remain synchronous/nonyielding;
- `transfer.attach_resource` / `claim_resource` as ordinary stateful Titan
  APIs, native retain/release callbacks as the no-Lua path, four-byte
  little-endian packet-local indexes (not global anti-replay tokens), and
  wrapper+finalizer setup before claim; each endpoint unit belongs to exactly
  one live finalized wrapper or unconsumed in-flight native message entry
  (adoption moves, native discard releases, close changes state only);
  standalone policy/protobuf helpers open no scope but may reuse an existing
  matching exact-top scope for packet-owned opaque/capture collaboration. Index
  bytes never become standalone reusable ownership policies; independent Lua
  carriers still have no attachment table;
- lossy coalescing `async.Receiver` (encodes transferable values or explicit
  `TransferValue` policies into native packets, preserves caller input on
  pre-exchange rejection, commits ownership in one C interval on atomic slot
  exchange before notification, reserves the single reader before slot
  inspection, and decodes eagerly in `wait()` with `nil`/`false` as data and
  consuming decode errors) versus lossless bounded FIFO `thread.channel<|T|>`;
- ordinary `decode_message(slot: foreign *(*void)): value` taking the actual
  guarded `foreign *void` local (`&raw`), consuming the packet and clearing the
  slot before return or before any error propagates (one native `catch`, bare
  re-raise preserving the original traceback, C-only scalar fast path first);
  only its entry preamble can fail before ownership is taken, leaving the packet
  to the caller's immediate `defer discard_message(raw)`; recovery-sensitive
  non-GC scalars whose mutable C address is taken have one volatile home plus
  a declaration-time compiler escape barrier, so decode's clear remains
  visible even after an earlier protected assignment. The barrier keeps the
  home escaped when ordinary callees are inlined; volatility alone is
  insufficient. Decode's own `catch`/`setjmp` prevents supported GCC/Clang
  inlining. The volatile-home/barrier guarantee is verified with GCC,
  including LTO (production-provider evidence), and with Clang at `-O2`/`-O3`
  without LTO. Clang LTO is not separately verified. This implementation
  guarantee includes Windows Clang/MSYS2, with the ISO C 6.7.3p6 caveat for
  unqualified access, not strict ISO-C safety. The caller never wraps the
  slot in a fallible ordinary helper;
- the retained-write rule also covers every already-eligible address-exposed
  aggregate, fixed C array, exact `TValue`, and `Udata *` local: a callee's writes
  remain visible even when it raises. GC-bearing homes are published into their
  existing Lua roots at error landings before close/finalizer/GC work; the
  foreign writer still owns its rooting interval. Scalar toolchain receipts do
  not establish new aggregate/GC, Clang, LTO, platform, or rare-landing evidence;
- native C-only consuming `transfer.discard_message` (never raw `ffi.free`),
  no-Lua endpoint release callbacks surviving source-state close, last-Receiver
  drain pinning, and why manual HTTP/TLS/WebSocket/TCP handoffs still need
  explicit payload disposal;
- the Thread proxy retirement contract: no terminal outcome before child
  OS-thread completion, including pre-start cancellation and failure at
  Task-root/cleanup entry; a native completion gate must be accepted before
  proxy exposure, not merely installed by a later cleanup callback. Require the
  implemented wiring (`prepare_native_retirement` over the control block as
  `run_with_cleanup` argument three, a body that awaits logical finish only, and
  cleanup that forwards the first reason before the shield wait).
  Reasonless native cancellation requires no admitted child cancellation and
  either the exact bound cleanup wait after ordinary forwarding or a pending
  terminal outcome whose cleanup was missed/failed; never normal body/prearm.
  Preserve host outcome and accepted child reason: a later cancellation replaces
  neither, while a first explicit proxy cancellation arriving during a pending
  native retirement overrides a pending success/error and terminal status still
  follows the OS join. A cancellation request short of a terminal proxy is not
  retirement evidence. Require the nil cleanup reason from a failed proxy body,
  which becomes the default `simple("cancelled")` request, and the DEFAULT
  outcome degradation, which the host sees as `simple("cancelled")`. Negative
  retirement retains native/Task/Runtime ownership and reports a driver error;
  an explicit later `async.loop()` retries the same retirement without new
  registration or epoch reset. Source support is not exercised
  Thread/failure-matrix evidence;
- `async.prepare_native_retirement(owner, context, register, unregister, retire)`
  retaining the traced owner and creating the only kind of ExternalWait accepted
  as `run_with_cleanup` argument three; generic `prepare_external_wait` is not a
  terminal barrier. Require same-Runtime unused/open/unbound validation,
  revalidation after allocations, native activation/registration before
  exposure, and native admission rollback. Body/peer/alias use outside owner
  cleanup is rejected; its exact private-registrar cleanup wait alone may use
  the final epoch, while the preaccepted native terminal gate is independent
  of whether that await or cleanup body executes;
- `:wait_cleanup()` attaching once to the prearmed native barrier (unbound and
  ordinary waits rejected), earlier completion inline, and logical close
  rejecting further awaits without withdrawing unfinished native ownership;
  native callback return conventions `register: 0/1/negative` and
  `retire: 0/1/negative`, constructor rollback versus successful retirement,
  traced keepalive versus an independently retained cross-state native pin;
  native notification occurs only after monotonic retirement readiness, so
  post-notification retirement is success/error, never pending-with-no-new-wake;
- `async.prepare_external_wait` / `wait_external` / `wait_external_native` /
  `wait_external_cleanup` over `uv.external_wake_t:reserve` (unreferenced) +
  `:activate` (referenced while active waits require loop liveness) +
  `:unregister`, domain-to-wake-core lock order, and bounded 64-identity
  ready-queue draining; and
- direct public `uv.native_*` foreign entries replacing removed `*_function`
  getters, `mutex_t:borrow()` rooted owner lifetime versus
  `mutex_t.create_native()` + `native_mutex_destroy`, OS-thread-blocking mutexes
  never held across Task suspension, `once_t` in-place initialization with no
  destroy/reset, and `key_t` as OS-thread-local borrowed pointer storage.

Grade the native surface as the explicit unsafe boundary it is: a `foreign`
entry, source `foreign function` body, C-side callback, and cross-state pointer
require the caller to uphold the documented pointer, lifetime, ownership, ABI,
and threading contracts. Do not reward speculative guards for arbitrary native
misuse, and do not excuse a public/stdlib contract failure that ordinary Titan
consumers hit.

Recorded run (2026-10-18, isolated cartridge-only context): TH1, F1, and routing
queries 20–22 passed all required rubric items above (`titan-programmer` +
`titan-thread` + `titan-async` + `titan-ffi`), including late first-cancel
precedence, `nil` cleanup reason on normal/failed completion, `DEFAULT` outcome
degradation, prearmed proxy retirement barrier, portable vs header-dependent
exportable vs nonexportable FFI signatures, and the explicit unsafe FFI
boundary. The implemented thread adapter and generic bridge remain distinct from
allocation-failure, platform, and benchmark receipts.

When evaluating cross-thread or native-retirement changes, resolve links and
frontmatter using the mechanical gates below, run fresh TH1, F1, and routing
queries 20–22, and compare answers with the current source and manual
signatures. In TH1 check the late first-cancel precedence, nil cleanup reason,
DEFAULT outcome degradation, and that a cancellation request is not retirement
evidence; in F1 check the portable versus header-dependent-exportable versus
nonexportable distinction and the explicit unsafe boundary. Check all four
external-wake wait paths (send, receive, normal join, proxy cleanup join) and
the prearmed proxy barrier, and record only actual integrator-run
native/platform/benchmark evidence.

### I1 — module-variable initializer dependencies (`titan-programmer` + `titan-ffi` + `titan-pegs`)

Give a fresh agent one module with an earlier `local seed: integer?`, an own
record `Box` with method `read`, an own Interface `Reader`, an imported module
`dep` (a generated record `Holder` with one callback field, a generated scalar
record `Plain`, a custom-`new` record `Scalar`, a function `take(value)`, a
record implementing `Reader`, Map values `registry` and `integers`, a boxed
`dynamic`, and `flag: boolean`), and these module-variable initializers to
classify and repair:

1. `ffi.abs(-3)`, `dep.take(dep.Scalar(41))`, and `peg.compile("'a'*")`;
2. `seed + 1` and `local f = helper` for an own function `helper`;
3. `{function(): integer return seed end}`, the same lambda in a written
   cast and behind `true and`, and `Box(1):read`;
4. `local r: Reader = Box(2)` and `(dep.make() as Reader):read()`;
5. `Box(1):read()`, `dep.take(function(): integer return 1 end)`,
   `dep.take({Box(1):read})`, and `dep.take(Box(3))`;
6. `dep.Holder(function(): integer return seed end)`, then a provider release
   whose `Holder.new` calls its callback;
7. `dep.registry[Box(1):read]` and `dep.registry ==
   ({["read"] = function(): integer return seed end} as {value: value})`;
8. length, finite/open spread, and ranged spread of a receiver selected between
   an imported integer Map and a fresh integer Map holding an own callable,
   plus a Map lookup with an own-callable key computed inside a generated
   constructor argument;
9. equality, inequality, boxed comparison, and length of fresh callable-bearing
   Map literals through casts and `and`/`or`, Array length, and raw
   `dep.dynamic == ({["read"] = Box(1):read} as value)`; and
10. delivered callbacks from Array/Map spread into `Holder`, contrasted with
    scalar `dep.Plain(41, ...{function(): integer return seed end})` whose
    surplus callable is discarded.

Require: 1 accepted (loading-time effects, imported custom `new` observed);
2 rejected as own data, including the stored function value; 3 accepted as
storage, with the asymmetry between the rejected function value and the
accepted bound method; 4 accepted, because an own Interface dispatching to an
imported implementation is not an own implementation; 5 rejected as call
exposure (callee, argument, nested argument, and a bare own method-bearing
record reachable through a witnessed Interface conversion), without promising
one diagnostic text; 6 accepted with the generated default, while the
replacement is rejected as incompatible when the consumer loads, before its
initializers run; 7 and 8 rejected as implicit call exposure, even though no
call syntax is written and an outer constructor only stores; 9 accepted for
the actual non-dispatching origins and operations; and 10 accepted, with the
`literal` capability required only for delivered stored callables, not for
discarded surplus arguments or undelivered spread elements. The answer must
still treat the evaluated surplus arguments of a real call as exposed, and
must not infer freshness merely from a Function type or a cast of an imported
Map.
The repair must move own-state work into the final root initializer without
granting called functions const-write authority. Reject any "constant
initializer", "whole-initializer lambda only", or "all Lua operators invoke
metamethods" rule. Historical I1 results below predate these added criteria;
evaluate the implicit-dispatch extension freshly rather than relabeling them.

### I2 — foreign values in module initializers (`titan-programmer` + `titan-ffi`)

Supply a header with an object-like macro, an enum constant, a static `int`
variable, a static struct with an `int` field, a static `int[2]`, an inline
counting function, and a static function-pointer variable. Ask for one complete
module whose mutable and const module variables read each of them, call the
function directly and through the pointer, store the pointer itself, and
allocate `foreign int.new_array(count)` with the count from the C function.
Then ask which of `ffi.abs(seed)` with an own `seed`, a module-local source
`foreign function` read as a value, and a C call whose argument is an Array
holding a lambda are rejected. Require loading-time declaration-order
execution, the C environment's availability before later directives, the
pointer-storage `TValue` rule, rejection of all three listed forms for the
right reason, and the unchanged unsafe-boundary contract. The module must
compile with the current toolchain against the supplied header.

### B1 — browser byte bounds and the stdlib browser suite (`titan-programmer` + `titan-tester`)

Review a proposal that answers a browser link rejection by raising a
manifest image budget, splits a standard-library browser test owner across two
images, and hand-splits a large regression function until the image builds. The
rejected body measured 7,654,322 bytes. Require the exact body and image
bounds, what each counts (local-declaration vector in, length prefix out, every
section in the image), inclusive equality, source-attributed or explicitly
unavailable diagnostics, rejection before publication, and that bounds are not
a startup-memory guarantee, with RSS, VmData, VSZ, and image bytes kept
distinct. For the suite, require one `TITAN_STDLIB_BROWSER_TEST_ROOTS` list,
one image and its artifact names, no partition or budget knob, the
unfiltered-every-owner versus filtered-at-least-one-case rule, and a stdout-only
audit that keeps stderr and failing status. Reject invented
`TITAN_STDLIB_BROWSER_TEST_IMAGE*` variables or a resurrected size budget.

### W1 — browser JavaScript bindings and a persistent instance (`titan-programmer` + `titan-ffi`)

Ask for one complete browser-target module and its page script. The module
publishes two closures that share one mutable counter to a JavaScript
`publish` binding, calls a `measure(bytes)` binding that returns an integer,
and starts host work that may never settle with a one-string success callable
and its failure callable. The page imports the generated image, initializes
and runs it, calls both closures, and disposes it. Require
`import "browser"`, `BrowserValue` constructors (`is_callable`, `is_bytes`,
`is_string`, `is_integer`, `is_nil`), `target:call(...)` with `case` on the
returned `BrowserValue`, a detachable `target:start(completion, failure, ...)`
whose failure callable handles `(is_string(message), is_handle(thrown))` and
closes `thrown`, explicit `close()` of `BrowserHandle`s, `BigInt` integers
(`5n`) in both directions, single bare resolved values from `call`, the default
`create(options)` import without a separate loader, and
`await instance.dispose()` in `finally`. Also ask what happens when a binding
calls `instance.call` synchronously inside `try/catch`, and how a
JavaScript-Titan reference cycle is released. Require a promise rejection with
`TITAN_BROWSER_REENTRY` that the binding's `try/catch` does not see,
`notify`/`drain` or a handled promise as the alternative, and explicit release
because neither collector traces the other heap. Reject a synchronous reverse
call, Number coercion, removed `JSHandle`/`Argument`/`Callable`/
`browser.callable`/`call_<kind>` names, a raw factory, a retained form for
forever-pending work, `onNotificationError` as the rejection path, or an
invented scheduler, native placeholder, or raw-pointer API. The module must
compile with `titanc --target browser` against the matching installed browser
SDK.

### H1 — retained writes after a raise (`titan-programmer` + `titan-ffi` + `titan-tester`)

Review a module that lets C fill an automatic response struct with an owning
pointer through a mutable address, then calls a Titan helper that raises while
a `defer` releases the pointer, and a proposal to move the struct behind a
pointer local or heap box "so recovery sees the C writes". Add an exact
`TValue` out-parameter variant that stores a fresh object before raising and
one that clears it. Require the retained-write rule (the struct is its own
stable home, so the `defer` releases exactly once and nothing rolls back),
rejection of the workaround, root publication of the GC forms before recovery
can close frames, run `__close` or finalizers, or collect, collectability of a
cleared old object, the foreign writer's continuing rooting obligation, and
the raw-alias, asynchronous-write, and backing-lifetime limits. Then ask for
the native regression plan: real `-O2`/`-O3` native programs, every eligible
kind and exclusion, fresh-object survival and old-object finalization during a
full GC in Lua close with the foreign writer's own root truncated, and no new
Clang, LTO, or platform claim. The repaired module must compile natively
against the matching installed Titan.

### J3 — JSON depth on every target (`titan-programmer` + `titan-json` + `titan-tester`)

Review a change that clamps browser `json.encode` depth to 103 and adds
browser-only boundary tests at that constant. Require the configured
`max_depth` (default 32) on native and browser targets with no target writer
cap, shared boundary tests at the configured depth, engine stack exhaustion as
a fatal engine failure rather than a `json.Error`, and decoding's own depth and
shared PEG matching-stack policy. Reject the clamp and the browser-only
constant.

### F2 — Titan-first native callback binding (`titan-programmer` + `titan-ffi`)

Supply an authored header whose `static inline` `items_each(first, last,
visit, userdata)` calls `void (*)(int item, void *userdata)` once per item,
and ask for trusted standard-library module `items` with
`each(first: integer, last: integer, callback: function (integer))`. The Titan
callback runs once per item and may raise; after a raise the remaining items
skip it, and once `items_each` returns, `each` raises the same error value. The
callback stays pinned for the native call. Also ask for a runnable demo, the
`titanc` command, and a justification of every `lua_*`/`luaL_*` call and
authored C line. Require the Titan-first trampoline: a `foreign function` with
the exact `items_visit` signature that recovers the state, the owner, the
handler closure and its native entry through the `titan/ffi.h` bridges, calls
the entry and restores the stack top, and does nothing else. The handler is
Titan, and its function-level `catch` latches the first error (`defer` where
cleanup is needed). The callback is pinned in a per-call owner record's field
or a module variable, and a local roots the owner for the call. The callback
stack is reserved before entering C. Reject a C trampoline that calls the
callback through `lua_pcall`, a `lua_pcall` of a C helper that Lua never sees,
C data routed through the Lua stack, `luaL_ref` or registry and uservalue
tables, and pushing parameters or locals to root them. The delivered modules
must compile unchanged and the demo must run. The judge also runs its own
driver: item order, a non-string error value surfacing unchanged, skipped
items, an empty range, a nested call, and a full collection inside every
callback.

### F3 — C scalar store-back (`titan-programmer` + `titan-ffi`)

Supply `typedef struct Stats { int hits; size_t bytes; unsigned char flags; }
Stats;` and ask for a minimal module `stats_update` whose `record(stats:
foreign *Stats, size: integer)` adds one to `hits` and `size` to `bytes`,
`set_flag(stats, bit)` sets one bit of `flags`, and `snapshot(stats)` returns
both counters, with a short explanation of how each update is typed and
checked. The literal makes `stats.hits = stats.hits + 1` C `int` arithmetic: it
compiles, and its overflow at `INT_MAX` is undefined. A non-literal Titan
operand puts a C-mode result in `lua_Integer`'s C type, arithmetic drops typedef
identity, and a store never converts one C integer type to another implicitly,
so `stats.bytes = stats.bytes + size` is rejected, and `unsigned char`
arithmetic promotes to `int`, so a C-mode `flags` update is rejected too. Accept
Titan arithmetic followed by a range-checked store, or C arithmetic or a
written C cast whose C behavior the answer states. The module and header must
compile unchanged. The judge's driver, built through a second `--tree` root
with `-I` naming the answer's directory, must observe two hits, fifteen bytes
and flags 9, and overflow behavior (a sum past `INT_MAX`, bit 8, a negative
byte count) that matches the explanation. An answer that keeps the C `int` sum
must say its overflow is undefined, and the judge skips that probe for it.

## Frontmatter-only routing set

Read only each skill's YAML `name` and `description`. Answer `none` when no
cartridge applies; `UNKNOWN` is not a routing answer. Choose the minimal set for
these queries:

1. edit an ordinary record method in a `.titan` file;
2. add native Titan subtests;
3. review Task cancellation/listener ordering;
4. use an API-provided HTTPS idle deadline;
5. bind a C header;
6. compile a Relabel parser;
7. test an async HTTP server;
8. review public `titan.uv` callback rooting and a generic async adapter;
9. dynamically load a Lua plugin from Titan;
10. use only `titan.string` regex;
11. change a URL PEG grammar;
12. edit a Lua-only Busted packaging test;
13. write Python `requests` HTTP code;
14. write C-only libuv code; and
15. author a source-defined C callback used by a PEG native Titan test;
16. encode Titan records as JSON and preserve explicit nulls;
17. change the JSON module's Relabel grammar;
18. add native JSON record/union mapping tests; and
19. edit a JSON configuration file for an unrelated Python application;
20. send a reply `thread.Sender` across `thread.channel` or `async.Receiver`;
21. call `uv.native_mutex_lock` from a source `foreign function` and manage
    `uv.mutex_t.create_native()` lifetime; and
22. write native `titan.test` cases for `Thread:task()` pre-start cancellation
    and `async.Receiver` coalescing;
23. configure `titan-language-server` in omp `lsp.json` with `trustedRoots`, set
    a slice's `compiler_root` in `titan-config.local.lua`, and query hover,
    definition, and `titan/workspaceStatus` on `.titan` files;
24. change the compiler's completion hole transform and detached descriptor
    serialization in `titan-compiler`;
25. configure `rust-analyzer` in omp `lsp.json` for a Rust repository;
26. expose a Titan closure to JavaScript with `titan.browser` and await its
    result from a web page; and
27. add `browser.tests` cases for a new `titan.browser` request form.

The intended policy is additive: `titan-programmer` is mandatory for `.titan`
work, while specialist skills activate only for their real boundary. Important
negative controls are no PEG cartridge for `titan.string` regex alone, no
programmer cartridge for a Lua-only test, and no Titan networking/async/FFI
cartridge for unrelated Python or C work; no JSON cartridge merely because
a configuration file uses JSON. Ordinary JSON use selects programmer + json;
JSON grammar changes add pegs, JSON tests add tester, and explicit reflection
construction work adds reflect. Thread channel and `async.Receiver` work selects
programmer + thread + async (adding ffi when touching `transfer.discard_message`
or raw C callbacks, and tester when writing native tests).
Query 21 selects **programmer + ffi**; add async only when changing the
retirement/wake protocol and tester only when writing its native tests. Query 23
selects **programmer + language-server** (not `titan-completion`, which owns
compiler completion internals, and not `titan-json` merely because `lsp.json` is
JSON); query 24 selects **completion** (adding programmer only when `.titan`
files are read or edited); query 25 is a negative control and selects `none`.
Queries 26 and 27 select **programmer + ffi**, adding **tester** for 27; the
bridge's promises are JavaScript, not Titan Tasks, so neither selects async.

## Recorded baseline and post-change results

The baseline used the former monolithic `titan-programmer`. P1, T1, and A1
could be answered only by following its links into manuals/source; the latter
two therefore demonstrated routing but not a self-contained cartridge.
Cartridge-only N1, F1, and G1 could establish little beyond the short imports
and explicitly returned UNKNOWN instead of usable APIs.

Fresh cartridge-only post-change evaluators passed all six original cases;
the later focused P2 evaluator passed as well:

| Case | Baseline | New cartridges |
| --- | --- | --- |
| P1 | Correct after linked-authority research | Exact from primary cartridge alone |
| P2 | Not present in the original baseline | Exact compiler-witness, per-state, container/generic, freshness, and forged-entry behavior from the primary cartridge alone |
| P5 | Not present in the original baseline | Exact spread subjects, ranges, placement, finite/open adjustment, capacity, and C-vararg separation from the primary cartridge alone |
| T1 | Correct after linked test research | Exact native tests, subtests, cleanup, filters, and Runtime modes |
| A1 | Correct after linked async/source research | Exact cooperative scheduling and direct watcher ownership |
| N1 | APIs UNKNOWN | Exact current client/server APIs and protocol constraints |
| F1 | Six of seven requested operations UNKNOWN | Exact FFI/Lua surface; independent review found and drove final pointer/lifetime corrections |
| G1 | PEG syntax and APIs UNKNOWN | Exact Relabel/search/recovery/combinator model |

A fresh frontmatter-only run after boundary clarification scored **15/15 exact,
0 ambiguous, 0 outright misses**. A focused FFI-only rerun after review fixes
also recovered the corrected pointer, string-lifetime, allocation, and raw-stack
rules without external authority. Independent specialist reviewers then checked
all six cartridges against manuals, implementation, source, and tests. Review
findings are not waived by a successful model answer: every blocker must be
fixed and the mechanical checks below rerun.

After compiler-witnessed Interface discovery was added, a fresh
cartridge-only P2 evaluator also passed: it recovered initialization-time
inventory without path execution, exact/witnessed leaf behavior across every
listed boundary, per-state and cross-module rules, wrapper freshness, static
`is` non-registration, and the trusted forged-entry boundary. It marked exact
diagnostic text and duplicate-physical-provider behavior UNKNOWN rather than
guessing.

### Recorded run metadata

The initial baseline/post run was performed on 2026-08-16 by independent fresh
`openai-codex/gpt-5.6-sol` subagents. Each evaluator received the case's stated
file restriction and wrote a separate response; the six baseline, six post,
frontmatter-routing, and six authority-review reports were retained in the
session workspace under `/tmp/titan-skill-tree-research/`. Those temporary
reports are not a runtime dependency or repository fixture. The prompts,
pass/fail gates, aggregate outcomes, and mechanical checks are preserved here so
the evaluation can be rerun with another model; the pull-request description
records the final run summary.

The focused P2 addition was run on 2026-08-17 in a separate fresh context with
only `titan-programmer`; it did not inspect manuals, source, tests, plans, or
the worktree diff.

The focused P5 addition was run on 2026-08-28 in a separate fresh context with
only `titan-programmer`; it did not inspect manuals, source, tests, plans,
`EVALUATION.md`, `AGENTS.md`, or the worktree diff.

### Issue #314 rerun (2026-10-29)

The skills at `issue-314` @ `81d5309` (diff base `main` @ `80d1f70`) changed six
cartridges for the Titan support module, the installed package searcher,
`TITAN_ROOT`, the run-time provider search, and the compiler-owned application
build. No frontmatter description changed, so the frontmatter-only routing set
ran as a control. Seven cases covered the changed text: tester Eval 9 and
Eval 13, `T1`, `F1`, `G1`, `J2`, and the compiler-owned application build,
extended with the `TITANC` and relocated-delivery questions below. `P0`–`P6`,
`A1`, `N1`, `J1`, `TH1`, and the coverage, named-union, `R1`, and `R2` cases
cover unchanged text and keep their recorded results.

Each answer came from a fresh subagent given only the case's cartridges; the
T-E13 and T1 answers report a DeepSeek V4 Flash engineer role, and the others
name no model. Every complete Titan example was then compiled with the
issue-314 toolchain in scratch trees. **T-E9 and J2 passed; routing, T-E13,
T1, F1, G1, and the application build failed.**

| Case | Failure | Disposition |
| --- | --- | --- |
| routing | 19/22 exact. Query 20 omitted `titan-async` for `async.Receiver`, reasoning that `titan-thread`'s description already claims it; queries 13 and 14 answered `UNKNOWN` instead of "none". | Deferred to a skills follow-up issue: a frontmatter note that `titan-thread` adds to, and never replaces, `titan-async`. |
| T-E13 | Every rebuild and `TITAN_ROOT` item was right, but the answer never said that the checkout profile leaves Lua's C module path at its default, so the installed `lib/lua/5.5/titan.so` loads, and never addressed a recipe that still sets the removed `TITAN_ROCKS_ROOT`. | Fixed in this branch. The tested text stated the C-path rule in one bullet and never stated the `TITAN_ROCKS_ROOT` removal; `titan-tester` now states both wherever it discusses the ambient environment and stale installs, and Eval 13 lists them as must-hit items and fail signatures. |
| T1 | The migration design and runner semantics were exact, and the suite ran 23/23 once one annotation was added. As written, `local keep = (a and b) or (c and d)` failed to compile: `and` with a `boolean` left operand yields `boolean?`, and the `or` of two `boolean?` operands is rejected. | Deferred: the cartridge does not state the rule, and the language manual says long all-boolean `and`/`or` chains compile; the checker/manual conflict is a separate compiler follow-up. |
| F1 | Export classes, the unsafe boundary, rooting, `void *` rules, the Map protocol, and Lua-host loading were exact. The example failed on `local count: *int` in a `foreign function` body (it needs `foreign *int`); on a fixture header whose `typedef` and function share the name `widget_stats` (invalid C); on reading scalar `foreign int.new()` as automatic storage (it is `owned *int`); and on `M as foreign *Udata`, which compiles only after `foreign import "titan/ffi.h"`. | Header and scalar `.new()`: answer errors. `*int` in body locals and the `Udata` prerequisite: deferred. No corrected F1 tree compiled. |
| G1 | The parser built a real provider and its assertions passed once fixed. As written, `local hit, failure = parser.find_assignment(...)` dropped both Options, so `hit == nil` was rejected. | Deferred: the cartridge states the drop, but a multiple-result example (`local hit?, failure? = ...`) would prevent a repeated failure. |
| Application build | The Makefile built both images, ran the suite, and captured one certified object path. Its `check-delivery` target depended, through `package`, on the phony application image and the generator, so it needed `titanc` and `lua` on `PATH` while refusing to run with `titanc` there. The captured C fixture object was never linked into either image. | Fixed in this branch: the `titan-application` Makefile links the captured helper into both images with `-X` and runs `check-delivery` against the packaged copy under `env -i`, with no build prerequisite and with `titanc` and `lua` out of reach. |

The deferred items predate issue #314 and are collected, with their evidence
and proposed cartridge text, in one skills follow-up issue. No answer invented
Titan API or contradicted the ownership or single-loop model. The two branch
fixes have not yet been confirmed by a fresh rerun of T-E13 and the
application-build case. Until the deferred items land and their cases are
rerun, this run does not show the cartridges' executable text to be reliable.

All answers also received harness-injected context that the evaluation rules
exclude: an engineer role block (skill-loading mandate, review-protocol path),
workstation lines, a peer roster, and memory recalls. Each answer disclosed
this and said it relied only on the listed cartridges. Spot checks found no
case where injected text supplied a case-specific fact. These contexts were
still not hermetic, so they do not strictly satisfy the rule that answers come
from the cartridges alone.

**Rerun at `abd3fcb`.** Fresh evaluators reran T-E13 and the application-build
case against the fixed skills, with the same rubrics, authority tree, and
compile pattern. Both still failed, for reasons the cartridges do not cause:

- Application build: every rubric item passed by execution. Both images
  linked the captured helper with `-X`, and the same link without it failed
  with an undefined reference to the helper. `check-delivery` passed with
  `PATH=/usr/bin:/bin`, where neither `titanc` nor `lua` is reachable. The
  case failed on the evaluator's own `TREE := src;gen;tests    # …` line:
  Make keeps the spaces before an inline comment, so the quoted
  `--tree 'src;gen;tests    '` no longer contained `tests`, and `make test`
  stopped with `--test-dir 'tests' is outside every --tree source root`.
  With the comment moved to its own line, the suite built and passed. The
  `titan-application` snippet has no inline comment after a variable value,
  so this was an authoring slip in the answer.
- T-E13: the answer still omitted the bullet saying that the installed support
  module in `lib/lua/5.5` still loads because the C module path is unchanged.
  It said `TITAN_ROCKS_ROOT` "is removed and silently ignored" but not what
  follows from that: a fallback to the running interpreter's prefix, and a
  checkout profile that stops for the missing `TITAN_ROOT`. The answer was
  written a minute after the fix commits. Its "silently ignored" wording,
  however, appears only in the fixed `titan-tester` text. The evaluator
  therefore likely read that text, so this omission cannot be blamed on a
  stale revision. The cartridge now states both items in the environment
  section and in Eval 13; the case remains failed until a fresh run includes
  them.

**T-E13 third run (`8ef926f`): pass; the second run's omission was evaluator
variance.** `8ef926f` changed only this file, so the third evaluator read the
same `titan-tester` text as the second. This time the answer met every
must-hit item:

- The checkout profile keeps the installed support module through Lua's default
  C module path. Canonical validation clears `LUA_PATH`/`LUA_CPATH` "so the
  default C module path selects the installed support module".
- A stale `TITAN_ROCKS_ROOT` is silently ignored, the checkout profile then
  stops for the missing `TITAN_ROOT`, and a leftover setting should be removed.
- The rebuild, reinstall, run-only, `make test`, ambient-variable, and
  focused-to-broad items were all correct.

One detail is thinner than the cartridge: the answer calls the old variable
inert but does not name the fallback to the running interpreter's prefix that
`titanc` and default Busted use. The application-build rerun's only failure
remains the evaluator's own Makefile line described above.

### Issue #315 rerun (2026-10-29)

The skills at `issue-315-skills` @ `b589563` (diff base `main` @ `25ff4ed`)
close the five gaps deferred above:

- the `and`/`or` typing after titan#316, including the Lua-exact
  `boolean`/`value` `or` (`titan-programmer`);
- foreign-qualified locals and casts in a `foreign function` body, and the
  `foreign import "titan/ffi.h"` that `M as foreign *Udata` needs
  (`titan-programmer`, `titan-ffi`);
- both Options of a multiple-result local (`titan-programmer`);
- `titan-thread` adding to, never replacing, `titan-async`;
- `none` as a determinate routing answer.

The issue named routing, T1, F1 and G1. P0, P1 and TH1 also cover edited text
(the foreign-body rules and Option forcing), so they were rerun too. The other
cases keep their recorded results.

Each answer came from a fresh DeepSeek subagent (`titan-engineer-deepseek`
profile) given only the case's cartridge paths. The prompts were the case text plus
concrete fixtures: twenty slug rows for T1, a `widget.h` for F1, and a draft
module for P0 and for P1. Every complete Titan file was compiled in a scratch
tree with explicit `--tree` and `--output`, using the titan
`issue-315-followups` toolchain, which contains the titan#316 checker fix.
**Routing, T1, F1, G1, P0, and P1 passed; TH1 failed on an evaluator error.**

| Case | Result and receipts | Disposition |
| --- | --- | --- |
| routing | 22/22. Query 20 selected programmer + thread + async and cited the new `titan-thread` sentence; 13, 14, and 19 answered `none`; 12 answered `none` (the routing policy rules out only programmer there); no `UNKNOWN`. | Pass, but not hermetic: the harness also listed the installed pre-change skill descriptions, and project context may have included the repository's work-to-skill table. The cited sentence exists only in the new description. |
| T1 | `slug_test` built with `--test`; 24/24 ran (two cases, twenty row subtests, two cleanup subtests). Discovery, isolation, `defer` versus `Context:cleanup`, filtering, exit status, commands, and Runtime modes matched `titan-tester`. | Pass. `slugify` classified bytes with `if`/`elseif` ranges, so the answer did not exercise item 1's `and`/`or` shape, and it made no stale `boolean?` claim. The #314 shape `local keep = (c >= 97 and c <= 122) or (c >= 48 and c <= 57)` compiles unannotated under the fixed checker. |
| F1 | `titanc -c` of `widget.titan` against the case header exits 0 as written. The callback body declares `local counter: foreign *int = context as foreign *int`; `M as foreign *Udata` appears with `foreign import "titan/ffi.h"`. | Pass, with both #315 items hit. This is the compile receipt #315 asked for. |
| G1 | `my.parser` and `check` built; `check` exits 0 for the found, absent, and labeled-failure (line 2, column 3) inputs. Each multiple-result call uses `local found?, failure? = ...`. | Pass. |
| P0 | `raw_slot`, `slot_view`, and the corrected `review_me` compile with `-c`. The correction writes `local p: foreign *int = slot`, removes `M.end()` from the foreign body, and annotates `counter: integer?`. | Pass. |
| P1 | The corrected function and its `fs.stat` variant compile. Strict projection versus `as integer`, the Map metatable protocol, function-level `catch`, and `defer` match the cartridge, including the `boolean` Option truthiness note. | Pass. |
| TH1 | All seven modules compile with `-c`; three needed a scorer-supplied `worker_queue.h` transcribed from the answer's own declaration comments, because the case supplies no fixture. Four `Record.new` overrides (`LatestOwner`, `LatestSink`, `HeapMutex`, `Handoff`) return `Record(...)`, which calls the override again; GCC reports `-Winfinite-recursion` for each. | Evaluator error. `titan-programmer` already says that calling `Counter(...)` or `Counter.new(...)` inside the override recurses and that the override builds storage with `{ ... }`. The answer wrote no source `foreign function` body, so it did not exercise the edited text. No cartridge change and no rerun for #315. |

No case failed because of cartridge text, so this run requires no cartridge
change and no further rerun.

All seven evaluators disclosed harness-injected context:

- the engineer role block;
- a `skill://` catalog carrying the installed pre-change descriptions;
- memory recalls;
- a peer roster.

T1 through TH1 read only their listed cartridge paths. As in #314, the
contexts were therefore not hermetic.

### Issues #349 and #350 evaluation (2026-11-05)

The skills at `issue-349-skills` @ `690a822` (diff base `main` @ `9cd94a7`)
replace the compile-time-constant module-initializer rule with the dependency
and call-exposure rule (`titan-programmer`, `titan-ffi`, one `titan-pegs`
sentence), add the browser byte bounds (`titan-programmer`), and retire the
browser test image partition and budget (`titan-tester`). No frontmatter
description changed, so the routing set was not rerun. New cases `I1`, `I2`
and `B1` cover the edited text; `I1` items 1 and 5 cover the changed
`titan-pegs` sentence, so `G1` (whose scoring text only drops its
nonconstant-initializer rejection) was not rerun.

Each answer came from a fresh process,
`omp -p --model openai-codex/gpt-6.1-sol --thinking high --no-skills
--no-context-files --no-rules --no-session --no-extensions --tools read,write`,
given only a prompt file naming its cartridge and fixture paths. The scorer
compiled with the titan `issue-349-initializers` toolchain at `5dee32cc`
(explicit `--tree` and `--output` in scratch trees outside the source).
**I1, I2 and B1 passed.**

| Case | Result and receipts | Disposition |
| --- | --- | --- |
| I1 | All sixteen initializers classified as the compiler decides: each was compiled alone, ten accepted and six rejected with the expected own-reference or anonymous-function diagnostic, and the repaired module (rejected work moved into the root initializer after `seed = 41`) compiled; 17/17. The answer stated the function-value versus bound-method asymmetry, the latent bare-nominal exposure, the own-Interface-to-imported-implementation case, the load-time `Holder.new` rejection before consumer initializers, the observed `Scalar.new` override, and the `peg.compile` callback condition. | Pass. |
| I2 | `ffi_init` compiled against the case header and, loaded by Lua, returned the predicted `total() == 83`. The four extra forms were all rejected as predicted; the source `foreign function` value also reports the general "cannot be used as a first-class value" error, which the answer did not mention beside the correct own-function reason. | Pass. |
| B1 | Both bounds, what each counts, inclusive equality, source-attributed versus unavailable diagnostics, rejection before publication, the non-guarantee and the six distinct quantities, one root list, one image and its artifacts, no partition or budget knob, the filter rules, and the stdout-only audit were all correct; the three proposals were rejected. It marked the substituted `<engine>` tokens and the literal fallback wording as unknown, which the cartridges leave implicit. | Pass. No Titan code to compile. |

All three evaluators disclosed harness-injected context despite the `--no-*`
flags: system and developer blocks, tool schemas including memory and
managed-skill tools (unused), workstation metadata, the date and working
directory, and eight recalled memories unrelated to these rules. No skill
catalog or agent roster was injected. The contexts were therefore not
hermetic, although each answer reports reading only its listed files.

### Issue #349 implicit-dispatch extension (2026-11-05)

A fresh GPT 6.1 Sol evaluator read only the programmer and FFI cartridges at
`c8ab8492` and the focused thirty-row exercise. It did not inspect compiler
source, the implementation handoff, expected answers or earlier evaluations.
**The extended I1 case passed.** All thirty source classifications matched
independent compilation: thirteen accepted and seventeen rejected with the
expected initializer-exposure or unsupported-operator diagnostics. The complete
repaired consumer also compiled, for **31/31** matching outcomes.

The scorer used the `issue-349-initializers` toolchain at `929721be`
(production code unchanged since its installed `51768381`), with explicit
`--tree` and `--output` in a scratch tree. This was compile-only validation;
it did not execute the consumers' initializers. The answer correctly
distinguished Map-key/equality/length/spread exposure, non-dispatching fresh
origins and raw value equality, delivered versus discarded constructor
arguments, record-specific `literal` requirements, and compatibility rejection
before callback execution. The checker and coder binary-compatibility specs,
the latter with actual shared-library replacements, separately cover the
runtime side: a callback-invoking `Holder.new` replacement is rejected before
consumer initialization, while callback-free imported construction, including
a nested one, observes the replacement's 42 instead of the stored 41. This
compile-only evaluation does not re-claim those results.

The evaluator disclosed injected profiles, tool schemas, skill/agent catalogs,
machine metadata, unrelated historical memories and a peer roster. This was
therefore **not hermetic**, although its answer reports using only the supplied
cartridges for language guidance. Its answer, exact sources and command/status
receipt are retained as `eval/349-metamethod-answer.md`,
`eval/349-metamethod-compile-results.json` and
`logs/349-metamethod-eval-compile.log` in the issue's validation evidence.

### Issues #353/#332 evaluation (2026-11-06)

The evaluated cartridges were `issue-353-skills` at `26f85b10`, based on
`e6328d3e`. They integrate the removed browser JSON writer cap, persistent
image lifecycle, browser-only JavaScript bridge, original-callable rooting,
retained-write recovery, and the owning test layers. No cartridge changed
during evaluation. Before scoring, this file's TH1 oracle was corrected from
the obsolete aggregate rollback rule to the maintainer-approved retained-write
and pre-close root-publication rule; this evaluation file was not an allowed
input.

Each case ran in a separate `omp -p` process with
`opencode-go/deepseek-v4.1-flash`, high thinking, only `read,write`, and
`--no-skills --no-context-files --no-rules --no-session --no-extensions
--no-prewalk --no-lsp --no-title`. Each process received only its named
cartridge paths and was forbidden to compile or read manuals, source, tests,
repository instructions, history, or this file. Routing received only the
13 YAML name/description pairs. Answers disclosed injected Mnemopi memories
and, where noticed, project/workstation metadata: the allowed reads were
cartridge-only, but the contexts were not completely hermetic.

Ten processes exited 0. TH1 reached its 20-minute deadline after writing its
answer and exited 1; its content is available, but it is not a clean completed
run. The serial queue stopped there. J1, which had not started, then ran alone;
no successful case was restarted. Exact commands, statuses, and durations are
in `evaluations/final332/runs.json` in the workstream evidence directory
(`/tmp/titan-353` for this run).

| Case | Observed result | Assessment |
| --- | --- | --- |
| Routing | The new browser queries 26/27 select programmer + ffi, adding tester only for 27, without async. Query 23 omits the oracle's programmer cartridge; 24 adds it while assuming the compiler source is Titan; 8 conservatively adds ffi to the public callback/adapter route. | Not 27/27 exact. The two new bridge routes are correct; preserve the other mismatches rather than treating the whole routing set as green. |
| W1 | The unchanged counter module compiles against the composed browser SDK. Its original page runs on Node 26, prints `counter ok [ 3n ]`, preserves shared captures and result Arrays, and disposes a never-settling detachable request. | Pass. The answer also gives strict BigInt, the exact failure callable, promise reentry rejection, explicit release, and cross-heap cycle rules. No browser-page engine run of this evaluator page is claimed. |
| H1 | The answer explains retained writes and GC publication, but the complete fixture fails parsing at `local owned` (`response_case_test.titan:18`). Its plan also omits the requested optimized/all-kind/exclusion matrix and full GC during Lua close after truncating the writer's root. | Fail as written. The missing test requirements are explicit in the allowed tester cartridge; this is an evaluator omission, not absent reference material. |
| J3 | The depth/default32/no-target-cap contract is correct. Its complete module compiles and passes 8 cases natively and under Node/Chromium. Its above-cap tests nevertheless catch and merely log every non-JSON error. | Partial: the boundary examples execute, but their broad catch is not valid evidence for fatal engine-failure propagation and can hide an unrelated runtime error. Do not advertise it as an exhaustion test. |
| FFI13 | The review corrects the prose contracts. Its purported page module has `main()` rather than the standalone signature, so image compilation rejects `--exe`. A separate library compile then rejects `self.on_fetch_success`/`self.on_fetch_failure` and the missing nominal Callable arguments to `browser.start`. | Fail as written. Method binding and explicit callable construction are not interchangeable; no repaired answer is substituted. |
| FFI14 | Correct stable-home/no-rollback rule; pre-close publication and clearing; writer rooting; raw-alias, asynchronous-write and backing-lifetime limits; scalar versus aggregate/GC toolchain evidence. | Pass, review-only. No module or new execution claim. |
| F1 | Both delivered dotted filenames fail logical module lookup. With only the directory layout corrected and source/header bytes unchanged, both complete module bodies compile with `-c`. | Fail as delivered; diagnostic compile passes. The export classes, unsafe boundary, ownership and Map rules are otherwise explained. No runtime behavior of those library functions is claimed. |
| T1 | The unchanged production/test pair compiles and runs 21/21 cases: one parent and twenty isolated named children. Discovery, cleanup, filtering, exit statuses and Runtime modes match the cartridge. | Pass. |
| A1 | Root ownership and complete follow-on batches are correct, but the answer omits the required synchronous `uv.walk`/Windows-TTY callback exceptions and says subscription publication never enters a Task inline. | Fail: it misses the explicit immediate-operation-continuation versus deferred public `Task:resume` distinction. Both rules are in the supplied async cartridge. |
| TH1 | A substantial answer exists, with the packet/retirement fundamentals and retained-write publication, but the process expires at 1200.278 s. It omits parts of the late-cancel/admission rubric and writes a guessed `m:init()` while saying the exact spelling is unknown. | Incomplete/deadline, not a clean pass. No complete module or execution is claimed, and no rerun conceals this result. |
| J1 | Three unchanged complete programs compile and exit 0: union/record round-trip plus null-tail identity, a const integer Array schema, and public custom construction with a private field. Exact decode shape, schema identity, null policy, constructor rules and erased leaves are explained. | Pass. |

This is **not an all-pass evaluation**. Model-answer errors remain separate
from product regressions and cartridge gaps. The originals are preserved; no
API or example in the cartridges was changed to accommodate an incorrect
answer. The path-normalized F1 diagnostic is explicitly separate from its
as-delivered failure.

Mechanical and documentation evidence:

- All 13 frontmatters have exactly `name` and `description`; 186 relative file
  targets and 57 anchors resolve in the composed tree.
- All 98 `titan` fences parse with the current compiler. This is grammar
  evidence, not a claim that all fences were typechecked.
- Ten unchanged complete representative modules cover all nine cartridges
  containing Titan fences. Three standalone programs run, and the tester pair
  passes five native cases. The other four cartridges contain no Titan fences.
- Four changed browser documentation examples, extracted verbatim from the
  language manual and FFI cartridge, compile together and run under Node and
  Chromium. They exercise exact NUL/0xFF bytes, recovered binding errors,
  shared captures, decoded result Arrays, explicit release and disposal.

Receipt index: `notes/EVALUATION-FINAL332.md`. Execution logs:
`logs/final332-evaluator-native.log`, `final332-evaluator-f1-layout.log`,
`final332-evaluator-j1.log`, `final332-evaluator-ffi13-module.log`,
`final332-browser-examples.log`, `final332-skills-parser.log`, and
`final332-skills-representative.log`. Extracted sources, original answers,
machine-readable command results and mechanical inventories are under
`evaluations/final332/`. The exercised toolchain is Linux x64, the composed
Titan candidate `010de910`, Emscripten 6.0.13, Node 26.13.0 and Chrome for
Testing 156.0.8078.80; these receipts establish no new macOS, Windows, Clang
or LTO qualification.

### Issue #366 re-evaluation (2026-11-06)

titan#366 asked for one clarification at each location where a #353/#332
answer failed. The evaluated cartridges were `issue-366-cartridge-clarity`
at `1e0c8415`, based on `aa03f9a`, whose `SKILL.md` text equals the
#353/#332 input `26f85b10`; A1's reruns used `7d5ecc56` and `6485f837`.
Every added statement was checked against titan master `843b446e`. The
reserved words were checked against `lexer.lua` and `grammar.md`, module
lookup against `driver.lua` and `folder-modules.md`, and the bridge against
`browser.browser.titan` and `standard-library-browser.md`. Callback timing
and watcher drains were checked against `async.native.titan` (now the
`titan/async/` folder),
`fs.native.titan`, `async-io.md`, `standard-library-fs.md` and the uv
contract notes.

| Case | Clarification |
| --- | --- |
| H1 | `titan-programmer` lists the 38 reserved words beside the `Name`/`AnyName` rule: a member may be named `owned`, but `local owned` does not parse. `titan-tester` shows the retained-write matrix as a five-part checklist. Its "Public UV and generic async boundary tests" section moved verbatim out from under the evaluation-appendix heading into the numbered body, and the layer-choice section points to it. |
| FFI13 | `titan-ffi` adds a complete page module with the exact `main`, `browser.callable` for both callbacks, and `browser.start`. Beside it is the rule that a colon-declared method is not a field value. |
| F1 | `titan-programmer` adds a file-name versus logical-name table. The right layout is `ring/main.titan`, not `ring.main.titan`; a relative header sits beside its importer; operands are dotted names. |
| A1 | `titan-async` lists, beside the scheduling invariant, the three callback-timing cases a review must name: the synchronous `uv.walk` and Windows-TTY callbacks; the inline operation continuation, stated as a sequence; and the deferred wakes from `Task:resume` and subscriptions. Its Domain adapters rule says a follow-on batch maps every event, the retired registration's included. |
| J3 | `titan-json` adds an exhaustion-test template that rethrows anything except the expected `json.Error`. |

That source check corrects one point of the #353/#332 A1 assessment.
Subscription `publish`, `fail` and `finish` wake the reader through
`Task:resume`, which never enters a Task inline (`async-io.md`: "Producer
notifications use the same token-based deferred wake"). The baseline was
therefore right that publication never enters the Task inline. Its A1 failure
stands on the omitted synchronous `uv.walk`/Windows-TTY callbacks and the
missing inline operation-continuation distinction.

Each answer came from a fresh `omp -p` process with the #353/#332 command
shape: high thinking, only `read,write`, `--no-skills --no-context-files
--no-rules --no-session --no-extensions --no-prewalk --no-lsp --no-title`,
`--approval-mode yolo` and `--max-time 20m`. The prompts were the preserved
ones, with only the cartridge paths changed. Each case ran with
`opencode-go/deepseek-v4.1-flash`, `anthropic/claude-haiku-5-5` and
`openai-codex/gpt-6-luna`, one serial queue per provider. Each run added
`--config` with an overlay setting `memory.backend: "off"`. A smoke prompt
reported no injected memories for any model, while a control without the
overlay reported one. The harness's workstation/project block (OS,
architecture, model, working directory) remained, so the runs were memory-free
but not completely hermetic. All 21 scored processes (15 in round 1 and 3 in
each of two A1 reruns) exited 0 and wrote an answer; none was retried. A first
round-3 attempt, interrupted by a maintainer power loss, was voided unscored
and rerun cleanly.

Delivered complete modules were compiled unchanged with the session SDK
(validation profile, Linux x64; Emscripten 6.0.13 and Node 26.13.0 for
browser images). Code that appeared only in `answer.md` was extracted
verbatim. H1 and J3 ran as native `--test` executables, F1 compiled with `-c`
as delivered, FFI13 built browser images, and A1 is review-only.

Round 1 left one gap: no A1 answer named every timing case, and none stated the
inline operation continuation. The A1 list was revised once, to name the three
cases a callback or wake review must cover and to say the operation callback
resumes its Task immediately, inside that callback. A1 alone was then rerun
with all three models.

The maintainer then asked for a third A1 round. Each round-2 miss traced at
least partly to wording:

- DeepSeek read the registration case, which shared a bullet with the main
  rule, as limiting inline completion to registration.
- Haiku named `Completion` as the one-shot wake capability without its timing.
- Luna dropped the retired registration's own follow-on events. The rule had
  forbidden filtering only "other registrations' events".

So `6485f837` leads with the inline sequence: the callback settles the exact
`Completion`, the Task runs inside it to its next callback-bearing await,
return or raise, and then the callback returns to libuv. It marks the
registration and peer-Task/finalizer cases as secondary, contrasts the three
wake routes, and says a follow-on batch maps every event. No cartridge text
other than `titan-async` changed after round 1.

| Case | Baseline (#353/#332, DeepSeek) | DeepSeek | Haiku | Luna |
| --- | --- | --- | --- | --- |
| H1 | Fail: `local owned` does not parse. The matrix omits optimized programs, kinds and exclusions, and Lua-close GC with the writer's root truncated. | Partial: the five-part matrix is complete and no local uses a reserved word. `response.fills = response.fills + 1` fails typecheck: it stores a C-mode `long long` into an `int` field. | Pass: 4/4 native cases, and the matrix names all five parts. | Partial: 2/2 native cases. The matrix omits optimized programs, exclusions, Lua-close GC and the truncated writer root. |
| FFI13 | Fail: `main()`, `self.on_fetch_*` as method values, and no Callables for `browser.start`. | Partial: exact `main` and two `browser.callable` lambdas passed to `start`; its own page prints `5n 5n`. As delivered, the file `counter.page.titan` is not found as `counter.page` (the F1 error). The page ran after path-only staging. | Pass: the complete page module builds as a browser image. | Pass: Titan code marked illustrative, exact `main` stated; the fragment compiles as a library. |
| F1 | Fail: `ring.main.titan` and `plugin.main.titan` are not found. | Pass: two flat modules compile with `-c`. | Pass: seven flat modules compile with `-c`. | Partial: the flat layout is found, but `recovered[0] = recovered[0] + 1` fails typecheck (the same C-mode narrowing). |
| A1, round 1 | Fail: omits the `uv.walk`/Windows-TTY callbacks and the inline-continuation versus deferred `Task:resume` distinction. | Partial: walk/TTY explicit and `Task:resume` deferred; the inline continuation is only implied. | Fail: omits both walk/TTY and the inline continuation; it correctly treats publication as deferred. | Partial: names walk/TTY and defers `Task:resume`, but omits the inline continuation. |
| A1, round 2 | — | Partial: walk/TTY explicit, but limits inline completion to registration. | Partial: walk/TTY explicit; still omits the inline continuation. | Partial: walk/TTY and the inline continuation explicit, but it discards events of owners retired in the batch. |
| A1, round 3 | — | Pass: walk/TTY explicit, the Task resumes inside the settling callback, and publication and `Task:resume` are both deferred; it maps the retired registration's follow-on events. | Partial: states the inline continuation, but names only `uv.walk` (not the Windows TTY calls) and never calls `Task:resume` deferred. | Partial: all three timing cases correct, but it discards retired-owner events; it read `titan-async` only to line 903, before the Domain adapters rule. |
| J3 | Partial: the above-cap tests catch and log every non-JSON error. | Pass: 12/12 native cases; its one catch helper rethrows anything except `json.Error`. | Pass: 6/6 native cases; every catch rethrows. | Pass: plan only, stating the rethrow rule. |

Did each baseline failure recur?

- **H1:** no local uses a reserved word. Two of three plans contain the whole
  five-part matrix.
- **FFI13:** no answer repeats the `main`, method-value or Callable errors.
- **F1:** no answer uses a dotted file name.
- **J3:** no test catches and passes an unexpected failure.
- **A1:** after round 3, all three answers state the inline operation
  continuation and DeepSeek passes. Haiku omits the Windows TTY calls and the
  `Task:resume` deferral, and Luna still discards retired-owner events, so A1
  remains the weakest case.

The remaining errors are model-answer errors, not gaps in the clarified
text:

- **C-mode store-back (H1 DeepSeek, F1 Luna):** both compile failures add a
  Titan integer to a C `int` and store the result back. `titan-ffi`
  "C operator mode" says mixed Titan operands enter C mode as `lua_Integer`
  and are not narrowed, but it has no worked store-back example. That is a
  candidate follow-up outside this issue's five locations.
- **Dotted file name (FFI13 DeepSeek):** this repeats the layout error that
  the new table addresses.
- **Discarded events (Luna's A1, rounds 2 and 3):** discarding retired-owner
  events contradicts the no-discard retirement-boundary rule. Round 2 traced
  partly to the old "other registrations' events" wording, now fixed. Round 3
  read `titan-async` only to line 903, so it never reached the rule in Domain
  adapters (about line 1708). An earlier pointer to that rule is a candidate
  follow-up.

This is **not an all-pass evaluation**. No answer was repaired before scoring.
The FFI13 path-only staging is a diagnostic; its as-delivered lookup failure
stands.

Limitations:

- Each case has one answer per model and round, and answers vary between runs:
  Luna fixed the A1 timing in round 2 but regressed on batch handling, and A1
  needed three rounds for its first pass.
- Browser images ran on Node 26 only, and a page ran only when delivered
  complete. Haiku's FFI13 page was illustrative and was not run.
- Everything ran on Linux x64, so there is no macOS, Windows, Clang or LTO
  claim.

Final-tree checks:

- All 13 frontmatters have exactly `name` and `description`.
- 187 relative link targets and 58 anchors resolve, including the new tester
  pointer.
- All 100 `titan` fences parse: the 98 earlier ones plus the two new examples.
- The reserved-word list equals the 38 keywords in `lexer.lua`.
- Both new examples were extracted verbatim and run:
  - The page module builds a browser image, and a harness page drives its
    success and failure callbacks on Node 26.
  - The JSON template passes natively and on Node.
- Derived controls:
  - `--exe` rejects the `main()` variant.
  - `session.on_done` is a field-lookup error, while a bound `session:on_done`
    works as a callable.
  - A non-JSON raise inside the template's protected block fails its test.
- Probes:
  - `local owned` and a parameter named `type` do not parse.
  - Members named `owned` and `type` work.
  - The layout diagnostics match the new table.

Receipts are in `/tmp/titan-366/eval` (prompts, answers, process logs,
`runs-all.json`, `round2/`, `round3/`, the voided
`round3-void-20261106T162431Z/`, `smoke/`) and `/tmp/titan-366/logs`
(`issue366-*.log`, `eval/*.omp.log`), with `/tmp/titan-366/examples` and
`/tmp/titan-366/mechanical`. They are archived as the
`issue-366-validation-archive` release on mascarenhas/titan.

### Issue #370 evaluation (2026-11-06)

titan#370 adds guard-rails against C and Lua C API overuse in
standard-library and runtime code. The style guide's new "Write native
bindings Titan-first" section holds the six rules' normative text, and
`standard-library-maintenance.md` pairs each with a #364 bridge
counterexample. `titan-ffi` adds "Guard-rails for standard-library and
runtime C": the six rules with wrong and right examples, and a compiled
`counter` binding. Its Titan `foreign function` trampoline calls a handler
whose function-level `catch` latches the error; an owner field pins the
callback, a local roots the owner, the callback stack is reserved before C
runs, and an outer-block local keeps an owned buffer. The callback,
bridge-maintenance, review and checklist sections point to the rules, and
`titan-programmer` points to them for any standard-library or runtime work
that touches C. The new case is F2.

The before cartridges were `main` at `1d49841`, the after cartridges
`issue-370-c-api-guardrails` at `04a38ffe`; each was exported read-only. After
the evaluation, three edits that F2 does not exercise landed: the rules and
the source map cite the style guide as their normative text, rule 6 is
phrased generically instead of naming a future bridge API, and rule 3's wrong
example names the four bridge entries that use `protected_entry` instead of
"every bridge entry". The recipe that F2 measures (rules 1 and 3 to 5, the
`counter` binding and its notes) is unchanged. Every statement was checked
against titan master `f01e6c9f`:

- the counterexamples against `titan-browser.c`
  (`titan_browser_root_callable`, `root_callable_worker`, `protected_entry`,
  `complete_failure`), `browser.browser.titan` (`invoke`, `request`,
  `callable`) and the loader's `snapshotArguments`;
- the trampoline against `timer_callback` and `timer_deliver`, `uv.run`'s
  `LUA_MINSTACK` reservation and the HTTP parser's `callback_state`, and the
  record-field intrinsic against `checker/native_record_fields.lua`;
- rooting against `values-and-gc.md`, "The function frame" and "Home roots";
  the generated C of the `counter` example confirms that a handler entry
  reserves its frame before its protected block begins.

Each answer came from a fresh `omp -p` process with the #366 command shape:
high thinking, only `read,write`, `--no-skills --no-context-files --no-rules
--no-session --no-extensions --no-prewalk --no-lsp --no-title`,
`--approval-mode yolo`, `--max-time 20m` and the memory-off overlay, one
serial queue per provider. The before and after prompts differed only in the
cartridge paths. A smoke prompt reported no injected memories for any model;
a DeepSeek control without the overlay reported one. The workstation block
remained, so the runs were memory-free but not completely hermetic. All six
scored processes exited 0 and wrote an answer; none was retried.

DeepSeek (`opencode-go/deepseek-v4.1-flash`) is the acceptance floor, because
it is the model used for implementation and review: its after answer must
pass. Haiku (`anthropic/claude-haiku-5-5`) and Luna (`openai-codex/gpt-6-luna`)
are additional signal. The one allowed revision was reserved for a DeepSeek
miss traced to wording or placement, or for a plain text defect that Haiku or
Luna exposed; none was needed.

Delivered modules were compiled unchanged with the session SDK (titan 0.6.0-1
from master `f01e6c9f`, validation profile, Linux x64), DeepSeek's before
bridge with its own `--c-source items_bridge.c`. Each demo ran. The judge's
driver was built against each unchanged `items` module through a second
`--tree` root and run. The reference solution in `eval/F2/reference` compiles,
its demo runs, and it passes the driver.

| Model | Before (`1d49841`) | After (`04a38ffe`) |
| --- | --- | --- |
| DeepSeek | Fail: an authored C trampoline (`items_call_visit` in `items_bridge.c`) calls the callback through `lua_rawgeti` and `lua_pcallk` (rules 1 and 3), and pins it with `luaL_ref` in the registry after a `lua_pushtvalue` (rule 4). The error waits on the Lua stack. Demo and driver pass. | Pass: a Titan `foreign function` recovers the state, owner, handler and entry, calls the entry and restores the top; the handler's function-level `catch` latches the first error; owner fields pin the callback and a local roots the owner; `LUA_MINSTACK` is reserved before `items_each`; the error is raised after return. No authored C, `lua_pcall`, registry or push. Demo and driver pass. |
| Haiku | Fail: an authored `static inline` trampoline (`items_bridge_visit`) calls the callback with `lua_pcallk` (rules 1 and 3) and roots the parameter with `lua_pushtvalue` (rule 5). Demo and driver pass. | Pass: the same shape as DeepSeek's; demo and driver pass. |
| Luna | Fail: authored `items_lua_visit` and `items_each_lua` call the callback with `lua_pcall` (rules 1 and 3), and the parameter is pushed to root it (rule 5). Demo and driver pass. | Partial: the binding has the whole shape and passes the driver, but the demo declares `main()`, so it builds a library and no program runs. |

Every before answer works: its demo and the driver pass. That is the #364
situation, where tests pass while the C and Lua C API layering is wrong.
Every after answer drops the authored C, the manual protected call, the
registry pin and the rooting push. The after answers follow the cartridge
model closely (DeepSeek and Haiku keep its `Run`, `step` and
`step_trampoline` names), so F2 shows that the model is found and applied,
not that it is derived independently. Luna's `main()` repeats the FFI13
baseline error, which the programmer cartridge's standalone-`main` rule
already covers, so it is not a #370 wording gap.

Limitations:

- Each model ran once per round, and answers vary between runs.
- Print-mode logs keep only the final message, so the read-only-cartridges
  instruction rests on each answer's disclosure; all six name only the two
  cartridges.
- F2 exercises rules 1 and 3 to 5, and rule 2 by the absence of a C helper.
  Rules 2 and 6 rest on compiled examples, not on an evaluation case.
- F2's callback is synchronous. A trampoline called later, such as uv's,
  needs a module or loop pin and an owner push, which the cartridge describes
  and F2 does not exercise.
- Everything ran on Linux x64, so there is no macOS, Windows, Clang or LTO
  claim.

Final-tree checks:

- All 13 frontmatters have exactly `name` and `description`.
- 196 relative link targets and 67 anchors resolve in the skills tree, and 57
  targets and 37 anchors in the four edited titan docs.
- All 102 `titan` fences parse: the 100 earlier ones plus `counter.titan` and
  the rule-6 union example.
- The reserved-word list still equals the 38 keywords in `lexer.lua`.
- The new cartridge examples were extracted verbatim and run with drivers:
  the `counter` binding (a full collection inside every callback, a raise, a
  nested call, and both buffer paths of `sum`), the rule-2 C function, and
  the rule-6 receiver.
- `git diff --check` is clean in both worktrees.

Receipts are in `/tmp/titan-370/eval` (prompt template, prompts, answers,
delivered files, per-round `runs.json`, `smoke/`, `reference/`, `driver/`,
`run_eval.py`, `judge-run.sh` and the memory-off overlay) and
`/tmp/titan-370/logs` (`issue370-*.log`, `eval/*.omp.log`), with
`/tmp/titan-370/examples` and `/tmp/titan-370/mechanical`. They are archived
as the `issue-370-validation-archive` release on mascarenhas/titan.

### Issue #369 evaluation (2026-11-06)

titan#369 adds the two follow-ups that the #366 re-evaluation proposed. In
`titan-async`, one sentence at the end of the
`drain_pending()`/`drain_if(predicate)` paragraph states the follow-on batch
rule and links to it under "Domain adapters". Luna's round-3 A1 answer had
stopped reading about 800 lines before that rule. In `titan-ffi`, "C operator
mode" adds a two-line store-back example for a C `int` field: the rejected
`response.fills = response.fills + 1` with its diagnostic, and the accepted
`response.fills = (response.fills as integer) + 1`. The surrounding text says
that a C-mode arithmetic result drops typedef identity, that a store never
converts one C integer type to another implicitly, and that a
`foreign function` body types the literal `1` as C `int`. The new case is F3.

The evaluated cartridges were `issue-369-skills-pointers` at `a662dcdc`, based
on `b5bef05`, exported read-only. Every added statement was checked against
titan master `c6ae114b`:

- the drain rule against `Watcher:drain_notifications` and
  `Watcher:map_notification` in `fs.native.titan`, "One-to-one drain mapping"
  in `filesystem-library.md`, and the watcher passage of `async-io.md`;
- the example by compiling both lines verbatim with the session SDK (titan
  0.6.0-1 from `c6ae114b`, validation profile, Linux x64, gcc 16.2.1). The
  rejected line reports
  `type error: types in assignment do not match, expected foreign int but found foreign long long`
  twice, at columns 28 and 11. The accepted line runs, and at `INT_MAX` its
  store raises `numeric value is outside the range of foreign int` and leaves
  the field unchanged;
- the surrounding text against "Promotions and mixed Titan operands" in
  `c-ffi-expressions.md` and compiled controls. An `int` to `long long`
  declaration, a `size_t` sum (`unsigned long long`), an `unsigned char` sum
  and an `int` element sum are rejected. The Titan form for `size_t` and for
  the element, a `long long` field sum and a `foreign function` body sum
  compile.

The A1, H1 and F1 rubrics were checked against the same tree before scoring,
because the #366 source check once corrected A1's. A1's timing cases match
`uv/CONTRACT-NOTES.md` (synchronous `walk`, inline Windows TTY
`read_start`/`tty_set_mode`) and "The callback/continuation model" in
`async-io.md`: callback settlement enters the Task directly, while
`Task:resume` and producer notifications are deferred. Its caller rule matches
`standard-library-fs.md` (one polling Task per Watcher, concurrent mutation
coordinated externally). H1 matches "C storage after a caught error" in
`c-ffi-expressions.md` and the `titan-tester` five-part matrix, and F1's export
classes match `ffi.md`. No rubric needed a change; between #366's check at
`843b446e` and `c6ae114b` only the #370 documents changed.

Each answer came from a fresh `omp -p` process with the #366 and #370 command
shape: high thinking, only `read,write`, `--no-skills --no-context-files
--no-rules --no-session --no-extensions --no-prewalk --no-lsp --no-title`,
`--approval-mode yolo`, `--max-time 20m` and the memory-off overlay, one serial
queue per provider. The prompts were the preserved #366 prompts (A1 from round
3), with only the cartridge paths changed. A smoke prompt reported no injected
memories for any model; a DeepSeek control without the overlay reported one.
The workstation block remained, so the runs were memory-free but not completely
hermetic. All nine scored processes exited 0 and wrote an answer; none was
retried. Delivered modules were compiled unchanged with the session SDK: H1 as
native `--test` executables that ran, F1 with `-c`. A1 is review-only.

| Case | Before (#366; A1 from round 3) | DeepSeek | Haiku | Luna |
| --- | --- | --- | --- | --- |
| A1 | DeepSeek Pass. Haiku Partial: names only `uv.walk` and never calls `Task:resume` deferred. Luna Partial: discards retired-owner events; it read `titan-async` only to line 903. | Pass: walk/TTY explicit, the inline continuation stated as a sequence, publication and `Task:resume` deferred; the follow-on batch maps the retired registration's events and leaves a live-only batch buffered. | Partial: walk/TTY explicit and the follow-on batch mapped whole, retired-owner events included; omits the inline continuation and the `Task:resume` deferral. It also adds Task-side state so a detached batch survives poll cancellation, which the real `poll` does not promise. | Partial: maps every follow-on event in callback order, the retired registration's included; walk/TTY and the `Task:resume` deferral explicit; omits the inline continuation. |
| H1 | DeepSeek Partial: `response.fills = response.fills + 1` fails typecheck. Haiku Pass. Luna Partial: matrix omissions. | Fail: `local owned = response.owned` is a syntax error (the #353/#332 baseline error). A rename-only copy compiles and passes 6/6. No C read-modify-write. | Partial: 5/5 native cases; the matrix omits part 2 (eligible kinds and exclusions), which its #366 answer named. | Partial: 2/2 native cases; the matrix omits optimized programs, kinds and exclusions, Lua-close GC and the truncated writer root, as in #366. |
| F1 | DeepSeek Pass. Haiku Pass. Luna Partial: `recovered[0] = recovered[0] + 1` fails typecheck. | Pass: five modules in `examples/` compile with `-c`, as flat names or as `examples.*`; content complete. | Partial: `local info = M.counter_info(start)` forces an `Info?`, so `info == nil` fails typecheck; `local info?` compiles. It read `titan-programmer` only to line 303, before that Option rule. | Pass: the flat module compiles with `-c`; the only Titan-to-C store is `context[0] = n as foreign int`. Content complete. |

Did the two targeted failures recur?

- **Retired-owner events (A1):** no. All three answers take the complete
  follow-on batch and map the retired registration's events. Luna's wording
  follows the new sentence ("Take the complete follow-on batch with `drain_if`
  and map every event in callback order, including events referring to the
  registration retired in this batch"). Print-mode logs keep only the final
  message, so whether it read on to Domain adapters is unknown.
- **C store-back (H1, F1):** no answer stores a C-mode sum back into a C field,
  but no H1 or F1 answer writes a C read-modify-write at all: their C stores
  take Titan values (`out.code = 11`, `context[0] = n as foreign int`). These
  runs therefore show only that the error did not recur. F3 below measures the
  example directly.

The remaining failures are model-answer errors in material this issue did not
change, recorded and not fixed here:

- **Inline operation continuation (A1 Haiku and Luna):** both omit it, and
  Haiku never calls `Task:resume` deferred. #366 round 3 had Haiku and Luna
  stating the continuation, so the timing list still varies between runs.
- **`local owned` (H1 DeepSeek):** the #353/#332 baseline syntax error
  returns, beside the reserved-word list that #366 added to `titan-programmer`.
- **Retained-write matrix (H1 Haiku and Luna):** Haiku drops part 2, which its
  #366 answer named; Luna omits parts 1 to 4, as in #366.
- **Forced Option (F1 Haiku):** `local info = M.counter_info(start)` forces an
  `Info?`, so `info == nil` does not typecheck. The rule sits at
  `titan-programmer` line 392; Haiku read only to line 303.

F3, added for this issue, isolates the store-back. Each model answered it once
with the before cartridges (`b5bef05`) and once with the after cartridges
(`a662dcdc`), in the same command shape. The judge compiled each module
unchanged and built its own driver against it through a second `--tree` root,
with `-I` naming the answer's directory so that both modules import the same
`stats.h`. The reference solution in `judge/F3/reference` passes the driver.
All six F3 processes exited 0 and wrote an answer; none was retried.

| Model | Before (`b5bef05`) | After (`a662dcdc`) |
| --- | --- | --- |
| DeepSeek | Pass: typed `integer` locals, Titan arithmetic, checked stores. | Pass: `(stats.hits as integer) + 1` and its siblings, plus a bit-range guard; it quotes the new diagnostic. |
| Haiku | Pass: typed `integer` locals and a bit-range guard. | Pass: the `as integer` form; it cites the new example. |
| Luna | Pass: the `as integer` form. | Pass: the `as integer` form. |

Every module compiles, and the driver sees two hits, fifteen bytes and flags 9.
Each overflow probe (a sum past `INT_MAX`, bit 8, a negative byte count) raises
and leaves its field unchanged, as each explanation says. F3 therefore does not
separate before from after: asked directly how each update is typed, every
model already chose Titan arithmetic from rule 9 and "Choose before the
operation". The #366 store-back failures were slips inside long answers about
other subjects. Two after answers cite the new example, so it is found and
applied; F3 does not show that it was needed.

This is **not an all-pass evaluation**. Neither targeted failure recurred, and
no remaining failure traces to the two additions, so the one allowed revision
was not used. No answer was repaired before scoring; the rename-only and
`local info?` copies are diagnostics, and the as-delivered failures stand.

Limitations:

- Each model answered each case once, and answers vary between runs: H1 Haiku
  and F1 Haiku lost points they had in #366, and A1 Haiku and Luna dropped the
  inline continuation that their #366 round-3 answers stated.
- Print-mode logs keep only the final message, so the read-only-cartridges
  instruction and the reading ranges rest on each answer's disclosure.
- No H1 or F1 answer exercised the store-back, and F3 is one focused case.
- Everything ran on Linux x64 with gcc 16.2.1, so there is no macOS, Windows,
  Clang or LTO claim.

Final-tree checks:

- All 13 frontmatters have exactly `name` and `description`.
- 197 relative link targets and 68 anchors resolve in the skills tree,
  including the new `#domain-adapters` pointer, and so do the two in-file
  anchors of this file.
- All 102 `titan` fences parse. The new example is a `text` fence because its
  first line is intentionally invalid.
- The reserved-word list still equals the 38 keywords in `lexer.lua`.
- Both example lines were extracted verbatim from the cartridge. The accepted
  line ran in a program; the rejected line's module reports the quoted
  diagnostic. With the controls above, that is 12 checks.
- `git diff --check` is clean.

Receipts are in `/tmp/titan-fu/eval` (`prompts.json`, case prompts, answers
and delivered files, `runs.json`, `smoke/`, `F3/` with its before and after
runs, `judgments.md`, `diagnostic/`, `run_eval.py`, `judge-run.sh`, the
memory-off overlay and both read-only cartridge exports), `/tmp/titan-fu/judge/F3`
(reference, driver, judge script) and `/tmp/titan-fu/logs` (`issue369-*.log`,
`eval/*.omp.log`), with `/tmp/titan-fu/examples` and `/tmp/titan-fu/mechanical`.
They are archived as the `issue-369-validation-archive` release on
mascarenhas/titan (the compiled `eval/build` outputs are left out).

### Issue #373 update (2026-11-07)

titan#373 types a numeric literal next to a C arithmetic operand of an
arithmetic, bitwise or shift operator by C99 rules, lets a foreign-body numeral
take a fitting C type from its declaration, assignment, argument or return, and
reports an assignment mismatch once. In `titan-ffi`, "C operator mode" now
states the literal rule (decimal and hexadecimal candidates, `double` floats,
unary `-` and `~`, comparisons unchanged) and reverses the #369 example:
`response.fills = response.fills + 1` is C `int` arithmetic with undefined
overflow, and the Titan form is preferred when the value can reach the limit.
It adds that promotion still makes an `unsigned char` or `short` sum an `int`,
how to cast the literal for a wider C type, and that a literal sum stored into
a wider C type is rejected. "Signature and body limits" gives the foreign-body
numeral rule, including that enum targets do not adapt. F3 above now accepts
the C `int` sum when the answer states its undefined overflow.

No fresh-agent evaluation was run for this update. Every added statement was
checked against titan `issue-373-c99-literals` at `ff26ecff` (validation
profile, Linux x64, gcc 16.2.1) by compiling 24 checks on a review slice:

- the two example lines, extracted verbatim and wrapped in programs: the C
  form bumps a field twice and reads 2; the Titan form also raises
  `numeric value is outside the range of foreign int` at `INT_MAX` and leaves
  the field unchanged;
- 18 controls behind the prose: the literal types (`0xFFFFFFFF`,
  `c_unsigned + -1` at run time, `3000000000` as `long` on LP64,
  `c_float * 2` and `c_float * 0.5`), non-literal operands (a local and
  `(1 + 2)`), the unchanged comparison, the `unsigned char` and `short`
  promotions with the quoted diagnostic, the wider store, the cast-literal
  shift, `size_t` and element read-modify-writes, and the foreign-body rules
  (`ffi.malloc(16)`, `255` and `300` into `unsigned char`, an integer literal
  into `float`, an operator operand, an enum target);
- F3's three claims (the `int` sum compiles, the non-literal `size_t` sum and
  the promoted `flags` update are rejected).

On master `c149571f`, 12 of the 20 checks that predate the enum and F3
controls fail, as expected.

Final-tree checks:

- All 13 frontmatters have exactly `name` and `description`.
- 199 relative link targets and 70 anchors resolve, including the two new
  in-file anchors of `titan-ffi`.
- All 102 `titan` fences parse. The example stays a `text` fence because its
  lines are fragments.
- The reserved-word list still equals the 38 keywords in `lexer.lua`.
- `git diff --check` is clean.

Receipts are in `/tmp/titan-373/review-scratch` (`skills-check/` with the
extractor, controls and logs, and `mechanical/`).

### Issue #388 evaluation (2026-11-10)

titan#388 moves browser-bridge state, policy and bookkeeping from the
loader's JavaScript into Titan, and extends the six Titan-first rules to
authored JavaScript. Three commits changed the cartridges before the
evaluation:

- `7963199`: `titan-ffi` adds "Browser JavaScript under the same rules" (the
  host-capability table and the JavaScript reading of rules 1, 3, 4 and 6),
  and `titan-programmer` points to the guard-rails for runtime JavaScript.
  The new case is `titan-ffi` Eval 17.
- `754069a`: `titan-ffi` and `titan-async` describe the bridge that #388
  ships: one-shot hold release, a cancel that drops a settlement already
  queued, the synchronous `release_callable` entry with its stopped
  collector, bounded host timers, and `WAIT_HELD`.
- `0033af3`: the prompt of `titan-ffi` Eval 16 draws out two criteria that
  the case already scored, borrowed HANDLE arguments and the generic V8
  poison.

The evaluated tree was `issue-388-guidance` at `0033af3`, based on `main` at
`0ce1d1a`. By the maintainer's decision this round used only DeepSeek
(`opencode-go/deepseek-v4.1-flash`), the acceptance floor since #370. The
cases were `titan-ffi` Eval 13 (prompt and criteria unchanged by this issue,
run as a regression over the changed body), Eval 16 (prompt revised) and
Eval 17 (new). Every statement that the three rubrics depend on was checked
against the integrated #388 tree at `476ab65d`: `titan/browser.browser.titan`,
`titan-runtime/titan/browser.h`, the loader and its two libraries, the
`spec/fixtures/browser_bridge/counter.*` fixture, and `html5.h` of Emscripten
6.0.13. No rubric contradicted the source.

Each answer came from a fresh `omp -p` process with the #366 and #370 command
shape: high thinking, only `read,write`, `--no-skills --no-context-files
--no-rules --no-session --no-extensions --no-prewalk --no-lsp --no-title`,
`--approval-mode yolo`, `--max-time 20m`, an empty scratch working directory
and the memory-off overlay, in one serial queue. Each prompt was a fixed
preamble followed by the case's prompt text, without its criteria. The
preamble allowed four cartridges (`titan-programmer`, `titan-ffi`,
`titan-async`, `titan-tester`) and no other file. A smoke prompt reported no
injected memories, and a control without the overlay reported a memory
block. The workstation block remained, so the runs were memory-free but not
completely hermetic. All three scored processes exited 0 and wrote an
answer; none was retried.

The modules that Eval 13 and Eval 16 delivered were passed unchanged to
`titanc --target browser` from the session SDK (the #388 tree, Linux x64,
Emscripten 6.0.13), and Eval 16's C helper to `emcc -c`. Eval 17 is
review-only.

| Case | Result |
| --- | --- |
| Eval 13: browser bindings and a persistent instance | Pass. Two closures over one capture are exported with `Value.is_callable`. Calls use `target:call` and case on `BrowserValue`. Integers are `5n` in both directions, and a call resolves to one bare value. The reentrant call is explained as a promise rejection that the binding's `try/catch` does not see, and `notify` with `drain` replaces it. The fetch uses the detachable form, and its failure callable takes `(is_string, is_handle)` and closes `thrown`. The page imports only the image's `create`, releases both wrappers, and awaits `dispose()` in `finally`. The 66-line module built a browser image, and both JavaScript blocks passed `node --check`. |
| Eval 16: Emscripten callback into Titan | Partial at `0033af3`; Pass on the rerun at `e4f4d45` (below). The prose meets five of the six criteria: direct `html5.h` registration through the declared function, cleanup after every status, the borrowed HANDLE argument, switches that raise so that `Task:resume` takes effect in a later turn, and `emscripten_sleep` removed, with the generic V8 poison and a test that expects no named diagnostic. The identity is not rooted: `install_click` keeps the `owned *titan_browser_identity` in a local and returns only the pin, so a collection frees the bytes that C points at. The delivered module does not compile: it invents `em_click_callback_func` (html5 declares `em_mouse_callback_func`) and passes `ffi.EM_FALSE`, a C `int`, for a C `bool` parameter. The C helper compiles, with two warnings because it passes `const` pointers to `free`. |
| Eval 17: loader JavaScript or Titan | Pass. Each part is classified by host capability. The loader mirror becomes a count that Titan owns and passes as `WAIT` or `WAIT_HELD`. Both loader prechecks are deleted under rule 6. One bounded host call stays in JavaScript, and the retry loop, the backoff and the attempt state move to Titan. The import stays a one-line forward, and the review rule is applied to the 40-line function. |

The evaluation led to the one allowed revision, `e4f4d45`, which also added
this record. It changes `titan-ffi` only:

- **Rooting (Eval 16).** The answer quoted the rule ("root the pin and the
  identity before C receives the identity") and met it with locals of the
  registering function. The rule said when rooting begins, not how long it
  lasts, and the rooted example was only linked, in the language manual. In
  "Synchronous C callbacks and Emscripten APIs" the pin bullet now says that
  both values stay reachable for as long as C can call back, that a
  module-level list or another long-lived record does this, and that locals
  do not. Eval 16's rooting criterion, a new fail signal and the final
  checklist say the same.
- **The callback and the registration call (Eval 16).** No cartridge named
  `em_mouse_callback_func` or showed a registration call. The section now
  carries the click counter itself, ahead of the rules: `counter.h`,
  `counter.c` and `counter.titan` of `spec/fixtures/browser_bridge`,
  unchanged apart from two file-name comments in the C fence, with the
  `Listener` records in a module-level `listeners` array. Three notes
  cover the call's arguments: the imported C function is passed directly,
  `useCapture` is a C `bool` that takes `0` or `1` and rejects the
  `EM_FALSE` macro, and the identity owner converts to `void *`. The cleanup
  rule names `result.value.bytes`, whose spelling the answer marked UNKNOWN,
  and the `void *` cast that `free` needs.
- **The page import (Eval 13 and Eval 16).** "Imports only the generated
  image's default `create`" is an Eval 13 criterion, but no cartridge showed
  the import. The Eval 13 answer inferred it. The Eval 16 answer marked the
  import path UNKNOWN and awaited `create`. "Instance lifetime" now begins
  with the page script: `import create from "./app.mjs"`, a `create(options)`
  that returns the instance at once, `run`, and `dispose()` in `finally`.
- **Eval 17's last criterion.** "Counts the JavaScript lines that the diff
  adds" cannot be done on a draft that the prompt only describes. The
  criterion now asks the answer to name the host capability for each
  function left in JavaScript, to treat the 40-line retry function as a
  finding, and to state the line-count rule.

Eval 16 was rerun once against the revised text at `e4f4d45`, with the same
prompt, command shape, overlay and preamble, after a smoke run that again
reported no memories. It passes, and both misses are gone:

- The pin and the identity stay in a module-level `listeners` array from
  before the registration until `stop` unregisters the callback and closes
  the pin, and the answer says why locals do not do this.
- The registration passes `ffi.click_callback` directly, with `0` for
  `useCapture`. Neither the invented typedef nor `EM_FALSE` appears.
- The page script imports the image's default `create` and does not await
  it.
- The other criteria are met as in the first round, and the cleanup rule is
  stated with `result.value.bytes` and the `void *` casts.

The delivered 100-line module built a browser image with its C helper. The
helper compiled alone with `emcc -c` and no warnings, and the page script
passed `node --check`. A scratch copy of the fixture with `useCapture`
changed to `1` also built, so both literals compile.

Two things limit what this pass shows. The answer reproduces the new example
closely (the `Listener` record, `listeners`, the registration call and
`stop`), so it shows that the example is found and applied, not that the
rule is derived independently, as #370 recorded for F2. And the answer marks
two C-side details UNKNOWN that no cartridge states: how C reads a HANDLE
`titan_browser_value`, and how C would release a HANDLE result that it
keeps. This issue leaves both as they are.

One rerun attempt before the scored one is void. The provider dropped the
connection (`ECONNRESET`), and the process ended at the 20-minute limit with
exit 1 and no answer. `runs.json` keeps its entry, and the scored run
overwrote its log.

Limitations:

- Each case has one answer from one model, and Eval 16 has one for each
  cartridge revision. Answers vary between runs.
- Print-mode logs keep only the final message, so the read-only-cartridges
  instruction rests on each answer's disclosure.
- Eval 17 is review-only, so it has no build evidence. Its placements were
  checked against the #388 tree by hand.
- No delivered page was driven in a browser.
- Everything ran on Linux x64 with Emscripten 6.0.13, so there is no macOS,
  Windows, Clang or LTO claim.

Final-tree checks, on the revised tree:

- All 13 frontmatters have exactly `name` and `description`.
- 208 relative link targets and 79 anchors resolve.
- The tree has 104 `titan` fences. The click counter is the only one that
  this branch adds or changes. It is byte-identical to `counter.titan`, which
  `spec/coder/browser_bridge_spec.lua` builds with `counter.c` and runs as a
  page test in Chromium (passing on the #388 tree at `a0931567`). The
  evaluation harness also built the fixture as a browser image from a
  scratch copy before the cases ran. The fence was not parsed or compiled
  again for this revision.
- The new page script passes `node --check`.
- `git diff --check` is clean.

Receipts are in `/tmp/titan-388/eval`: the report (`EVAL-388.md`), the
overlay (`memory-off.yml`), the preamble and prompts (`prompts/`), the
answers and their extracted files (`answers/`, `answers/compile/`), the
per-case logs, the compile log and the memory-on control (`logs/`),
`run_eval.py`, and `runs.json` with the argv, times and exit status of every
run.

### Issue #372 update (2026-11-10)

titan#372 audits the existing standard-library and runtime C against the six
Titan-first rules. The survey found legitimate code that the rules did not
name, so three points of rule text change in `doc/style-guide.md` and in
`titan-ffi` "Guard-rails for standard-library and runtime C":

- "Where each piece of a native boundary goes" gains a row for a private
  helper of a C-ABI entry or a C-only critical interval (a
  `local foreign function` called by name; code that only computes is an
  ordinary function).
- The same table gains a row for a platform-conditional operation (a
  `static inline` helper that returns a status or fills a plain struct; a
  platform fact with no argument is a macro), and rule 1 names
  platform-conditional work as the other legitimate multi-statement helper.
- Rule 2 says that scratch userdata which a runtime `lua_CFunction` keeps on
  its own stack is not transit.

In the trusted Lua C API ledger, the `lua_pcallk` row no longer names the
test helper factory: `titan.test` now calls its loaded helper chunk as a
typed function value, so no site uses `lua_pcallk` on the current state.

No fresh-agent evaluation was run for this update. It adds no example and no
case, and F2 above scores the same binding shape as before. Every added
statement was checked against titan `issue-372-native-binding-audit` at
`5973327e` (Linux x64):

- The survey in the #372 audit classifies 85 `local foreign function`s under
  the first new row and 28 header functions as platform-conditional.
  `reserve_resource` in `titan/transfer.titan` is the ordinary function that
  the row contrasts with them.
- `titan_probe_parent_stdio` in `titan/os_platform.h` fills a probe struct
  whose `status` `titan/os.native.titan` reads, and `titan/path.titan` reads
  `ffi.TITAN_PATH_WINDOWS`.
- `titan_path.c`, `ltitanlib.c` and `titan_winloader.h` hold 17 scratch
  userdata sites, and none of the three files nor `titan.c` calls `luaL_ref`
  or `luaL_unref`.
- `ffi.lua_pcallk` has three call sites under `titan/`, all on a state other
  than the caller's: two in `titan/lua/worker.titan` and one in
  `titan/thread/spawn.titan`.
- All 26 native standard-library owners pass on that tree (2,396 cases
  selected, none failed), and `spec/libuv_build_spec.lua` passes.

Final-tree checks:

- All 13 frontmatters have exactly `name` and `description`.
- 208 relative link targets and 79 anchors resolve.
- The tree has 104 `titan` fences. This update changes none of them, so none
  was parsed again.
- `git diff --check` is clean.

Receipts are in `/tmp/titan-372`: the audit (`notes/AUDIT.md`) and the test
logs (`fable/tmp/`).

## Mechanical gates

For every update:

1. Parse YAML frontmatter and require exactly `name` plus `description`; the
   directory and `name` must agree.
2. Resolve every relative Markdown link.
3. Extract every fence labeled `titan` and parse it with the current compiler
   parser. Fragments, signature inventories, placeholders, and intentionally
   invalid examples must be `text`. A cross-file example may use `titan` only
   when every file is explicit and the named composition is complete.
4. Typecheck or compile representative complete modules from every cartridge;
   compile and run native tester examples.
5. Run focused repository specs for every behavior exposed or compiler defect
   found during validation, then the broader relevant suites.
6. Run `git diff --check`, inspect all generated files, and remove exact checkout
   artifacts before committing.

At the initial tree revision, the six cartridges contain 84 complete or
explicitly paired runnable Titan fences and measure as follows with
`o200k_base`:

| Cartridge | Approx. tokens |
| --- | ---: |
| `titan-programmer` | 12,054 |
| `titan-tester` | 13,591 |
| `titan-async` | 13,261 |
| `titan-networking` | 13,891 |
| `titan-ffi` | 19,064 |
| `titan-pegs` | 12,528 |

These counts are a density guard, not a target to pad. A cartridge should remain
roughly 10–20K tokens, self-contained in its advertised domain, example-rich,
and honest about unsupported boundaries.


### JSON cartridge evaluation (2026-09-05)

Fresh agents read only the cartridges named by J1/J2; they did not read source,
manuals, tests, repository instructions, or earlier implementation discussion.
J1 produced a complete named-union/const-record round trip, lossless sentinel
tail, default nil-loss baseline, and structural const-Array decoder. A separate
current-prefix static compile and execution passed. All six complete examples
extracted from the JSON manual and skill also compiled and ran with that
provider. The evaluator correctly described private constructors, erased generic
leaves, and the retained value-Array Lua writer. No invented API was needed.

J2 identified all six parser defects and specified anchored compiled-once
matching, committed labels, fresh delayed folds, bounded callback arity,
recognition-only guards, deferred path/location formatting, native test
placement, and separate wide/deep/scaling evidence. Its exact location oracles
were correct. It marked the unlisted JSON label spellings and depth-counting
convention UNKNOWN; the JSON skill now includes the common labels and explicit
container-depth rule. J1's schema-routing ambiguity was likewise clarified: the
included recipes are ordinary use; designs beyond them add reflection guidance.

Routing checks selected JSON for ordinary Titan serialization, JSON grammar
maintenance, and native JSON mapping tests, with the relevant programmer/PEG/
tester peers. The unrelated Python JSON configuration control did not select
Titan skills. Modified skill frontmatter, Markdown fences, and JSON-relative
links passed structural validation. These are scoped J1/J2 and routing results,
not a re-evaluation of every older cartridge case.


## Named union payload exercise

Ask a fresh agent to define a union variant with `id: integer`, `end: string`,
and `note: string?`; construct it with reordered named arguments while omitting
`note`; then match only `end` using a local alias. Ask it to explain why a
second alias selecting `end` is invalid and why `id` can be omitted from the
match but not from construction. Include an existing `some(integer)` variant
and ask for its named constructor spelling.

Score the result for `value` sugar, fixed arity, left-hand aliases, keyword
part access, source-order evaluation, and distinct construction/matching
omission rules. The produced complete module must parse and typecheck; the
duplicate-selection negative example must fail parsing. This exercise targets
ordinary language use, not userdata internals.

### R1 — record calls and custom constructors (`titan-programmer` only)

Ask for an exported record with a private integer state, a public optional-input
`new` override that validates and fills that state, and an importer using named
record-call shorthand. Require raw `{ ... }` construction inside the override,
no call to a hidden default constructor, and a rejection of raw literals in
both ordinary and explicit source importers. Ask whether a second record's
`new` may return `(integer, string?)` and whether bare calls expand both results.
Require yes, ordinary call adjustment, public-only Lua namespace `__call`, and
the distinction between Titan named calls and Lua's one-table brace argument.
Require `Box<|integer|>(x)` to bind owner arguments and `.new<|U|>` for explicit
callable-local generic arguments under the existing all-or-none inference rule.
Compile the complete owner/importer examples with the current isolated toolchain.

### R2 — choosing readable constructor calls (`titan-programmer` only)

Give a fresh agent a short `Point(x: integer, y: integer)` constructor and a
record constructor with two strings, three integer positions, and two boolean
flags. Ask it to write call sites using both meaningful local variables and
literal initial state, choosing the clearest syntax. Include an overridden
`new` whose parameter names differ from the fields and a call whose arguments
have side effects.

Score whether it keeps the obvious coordinate pair concise, names ambiguous
state and flag arguments, uses constructor parameter names rather than field
names, and preserves evaluation order. A final multi-result argument requires
preserving expression-list adjustment, not blindly mapping it to one name.

## Native line coverage case (`titan-programmer`, `titan-tester`)

Ask for executable-line coverage of `app.used` and unused `app.unused` through
native tests in `app.used_tests`. The tests import both production modules, a
prebuilt dependency and a mixed module containing a `test_` function. Ask for
a basic workflow without Python/gcovr, a glob override selecting `app.*`, an
incremental rerun, an optimized release afterward without cleaning, and optional
HTML/LCOV output. Include an ordinary CLANG64 Windows validation gate.

Require boolean `--coverage` followed by direct test-binary execution, automatic
source-graph selection and whole-module exclusion for tests. Globs restrict the
same graph and still exclude mixed/prebuilt owners; explain `*`/`?` including
dots. The unused imported module remains visible with zero-hit lines. Separate
`.coverage` objects protect ordinary/release lookup; reused incremental objects
retain their file inventory. Repeated execution resets matching counters and
reports after success, while failed tests preserve failure. Basic reporting
needs only matching GCC 14+/gcov or Clang/llvm-cov gcov. Windows defaults to the
LLVM backend, validated with LLVM 22.1.8. gcovr 8.4/Python is optional for rich
formats. Require Titan line metrics, external combination/uploads, ordinary
child cleanup, build artifacts kept at embedded absolute paths, and separate
build trees for concurrent sessions.

This case is intentionally unscored until run in a fresh cartridge-only context.

### Existing application workflow with two covered executables

Give a fresh agent an application Makefile that copies sources into coverage
stages, requires Python to normalize gcovr JSON, and externally merges reports
from a test runner and its standalone child. Ask it to adopt `--output` and
retain basic native coverage. Do not request a combined metric or rich formats.

Require original-source compilation, compiler-owned `.coverage` artifacts,
native summaries and annotated reports, and no mandatory Python/gcovr or
duplicated report processing. The independent covered processes need separate
output roots for their counters; ordinary app/test links may share compatible
production objects. Retire the legacy report wrappers and update any test
expectation that requires renderer-specific output. Keep normal test failures
and child cleanup, without introducing a new custom audit or merge protocol.

An explicitly requested aggregate or rich report is a separate variant: verify
that the agent uses the compiler's rich-format options or an appropriate
external combination tool, rather than interpreting native reporting as a ban
on optional dependencies. Record observed behavior after running the case.

Forward-check on 2026-10-15: a fresh agent given only the three relevant skills,
a legacy Makefile, and its stdout assertion selected native per-executable
reports, removed mandatory Python/gcovr and merge processing, and identified the
renderer-specific assertion change. With aggregation and rich formats explicitly
requested, it allowed the optional external tooling. This was a read-only build
plan evaluation; it did not execute the application.

## Compiler-owned application builds

Give a fresh agent an application Makefile with a per-module import graph,
compiler/SDK/configuration stamps, generated source mirrors, a moved test
runner, and a C fixture rule that globs `.native/*.o`. Ask it to use the
installed compiler's incremental build contract for application and test
images, preserving a custom generator, packaging, and runtime test execution.

Require always-invoked `--incremental --output` image recipes with `+` for
Make's jobserver, exact `--exe` destinations relative to the working directory,
and direct native switches/`--c-source`. The fixture's external object consumer
must capture `-c --c-source FILE --print-c-objects`: one absolute certified path
per argument on stdout, with verbose commands and diagnostics on stderr. That
capture takes only compile-phase switches (`-I`, `-D`, `--cflag`); link
switches belong to the final images, because `-c` rejects them. A
caller-configurable `CC` must reach `titanc` unchanged (for example through
`export CC`): `titanc` parses it as shell words, so recipe re-quoting such as
`CC="$(CC)"` breaks a valid quoted path. When tests in `tests/` import modules
from `src/`, require one ordered root list such as `--tree 'src;tests'` that
keeps both logical namespaces. Reject guessed cache paths, globs, stale
`.parts` inventories, a shared complete native argument list, and a second
Make-owned invalidation graph. Score the complete proposed Makefile, not only
its Titan-specific parts: a recipe that breaks a valid caller configuration
fails the case.

Ask about shared application/test outputs, synthetic runner paths, an identical
SDK republish, and changing only source-root spelling. Require output locking,
compatible production-object reuse, target-private
`.titan-links/<key>/synthetic/`, the disposable `.titan/digests` precise-stat
hint, content-based certification that makes an identical SDK republish at
unchanged resolved paths a full hit for an otherwise cacheable build (opaque
or uncertified native mechanisms still miss either way), and legitimate
source-path-spelling misses.
Require reserved split-part paths and separate incompatible configurations.
Stock macOS Make uses the local cap for unshareable pipe jobservers; GNU Make
4.4's FIFO pool and Linux's private pipe reopen can share tokens. Windows uses
the local cap, `--exe` (with automatic `.exe`), and the provider DLL layout;
reject `--static` and any separate launcher-name option, which `titanc` lacks.

Since issue #314, also ask what `TITANC` may contain and how to validate a
relocated delivery. `TITANC` must be a single program name or path, because
compiled programs and Lua hosts run `$TITANC --print-root` without a shell for
their SDK fallback. The delivery check runs an already packaged copy with
`TITAN_ROOT`, `TITANC`, `TITAN_PATH_0_6`, and `TITAN_PATH` cleared, with
neither `titanc` nor the SDK's `lua` reachable, and with no prerequisite that
rebuilds. Providers live only beside the executable or in `../lib/titan/0.6`
next to it. The C fixture must still be linked into every image that used it.

Fresh cartridge-only runs on 2026-10-27 (read-only build plans; nothing was
executed). The first, given the skills at `b01ae48`, left identical SDK
republication as unknown, could not let `tests/` import `src` modules under one
`--tree`, and reused link options in the `-c` object capture. The second, at
`0357943`, passed every required item above. It wrote phony always-invoked
`+` recipes with exact `--exe` paths, translated `CPPFLAGS`/`CFLAGS` and
`LDFLAGS`/`LDLIBS` into phase-specific switches, and passed only compile
switches to the `--print-c-objects` capture with stderr kept separate. It used
`--tree 'src;tests'` to keep `demo.main` and `runner`, shared a compatible
output tree, and kept the Windows and jobserver distinctions. It repeated the
then-unqualified republication claim. The third, at `1f16c45`, met every
Titan-specific item, including the qualified rule: an identical republication
hits only for an otherwise cacheable build, while opaque native mechanisms and
uncertified toolchains still run. It forwarded `-I`/`-D` as single `--cflag`
arguments, which is valid but not the preferred direct spelling. It did not
pass overall: its recipes re-quoted `CC="$(CC)"`, which breaks a valid quoted
compiler path such as one under `C:/Program Files`. The skills then gained the
`export CC` rule, which a fourth fresh run had to confirm.

The fourth run, at `8758e92`, passed the case, scored on its whole Makefile. It
exported `CC` unchanged with the shell-word reason. It gave both images
always-invoked `+` recipes with exact `--exe` paths, and kept the generator
rule, packaging, and runtime test execution. It translated `CPPFLAGS`/`CFLAGS`
into direct `-I`/`-D` plus `--cflag`, and `LDFLAGS`/`LDLIBS` into direct
`-L`/`-l` plus `--ldflag`, preserving shell-word boundaries and rejecting a
dangling operand. The `--print-c-objects` capture got only the compile
switches, and it consumed each returned line separately with stderr kept
apart. It also used `--tree 'src;tests'` for `runner`, a shared default
output tree, the qualified republication rule, and the source-spelling,
split-path, jobserver, Windows payload, and staging distinctions. No
skill-caused or generic Make/shell defect was found.

## Language-server usage in omp (`titan-language-server`)

### LS1 — multi-root omp configuration, per-slice SDK selection, trust, and reload (`titan-language-server`)

Review a proposed multi-agent setup for two concurrent Titan slices
(`/tmp/titan-400/slice-a/source` with `/tmp/titan-400/slice-a/prefix` and
`/tmp/titan-400/slice-b/source` with `/tmp/titan-400/slice-b/prefix`) that:

1. builds two separate `titan-language-server` executables (one per slice) and
   writes an omp `lsp.json` entry with an invented `"env"` object setting
   `"TITAN_PREFIX": "/tmp/titan-400/slice-a/prefix"` and
   `"LUA_PATH": "/tmp/titan-400/slice-a/prefix/share/lua/5.5/?.lua;;"`;
2. edits the tracked `titan-config.lua` in `slice-a/source` to add
   `compiler_root = "/tmp/titan-400/slice-a/prefix"`, and writes
   `include = { "./titan" }` alongside `compiler_root` in
   `slice-b/source/titan-config.local.lua`;
3. omits `initOptions.trustedRoots` (and `TITAN_LS_TRUSTED_ROOTS`) and claims
   that when a root's `compiler_root` is untrusted, missing, or fails the ABI/API
   check, the router automatically falls back to its default `TITAN_ROOT` SDK so
   queries still succeed;
4. edits a compiler Lua file in `slice-a/source/titan-compiler/`, skips
   reinstalling into `slice-a/prefix`, and claims the running worker immediately
   uses the edited Lua source from the worktree; and
5. deletes `/tmp/titan-400/slice-b/source/.titan-ls` from the `slice-a` agent to
   force a fresh index.

Require the corrected `lsp.json`, `titan-config.local.lua`, and workflow
explanations covering:

- one `titan-language-server` executable serving every SDK via `compiler_root`,
  with one isolated worker process per root and the sole linked `titan` C
  support-table limit stated;
- `/usr/bin/env` in `command` and `args` (because omp's `ServerConfig` has no
  `env` field), unsetting contaminating variables (`TITAN_PREFIX`,
  `TITAN_PATH_0_6`, `TITAN_PATH`, `TITAN_SOURCE_PATH`, `LUA_PATH*`,
  `LUA_CPATH*`), `TITAN_ROOT` plus verbatim `TITAN_LS_LUA_PATH` and
  `TITAN_LS_LUA_CPATH` without `;;`, why `TITAN_PREFIX` in the server only
  redirects the C probe cache, and why `"."` in `rootMarkers` makes a user-level
  entry eligible in every `cwd`;
- keeping tracked `titan-config.lua` clean and putting **only** `compiler_root`
  in untracked `titan-config.local.lua` (any other key, non-string/empty value,
  or unreadable file fails the root);
- canonical containment in `initOptions.trustedRoots` or
  `TITAN_LS_TRUSTED_ROOTS`, and root-scoped `RequestFailed` (`-32803`) with
  **no** fallback to the default SDK when `compiler_root` is untrusted, missing,
  incomplete, or ABI/API-incompatible;
- reinstalling compiler or standard-library changes into the slice's prefix
  before expecting the worker to see them, automatic router revalidation or
  immediate `lsp(action="reload", file="*")`, and inspecting root state with
  `lsp(action="request", query="titan/workspaceStatus")` (`roots` entries with
  `root`, `origin`, `trusted`, `compilerRoot`, `state`, `failure`, `workerPid`,
  `generation`, `titanRoot`, `probePrefix`); and
- per-root `<root>/.titan-ls` cache ownership and the prohibition on deleting
  another agent's `.titan-ls` directory.

See the [recorded language-server evaluation results](#language-server-cartridge-evaluation-2026-11-04).

### LS2 — querying through omp's `lsp` tool and interpreting results (`titan-language-server` + `titan-programmer`)

Review an agent session that:

1. sets `"pullDiagnostics": false` in omp's `initOptions`, then runs
   `lsp(action="diagnostics", file="*")` and `lsp(action="symbols", file="src/main.titan")`
   on a Titan checkout and cites the responses as proof that every `.titan`
   module compiled cleanly and that `src/main.titan` declares no symbols;
2. runs `lsp(action="definition", file="src/main.titan", line=15)` without
   `symbol`, then runs `definition` on a `foreign import "stdio.h"` `ffi.printf`
   call and on a metadata-only standard-library `string.sub` call, concluding
   from `No definition found` that both calls are invalid;
3. calls `lsp(action="completion", ...)` as a named tool action, or sends
   `lsp(action="request", file="src/main.titan", query="textDocument/completion", payload=...)`
   with 1-based byte columns copied from an earlier revision of the file before
   recent edits;
4. calls `lsp(action="rename", file="src/main.titan", line=10, symbol="helper", new_name="run_helper")`
   during a read-only review under the assumption that `rename` only previews
   edits; and
5. queries a standalone scratch file `/tmp/scratch.titan` outside every
   workspace folder and with no ancestor `titan-config.lua`, or treats a
   `diagnostics` timeout / empty hover during initial indexing as a clean pass
   and skips running `titanc` and tests.

Require exact corrected `lsp(...)` calls and explanations of:

- leaving `pullDiagnostics` enabled in omp (`pullDiagnostics: false` is for VS
  Code so `vscode-languageclient` does not duplicate pushed and pulled
  diagnostics), passing a concrete `.titan` file or `.titan` glob to
  `diagnostics` (because `file="*"` invokes omp's built-in Rust/TS/Go/Python
  workspace CLI checkers, not the Titan language server), how work-done progress
  (`window/workDoneProgress/create` + `$/progress` `begin`/`report`/`end` with
  `titan-progress/<pid>/<n>`) and `textDocument/diagnostic` (`resultId` /
  `unchanged`) act as a saved-change freshness barrier (scan-only when nothing
  is dirty, revalidating newly created, deleted, edited, or dependency/folder
  contributor files on disk while returning an empty report for `.titan` files
  the project does not contain), and recognizing that `symbols`, `type_definition`,
  `implementation`, and `code_actions` are unimplemented by the server
  (`MethodNotFound`, `-32601`);
- mandatory `symbol` (with optional `name#N` 1-based occurrence selector) when
  `line` is supplied to `definition`, `references`, or `rename`, versus raw
  `action="request"` payloads using zero-based `line` and zero-based UTF-16
  `character` computed from the current saved text;
- saved-file authority for `definition`, `references`, `rename`,
  `textDocument/foldingRange`, and `diagnostics` versus buffer-captured
  `textDocument/completion` and post-completion private hover;
- why C FFI declarations (`foreign import`, `ffi.*`, `foreign` types) and
  external or metadata-only standard-library modules have no definition target
  even when hover and completion work;
- why empty/incomplete results and timeouts are inconclusive, how unowned files
  outside every workspace folder and without a `titan-config.lua` ancestor fail
  with `RequestFailed` (`-32803`), why `apply=false` is mandatory on `rename` /
  `rename_file` to prevent disk mutation, and why compiler and test runs remain
  the verification proof.


### LS3 — live multi-root omp session across two slices (`titan-language-server` + `titan-programmer`)

Run in a live environment with `cwd` `/tmp/vst/eval/work/slice-a` and tools
`read`, `write`, `lsp`, and `glob`. The project config
`/tmp/vst/eval/work/slice-a/.omp/lsp.json` is pre-configured for the session
server with `trustedRoots: ["/tmp/vst/eval/work"]` and must not be edited.

Ask the fresh evaluator to:

1. configure sibling worktree `/tmp/vst/eval/work/slice-b` to use the installed
   SDK at `/tmp/vst/sdk-b/prefix` without modifying any tracked file, and prove
   which SDK each root (`slice-a` and `slice-b`) is actually using through the
   live language server;
2. report each slice's diagnostics for `src/main.titan` with exact
   `file:line:col`;
3. report the signature of `mathutil.double` in each slice;
4. explain what an empty `hover` or `definition` result on a symbol inside a
   module with a type error means, and what establishes verification proof; and
5. leave both worktrees in the state required by the cartridge and list every
   file it created or modified.

Require:

- creating only untracked `/tmp/vst/eval/work/slice-b/titan-config.local.lua`
  assigning `compiler_root = "/tmp/vst/sdk-b/prefix"` while leaving tracked
  `titan-config.lua` and `.omp/lsp.json` untouched;
- querying `titan/workspaceStatus` through `lsp(action="request", query="titan/workspaceStatus", ...)`
  (after opening/querying a file in `slice-b` or passing `file=` so `slice-b` is
  registered and active) and citing each root's `compilerRoot` and worker-reported
  `titanRoot`;
- reporting the exact diagnostics for both `slice-a/src/main.titan` and
  `slice-b/src/main.titan` and the distinct `mathutil.double` signatures from the
  two slices;
- stating that a module that fails typechecking publishes no semantic facts for
  that generation (so empty `hover`/`definition` on its symbols is expected
  while `diagnostics` reports the error, whereas clean modules still answer
  both, and `titanc`/tests remain the proof of correctness); and
- cleaning up untracked `.titan-ls/` and `titan-config.local.lua` artifacts if
  leaving the worktrees clean, with an accurate list of touched paths.

### Language-server cartridge evaluation (2026-11-04)

Fresh evaluators were launched in separate processes with `omp -p --model opencode-go/deepseek-v4.1-flash --thinking high --no-skills --no-context-files --no-rules --no-session --approval-mode yolo`:

- **Paper cases (`LS1`, `LS2`):** `--cwd /tmp/vst/eval/paper --tools read`, reading only `/tmp/vst/skills/source/titan-language-server/SKILL.md` (`LS1` and `LS2`) and `/tmp/vst/skills/source/titan-programmer/SKILL.md` (`LS2`) at `64cefdd`.
- **Live cases (`LS3`, two independent runs):** `--cwd /tmp/vst/eval/work/slice-a --tools read,write,lsp,glob` against the `vscode-titan` `6ca55ed` server binary, reading `/tmp/vst/skills/source/titan-language-server/SKILL.md` and `/tmp/vst/skills/source/titan-programmer/SKILL.md` at `e5d9b61`, with `/tmp/vst/eval/work/slice-b/titan-config.local.lua` and both `.titan-ls/` directories removed before each run.

All four evaluators disclosed their harness-injected context: the omp role/runtime/tool-policy blocks, workstation metadata, `<system-reminder>` with date and `cwd`, and Mnemopi `<memories>` entries; no `skill://` catalog, `AGENTS.md`, or peer roster was injected.

| Case | Result and receipts | Disposition |
| --- | --- | --- |
| `LS1` | 6/6. Rejected per-slice server binaries and `"env"`; wrote `/usr/bin/env` with `-u` clearing `TITAN_PREFIX`, `TITAN_PATH*`, `TITAN_SOURCE_PATH`, `LUA_PATH*`, `LUA_CPATH*`; set `TITAN_ROOT` and verbatim `TITAN_LS_LUA_PATH`/`TITAN_LS_LUA_CPATH` without `;;`; kept tracked `titan-config.lua` clean and put only `compiler_root` in `titan-config.local.lua`; configured `initOptions.trustedRoots` with the no-fallback `-32803` and `configuration`-diagnostic rules; required reinstalling compiler Lua edits into `<slice>/prefix` and listed all 10 `titan/workspaceStatus` fields; forbade deleting a sibling's `.titan-ls/`. Marked `TITAN_LS_TRUSTED_ROOTS` separator `UNKNOWN`. | Pass. Added a 5-word note (`using the OS path-list separator`) in `3773185` for `TITAN_LS_TRUSTED_ROOTS`. |
| `LS2` | 6/6. Kept `pullDiagnostics` enabled in omp; replaced `file="*"` with concrete `.titan` files/globs; identified `symbols`, `type_definition`, `implementation`, and `code_actions` as unimplemented (`MethodNotFound` `-32601`); supplied mandatory `symbol` on `definition` and zero-based UTF-16 positions on raw `textDocument/completion`; distinguished saved-file features from buffer-based completion/private hover; explained why FFI and metadata-only stdlib modules have hover without definition targets; explained that modules failing typechecking publish no semantic facts while `diagnostics` reports the error; required `apply=false` on `rename` and `titanc`/tests as verification proof. | Pass. |
| `LS3` (run 1) | 5/5. Created only untracked `/tmp/vst/eval/work/slice-b/titan-config.local.lua` with `compiler_root = "/tmp/vst/sdk-b/prefix"`; verified via `titan/workspaceStatus` that `slice-a` used `titanRoot = "/tmp/vst/sdk/prefix"` (`compilerRoot = null`, `trusted = true`, `state = "ready"`) and `slice-b` used `compilerRoot = "/tmp/vst/sdk-b/prefix"`, `titanRoot = "/tmp/vst/sdk-b/prefix"` (`trusted = true`, `state = "ready"`, distinct `workerPid` and `probePrefix`); reported exact diagnostics (`slice-a/src/main.titan:6:26` integer vs string, `slice-b/src/main.titan:5:26` float vs string) and `mathutil.double` signatures (`double(n: integer): integer` "Doubles an integer." vs `double(x: float): float` "Halves a float."); verified empty hover/definition on failed `main.titan` vs full hover/definition on valid `mathutil.titan`; left tracked files untouched and listed all touched paths. | Pass. |
| `LS3` (run 2) | 5/5. Created only untracked `slice-b/titan-config.local.lua` with `compiler_root = "/tmp/vst/sdk-b/prefix"`; proved per-root SDK isolation through `titan/workspaceStatus` (`file=` in `slice-b`) plus an A/B control clearing the override; reported exact `main.titan` diagnostics (`6:26` and `5:26`) and `mathutil.double` signatures/docs in both slices; verified and explained empty hover/definition in failed `main.titan` vs valid `mathutil.titan`; left tracked files and `.omp/lsp.json` untouched and disclosed all touched files. | Pass. |
