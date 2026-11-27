#include "helper.h"

int64_t bundle_mix_hash(int64_t a, int64_t b) {
    return (a * 31) + b;
}
