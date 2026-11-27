---
name: titan-pegs
description: Use when writing or debugging Titan byte parsers, grammars, DSLs, or labeled syntax errors with titan.peg. Covers Relabel source notation, captures/folds, anchored vs search matching, labeled recovery, and dynamic combinators; use titan-stdlib for string.Regex, titan-json for JSON, titan-protobuf for Proto3.
---

# Titan PEGs (`titan.peg`)

Typed byte-oriented parsing-expression grammars backed by a private embedded LPegLabel (`1.6.1`) engine (native & browser complete). Import `local peg = import "peg"` (Lua: `require "titan.peg"`).
Pair with `skill://titan-programmer` for core syntax/types/`T?`/`catch`. Peers: `skill://titan-stdlib` (`string.Regex`), `skill://titan-json`, `skill://titan-protobuf`, `skill://titan-tester`.

## Non-negotiable invariants

1. **Relabel-first, compile once:** Write static grammars with `peg.compile([[ ... ]])` (first rule = start rule). When passing module-local Titan callbacks via `peg.define_value`, compile in the module's final `do ... end` initializer (module-var initializers cannot capture own functions/lambdas). Reserve named combinators (`sequence`, `choice`, `grammar`) for dynamically built patterns or non-identifier binary rule/label names.
2. **Suffix precedence (`->`, `=>`, `~>`, `^label`, `*`, `+`, `?`):** Every capture, label, and repetition suffix binds to one primary **tighter than sequence `p q` and choice `p / q`**. `A B -> fn` parses as `A (B -> fn)` and `A B^err` parses as `A (B^err)`—always parenthesize `(A B) -> fn`, `(A B) ~> fold`, and `(A B)^err`. Write **no space** between `^` and its operand (`'a'^3`, `'a'^+3`, `'a'^-3`, `'a'^err`).
3. **Byte-oriented, possessive, no nullable loops:** Patterns match raw bytes (`.` matches LF too; only `peg.utf_range` decodes UTF-8), and quoted literals have **no backslash escapes** (switch quote kinds or use `%nl`). Choice `/` is ordered; `*`/`+` are **possessive** and never backtrack—write `(!'END' .)* 'END'`, never `.* 'END'`. Nullable bodies under `*`, `+`, or `^+n` (`at_least`) and left-recursive rules fail compilation (`loop body may accept empty string`).
4. **Anchored `Pattern:match` vs. searching `peg.match`:** `Pattern:match(subject, init?, ...)` attempts one anchored match at `init` (no forward scan; add `!.` or `peg.negative(peg.any())` for whole-subject validation). `peg.match(subject, cand, init?)` searches leftmost and returns `Match?` (`first`/`last` inclusive, empty `last == first - 1`; `Match:values()` yields captures or 0 values if capture-free). **No `peg.find`.** `init == 0` starts **after** the last byte (`#subject + 1`), unlike `string.Regex` where `0` clamps to `1`.
5. **Labels commit; `"fail"` is reserved; predicates suppress throws:** `%{label}`, `p^label` (`p / %{label}`), and `peg.throw(label)` escape ordered choice, repetition, and `peg.match` search (returning `nil`) unless caught by a same-named recovery rule in the grammar. Place labels at the exact expectation site (`p / %{lbl}` rewinds failed `p` before throwing). `"fail"` equals ordinary failure and never enters recovery. Throws inside `&p`/`!p` become ordinary predicate failures.
6. **Non-nil capture envelope for `Pattern:match`:** Capture-free `Pattern:match` returns the post-match byte position; failure returns `nil, "fail", abs_farthest_pos` or `nil, label, abs_throw_pos` (always absolute even when `init ~= 1`). Because a valid match can capture `nil`, wrap results in a non-nil envelope like `{| ... |}` (a `{value: value}` Map, **not** an Array) or use `peg.match` (`Match?`) before testing `first_res == nil`.
7. **Callback timing & strict containers:** `=>`/`match_time` and `runtime` run **immediately** (including on abandoned branches and inside `&p`/`!p`); `->`/`function_capture` and `~>`/`fold_capture` are **delayed** (skipped on abandoned branches, but never guaranteed exactly-once). All callbacks are **non-yieldable**. Pass dense Titan Arrays `{Definition}`/`{Rule}` (never Lua tables/Maps); `query_capture` uses a `{value: value}` Map (honoring `__index`).
8. **Private engine & limits:** `titan.peg` is isolated from external Lua `lpeglabel` (distinct metatable & stack). Caps: **32,757** tree slots, **1,000** grammar rules, **255 B** fixed capture-free `behind`, **200** variadic match args/public capture results, `set_max_stack(1..21474836)` (default 400).

## Choosing a surface (and `peg` vs. `string.Regex`)

| Need | Use | Key delta / contract |
| --- | --- | --- |
| Declarative grammar, DSL, labeled errors | `peg.compile(src, defs?)` | Relabel syntax; def-free strings share weak cache cleared by `update_locale()`. |
| Anchored parse + failure `(label, pos)` | `pat:match(s, init?, ...)` | Single attempt at normalized `init`; extra args read via `peg.argument(n)`. |
| Leftmost search + span/captures | `peg.match(s, cand, init?)` | Returns `Match?`; uncaught label stops search -> `nil`. No `defs` arg (compile first). |
| Global whole-match replacement | `peg.gsub(s, cand, fn)` | `fn: function(string): (string)` gets whole match only; literal insert; returns `string` only. |
| Runtime-assembled or binary-named rules | Named combinators | `sequence`, `choice`, `grammar`, `rule`, `capture`, `behind`, `utf_range`. |
| Backtracking regex (`|`, `\d`, groups) | `string.compile_regex` | In `titan-stdlib`: backtracking `*`/`+`, `.` excludes LF, escapes work, `init=0` -> `1`. |

**`init` normalization (`Pattern:match` and `peg.match`):** `nil` -> `1`; `1..#s+1` -> `init`; `> #s+1` -> `#s+1`; `0` -> `#s+1`; negative in range -> `#s + init + 1` (`-1` = last byte); negative overshoot -> `1`.

## Relabel syntax, captures, and callback protocols

- **Core notation:** `'lit'`/`"lit"` (raw bytes, no `\`), `.` (any byte incl. LF), `[a-z]`/`[^0-9]` (byte class, may contain `%name`), `(p)`, `p q`, `p / q`, `&p`/`!p` (discard inner captures; eager `=>` still runs), `p?`/`p*`/`p+`, `p^n`/`p^+n`/`p^-n`, `p^label` (`p / %{label}`), `%{label}` (decimal labels stay strings: `%{01}` -> `"01"`), `name <- p` (rule), `name`/`<name>` (nonterminal), `-- comment`.
- **Predefined C-locale classes:** `%alnum`, `%alpha`, `%cntrl`, `%digit`, `%graph`, `%lower`, `%print`, `%punct`, `%space`, `%upper`, `%xdigit`, short forms `%a %c %d %g %l %p %s %u %w %x` (uppercase = complement), `%nl` (LF). Call `peg.update_locale()` after `os.setlocale` to refresh classes and clear the def-free cache.
- **Captures:** `{}` (1-based pos), `{ p }` (substring), `{: p :}` (anon group), `{:k: p :}` (named group; hidden from direct results, stored at `k` in `{| p |}`), `=name` (matching backreference consuming equal bytes—distinct from `peg.back_capture(key)` which yields values without consuming), `{| p |}` (table capture -> `{value: value}` Map), `{~ p ~}` (substitution), `p -> 0` (discard), `p -> n` (`1..32767`), `p -> 'tpl'` (`%0` whole, `%1..%9` nested), `p -> {}` (table), `p -> name`, `p => name`, `p ~> name`.
- **External definitions:** `peg.define(name, pat)` binds `%name`; `peg.define_value(name, val)` binds `->`/`=>`/`~>` (rejects `nil`/`false`). For `-> name`, classification order is: `string` template -> `is integer` selector (includes integral floats) -> Map query (before `__call`) -> delayed callable fallback (non-callable raises only if invoked). Passing an existing `Pattern` to `peg.compile(pat, defs)` ignores `defs`.
- **Empty-child capture defaults:** With no nested captures: anon `group`/`query`/`function`/`select 1` -> whole substring; `select 0` -> none; template `%0` -> whole (`%1` raises); `table_capture` -> empty Map; `fold_capture` -> raises (no initial accumulator).
- **Callback protocols:**
  - `runtime(cb)` receives `(subject, pos, "")`; `match_time(p, cb)` / `=>` receives `(subject, pos_after_p, captures_or_whole...)`. First return: `nil`/`false`/none = fail; `true` = succeed at current pos; `int` in `cur..#s+1` = succeed at new pos; remaining returns = captures.
  - `function_capture(p, cb)` / `->` returns all captures; `fold_capture(p, cb)` / `~>` uses 1st nested capture as accumulator and calls `cb(acc, next...) -> new_acc`. Seed mutable folds with a per-match factory (e.g. `{}` position capture -> factory), never a shared constant object.

```titan
local math = import "math"
local peg = import "peg"

record Assignment
  const name: string
  const total: integer
end

record ParseError
  const label: string
  const line: integer
  const column: integer
end

local function to_int(raw: value): integer
  local n? = math.tointeger(raw)
  return n or 0
end

local function add_nums(acc: value, ...: value): value
  local sum = acc as integer
  for i = 1, #... do
    sum = sum + (...[i] as integer)
  end
  return sum
end

local ASSIGN_PAT: peg.Pattern? = nil
local RECOVER_LIST: peg.Pattern? = nil

function parse_assignment(input: string): (Assignment?, ParseError?)
  local captured, label, pos = ASSIGN_PAT:match(input)
  if captured == nil then
    local line, col = peg.line_column(input, pos as integer)
    return nil, ParseError(label as string, line, col)
  end
  local fields = captured as {value: value}
  return Assignment(fields["name"] as string, fields["total"] as integer), nil
end

function main(args: {string}): integer
  local ok?, err? = parse_assignment("score = 10 + 25 + 7")
  if ok == nil or err ~= nil or ok.name ~= "score" or ok.total ~= 42 then
    return 1
  end
  local bad?, perr? = parse_assignment("score 10")
  if bad ~= nil or perr == nil or perr.label ~= "expected_eq" or perr.column ~= 7 then
    return 2
  end
  -- Recovery rule skips bad items inside a semicolon list
  local list_val = RECOVER_LIST:match("ok;123;good")
  local items = list_val as {integer: string}
  if items[1] ~= "ok" or items[2] ~= "good" or #items ~= 2 then return 3 end
  return 0
end

do
  ASSIGN_PAT = peg.compile([[
    Assign <- {|
      %s* {:name: {Ident / %{expected_name}} :}
      %s* ('=' / %{expected_eq}) %s*
      {:total: ((Num (%s* '+' %s* Num)*) ~> add / %{expected_expr}) :}
      %s* (!. / %{trailing_input})
    |}
    Ident <- [A-Za-z_] [A-Za-z0-9_]*
    Num   <- {%d+} -> to_int
  ]], {
    peg.define_value("to_int", to_int),
    peg.define_value("add", add_nums),
  })
  RECOVER_LIST = peg.compile([[
    List     <- {| Item (';' Item)* ';'? !. |}
    Item     <- %s* ({[A-Za-z]+} / %{bad_item}) %s*
    bad_item <- [^;]*
  ]])
end
```

## Dynamic combinators, labeled recovery, and diagnostics

- **Combinator constructors:** `sequence()` -> `succeed()`; `choice()` -> `fail()`; `difference(a, b, c)` = `(a - b) - c`; `any(count?)` defaults to `1` (`count < 0` succeeds without consuming if fewer than `-count` bytes remain); `at_most(p, 0)` is empty success; `ranges("az", "09")` fails with 0 args; `utf_range(first, last)` (`0..0x10ffff`) matches UTF-8 encodings including surrogates.
- **Grammar, capture & locale combinators:** `behind(p)` requires capture-free fixed-length `<= 255 B`; `variable(name)` must be closed in `grammar(start, rules)` (unique names, `start` present, binary strings ok); `capture(p)` yields whole substring **followed by** nested captures; `argument(n)` (`1..32767`) reads `Pattern:match` extra arg `n` (raises if absent); `locale()` snapshots C classes once (unaffected by later `os.setlocale`).
- **Recovery & diagnostics:** A grammar rule named identically to a thrown label catches that throw at the throw position and resumes after the throwing expression if recovery succeeds. Invalid Relabel source raises `PEG syntax error [label] at Lx:Cy (byte p): ...` with source line + caret. `peg.line_column(subject, pos)` maps `1..#subject + 1` treating CR, LF, and CRLF each as one newline.

```titan
local peg = import "peg"

local function balanced_parens(): peg.Pattern
  local text = peg.one_or_more(peg.difference(peg.any(), peg.set("()")))
  local rules: {peg.Rule} = {
    peg.rule("Start", peg.sequence(
      peg.capture(peg.variable("Balanced")), peg.negative(peg.any()))),
    peg.rule("Balanced", peg.sequence(
      peg.literal("("),
      peg.zero_or_more(peg.choice(text, peg.variable("Balanced"))),
      peg.literal(")"))),
  }
  return peg.grammar("Start", rules)
end

function main(args: {string}): integer
  local pat = balanced_parens()
  local matched = pat:match("(a(b)c)")
  if matched ~= "(a(b)c)" then return 1 end
  -- Leftmost search + extra match argument via peg.argument(1)
  local hit? = peg.match("id=Titan42!", "{[A-Za-z_][A-Za-z0-9_]*}", 4)
  if hit == nil or hit.first ~= 4 or hit.last ~= 10 then return 2 end
  local word = hit:values()
  if word ~= "Titan42" then return 3 end
  local tagged = peg.compile("{%a+} %tag", { peg.define("tag", peg.argument(1)) })
  local first, second = tagged:match("hi", 1, "ok")
  if first ~= "hi" or second ~= "ok" then return 4 end
  return 0
end
```

## Pre-delivery verification checklist

- [ ] Static grammars use `peg.compile([[ ... ]])` once (in `do ... end` when passing module-local callbacks via `define_value`).
- [ ] Every multi-part `->`, `=>`, `~>`, or `^label` target is parenthesized; no whitespace appears after `^`; no nullable body sits under `*`/`+`/`^+n`.
- [ ] Whole-input parsers anchor with `Pattern:match` + explicit `!.` (or `(!. / %{trailing_input})`) and return a non-nil capture envelope (e.g. `{| ... |}`).
- [ ] Leftmost search uses `peg.match` (`Match?` + `Match:values()`); `init == 0` is never used to mean byte `1`.
- [ ] Table captures cast to Maps (`{value: value}` or `{integer: T}`, never Arrays); `{Definition}`/`{Rule}` arguments are Titan Arrays; callbacks never yield.
