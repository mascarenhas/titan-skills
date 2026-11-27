#ifndef RING_EXT_H
#define RING_EXT_H

#include <stddef.h>
#include <stdint.h>
#include "lua.h"

/* Status codes for plain-C ring operations (never use lua_pcall internally). */
enum {
    RING_OK = 0,
    RING_ERR_ARG = 1,
    RING_ERR_EMPTY = 2,
    RING_ERR_STACK = 3
};

/* Native header stored in the full userdata payload of a Lua ring object. */
typedef struct ring_udata {
    uint32_t capacity;
    uint32_t head;
    uint32_t count;
} ring_udata;

/* Allocate a full userdata via lua_newuserdatauv with `capacity` uservalue slots
 * (1 <= capacity <= 65535), initialize ring_udata, and leave the userdata on top
 * of L's stack (net +1 on RING_OK; net 0 on error). */
int ring_ext_new(lua_State *L, uint32_t capacity);

/* Push the Lua value at `val_idx` into the ring userdata at `ring_idx`
 * (overwriting the oldest slot if full), using lua_setiuservalue so Lua 5.5
 * GC write barriers fire. Must restore L's stack top on every return path. */
int ring_ext_push(lua_State *L, int ring_idx, int val_idx);

/* Pop the oldest item from the ring userdata at `ring_idx`, clear that slot to
 * nil with lua_setiuservalue so GC can collect it, and leave the popped value on
 * top of L's stack (net +1 on RING_OK; net 0 on RING_ERR_EMPTY/RING_ERR_ARG). */
int ring_ext_pop(lua_State *L, int ring_idx);

/* Peek item at 0-based `offset` (0 = oldest, count-1 = newest) from `ring_idx`
 * and leave it on top of L's stack via lua_getiuservalue (net +1 on RING_OK). */
int ring_ext_peek(lua_State *L, int ring_idx, uint32_t offset);

/* Query live count and capacity without mutating L's stack. */
int ring_ext_stats(lua_State *L, int ring_idx, uint32_t *out_count, uint32_t *out_cap);

#endif
