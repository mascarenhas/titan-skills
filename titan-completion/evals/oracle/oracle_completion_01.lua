-- Independent Stage-B oracle for completion-01-caret-transform-and-member-visibility.
local completion = require("titan-compiler.completion")
local driver = require("titan-compiler.driver")
local parser = require("titan-compiler.parser")
local checker = require("titan-compiler.checker")
local types = require("titan-compiler.types")

local function fail(msg)
  io.stderr:write("FAIL: " .. tostring(msg) .. "\n")
  os.exit(1)
end

local function check(cond, msg)
  if not cond then fail(msg) end
end

local function read_file(path)
  local f = assert(io.open(path, "rb"))
  local data = f:read("*a")
  f:close()
  return data
end

local function split_caret(source_with_at)
  local pos = source_with_at:find("@", 1, true)
  check(pos ~= nil, "test fixture missing '@' caret marker")
  local caret = pos - 1
  local src = source_with_at:sub(1, caret) .. source_with_at:sub(caret + 2)
  return src, caret
end

local cq = dofile("./complete_query.lua")
check(type(cq) == "table", "complete_query.lua must return a module table")
check(type(cq.prepare_caret) == "function", "missing prepare_caret")
check(type(cq.map_to_original_byte) == "function", "missing map_to_original_byte")
check(type(cq.extract_dependencies) == "function", "missing extract_dependencies")
check(type(cq.query_completion) == "function", "missing query_completion")

-- 1. Compiler version markers intact.
check(driver.LANGUAGE_SERVER_API_VERSION == 1, "expected LANGUAGE_SERVER_API_VERSION == 1")
check(completion.VERSION == 1 and completion.TRANSFORM_VERSION == 1, "expected completion VERSION/TRANSFORM_VERSION == 1")

-- 2. Caret transforms: separators, mid-token replacement, original_byte, exclusions, import, multiword C primitives.
do
  local src, caret = split_caret("function f(r:value) r.pa@rtial end")
  local p = cq.prepare_caret("./t.titan", src, caret)
  check(p ~= nil, "prepare_caret returned nil on r.pa@rtial")
  check(p.kind == "dot", "expected kind='dot', got " .. tostring(p.kind))
  check(p.prefix == "pa", "expected prefix='pa', got " .. tostring(p.prefix))
  check(p.replacement_end - p.replacement_start == 7, "expected replacement span len 7 for 'partial'")
  check(p.text:find("r.__titan_completion_hole end", 1, true) ~= nil, "dot separator or replacement corrupted")
  check(cq.map_to_original_byte(p.request, p.request.analysis_end_byte) == p.replacement_end,
    "map_to_original_byte did not reverse analysis_end_byte to replacement_end")
  check(cq.map_to_original_byte(p.request, p.request.analysis_start_byte + 2) == p.replacement_start,
    "positions inside synthetic hole must map to original leaf start")

  local src_c, caret_c = split_caret("function f(r:value) r:@ end")
  local pc = cq.prepare_caret("./t.titan", src_c, caret_c)
  check(pc ~= nil and pc.kind == "colon", "expected colon kind on r:@")
  check(pc.text:find("r:__titan_completion_hole end", 1, true) ~= nil, "colon separator corrupted")
  check(pc.text:find("__titan_completion_hole()", 1, true) == nil, "must not synthesize () after colon hole")

  -- Excluded positions: comments, unrelated strings, UTF-8 mid-sequence byte.
  for _, bad_case in ipairs({
    "function f() local s = \"a@b\" end",
    "-- comment @here\n",
    "--[[ block @ comment ]]",
  }) do
    local s, c = split_caret(bad_case)
    local res, reason = cq.prepare_caret("./t.titan", s, c)
    check(res == nil and type(reason) == "string", "expected nil, reason for excluded case: " .. bad_case)
  end
  local utf8_src = "local s = 1 -- \xC3\xA9"
  local utf8_res, utf8_reason = cq.prepare_caret("./t.titan", utf8_src, #utf8_src - 1)
  check(utf8_res == nil and type(utf8_reason) == "string", "expected nil, reason for UTF-8 split byte")

  -- Import string leaves source unchanged with kind='import'.
  local imp_src, imp_caret = split_caret('local m = import "foo.ba@r"')
  local pi = cq.prepare_caret("./t.titan", imp_src, imp_caret)
  check(pi ~= nil and pi.kind == "import", "expected kind='import'")
  check(pi.prefix == "foo.ba" and pi.text == imp_src, "import transform must keep source text unchanged")

  local qi = cq.query_completion({ modname = "t", filename = "./t.titan", source = imp_src, caret = imp_caret })
  check(qi ~= nil and qi.kind == "import" and qi.prefix == "foo.ba", "query_completion must handle kind='import'")

  -- Multiword C primitives after foreign/owned and inside foreign function after : / as (even with keyword-as-arg).
  local f1_src, f1_caret = split_caret("function f(x: foreign const *unsigned lo@ng long) end")
  local pf1 = cq.prepare_caret("./t.titan", f1_src, f1_caret)
  check(pf1 ~= nil and pf1.kind == "foreign" and pf1.prefix == "unsigned lo", "multiword C primitive failed")
  check(pf1.text:find("foreign const *__titan_completion_hole)", 1, true) ~= nil, "qualifiers not preserved")

  local f2_src, f2_caret = split_caret(
    "foreign function f(p: *void) ffi.slice { start = 0, end = 5 } local x = p as const *unsigned lo@ng long end"
  )
  local pf2 = cq.prepare_caret("./t.titan", f2_src, f2_caret)
  check(pf2 ~= nil and pf2.kind == "foreign" and pf2.prefix == "unsigned lo",
    "foreign function unprefixed C type with keyword-named arg failed")
  check(pf2.text:find("as const *__titan_completion_hole end", 1, true) ~= nil,
    "foreign function multiword C leaf replacement failed")
end

-- 3. Parser-backed dependencies discovery (canonical shorthand + .titan source_required).
do
  local deps = assert(cq.extract_dependencies({
    { filename = "a.titan", contents = 'local m = import "math"' },
    { filename = "b.titan", contents = 'local l = import "lib_mod.titan"' },
  }))
  check(#deps == 2, "expected 2 dependencies, got " .. #deps)
  check(deps[1].module_name == "lib_mod" and deps[1].source_required == true,
    "expected lib_mod with source_required=true")
  check(deps[2].module_name == "titan.math" and deps[2].source_required == false,
    "expected canonical titan.math with source_required=false")
end

-- Helper to assert query_completion restores caller global state and returns scalar rows.
local function run_q(source_with_at, modules, include_dirs)
  local sentinel_imp = { _sentinel = "imp" }
  local sentinel_reg = { _sentinel = "reg" }
  driver.imported = sentinel_imp
  types.registry = sentinel_reg

  local src, caret = split_caret(source_with_at)
  local q, err = cq.query_completion({
    modname = "test_mod",
    filename = "./test_mod.titan",
    source = src,
    caret = caret,
    modules = modules,
    include_dirs = include_dirs,
  })
  check(driver.imported == sentinel_imp, "query_completion must restore driver.imported")
  check(types.registry == sentinel_reg, "query_completion must restore types.registry")
  check(q ~= nil, "query_completion failed: " .. tostring(err))
  check(type(q.candidates) == "table" and type(q.by_name) == "table", "missing candidates/by_name")
  for _, row in ipairs(q.candidates) do
    check(row.name ~= q.request.name, "synthetic dummy hole leaked into candidates")
    for k, v in pairs(row) do
      if k == "documentation" then
        check(type(v) == "table", "documentation must be table")
      else
        check(type(v) ~= "table", "candidate field " .. k .. " must be scalar, got table")
      end
    end
  end
  return q
end

-- 4. Hole identified by filename + transformed span, NOT spelling: real __titan_completion_hole visible!
do
  local q = run_q("function f(...: integer) local __titan_completion_hole = 1 local x = @ end")
  check(q.by_name.__titan_completion_hole ~= nil,
    "real local named __titan_completion_hole must remain visible (hole identified by span, not spelling)")
  check(q.by_name["..."] ~= nil, "vararg '...' must be visible inside variadic function")
end

-- 5. Live module initializer frontier + placement-independent function.
do
  local q = run_q("local earlier = 1 local current = @ local later = 2 function after() end")
  check(q.by_name.earlier ~= nil, "earlier local must be visible before frontier")
  check(q.by_name.after ~= nil, "placement-independent function after() must be visible")
  check(q.by_name.current == nil, "current local must NOT be visible in its own initializer")
  check(q.by_name.later == nil, "later local must NOT be visible before its declaration")
end

-- 6. Dot vs colon vs static splits + generic specialization + interface views.
do
  local prefix = [[
record Box<|T|>
  item: T
end
function Box:unwrap(): T return self.item end
function Box:map<|U|>(fn: function(T): U): U return fn(self.item) end
function Box.make(v: T): Box<|T|> return Box.new(v) end
interface Reader
  id: string
  function read(): integer
end
]]
  local q_dot = run_q(prefix .. "function f(b: Box<|integer|>) local x = b.@ end")
  check(q_dot.kind == "dot", "expected dot kind")
  check(q_dot.by_name.item ~= nil and q_dot.by_name.item.detail == "integer",
    "generic Box<|integer|>.item must specialize to integer")
  check(q_dot.by_name.unwrap == nil and q_dot.by_name.new == nil, "dot on instance must hide methods/statics")

  local q_col = run_q(prefix .. "function f(b: Box<|integer|>) b:@ end")
  check(q_col.kind == "colon", "expected colon kind")
  check(q_col.by_name.unwrap ~= nil and q_col.by_name.unwrap.detail == "function (): integer",
    "bound method unwrap must specialize to integer")
  check(q_col.by_name.map ~= nil and q_col.by_name.map.detail:find("integer", 1, true) ~= nil,
    "generic method map must preserve specialized receiver type")
  check(q_col.by_name.item == nil and q_col.by_name.make == nil, "colon on instance must hide fields/statics")

  local q_stat = run_q(prefix .. "function f() local x = Box<|integer|>.@ end")
  check(q_stat.by_name.new ~= nil and q_stat.by_name.new.detail:find("integer", 1, true) ~= nil,
    "static Box<|integer|>.new must specialize to integer")
  check(q_stat.by_name.make ~= nil and q_stat.by_name.item == nil, "static namespace must show make, hide item")

  local q_iface = run_q(prefix .. "function f<|T: Reader|>(r: T) r:@ end")
  check(q_iface.by_name.read ~= nil and q_iface.by_name.id == nil, "constrained interface colon must show read only")
end

-- 7. .titan source-private visibility against starter lib_mod.titan.
do
  local lib_src = read_file("./lib_mod.titan")
  local q_pub = run_q('local m = import "lib_mod" function f() m.@ end', { lib_mod = lib_src })
  check(q_pub.by_name.Public ~= nil and q_pub.by_name.exported_fn ~= nil,
    "compiled import must expose Public and exported_fn")
  check(q_pub.by_name.secret == nil and q_pub.by_name.Private == nil,
    "compiled import must hide local secret and Private")

  local q_src = run_q('local m = import "lib_mod.titan" function f() m.@ end', { lib_mod = lib_src })
  check(q_src.by_name.secret ~= nil and q_src.by_name.Private ~= nil,
    ".titan source import must expose source-private secret and Private")
end

-- 8. ffi shadowing never hides C types, C aggregate/macro fields, and target-int C enum eligibility.
do
  local c_prefix = 'foreign import "c_defs.h"\n'

  -- Shadowing `ffi` in a function parameter resolves `ffi.` to the local record,
  -- while `foreign @` STILL exposes C types from c_defs.h!
  local q_shad_val = run_q(
    c_prefix .. "record LocalRec tag: integer end function f(ffi: LocalRec) local x = ffi.@ end",
    nil, { "." }
  )
  check(q_shad_val.by_name.tag ~= nil, "shadowed ffi. must resolve to LocalRec.tag")
  check(q_shad_val.by_name.callable == nil, "shadowed ffi. must not show C namespace members")

  local q_shad_type = run_q(
    c_prefix .. "record LocalRec tag: integer end function f(ffi: LocalRec, p: foreign *@) end",
    nil, { "." }
  )
  check(q_shad_type.kind == "foreign", "expected foreign kind under ffi shadowing")
  check(q_shad_type.by_name.Outer ~= nil and q_shad_type.by_name.Wide ~= nil and q_shad_type.by_name.int ~= nil,
    "ffi local shadowing must NEVER hide C types in foreign type position")

  -- C aggregate pointer + macro field (#define PROJECTED inner.leaf).
  local q_agg = run_q(c_prefix .. "local function f(x: foreign *Outer) x.@ end", nil, { "." })
  check(q_agg.by_name.inner ~= nil and q_agg.by_name.plain ~= nil and q_agg.by_name.bits ~= nil,
    "expected Outer C struct fields")
  check(q_agg.by_name.PROJECTED ~= nil, "expected macro field PROJECTED on foreign *Outer")

  -- C enum target-int proof: provable target-int enumerators present; wide ULL omitted -> quality='partial'.
  local q_ffi = run_q(c_prefix .. "local function f() ffi.@ end", nil, { "." })
  check(q_ffi.by_name.callable ~= nil and q_ffi.by_name.global_value ~= nil and q_ffi.by_name.NUMBER_VALUE ~= nil,
    "expected C functions, globals, and numeric object macros")
  check(q_ffi.by_name.FIRST_VALUE ~= nil and q_ffi.by_name.IMPLICIT_VALUE ~= nil and q_ffi.by_name.REFERENCED_VALUE ~= nil,
    "expected target-int provable enum constants")
  check(q_ffi.by_name.MINIMUM ~= nil and q_ffi.by_name.AFTER_MINIMUM ~= nil and q_ffi.by_name.REFERENCE_MINIMUM ~= nil,
    "expected INT_MIN boundary target-int enum constants")
  check(q_ffi.by_name.WIDE_VALUE == nil and q_ffi.by_name.WIDE_ENUM_VALUE == nil,
    "wide ULL enum constants must be omitted, never trusted from host Lua")
  check(q_ffi.quality == "partial", "omitting unproven wide enum entries must yield quality='partial'")
end

-- 9. Ordinary checking remains unweakened (member reference as statement is still an error).
do
  driver.imported = {}; types.registry = {}
  local ast = assert(parser.parse("./ordinary.titan", "record R field: integer end function f(r: R) r.field end"))
  local _, errs = checker.check("ordinary", ast, "", "./ordinary.titan")
  check(#errs > 0 and table.concat(errs, "\n"):find("only a function call may be used as a statement", 1, true) ~= nil,
    "ordinary checking must remain unchanged")
end

print("oracle_completion_01 PASS")
