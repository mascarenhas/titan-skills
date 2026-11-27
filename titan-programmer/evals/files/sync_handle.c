#include "sync_handle.h"
#include <stdlib.h>

struct sync_handle {
  int capacity;
  int magic;
};

#define SYNC_HANDLE_MAGIC 0x53594E43

static int g_created = 0;
static int g_released = 0;

sync_handle_t *sync_handle_create(int capacity) {
  if (capacity <= 0) {
    return NULL;
  }
  sync_handle_t *h = (sync_handle_t *)malloc(sizeof(sync_handle_t));
  if (h == NULL) {
    return NULL;
  }
  h->capacity = capacity;
  h->magic = SYNC_HANDLE_MAGIC;
  g_created += 1;
  return h;
}

int sync_handle_capacity(const sync_handle_t *h) {
  if (h == NULL || h->magic != SYNC_HANDLE_MAGIC) {
    return -1;
  }
  return h->capacity;
}

void sync_handle_release(sync_handle_t *h) {
  if (h == NULL) {
    return;
  }
  if (h->magic != SYNC_HANDLE_MAGIC) {
    abort();
  }
  h->magic = 0;
  g_released += 1;
  free(h);
}

int sync_handle_created_count(void) {
  return g_created;
}

int sync_handle_released_count(void) {
  return g_released;
}

int sync_handle_live_count(void) {
  return g_created - g_released;
}
