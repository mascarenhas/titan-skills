#include "spatial.h"

#include <stdlib.h>
#include <string.h>

struct spatial_index {
    size_t capacity;
    size_t count;
    spatial_point_t *points;
};

static int64_t g_active_handles = 0;
static int64_t g_destroy_calls = 0;
static int64_t g_sort_calls = 0;

spatial_index_t *spatial_index_create(size_t capacity) {
    if (capacity == 0 || capacity > 1000000u) {
        return NULL;
    }
    spatial_index_t *idx = (spatial_index_t *)calloc(1, sizeof(spatial_index_t));
    if (!idx) {
        return NULL;
    }
    idx->points = (spatial_point_t *)calloc(capacity, sizeof(spatial_point_t));
    if (!idx->points) {
        free(idx);
        return NULL;
    }
    idx->capacity = capacity;
    idx->count = 0;
    g_active_handles++;
    return idx;
}

void spatial_index_destroy(spatial_index_t *idx) {
    if (!idx) {
        return;
    }
    g_destroy_calls++;
    if (g_active_handles > 0) {
        g_active_handles--;
    }
    free(idx->points);
    idx->points = NULL;
    free(idx);
}

spatial_status_t spatial_index_add(spatial_index_t *idx, const spatial_point_t *pt) {
    if (!idx || !pt) {
        return SPATIAL_ERR_INVALID;
    }
    if (idx->count >= idx->capacity) {
        return SPATIAL_ERR_FULL;
    }
    idx->points[idx->count++] = *pt;
    return SPATIAL_OK;
}

size_t spatial_index_count(const spatial_index_t *idx) {
    return idx ? idx->count : 0;
}

size_t spatial_index_capacity(const spatial_index_t *idx) {
    return idx ? idx->capacity : 0;
}

size_t spatial_index_copy_points(const spatial_index_t *idx,
                                 spatial_point_t *out,
                                 size_t max_out) {
    if (!idx || !out || max_out == 0) {
        return 0;
    }
    size_t n = idx->count < max_out ? idx->count : max_out;
    memcpy(out, idx->points, n * sizeof(spatial_point_t));
    return n;
}

int64_t spatial_distance_sq(const spatial_point_t *a, const spatial_point_t *b) {
    if (!a || !b) {
        return -1;
    }
    int64_t dx = a->x - b->x;
    int64_t dy = a->y - b->y;
    return dx * dx + dy * dy;
}

static spatial_cmp_fn g_active_cmp = NULL;

static int qsort_adapter(const void *lhs, const void *rhs) {
    return g_active_cmp((const spatial_entry_t *)lhs, (const spatial_entry_t *)rhs);
}

void spatial_sort_entries(spatial_entry_t *entries, size_t n, spatial_cmp_fn cmp) {
    g_sort_calls++;
    if (!entries || n < 2 || !cmp) {
        return;
    }
    spatial_cmp_fn prev = g_active_cmp;
    g_active_cmp = cmp;
    qsort(entries, n, sizeof(spatial_entry_t), qsort_adapter);
    g_active_cmp = prev;
}

int64_t spatial_active_handles(void) {
    return g_active_handles;
}

int64_t spatial_destroy_calls(void) {
    return g_destroy_calls;
}

int64_t spatial_sort_calls(void) {
    return g_sort_calls;
}
