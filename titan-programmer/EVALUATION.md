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
combinator spelling. Reject invented separators and nonconstant module
initializers.

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
- the scalar guarantee is distinct from aggregate byte spills: an aggregate
  whose mutable address is passed directly to a C or ordinary Titan call has
  its spill committed only after that call returns normally, so recovery sees
  a completed callee write but not the partial writes of a callee that raised.
  Scalar tests do not supply aggregate coverage;
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

## Frontmatter-only routing set

Read only each skill's YAML `name` and `description`, then choose the minimal
set for these queries:

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
    and `async.Receiver` coalescing.

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
retirement/wake protocol and tester only when writing its native tests.

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
