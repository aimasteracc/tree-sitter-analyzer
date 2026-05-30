"""Built-in C corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SIZE 100
#define SQUARE(x) ((x) * (x))

typedef struct { int x; int y; } Point;
typedef enum { STATUS_OK = 0, STATUS_ERROR = 1 } Status;
typedef int (*Comparator)(const void *, const void *);

__attribute__((visibility("default")))
void attributed_func(void);

static int counter = 0;

Status process_array(int *arr, size_t len, Comparator cmp) {
    if (arr == NULL || len == 0) { return STATUS_ERROR; }

    for (size_t i = 0; i < len; i++) {
        if (arr[i] < 0) continue;
        if (arr[i] > MAX_SIZE) break;
    }

    int i = 0;
    while (i < 10) { i++; }
    do { i--; } while (i > 0);

    switch (len) {
        case 0: break;
        case 1: return STATUS_OK;
        default: break;
    }

    label_a:
    goto label_b;
    label_b: ;

    [[fallthrough]] ;
    __attribute__((unused)) int attr_var = 0;
    [[nodiscard]] int attr_stmt_var = 0;
    __try { __leave; } __finally { }

    return STATUS_OK;
}

int main(int argc, char *argv[]) {
    int nums[] = {5, 3, 1};
    process_array(nums, 3, NULL);
    return EXIT_SUCCESS;
}
"""
