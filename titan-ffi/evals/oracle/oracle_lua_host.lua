local titan = require "titan"
local host = require "plugin_host"
local rules = dofile("plugin_rules.lua")

assert(type(host) == "userdata", "Titan module must be userdata")
assert(getmetatable(host) == "Titan module plugin_host", "unexpected module metatable: " .. tostring(getmetatable(host)))

local acct = host.open_account("acct-lua", 20, 7777)
local limits = host.make_const_limits(host.make_limits_array(10, 20, 30))
local verdict = host.Verdict.approved("tier1")

local rep = rules.probe_account(acct, limits, verdict, host)
assert(rep.id == "acct-lua", "public const id mismatch")
assert(rep.balance_after_set == 50, "dynamic float->integer field write failed")
assert(rep.const_write_blocked, "const field write should be rejected")
assert(rep.frac_write_blocked, "non-integral float write to integer field should be rejected")
assert(rep.local_field_hidden, "local field secret_pin must not be accessible from Lua")
assert(rep.flag_zero == "on", "truthy 0 should map to true")
assert(rep.flag_nil == "off", "nil should map to false")
assert(rep.flag_false == "off", "false should map to false")
assert(rep.num_to_str_blocked, "number passed to string parameter must fail")
assert(rep.limits_len == 3 and rep.limits_sum == 60, "const array proxy read mismatch")
assert(rep.const_array_enforced, "const array proxy must block writes and rawget")
assert(rep.verdict_type == "userdata", "union must be opaque userdata in Lua")
assert(rep.verdict_text == "approved:tier1", "verdict_label mismatch")

local bal, active, tag = host.apply_dynamic_callback(acct, rules.dynamic_bonus)
assert(bal == 60 and active == true and tag == "acct-lua:ok", "dynamic_bonus callback mismatch")

local ok, err = pcall(host.apply_dynamic_callback, acct, rules.bad_string_return)
assert(not ok, "bad_string_return must fail at Lua->Titan string edge")
assert(type(err) == "string" and #err > 0, "expected error message")
local bt = titan.backtrace()
assert(type(bt) == "string" and #bt > 0, "require('titan').backtrace() must return traceback after Titan error")

-- Plain Lua tables must be rejected where a Titan Array proxy is required.
local ok_plain = pcall(host.make_const_limits, {10, 20, 30})
assert(not ok_plain, "plain Lua table must be rejected for Titan {integer} parameter")
