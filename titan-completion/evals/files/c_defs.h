#ifndef C_DEFS_H
#define C_DEFS_H

typedef struct Inner {
  int leaf;
} Inner;

typedef struct Outer {
  Inner inner;
  int plain;
  unsigned bits:3;
} Outer;

struct Incomplete;

extern int global_value;
int callable(int argument);

enum Values {
  FIRST_VALUE = 1,
  SECOND_VALUE = 2,
  IMPLICIT_VALUE,
  REFERENCED_VALUE = SECOND_VALUE + 2,
  WIDE_VALUE = 0xffffffffffffffffULL
};

typedef enum Wide {
  WIDE_ENUM_VALUE = 0xffffffffffffffffULL
} Wide;

enum Bounds {
  MINIMUM = (-2147483647 - 1),
  AFTER_MINIMUM,
  REFERENCE_MINIMUM = MINIMUM + 2
};

#define NUMBER_VALUE 42
#define PROJECTED inner.leaf
#define FUNCTION_MACRO(x) ((x) + 1)

#endif
