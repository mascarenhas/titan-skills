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
manual merely to answer the cartridge's advertised domain.

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
the built-ins `L` and `M`, and `titan.lua.load`. The answer must distinguish the
exportable contextual primitive/pointer/function/owner closure from imported
header-dependent C types that remain private, root every retained owner,
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

The first JSON evaluation results are recorded below.

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
19. edit a JSON configuration file for an unrelated Python application.

The intended policy is additive: `titan-programmer` is mandatory for `.titan`
work, while specialist skills activate only for their real boundary. Important
negative controls are no PEG cartridge for `titan.string` regex alone, no
programmer cartridge for a Lua-only test, and no Titan networking/async/FFI
cartridge for unrelated Python or C work; no JSON cartridge merely because
a configuration file uses JSON. Ordinary JSON use selects programmer + json;
JSON grammar changes add pegs, JSON tests add tester, and explicit reflection
construction work adds reflect.

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

Ask for coverage of production modules `app.used` and `app.unused` through native
tests in `app.used_tests`, with an ordinary CLANG64 Windows validation gate.
Require an explicit complete production inventory, an isolated coverage build,
GCC 14+ with matching gcov, pinned gcovr 8.4, and host-side seal/run/report after
process exit. The unused module must remain in the denominator. Test support,
helpers and native dependencies must stay outside it; Windows must reject the
unsupported backend while its ordinary native suite remains available.

Ask whether successful HTML rendering makes a failed test pass, whether branch
or function percentages are part of the contract, and whether local coverage
requires a Codecov token. Require preserved failure/incomplete receipts, line
metrics alone, and a separate CI upload. Ask how to reuse counters and how to
measure a staged source copy: require a fresh run directory per process tree,
matching build/run provenance for merging, explicit source mappings and exact
compiled/tracked source bytes.

This case is intentionally unscored until run in a fresh cartridge-only context.
