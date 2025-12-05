/**
 * Sample C file for tree-sitter-analyzer testing
 * Covers all major C language constructs
 */

/* ========== Preprocessor Directives ========== */
#include <stdio.h>
#include <stdlib.h>
#include "local_header.h"

#define MAX_SIZE 100
#define SQUARE(x) ((x) * (x))
#define DEBUG 1

#ifdef DEBUG
#define LOG(msg) printf("[DEBUG] %s\n", msg)
#else
#define LOG(msg)
#endif

/* ========== Type Definitions ========== */

/* Enum declaration */
enum Color { RED, GREEN, BLUE };

/* Enum with explicit values */
enum Status {
    STATUS_OK = 0,
    STATUS_ERROR = -1,
    STATUS_PENDING = 1
};

/* Struct declaration */
struct Point {
    int x;
    int y;
};

/* Struct with nested struct */
struct Rectangle {
    struct Point top_left;
    struct Point bottom_right;
};

/* Union declaration */
union Number {
    int i;
    float f;
    double d;
};

/* Typedef for struct */
typedef struct {
    char name[50];
    int age;
} Person;

/* Typedef for function pointer */
typedef int (*Comparator)(const void*, const void*);

/* ========== Global Variables ========== */

int global_value = 42;
static int static_value = 10;
const int CONSTANT_VALUE = 100;
extern int external_value;

/* Array declarations */
int global_array[MAX_SIZE];
static char buffer[256] = "Hello";

/* Pointer declarations */
int* global_ptr = NULL;
const char* message = "World";

/* ========== Function Declarations (Prototypes) ========== */

int add(int a, int b);
static int multiply(int a, int b);
void process_array(int arr[], size_t len);
int compare_ints(const void* a, const void* b);

/* ========== Function Definitions ========== */

/* Basic function */
int add(int a, int b) {
    return a + b;
}

/* Static function */
static int multiply(int a, int b) {
    return a * b;
}

/* Function with array parameter */
void process_array(int arr[], size_t len) {
    for (size_t i = 0; i < len; i++) {
        arr[i] = SQUARE(arr[i]);
    }
}

/* Function with pointer parameters */
int compare_ints(const void* a, const void* b) {
    return (*(int*)a - *(int*)b);
}

/* Function returning pointer */
int* find_max(int* arr, size_t len) {
    if (len == 0) return NULL;
    int* max = &arr[0];
    for (size_t i = 1; i < len; i++) {
        if (arr[i] > *max) {
            max = &arr[i];
        }
    }
    return max;
}

/* Function with struct parameter */
double calculate_distance(struct Point p1, struct Point p2) {
    int dx = p2.x - p1.x;
    int dy = p2.y - p1.y;
    return sqrt(dx * dx + dy * dy);
}

/* Function using function pointer */
void sort_with_comparator(int arr[], size_t len, Comparator cmp) {
    qsort(arr, len, sizeof(int), cmp);
}

/* Variadic function example declaration */
void log_message(const char* format, ...);

/* Main function */
int main(void) {
    /* Local variables */
    struct Point p = {1, 2};
    union Number n;
    n.i = 10;

    Person person = {"John", 30};
    enum Color color = RED;

    /* Using macros */
    LOG("Program started");
    int squared = SQUARE(5);

    /* Array operations */
    int numbers[5] = {5, 3, 8, 1, 9};
    process_array(numbers, 5);

    /* Function pointer usage */
    Comparator cmp = compare_ints;
    sort_with_comparator(numbers, 5, cmp);

    /* Output */
    printf("Result: %d\n", add(global_value, n.i));
    printf("Person: %s, %d\n", person.name, person.age);

    return 0;
}
