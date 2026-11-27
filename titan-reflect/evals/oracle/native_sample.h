#ifndef NATIVE_SAMPLE_H
#define NATIVE_SAMPLE_H

#include <stdint.h>

typedef struct sample_pair {
    int32_t tag;
    uint64_t mask;
} sample_pair_t;

static inline sample_pair_t make_sample_pair(int32_t tag, uint64_t mask) {
    sample_pair_t p;
    p.tag = tag;
    p.mask = mask;
    return p;
}

#endif
