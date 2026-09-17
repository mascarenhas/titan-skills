---
name: titan-pegs
description: Design, review, compile, and test byte-oriented parsers with Titan's typed titan.peg standard module. Prefer Relabel source notation for ordinary grammars, labeled errors, captures, and recovery; use the named combinator API when patterns must be assembled dynamically or need low-level runtime captures.
---

# Titan PEGs

Use this skill when code imports `"peg"`/`"titan.peg"`, builds a parser,
translates a textual grammar, handles LPegLabel-style failures, or chooses
between PEG parsing and `titan.string` regular expressions. Read
`titan-programmer` first; add `titan-tester` for native parser tests,
`titan-networking` when changing URL grammar behavior, and `titan-ffi` when
changing the private embedded engine boundary.

Titan's PEG API is **typed Titan**, backed by a private embedded LPegLabel
engine. It is not the Lua `lpeg`/`lpeglabel` API with operators renamed. Do not
run `.titan` source with Lua, pass an external LPeg pattern to this module, or
infer Titan call/result behavior from a Lua tutorial.

```text
local peg = import "peg" -- sugar for import "titan.peg"
```

Lua imports the compiled standard module as `require "titan.peg"`, but Lua and
Titan see opaque Titan records, not the external `lpeglabel` module's pattern
userdata. The embedded engine has its own native identity and stack setting.

Titan callback signatures use `function(...): results`; Relabel capture arrows
inside grammar strings remain `->` and `~>`. Do not rewrite those grammar
operators when migrating Titan type syntax.

## The five facts to remember

1. **Prefer Relabel notation.** For a grammar that can be written as source,
   call `peg.compile([[ ... ]])`. It is shorter, makes labels and captures
   visible at the grammar site, and is Titan's shipped dogfood path.
2. **A `Pattern:match` is anchored only at its initial position.** It attempts
   the pattern once there, but it does not require end of input. Add `!.` in
   Relabel or `peg.negative(peg.any())` with combinators for a complete parse.
3. **`peg.match` is the leftmost-search API.** It returns `peg.Match?` with an
   inclusive span and separately projected captures. There is no `peg.find`.
4. **Patterns operate on bytes.** `.` is one arbitrary byte, classes are byte
   classes, positions are one-based byte positions, and only `utf_range`
   interprets UTF-8 encodings.
5. **A label commits.** Ordinary failure may try another ordered alternative,
   another search position, or end a repetition. An uncaught `%{label}`/
   `peg.throw(label)` escapes those choices and reports its exact throw
   position. The spelling `fail` is reserved for ordinary failure.

Authority: `doc/language/standard-library-peg.md:1-27,291-340,402-530` and
`titan/peg/peg.titan:142-151,549-623`.

## Choose the right parsing surface

| Need | Use |
| --- | --- |
| A declarative parser or grammar | `peg.compile(source, definitions?)` |
| An anchored attempt at one position, with failure label/position | `pattern:match(subject, init?, ...arguments)` |
| A leftmost match at or after a position | `peg.match(subject, source_or_pattern, init?)` |
| Global whole-match replacement | `peg.gsub(subject, source_or_pattern, replacement)` |
| Patterns assembled from run-time pieces, arbitrary binary names, or low-level captures | Named combinators such as `sequence`, `choice`, `capture`, `grammar` |
| A conventional regex with backtracking repetition, `|`, capture groups, and iteration | `titan.string.compile_regex`, not `titan.peg` |

`Pattern:match` and `peg.match` interpret the candidate pattern identically,
and neither silently appends an end test. Their search and result/failure
protocols differ: the method exposes an anchored capture/failure run, while the
module function returns a leftmost `Match?`.

Complete copy-paste modules below use `titan` fences. Deliberate expression,
function-body, or final-initializer fragments use `text` and assume the visible
`local peg = import "peg"` context. A fragment is not permission to call an
imported function in an ordinary module-variable initializer.

### PEGs are not `titan.string.Regex`

Both APIs are byte-oriented, but their languages and matching policies differ:

* Relabel choice is `/`; regex alternation is `|`.
* PEG choice is ordered and PEG repetition is possessive. A repeated PEG does
  not shorten itself to satisfy a later expression. Regex repetition is
  continuation-aware and can backtrack.
* Relabel `.` matches any byte, including LF. Titan regex `.` excludes LF.
* Relabel quoted literals have no backslash escape layer. Titan regex has its
  documented regex escapes.
* `Pattern:match` starts exactly at `init`; `Regex:match` performs a leftmost
  search unless `^` anchors its expression. PEG's explicit search is
  module-level `peg.match`.
* PEG captures can produce arbitrary `value` runs, tables, substitutions, and
  match-time actions. Regex matches expose typed whole/group spans.

For example, this PEG is usually wrong if the intent is “scan until `x`”:

```text
local wrong = peg.compile(".* 'x'")
```

`.*` possessively consumes the `x`, so the following literal cannot match.
Constrain the repeated operand instead:

```text
local right = peg.compile("(!'x' .)* 'x'")
```

Authority: `doc/language/standard-library-peg.md:121-168,480-518`,
`doc/language/standard-library-string.md:278-320,371-469`, and
`spec/stdlib/titan/string/regex_test.titan:234-325,471-529`.

## Preferred workflow: compile once, return a capture envelope, label expected failures

The upstream family often calls this the **`re` syntax**; Titan documents and
exports it as **Relabel source notation** through `peg.compile` rather than as a
separate `re` module.

A production parser should normally:

1. express the grammar in Relabel source;
2. compile it once in the owning module's final initializer;
3. use a non-nil capture envelope (often `{| ... |}`) for success;
4. add `!.` or a labeled end check for complete input;
5. turn the `Pattern:match` failure label and byte position into the module's
   own typed error value.

This complete standalone example parses one assignment. Save it as
`assignment.titan`:

```titan
local peg = import "peg"

record Assignment
  name: string
  contents: string
end

record ParseError
  label: string
  position: integer
end

local ASSIGNMENT_PATTERN: peg.Pattern? = nil

local function build_assignment_pattern(): peg.Pattern
  return peg.compile([[
    Assignment <- {|
      {:name: {Identifier / %{expected_name}} :}
      %s* ('=' / %{expected_equals}) %s*
      {:contents: {[^%s]+ / %{expected_value}} :}
      (!. / %{trailing_input})
    |}

    Identifier <- [A-Za-z_] [A-Za-z0-9_]*
  ]])
end

function parse_assignment(subject: string): (Assignment?, ParseError?)
  local captured, failure_label, failure_position =
    ASSIGNMENT_PATTERN:match(subject)
  if captured == nil then
    local label = "fail"
    local position = 1
    if failure_label ~= nil then label = failure_label as string end
    if failure_position ~= nil then
      position = failure_position as integer
    end
    return nil, ParseError.new(label, position)
  end

  local fields = captured as {value: value}
  return Assignment.new(
    fields["name"] as string,
    fields["contents"] as string), nil
end

function main(args: {string}): integer
  local parsed?, failure? = parse_assignment("target = Titan")
  if parsed == nil or failure ~= nil then return 1 end
  if parsed.name ~= "target" or parsed.contents ~= "Titan" then return 2 end

  local rejected?, reason? = parse_assignment("target Titan")
  if rejected ~= nil or reason == nil then return 3 end
  if reason.label ~= "expected_equals" or reason.position ~= 8 then
    return 4
  end
  return 0
end

do
  ASSIGNMENT_PATTERN = build_assignment_pattern()
end
```

Compile from the source directory with a prepared, ABI-matched Titan toolchain:

```sh
titanc assignment
./assignment
```

Why this shape is robust:

* the first grammar rule, `Assignment`, is the start rule;
* `{| ... |}` returns one non-nil table capture, so `captured == nil` is a safe
  failure test for this parser;
* `{:name: ... :}` and `{:contents: ... :}` put named values in that table rather
  than adding positional return values;
* labels are placed at the byte where each missing construct is expected;
* `(!. / %{trailing_input})` both requires complete input and gives a useful
  label instead of a generic farthest-failure result;
* the pattern is compiled once, not per call.

`titan.url` is the production model for this style: it compiles an RFC-derived
Relabel grammar once, captures a named table, places labels at policy
boundaries, calls anchored `Pattern:match`, and converts `(label, position)`
into a typed nonthrowing error. See `titan/url.titan:25-163,198-201,288-405`.

## Relabel notation

Relabel source compiles to the same opaque `peg.Pattern` as the combinator API.
Use a Titan long string for a multiline grammar so Titan string escaping does
not obscure the parser notation.

### Core expressions and precedence

| Relabel | Meaning | Named API equivalent |
| --- | --- | --- |
| `'text'`, `"text"` | exact binary literal | `peg.literal(text)` |
| `.` | any one byte | `peg.any()` |
| `[a-zA-Z_]` | one byte from a class/range | `peg.set`/`peg.ranges` |
| `[^0-9]` | complemented byte class | `peg.difference(peg.any(), ...)` |
| `(p)` | grouping | `p` |
| `p q` | sequence | `peg.sequence(p, q)` |
| `p / q` | ordered choice | `peg.choice(p, q)` |
| `&p` | positive, non-consuming predicate | `peg.lookahead(p)` |
| `!p` | negative, non-consuming predicate | `peg.negative(p)` |
| `p?` | at most one | `peg.optional(p)` |
| `p*` | zero or more, possessive | `peg.zero_or_more(p)` |
| `p+` | one or more, possessive | `peg.one_or_more(p)` |
| `p^n` | exactly `n` | repeated sequence |
| `p^+n` | at least `n` | `peg.at_least(p, n)` |
| `p^-n` | at most `n` | `peg.at_most(p, n)` |
| `%name` | predefined or supplied definition | the bound pattern `p`; package it for source compilation as `peg.define(name, p)` |
| `name`, `<name>` | grammar nonterminal | `peg.variable(name)` |
| `name <- p` | grammar rule | `peg.rule(name, p)` |
| `%{label}` | labeled throw | `peg.throw(label)` |
| `p^label` | `p / %{label}` | `peg.choice(p, peg.throw(label))` |

Prefix predicates bind before sequence; suffixes bind to their preceding
primary/group; sequence binds before `/`. Parenthesize around a multi-part
construct before applying a suffix or label when intent might be unclear.

There may be whitespace before `^`, but no whitespace between `^` and its
operand. Write `'a'^3`, `'a'^+3`, `'a'^-3`, and `'a'^expected`; do not write
`'a' ^ expected`. A decimal operand selects repetition. An immediately
following identifier selects a label.

### Literals, classes, definitions, and comments

Relabel's quoted literal ends at the next matching quote. It has **no backslash
escape layer**. Use the other delimiter when the text contains one quote kind,
or concatenate adjacent literals. In a Titan `[[...]]` long string, a
backslash is just a backslash to Relabel.

Classes contain literal bytes, inclusive `a-z` ranges, and `%name` pattern
definitions. A leading `^` complements the class. Relabel is byte-oriented;
`[A-Z]` is exactly the ASCII byte range, not a Unicode category.

The predefined locale definitions are:

```text
alnum alpha cntrl digit graph lower print punct space upper xdigit
```

Short spellings are:

```text
a c d g l p s u w x
```

Their uppercase short forms are complements (`%D`, `%S`, and so on), and `%nl`
matches LF. These character classes follow the current C locale snapshot;
`peg.update_locale()` rebuilds them and clears the definition-free source
cache.

Whitespace and Lua-style `--` line comments are ignored between syntax items:

```text
local parser = peg.compile([[
  Start <- Word !.       -- the first rule is the start rule
  Word <- [A-Za-z_]
          [A-Za-z0-9_]*
]])
```

A bare name denotes a nonterminal and is legal only in a grammar. `%name`
denotes a predefined or externally supplied definition. Do not confuse these:

```text
Number <- %digit+   -- Number is a grammar rule; %digit is a definition
```

Grammar and definition identifiers use `[A-Za-z_][A-Za-z0-9_]*`. The direct
combinator API can still use arbitrary binary strings for rule names and throw
labels.

Authority: `doc/language/standard-library-peg.md:402-518` and
`titan/peg/relabel.titan:529-648,651-724`.

## Grammars and external definitions

A Relabel source containing rules is a grammar. The **first rule is the start
rule**. Rules may be recursive and may be referenced before or after their
textual definition.

```text
local balanced = peg.compile([[
  Start <- Balanced !.
  Balanced <- '(' (Text / Balanced)* ')'
  Text <- [^()]+
]])
```

Keep the end predicate in the start rule rather than the recursive rule; an
end predicate inside `Balanced` would incorrectly require every nested pair to
reach the subject's end.

The equivalent dynamic grammar uses a dense Titan Array of `peg.Rule`:

```text
local text = peg.one_or_more(peg.difference(
  peg.any(), peg.set("()")))
local rules: {peg.Rule} = {
  peg.rule("Start", peg.sequence(
    peg.variable("Balanced"), peg.negative(peg.any()))),
  peg.rule("Balanced", peg.sequence(
    peg.literal("("),
    peg.zero_or_more(peg.choice(text, peg.variable("Balanced"))),
    peg.literal(")"))),
}
local balanced = peg.grammar("Start", rules)
```

`peg.variable` is an open grammar reference; the native engine rejects one
used outside a closed grammar. Rule names must be unique, the named start rule
must exist, and a grammar has at most 1000 rules.

### Mix declarative grammar with dynamic patterns

Use `peg.define` to package a `Pattern` binding for `%name`, and pass that
`Definition` in the same `peg.compile` call's dense definitions Array. Use
`peg.define_value` there for a replacement table, template, selector,
match-time callback, fold callback, or delayed function callback. Definitions
are values, not global registrations.

```titan
local peg = import "peg"

local function decimal(candidate: value): integer
  -- Kept deliberately small for the three inputs below; a real parser should
  -- call its owning module's ordinary checked decimal helper.
  local text = candidate as string
  if text == "3" then return 3
  elseif text == "50" then return 50
  elseif text == "401" then return 401
  end
  return 0
end

local function add_values(accumulator: value, ...: value): value
  local total = accumulator as integer
  local index = 1
  while index <= #... do
    total = total + (...[index] as integer)
    index = index + 1
  end
  return total
end

local sum_pattern: peg.Pattern? = nil

function sum_example(): integer
  return sum_pattern:match("3 401 50") as integer
end

do
  sum_pattern = peg.compile([[
    Sum <- (Number (%s+ Number)*) ~> add !.
    Number <- {%d+} -> decimal
  ]], {
    peg.define_value("decimal", decimal),
    peg.define_value("add", add_values),
  })
end
```

This is the test-proven pattern from
`spec/stdlib/titan/peg/tests/relabel_test.titan:115-186,226-233`.
Real decimal conversion should use the owning module's normal numeric helper;
the point here is the capture/fold protocol.

The definitions argument is a **Titan Array** `{peg.Definition}`, not a Map.
Names must be unique. `define_value` rejects nil and false because Relabel
interprets them as absent. Definition names may be arbitrary strings at the
API boundary, but a name that the source notation cannot spell is unreachable.

`peg.compile(existing_pattern, definitions)` returns the same pattern and
ignores the definitions. `peg.match` and `peg.gsub` have no definitions
parameter: when search or substitution needs external definitions, compile
first and pass the resulting `Pattern`.

Definition-free source strings use a private weak compilation cache shared by
`compile`, module-level `match`, and `gsub`. Definitions make compilation
context-specific and bypass that source-only cache. Compile stable application
grammars once anyway; it makes initialization failure and ownership explicit.

## Captures in Relabel

Captures are values produced by a successful pattern. They do not change where
matching begins, and a capture-free successful `Pattern:match` returns the
position after the match instead.

| Relabel | Capture behavior |
| --- | --- |
| `{}` | current absolute one-based position |
| `{ p }` | whole substring matched by `p` |
| `{: p :}` | anonymous group; yields nested captures, or the whole substring if none |
| `{:name: p :}` | named group; no direct result |
| `=name` | match the subject bytes equal to the latest named group's value |
| `{| p |}` | table capture |
| `{~ p ~}` | substitution capture |
| `p -> 0` | discard `p`'s captures |
| `p -> n` | select nested capture `n` (`1..32767`) |
| `p -> 'template'` | apply `%0..%9` capture template |
| `p -> {}` | table-capture the nested results |
| `p -> name` | use a supplied template/selector/query/callback value |
| `p => name` | run a supplied match-time callback |
| `p ~> name` | fold nested capture operations with a supplied callback |

### Named groups, backreferences, and table captures

A named group is deliberately hidden from the ordinary result run. A table
capture stores the first value of each named group under its key; anonymous
captures occupy consecutive integer keys.

```text
local tagged = peg.compile([[
  {| {:kind: {%a+} :} ':' {:body: {.*} :} |} !.
]])
local captured: value = tagged:match("note:hello")
local fields = captured as {value: value}
-- fields["kind"] == "note"; fields["body"] == "hello"
```

Relabel `=name` is a matching backreference, not merely a request to return a
value. It compares the upcoming subject bytes to the latest matching named
group and consumes them on success:

```text
local doubled = peg.compile([[
  {:word: {%a+} :} %s+ =word !.
]])
-- matches "echo echo", not "echo other"
```

The lower-level `peg.back_capture(key)`, by contrast, returns the named group's
capture values without consuming subject bytes. Relabel implements its textual
backreference by combining a back capture with a match-time comparison.

### Templates, tables, and callbacks

A template's `%0` is the whole matched substring. `%1` through `%9` refer to
nested captures. With no nested captures, `%0` works but `%1` is an error.

```text
local swap = peg.compile("({.}{.}) -> '%2%1'")
-- swap:match("ab") == "ba"
```

`-> 0` discards captures; a capture-free successful anchored match then returns
its after-position. `-> {}` builds a raw Map-like table value. A supplied Map
uses query-capture behavior (including ordinary `__index`); a supplied string
is a template; a value satisfying Titan's checked `is integer` predicate is a
selector (so an in-range integral float also qualifies); every other supplied
value is treated as a delayed callable and fails only if matching reaches it
and tries to call it.

A table capture puts anonymous values at integer keys and the first value of
each named group at its named key. It does not turn the result into a Titan
Array. Cast it to the Map type that reflects the heterogeneous capture surface,
usually `{value: value}`.

### Capture defaults when the child has no capture

LPeg's implicit rules are operation-specific:

* `{ p }` always captures the whole substring.
* anonymous `{: p :}` yields the whole substring when `p` has no nested
  capture;
* a named group followed by direct `peg.back_capture` likewise supplies its
  whole substring if it has no nested capture;
* query/function capture and selector 1 receive/select the whole substring;
* template `%0` is the whole substring, but `%1` errors;
* table capture produces an empty table;
* fold capture errors because it has no initial accumulator;
* selector 0 produces no capture.

`peg.capture(p)` in the named API is subtly different from “replace with the
whole string”: it returns the whole substring **first, followed by any nested
captures**.

Authority: `doc/language/standard-library-peg.md:170-289,480-518`,
`titan/peg/peg.titan:393-503`, and
`spec/stdlib/titan/peg/tests/core_test.titan:384-490`.

## Callback timing and result protocols

Use pure callbacks when possible. PEG capture evaluation is not an exactly-once
side-effect mechanism.

### Immediate matching callbacks

`peg.runtime(callback)` runs at the current position and receives:

```text
(subject, current_absolute_position, "")
```

The third value is always the empty whole-match string. Its first result means:

* nil, false, or no result: fail;
* true: succeed without moving;
* integer: succeed at that new absolute position;
* later results: captures.

The new position must lie between the current position and one past the end.

`peg.match_time(p, callback)` and Relabel `p => name` first match `p`, then call:

```text
(subject, absolute_position_after_p, first_capture, ...captures)
```

If `p` has no capture, the callback receives the whole matched substring as its
capture-side argument. Its first result has the same fail/true/new-position
protocol; later results become captures.

Runtime and match-time callbacks execute immediately while the engine is
choosing a path. They can therefore run on an alternative that later fails.

### Delayed capture callbacks

`peg.function_capture(p, callback)`/Relabel `p -> name` calls the function with
all nested capture values, or the whole substring when there are none. Every
result becomes a capture.

`peg.fold_capture(p, callback)`/Relabel `p ~> name` uses the first nested
capture as the accumulator and calls `callback(accumulator, next...)` for each
later capture operation. One operation may contribute zero or several values;
the callback returns exactly one new accumulator.

Function and fold callbacks are delayed until capture results are evaluated. A
delayed callback on an abandoned alternative does not run. Ordinary capture
evaluation may happen zero, one, or multiple times, so even delayed callbacks
must not rely on exactly-once external mutation.

All PEG callbacks are non-yieldable. They may allocate or raise, but attempting
to yield raises a normal Lua-boundary error. A callback error propagates; it is
not converted to a match failure or label.

Exact public callback types are:

```text
function(string, integer, string): (...: value)                    -- runtime
function(string, integer, value, ...: value): (...: value)         -- match_time
function(value, ...: value): (...: value)                          -- function_capture
function(value, ...: value): value                                 -- fold_capture
function(string): string                                           -- public gsub
```

Authority: `doc/language/standard-library-peg.md:248-289`,
`doc/implementation/lpeglabel-embedding.md:150-190,282-320`, and
`spec/stdlib/titan/peg/tests/core_test.titan:467-560`.

## Labels, commitment, recovery, and good diagnostics

### Ordinary failure versus labeled failure

Ordered choice catches ordinary failure only:

```text
local ordinary = peg.compile("'a' / 'b'")
local committed = peg.compile("%{expected_a} / 'b'")
```

The first can try `'b'`. The second throws immediately and never tries it.
Likewise, module-level search advances to another byte only after ordinary
failure; an uncaught label stops the search.

Place a label where you want its byte position reported. `p^label` is
`p / %{label}`. If `p` consumes internally and then fails, ordered choice
rewinds to the start of `p` before throwing. Split a multi-byte expectation if
you need a later position:

```text
'BEGIN' (';' / %{expected_semicolon})
```

A throw inside a positive or negative predicate becomes predicate failure
instead of escaping. This matters for diagnostic lookahead: do not hide the
only useful label inside `&(...)` or `!(...)` unless ordinary predicate behavior
is intentional.

The exact string `fail` is reserved. `%{fail}`, `p^fail`, and
`peg.throw("fail")` are ordinary failure. They can fall through choice, end a
repetition, and let search advance. A recovery rule named `fail` can never
catch them.

Other labels are exact binary strings at the combinator API. Empty,
numeric-looking, and NUL-containing labels remain distinct. Relabel's
`%{01}` produces the string label `"01"`, not integer 1.

### Recovery rules

Inside a grammar, a rule whose name equals a thrown label is its recovery rule.
Recovery begins at the throw position; if it succeeds, matching resumes after
the expression that threw.

This small grammar is the canonical behavior test:

```text
local recovered = peg.compile([[
  S <- ('a'^recover) 'b'
  recover <- 'x'
]])
-- recovered:match("xb") == 3
```

`'a'` fails, `^recover` throws at byte 1, rule `recover` consumes `'x'`, and
the original sequence resumes with `'b'`. Without that rule, the label escapes
as a failure triple. Use recovery only when the parser has a real resynchronizing
contract. Do not add a catch-all recovery rule merely to hide malformed input;
uncaught labels are usually better for a public parser that returns one precise
error.

### Subject match failure results

An anchored match with no captures succeeds with the absolute position after
the match. A match with captures returns exactly those capture values. On
failure it returns exactly:

```text
nil, "fail", absolute_farthest_position        -- ordinary failure
nil, label, absolute_throw_position            -- uncaught label
```

Failure positions stay absolute even when `init` is not 1.

A successful pattern is allowed to capture nil, including a first or trailing
nil. Consequently, arbitrary captures can even imitate the three values of a
failure. Do not use `first_result == nil` as a universal success discriminator
when the parser's first successful capture may be nil. Prefer one of these:

* design an always-non-nil envelope capture, such as `{| ... |}`;
* use module-level `peg.match`, whose `Match?` separates match status from
  `Match:values()`;
* know and enforce a non-nil first capture type at your parser boundary.

This edge is pinned by
`spec/stdlib/titan/peg/tests/core_test.titan:305-381`.

### Grammar-source syntax errors

`peg.compile(source)` raises an ordinary string when the **Relabel notation**
is malformed. This is separate from a valid pattern failing on a subject. The
message has a stable parser label, one-based byte position, line/column, source
line, and caret:

```text
PEG syntax error [ExpPatt1] at L1:C6 (byte 6): expected a pattern after '/'
'p' /
     ^
```

CRLF is one line ending. End-of-input may put the caret one byte after the
source line. Compile stable grammars in module initialization so a bad grammar
fails at startup rather than on a rare request.

When a tool accepts user-authored grammar source, catch compilation errors at
the natural function/block boundary. Titan has no `try`; `catch` can attach
directly to a function body:

```text
local function compile_user_grammar(source: string): peg.Pattern?
  return peg.compile(source)
catch
  -- error: value and traceback: string are available here.
  -- Preserve or convert the exact error according to the owning API.
  return nil
end
```

`peg.line_column(subject, position)` converts a byte position in
`1..#subject+1` to one-based `(line, column)` with the same CR/LF/CRLF
convention. Use it to enrich a valid parser's returned label/position; do not
reimplement byte/line accounting ad hoc.

Authority: `doc/language/standard-library-peg.md:149-168,291-340,520-530`,
`titan/peg/relabel.titan:64-157`, and
`spec/stdlib/titan/peg/tests/relabel_test.titan:391-443`.

## Anchored matching versus leftmost search

### `Pattern:match`: one anchored attempt

```text
function Pattern:match(
  subject: string,
  init: integer?,
  ...: value
): (value, ...: value)
```

It begins exactly at normalized `init`. It does not scan forward. Extra values
are available to `peg.argument(n)`. To name such a pattern in Relabel source,
pass the resulting `Definition` to that exact `compile` call:

```text
local state_pattern = peg.compile("%state", {
  peg.define("state", peg.argument(1)),
})
local word = peg.compile("{%a+}")
local captured: value = word:match("Titan 42") -- "Titan"
local absent: value = word:match("42 Titan")   -- nil (anchored at byte 1)
```

To require the whole subject:

```text
local whole_word = peg.compile("{%a+} !.")
```

### `peg.match`: leftmost search and a typed span

```text
function match(
  subject: string,
  candidate: value,
  init: integer?
): peg.Match?
```

`candidate` must be a Relabel source string or this module's `Pattern`.
Search tries each byte position through `#subject+1` after ordinary failure. A
label commits and makes the search return nil; module-level search deliberately
does not expose that label or position. Compile and use `Pattern:match` when
failure detail is required.

```text
local function find_identifier(subject: string): string?
  local hit? = peg.match(
    subject, "{[A-Za-z_][A-Za-z0-9_]*}")
  if hit == nil then return nil end
  local found: peg.Match = hit
  -- For "123 Titan42!": found.first == 5; found.last == 11.
  local spelling: value = found:values()
  return spelling as string
end
```

`Match.first` and `Match.last` are one-based and inclusive. An empty match at
`first` has `last == first - 1`. `Match:values()` returns exactly the
candidate's captures, preserving nil and trailing nil; it returns **zero
values** when the candidate has no captures.

There is no `peg.find`. PEG source versus an already compiled `Pattern` is not
a useful literal/pattern distinction, so one module-level `match` handles both.

### Initial-position normalization

Both anchored and search matching normalize `init` this way:

| Supplied `init` | Normalized start |
| --- | --- |
| nil or omitted | 1 |
| positive `1..#subject+1` | supplied position |
| positive `>#subject+1` | `#subject+1` |
| `0` | `#subject+1` |
| negative in range | `#subject + init + 1` |
| negative overshoot | 1 |

Thus `-1` starts at the last byte, while **zero starts after the last byte**.
This intentionally differs from Titan regex search, where zero normalizes to
byte 1.

### Search does not repeat a successful match

Module search performs one anchored attempt per candidate start and keeps the
first success, its inclusive span, and its captures. It does not rerun a
successful candidate merely to recover captures. Match-time side effects for
the successful attempt therefore are not duplicated by search bookkeeping.

Authority: `doc/language/standard-library-peg.md:291-340,421-460`,
`titan/peg/peg.titan:115-158,567-593`, and
`spec/stdlib/titan/peg/tests/relabel_test.titan:285-356`.

## Substitution

The public global substitution API is deliberately narrow:

```text
function gsub(
  subject: string,
  candidate: value,
  replacement: function (string): (string)
): string
```

It searches globally, calls `replacement` once per accepted match with the
**whole matched byte string**, and inserts the returned string literally.
Captures inside the candidate do not change the callback arguments.

```text
local function bracket(found: string): string
  return "[" .. found .. "]"
end

local changed = peg.gsub("aba", "'a'", bracket)
-- changed == "[a]b[a]"
```

Unlike Lua `string.gsub`, this returns no replacement count. There is no public
template/table/selector overload on the callback parameter. If the grammar
itself needs a template, selector, query table, or dynamic capture callback,
put the corresponding `-> ...` suffix inside Relabel source or build the
capture combinator explicitly. The public replacement remains exactly
`function (string): (string)`.

`candidate` may be source or a compiled Pattern. As with search, compile first
when external definitions are needed.

Authority: `doc/language/standard-library-peg.md:421-478`,
`titan/peg/peg.titan:595-620`, and
`spec/stdlib/titan/peg/tests/relabel_test.titan:358-380`.

## Named combinator API

Prefer Relabel for static grammar structure. Use these functions when a pattern
must be assembled from typed run-time pieces, when a rule/label name is not
spellable in Relabel, or when direct capture primitives make ownership clearer.
Titan deliberately uses named functions instead of LPeg's overloaded
operators.

### Opaque types

These are the declarations inside `titan.peg`; consumers refer to them as
`peg.Pattern`, `peg.Rule`, `peg.Definition`, `peg.Match`, and `peg.Locale`.

```text
record Pattern
record Rule
record Definition

record Match
  first: integer
  last: integer
end

record Locale
  alnum: Pattern
  alpha: Pattern
  cntrl: Pattern
  digit: Pattern
  graph: Pattern
  lower: Pattern
  print: Pattern
  punct: Pattern
  space: Pattern
  upper: Pattern
  xdigit: Pattern
end
```

`Pattern`, `Rule`, and `Definition` internals are opaque. Do not inspect raw
native patterns, tree sizes, or definition values. The remaining prototypes
are the exact declarations inside `titan.peg`; consumers call them through the
alias, for example `peg.literal("x")`.

### Constructors and grammar

```text
function literal(text: string): Pattern
function any(count: integer?): Pattern
function succeed(): Pattern
function fail(): Pattern
function runtime(
  callback: function (string, integer, string): (...: value)
): Pattern

function set(bytes: string): Pattern
function ranges(...: string): Pattern
function utf_range(first: integer, last: integer): Pattern

function variable(name: string): Pattern
function rule(name: string, pattern: Pattern): Rule
function grammar(start: string, rules: {Rule}): Pattern
function behind(pattern: Pattern): Pattern
function throw(label: string): Pattern
```

Semantics that are easy to miss:

* `literal("")` succeeds without consuming.
* `any()`/`any(nil)` means exactly one byte; `any(0)` is empty success;
  positive `n` means exactly `n` bytes. Negative `-n` succeeds without
  consuming only when fewer than `n` bytes remain.
* `set` is a set of bytes. `ranges` receives any number of exactly-two-byte
  strings; no ranges means failure.
* `utf_range` matches an encoded code point in the inclusive bounds. It is the
  only UTF-8-aware constructor, and the pinned engine deliberately accepts
  UTF-8 encodings of surrogate code points. It is not a Unicode scalar-value
  mode for surrounding patterns.
* `behind` requires a capture-free fixed-length child no wider than 255 bytes.
* grammar `rules` is a dense Titan Array, not a Map or ordinary Lua table.

### Composition and repetition

```text
function sequence(...: Pattern): Pattern
function choice(...: Pattern): Pattern
function difference(first: Pattern, ...: Pattern): Pattern

function lookahead(pattern: Pattern): Pattern
function negative(pattern: Pattern): Pattern

function at_least(pattern: Pattern, count: integer): Pattern
function at_most(pattern: Pattern, count: integer): Pattern
function zero_or_more(pattern: Pattern): Pattern
function one_or_more(pattern: Pattern): Pattern
function optional(pattern: Pattern): Pattern
```

`sequence` and `choice` are left folds. Empty `sequence()` is success; empty
`choice()` is failure; a single operand is returned unchanged. `difference`
is a left fold: it matches `first` only when each exclusion fails at the same
starting position, and returns `first` unchanged with no tail. Repetition
counts must be nonnegative. `at_most(p, 0)` is empty success.

A direct, complete identifier parser is:

```text
local function identifier(): peg.Pattern
  local first = peg.choice(peg.ranges("az", "AZ"), peg.set("_"))
  local rest = peg.choice(first, peg.ranges("09"))
  return peg.sequence(
    peg.capture(peg.sequence(first, peg.zero_or_more(rest))),
    peg.negative(peg.any()))
end

-- identifier():match("Titan_42") returns "Titan_42"
-- identifier():match("Titan!") fails because of the explicit end predicate
```

### Direct captures

```text
function capture(pattern: Pattern): Pattern
function constant(...: value): Pattern
function match_time(
  pattern: Pattern,
  callback: function (string, integer, value, ...: value): (...: value)
): Pattern
function back_capture(key: value): Pattern
function argument(index: integer): Pattern
function position(): Pattern
function substitution(pattern: Pattern): Pattern
function table_capture(pattern: Pattern): Pattern
function fold_capture(
  pattern: Pattern,
  callback: function (value, ...: value): (value)
): Pattern
function group(pattern: Pattern, key: value): Pattern

function select_capture(pattern: Pattern, index: integer): Pattern
function template_capture(pattern: Pattern, template: string): Pattern
function query_capture(
  pattern: Pattern, lookup: {value: value}
): Pattern
function function_capture(
  pattern: Pattern,
  callback: function (value, ...: value): (...: value)
): Pattern
```

Omitting `group`'s fixed key argument nil-fills it and creates an anonymous
group. `back_capture` requires a non-nil key and raises at match time if no
matching group exists. `argument(n)` reads `Pattern:match` extra argument `n`
and raises if absent. `position()` is the current absolute one-based position.

This direct table capture mirrors the preferred Relabel capture envelope:

```text
local name = peg.group(
  peg.capture(peg.one_or_more(peg.ranges("az", "AZ"))), "name")
local number = peg.group(
  peg.capture(peg.one_or_more(peg.ranges("09"))), "number")
local pair = peg.table_capture(peg.sequence(
  name, peg.literal(":"), number, peg.negative(peg.any())))
```

### Relabel and utility functions

```text
function define(name: string, pattern: Pattern): Definition
function define_value(name: string, candidate: value): Definition

function compile(
  candidate: value,
  definitions: {Definition}?
): Pattern
function match(
  subject: string,
  candidate: value,
  init: integer?
): Match?
function Match:values(): (...: value)
function gsub(
  subject: string,
  candidate: value,
  replacement: function (string): (string)
): string
function update_locale()
function line_column(
  subject: string, position: integer
): (integer, integer)

function Pattern:match(
  subject: string,
  init: integer?,
  ...: value
): (value, ...: value)

function locale(): Locale
function set_max_stack(maximum: integer)
function version(): string
```

Optional-looking fixed parameters are normal Titan nil-accepting parameters.
Ordinary call adjustment nil-fills omission: `any()`, `group(p)`,
`p:match(subject)`, `compile(source)`, and `peg.match(subject, source)` do not
need overloads or source-level default arguments. Surplus arguments to a fixed
parameter list are evaluated and discarded; only declared variadic tails
collect them.

Authority for the exact public declarations:
`doc/language/standard-library-peg.md:29-120,121-170,170-289,291-400,402-478`
and `titan/peg/peg.titan:66-111,142-212,218-503,508-623`.

## Limits and boundary rules

The wrapper validates native limits before entering the engine:

| Surface | Limit |
| --- | --- |
| Conservatively constructed pattern | 32757 tree slots |
| Grammar | 1000 rules |
| Look-behind | capture-free, fixed length, at most 255 bytes |
| `argument` index | `1..32767` |
| `select_capture` index | `0..32767` |
| Private match stack | `1..21474836` |
| Titan public captures/results | at most 200 values |

`set_max_stack` affects only Titan's private engine in the current Lua state.
It is not a parser-construction-size switch and does not affect an external
LPegLabel installation.

Pattern matches preserve nil and trailing-nil capture slots. The public result
adapter caps the capture list at Titan's 200-value boundary. Extra match
arguments also follow Titan's variadic limit.

An ordinary Lua table is not a Titan Array. Lua code cannot pass a raw table as
`{peg.Rule}` or `{peg.Definition}`; it must obtain the canonical Array proxy
from Titan code. Query-capture lookup is different: its declared
`{value: value}` is a Map and preserves ordinary table/`__index` behavior.

Patterns are private-engine values. Loading an external `lpeglabel` before or
after `titan.peg` does not make its patterns compatible, and changing its stack
limit does not change Titan's.

Authority: `doc/language/standard-library-peg.md:358-400`,
`doc/implementation/lpeglabel-embedding.md:47-107,109-230`, and
`titan/peg/peg.titan:7-16,164-187,205-210`.

## Pitfall checklist for reviews

Reject or correct these recurring mistakes:

- **Regex intuition:** using `|`, relying on greedy repetition to backtrack, or
  assuming Relabel `.` excludes newline.
- **Accidental prefix acceptance:** using `Pattern:match` without `!.` while
  claiming to validate a complete subject.
- **Accidental anchoring/search confusion:** expecting `Pattern:match` to scan,
  or using `peg.match` when the caller needs the failure label and position.
- **Wrong zero position:** assuming PEG `init == 0` means byte 1; it means the
  position after the final byte.
- **Swallowed diagnostic:** putting a throw inside a predicate or using
  `%{fail}` as if it were a committed label.
- **Overbroad label site:** labeling one large pattern and expecting the throw
  position to be its farthest internal failure rather than the alternative's
  rewound start.
- **Nil-capture ambiguity:** treating a nil first capture as proof of failure.
  Use a non-nil envelope or `peg.Match?`.
- **Wrong collection kind:** passing a Map/raw Lua table where `{peg.Rule}` or
  `{peg.Definition}` requires a Titan Array; casting a table capture to an
  Array instead of a Map.
- **Definitions passed to search:** trying `peg.match(subject, source, defs)`.
  Compile with definitions first, then search the Pattern.
- **Per-call grammar compilation:** rebuilding stable source in a hot parse
  function instead of module initialization.
- **Hidden escape assumption:** writing `\n` in a Relabel literal and assuming
  the notation decodes it. Use `%nl`, a literal byte in a long string, or the
  correct outer Titan escape deliberately.
- **Callback side effects:** relying on capture callbacks to execute once, or
  trying to yield from one.
- **Callback widened to `value`:** the public direct APIs have precise callable
  types. Use those types; reserve dynamic `define_value` only for Relabel's
  intentionally dynamic suffix dispatch.
- **External engine mixing:** passing Lua LPegLabel patterns or configuring its
  max stack as though it were Titan's private engine.
- **Unicode claim:** calling a byte class a Unicode character class, or assuming
  `utf_range` changes the rest of the grammar into Unicode mode.
- **Ad hoc diagnostics:** discarding stable labels/positions, rescanning text
  with character rather than byte positions, or duplicating `line_column`.

## Validation

### Validate a scratch parser as Titan

Use a prepared ABI-matched installation, run from the source-tree root of the
scratch program, and pass dotted module names—not `.titan` paths:

```sh
titanc assignment
./assignment
```

For a library module, omit `main`, compile with `titanc my.parser`, and test its
public boundary from another Titan module or the generated Lua shim as
appropriate. Do not execute `.titan` files with `lua`.

### Prefer focused native Titan tests

A parser's observable behavior belongs in Titan tests. This minimal test module
exercises a successful capture and a precise failure. Save it as
`parser_test.titan`:

```titan
local test = import "test"
local peg = import "peg"

local PARSER: peg.Pattern? = nil

function test_parser(context: test.Context)
  context:run("success", function(child: test.Context)
    local captured: value = PARSER:match("name=Titan")
    local fields = captured as {value: value}
    test.assert(fields["name"] == "name")
    test.assert(fields["value"] == "Titan")
  end)

  context:run("missing equals", function(child: test.Context)
    local result, label, position = PARSER:match("name Titan")
    test.assert(result == nil)
    test.assert(label == "expected_equals")
    test.assert(position == 6)
  end)
end

do
  PARSER = peg.compile([[
    Pair <- {|
      {:name: {%a+} :}
      %s* ('=' / %{expected_equals})
      {:value: {%a+ / %{expected_value}} :}
      (!. / %{trailing_input})
    |}
  ]])
end
```

Run it from its source root:

```sh
titanc --test --tree . parser_test
./parser_test --verbose
```

For this repository's canonical PEG suite, use the native standard-library
test target without LuaCov:

```sh
make titan-stdlib-test TITAN_FILTER='^peg[.]tests[.]'
```

The authoritative cases are under `spec/stdlib/titan/peg/`; regular-expression
behavior is separately owned by
`spec/stdlib/titan/string/regex_test.titan`. Do not replace these Titan tests
with a Lua wrapper around the external `lpeglabel` module.

### Minimum behavior matrix

For a new parser, test at least the relevant rows:

1. the smallest valid input and a normal valid input;
2. exact end-of-input versus an otherwise-valid prefix with trailing bytes;
3. each public label and its exact one-based byte position;
4. ordinary failure versus a committed label inside ordered choice;
5. search before/at/after the requested `init`, including an empty match if
   allowed;
6. capture count, named/anonymous table keys, and nil/trailing-nil values;
7. recursive grammar and recovery synchronization if recovery is part of the
   public contract;
8. CR, LF, CRLF, NUL, and non-ASCII bytes when the format is binary;
9. syntax-error label/caret when grammar source itself is user input;
10. callback error propagation and path timing when callbacks are necessary.

## Evaluation cases for a fresh agent

Use these prompts to check whether the skill produces Titan-specific reasoning
rather than Lua/regex guesses.

### Eval 1: anchored validation

**Prompt:** “Review `peg.compile("[A-Za-z_][A-Za-z0-9_]*"):match(name)` used to
validate a complete identifier.”

**Pass criteria:** identifies prefix acceptance; adds `!.` (or the named
negative-any combinator); keeps `Pattern:match` because validation is anchored;
notes byte semantics. **Fail:** switches to regex from habit, claims
`Pattern:match` already consumes all input, or uses module search.

### Eval 2: leftmost search with captures

**Prompt:** “Find the first identifier in `"123 Titan42!"`, return its inclusive
span and captured spelling.”

**Pass criteria:** uses `peg.match`, checks `Match?`, reads `first/last`, calls
`values`; expects `5..11`. **Fail:** calls anchored `Pattern:match`, invents
`peg.find`, or expects `Match:values` to contain a whole match when the pattern
has no capture.

### Eval 3: possessive repetition

**Prompt:** “Why does Relabel `.* 'END'` fail on `abcEND`, and how should it be
written?”

**Pass criteria:** explains possessive PEG repetition and writes a guarded form
such as `(!'END' .)* 'END'`. **Fail:** says the engine should backtrack like a
regex or merely makes the repetition lazy (there is no lazy suffix here).

### Eval 4: labeled structured error

**Prompt:** “Design a complete `name=value` parser returning a record or a
structured error with label and byte position.”

**Pass criteria:** prefers a compiled-once Relabel grammar, uses a non-nil
capture envelope, puts labels at expected-name/equals/value/trailing sites,
uses anchored `Pattern:match`, and converts the failure triple. **Fail:** scans
with `peg.match`, catches subject mismatch as an exception, recompiles per call,
or tests only `result == nil` while allowing nil first captures.

### Eval 5: recovery

**Prompt:** “Explain what `S <- ('a'^recover) 'b'` with the next rule
`recover <- 'x'` does on `"xb"`, and what changes if the label is `fail`.”

**Pass criteria:** recovery begins at the throw position, consumes `x`, resumes
with `b`, returns after byte 2; `fail` is ordinary failure and cannot enter a
recovery rule. **Fail:** treats a recovery rule as an exception handler after
the whole parse or says every label tries the next ordered choice.

### Eval 6: dynamic definitions and folds

**Prompt:** “Parse a space-separated integer sum with Relabel and a Titan fold
callback.”

**Pass criteria:** uses a `{peg.Definition}` Array, `define_value` for numeric
conversion and fold callback, `{%d+} -> converter`, and `~> fold`; gives precise
callback types. **Fail:** passes a Map of definitions, expects `peg.match` to
accept definitions directly, or hides every callback as unqualified `value`.

### Eval 7: direct combinators

**Prompt:** “The allowed identifier punctuation is computed at run time. Build
a complete identifier pattern without generating Relabel source.”

**Pass criteria:** uses `set`/`ranges`, named `sequence`/`choice`/repetition,
`capture`, and an explicit end predicate. **Fail:** uses LPeg operators, emits
and reparses source unnecessarily, or passes a Lua LPeg pattern.

### Eval 8: PEG versus regex

**Prompt:** “A user needs conventional alternation, continuation-aware greedy
quantifiers, group spans, and iteration over all matches.”

**Pass criteria:** routes to `titan.string.Regex`, explains why this is not the
PEG surface, and does not force Relabel. **Fail:** assumes every pattern task
belongs in `titan.peg` or claims PEG repetition backtracks.

### Eval 9: capture timing

**Prompt:** “Can a `function_capture` callback increment a counter exactly once
for every branch the matcher explores?”

**Pass criteria:** says no; it is delayed, abandoned alternatives do not run it,
and capture evaluation may be zero/one/multiple times. Contrasts immediate
runtime/match-time callbacks and says callbacks cannot yield. **Fail:** promises
exactly-once execution.

### Eval 10: syntax diagnostics

**Prompt:** “A service accepts user-provided Relabel grammar source. Distinguish
bad grammar syntax from a valid grammar that does not match a subject.”

**Pass criteria:** catches the ordinary string raised by `peg.compile` for
syntax, preserves its stable label/caret, and separately handles the anchored
failure triple or `Match?`; uses `line_column` for subject byte positions.
**Fail:** treats compile errors as `nil, label, position`, or expects subject
mismatch to raise.

## Authoritative source map

This cartridge was derived from the repository at commit
`1fdfbe73f36e2936250c05d0d2b4a0f4e40bc91f`.

* **Normative public contract:**
  `doc/language/standard-library-peg.md` (entire chapter; especially
  lines 29-120 public types/constructors, 121-289 composition/captures,
  291-400 matching/limits, and 402-530 Relabel/search/diagnostics).
* **Embedding and callback rationale:**
  `doc/implementation/lpeglabel-embedding.md:47-107,109-230,231-383`.
* **Exact public declarations and implementation boundary:**
  `titan/peg/peg.titan:66-111,115-212,218-503,508-623`.
* **Relabel lexical grammar and suffix semantics:**
  `titan/peg/relabel.titan:232-392,395-513,516-724` and
  `titan/peg/relabel_parser.titan:10-76`.
* **Core behavior tests:**
  `spec/stdlib/titan/peg/tests/core_test.titan:58-161,215-381,384-560`.
* **Relabel, captures, search, labels, recovery, and diagnostic tests:**
  `spec/stdlib/titan/peg/tests/relabel_test.titan:59-186,189-389,391-473`.
* **Shipped labeled-parser example:** `titan/url.titan:25-163,198-405`.
* **Shipped Relabel dogfood with dynamic definitions and match-time actions:**
  `titan/string/regex_parser.titan:757-931`.
* **Shipped direct-combinator dogfood:**
  `titan/string/format.titan:504-600` and
  `titan/string/regex_compile.titan:188-318`.
* **Regex contrast and behavior tests:**
  `doc/language/standard-library-string.md:278-497` and
  `spec/stdlib/titan/string/regex_test.titan:234-325,471-529`.
* **Runnable introductory contrast:** `doc/quick-tour.md:322-380`.
* **Skill-tree mandate:** GitHub issue #82, especially maintainer comment
  `https://github.com/mascarenhas/titan/issues/82#issuecomment-5309065757`,
  which asks this skill to privilege Relabel while also teaching combinators
  and good parser error handling.
