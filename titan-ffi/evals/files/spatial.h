#ifndef SPATIAL_H
#define SPATIAL_H

#include <stddef.h>
#include <stdint.h>

typedef enum spatial_status {
    SPATIAL_OK = 0,
    SPATIAL_ERR_INVALID = -1,
    SPATIAL_ERR_FULL = -2
} spatial_status_t;

typedef struct spatial_point {
    int64_t id;
    int64_t x;
    int64_t y;
} spatial_point_t;

typedef struct spatial_entry {
    int64_t id;
    int64_t dist_sq;
} spatial_entry_t;

typedef struct spatial_index spatial_index_t;

typedef int (*spatial_cmp_fn)(const spatial_entry_t *a, const spatial_entry_t *b);

/* Synchronous handle lifecycle (non-yielding). */
spatial_index_t *spatial_index_create(size_t capacity);
void spatial_index_destroy(spatial_index_t *idx);

/* Raw primitive storage operations. */
spatial_status_t spatial_index_add(spatial_index_t *idx, const spatial_point_t *pt);
size_t spatial_index_count(const spatial_index_t *idx);
size_t spatial_index_capacity(const spatial_index_t *idx);
size_t spatial_index_copy_points(const spatial_index_t *idx,
                                 spatial_point_t *out,
                                 size_t max_out);

/* Raw geometric distance primitive and callback-driven sort primitive. */
int64_t spatial_distance_sq(const spatial_point_t *a, const spatial_point_t *b);
void spatial_sort_entries(spatial_entry_t *entries, size_t n, spatial_cmp_fn cmp);

/* Process-wide diagnostics for lifecycle and callback verification. */
int64_t spatial_active_handles(void);
int64_t spatial_destroy_calls(void);
int64_t spatial_sort_calls(void);

#endif
