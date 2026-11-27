#ifndef CRC_WASM_H
#define CRC_WASM_H

#include <stddef.h>
#include <stdint.h>
#include "titan/browser.h"

typedef int (*crc_chunk_cb)(void *userdata, uint32_t chunk_crc, uint32_t chunk_len);

/* Host WebAssembly import (module "env", name "host_feed_chunks"):
 * synchronously invokes `cb(userdata, chunk_crc, chunk_len)` via ctx.table.get
 * for up to `max_chunks` host chunks and returns the total chunks fed. */
TITAN_WASM_IMPORT("host_feed_chunks")
int host_feed_chunks(void *userdata, crc_chunk_cb cb, uint32_t max_chunks);

/* Host WebAssembly import (module "env", name "host_report_crc"):
 * receives a NUL-terminated tag C string (read via ctx.readCString),
 * final combined CRC32, successful callback count, and caught callback error count. */
TITAN_WASM_IMPORT("host_report_crc")
void host_report_crc(const char *tag, uint32_t combined_crc, int32_t ok_count, int32_t err_count);

/* Standard IEEE 802.3 CRC-32 update (polynomial 0xEDB88320):
 *   c = prev_crc ^ 0xFFFFFFFFu;
 *   for each byte b: c ^= b; repeat 8 times: c = (c >> 1) ^ (0xEDB88320u & -(c & 1u));
 *   return c ^ 0xFFFFFFFFu;
 * Note: crc32_update(0, "123456789", 9) == 0xCBF43926u. */
uint32_t crc32_update(uint32_t prev_crc, const uint8_t *data, size_t len);

/* Drives host_feed_chunks and invokes titan_browser_call_sync on `callable`
 * with two INTEGER args (chunk_crc, chunk_len) for each chunk.
 * - Starts `acc = crc32_update(0, (const uint8_t *)"123456789", 9)`.
 * - On TITAN_BROWSER_OK with TITAN_BROWSER_INTEGER: encodes the low 32 bits of
 *   res.value.scalar.integer in little-endian (4 bytes) and folds into `acc` via
 *   `acc = crc32_update(acc, le4, 4)`, incrementing ok_count.
 * - On TITAN_BROWSER_TITAN_ERROR: increments *out_error_count and continues
 *   processing subsequent chunks without aborting.
 * - Properly zero-initializes titan_browser_sync_result and frees message,
 *   trace, and STRING/BYTES value.bytes on every status.
 * Stores *out_combined_crc = acc and returns ok_count (or negative on fatal state error). */
int crc_wasm_run_pipeline(const titan_browser_identity *callable,
                          uint32_t max_chunks,
                          uint32_t *out_combined_crc,
                          int32_t *out_error_count);

#endif
