-- Lua rule plugin interacting with a Titan-exported Account record and arrays.
local M = {}

function M.dynamic_bonus(acct)
    -- Return integral float 2.0 (converts to integer), numeric 0 (truthy -> true),
    -- and a string tag derived from the account's public fields/methods.
    local after = acct:credit(10.0)
    return after + 0.0, 0, acct.id .. ":ok"
end

function M.bad_string_return(acct)
    -- Returns a number in a string return position; must fail at the Lua->Titan edge.
    return 1, true, 999
end

function M.probe_account(acct, limits, verdict, host_mod)
    local report = {}

    -- Public fields and methods work; dynamic float-to-integer conversion works.
    report.id = acct.id
    acct.balance = 50.0
    report.balance_after_set = acct.balance

    -- Writing const field must fail.
    local ok_const = pcall(function() acct.id = "hacked" end)
    report.const_write_blocked = not ok_const

    -- Writing non-integral float to integer field must fail.
    local ok_frac = pcall(function() acct.balance = 12.5 end)
    report.frac_write_blocked = not ok_frac

    -- Accessing private/local fields must fail.
    local ok_secret_read = pcall(function() return acct.secret_pin end)
    local ok_secret_write = pcall(function() acct.secret_pin = 0 end)
    report.local_field_hidden = (not ok_secret_read) and (not ok_secret_write)

    -- Truthiness on boolean parameter: 0 is truthy, nil/false are falsy.
    report.flag_zero = acct:flag_active(0)
    report.flag_nil = acct:flag_active(nil)
    report.flag_false = acct:flag_active(false)

    -- Passing a number where string is expected must fail.
    local ok_num_str = pcall(function() return host_mod.open_account(123, 0, 1) end)
    report.num_to_str_blocked = not ok_num_str

    -- Const array proxy: length and reads work; writes and rawget fail.
    report.limits_len = #limits
    report.limits_sum = limits[1] + limits[2] + limits[3]
    local ok_arr_write = pcall(function() limits[1] = 999 end)
    local ok_rawget = pcall(function() return rawget(limits, 1) end)
    report.const_array_enforced = (not ok_arr_write) and (not ok_rawget)

    -- Opaque union userdata can still be passed back to Titan.
    report.verdict_type = type(verdict)
    report.verdict_text = host_mod.verdict_label(verdict)

    return report
end

return M
