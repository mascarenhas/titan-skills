# Titan skill-tree evaluation

This companion is the lightweight, repeatable evaluation set for the six Titan
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

- callbacks cannot interleave with currently running Titan code;
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
the built-in `L`, and `titan.lua.load`. The answer must keep C types private,
root every retained owner, distinguish public call-only string borrowing from
the trusted standard-library exception, state the `void *` object/function-
pointer rules precisely, and treat `titan.lua` as an FFI-strength audited
escape hatch rather than a default module mechanism. For a Lua table observed
as a Map, also require the exact `__index`, `__newindex`, `__len`, and scoped
`__eq` behavior, including strict returned-value tags and raw `value`/`value`
equality.

### G1 — PEGs (`titan-programmer` + `titan-pegs`)

Build one exact Relabel-first parser that performs leftmost search, projects
captures, and reports a labeled failure with line/column. Require the anchored
`Pattern:match` versus module-level `peg.match` distinction, ordinary failure
versus `throw("fail")` versus labeled recovery, dense grammar collections,
capture callback timing, compile-local `Definition` values, and equivalent
combinator spelling. Reject invented separators and nonconstant module
initializers.

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
8. review private `titan.uv` callback rooting;
9. dynamically load a Lua plugin from Titan;
10. use only `titan.string` regex;
11. change a URL PEG grammar;
12. edit a Lua-only Busted packaging test;
13. write Python `requests` HTTP code;
14. write C-only libuv code; and
15. author a source-defined C callback used by a PEG native Titan test.

The intended policy is additive: `titan-programmer` is mandatory for `.titan`
work, while specialist skills activate only for their real boundary. Important
negative controls are no PEG cartridge for `titan.string` regex alone, no
programmer cartridge for a Lua-only test, and no Titan networking/async/FFI
cartridge for unrelated Python or C work.

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
