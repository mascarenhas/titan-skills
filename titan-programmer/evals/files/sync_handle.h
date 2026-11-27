#ifndef SYNC_HANDLE_H
#define SYNC_HANDLE_H

typedef struct sync_handle sync_handle_t;

/* Synchronously allocates a native handle (non-yielding). Returns NULL if capacity <= 0. */
sync_handle_t *sync_handle_create(int capacity);

/* Returns the handle's configured capacity, or -1 if h is NULL. */
int sync_handle_capacity(const sync_handle_t *h);

/* Synchronously releases a native handle (non-yielding). Safe to call with NULL (no-op). */
void sync_handle_release(sync_handle_t *h);

/* Process-wide handle accounting counters. */
int sync_handle_created_count(void);
int sync_handle_released_count(void);
int sync_handle_live_count(void);

#endif
