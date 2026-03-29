/**
 * C Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-c grammar
 * to verify complete coverage of C language features.
 *
 * Coverage includes:
 * - Function definitions and declarations
 * - Struct, union, and enum definitions
 * - Typedef declarations
 * - Pointer and array declarators
 * - Preprocessor directives (include, define, ifdef, etc.)
 * - Storage class specifiers (static, extern, register, etc.)
 * - Type qualifiers (const, volatile, restrict)
 * - Function pointers
 * - Variadic functions
 * - Bit fields
 * - Compound literals
 * - Designated initializers
 */

// ============================================================================
// Preprocessor Directives
// ============================================================================

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>
#include "local_header.h"

// Macro definitions
#define MAX_SIZE 100
#define MIN(a, b) ((a) < (b) ? (a) : (b))
#define MAX(a, b) ((a) > (b) ? (a) : (b))
#define SQUARE(x) ((x) * (x))
#define DEBUG 1

// Conditional compilation
#ifdef DEBUG
#define LOG(msg) printf("LOG: %s\n", msg)
#else
#define LOG(msg)
#endif

#ifndef BUFFER_SIZE
#define BUFFER_SIZE 256
#endif

#if defined(__linux__)
#define PLATFORM "Linux"
#elif defined(_WIN32)
#define PLATFORM "Windows"
#else
#define PLATFORM "Unknown"
#endif

// Macro undefinition
#undef MAX_SIZE
#define MAX_SIZE 200

// Stringification and token pasting
#define STRINGIFY(x) #x
#define CONCAT(a, b) a##b

// ============================================================================
// Enum Definitions
// ============================================================================

/**
 * Simple enum
 */
enum Color {
    RED,
    GREEN,
    BLUE,
    YELLOW
};

/**
 * Enum with explicit values
 */
enum Status {
    STATUS_OK = 0,
    STATUS_ERROR = -1,
    STATUS_PENDING = 1,
    STATUS_TIMEOUT = 2
};

/**
 * Enum with typedef
 */
typedef enum {
    NORTH,
    SOUTH,
    EAST,
    WEST
} Direction;

// ============================================================================
// Struct Definitions
// ============================================================================

/**
 * Simple struct
 */
struct Point {
    int x;
    int y;
};

/**
 * Struct with various field types
 */
struct Person {
    char name[50];
    int age;
    float height;
    double salary;
    bool is_employed;
};

/**
 * Struct with pointer fields
 */
struct Node {
    int data;
    struct Node* next;
    struct Node* prev;
};

/**
 * Struct with typedef
 */
typedef struct {
    float x;
    float y;
    float z;
} Vector3;

/**
 * Struct with bit fields
 */
struct Flags {
    unsigned int flag1 : 1;
    unsigned int flag2 : 1;
    unsigned int flag3 : 1;
    unsigned int reserved : 5;
};

/**
 * Struct with flexible array member
 */
struct Buffer {
    size_t size;
    char data[];
};

/**
 * Nested struct
 */
struct Rectangle {
    struct Point top_left;
    struct Point bottom_right;
};

/**
 * Anonymous struct in union
 */
struct Packet {
    int type;
    union {
        struct {
            int value;
            char message[100];
        } data_packet;
        struct {
            int code;
            char reason[100];
        } error_packet;
    } payload;
};

// ============================================================================
// Union Definitions
// ============================================================================

/**
 * Simple union
 */
union Value {
    int i;
    float f;
    char c;
};

/**
 * Union with typedef
 */
typedef union {
    uint32_t u32;
    uint16_t u16[2];
    uint8_t u8[4];
} Word;

/**
 * Tagged union
 */
struct TaggedValue {
    enum { INT_TYPE, FLOAT_TYPE, STRING_TYPE } type;
    union {
        int int_value;
        float float_value;
        char* string_value;
    } data;
};

// ============================================================================
// Typedef Declarations
// ============================================================================

// Basic typedefs
typedef int Int32;
typedef unsigned int UInt32;
typedef long long Int64;
typedef unsigned long long UInt64;

// Pointer typedefs
typedef char* String;
typedef void* VoidPtr;

// Function pointer typedefs
typedef int (*CompareFunc)(const void*, const void*);
typedef void (*Callback)(void);
typedef int (*BinaryOp)(int, int);

// Array typedefs
typedef int IntArray[10];
typedef char Matrix[10][10];

// Struct pointer typedef
typedef struct Node* NodePtr;

// ============================================================================
// Function Declarations
// ============================================================================

// Simple function declaration
int add(int a, int b);

// Function with pointer parameters
void swap(int* a, int* b);

// Function with array parameter
int sum_array(int arr[], int size);

// Function with const parameters
int string_length(const char* str);

// Function with multiple qualifiers
const char* get_const_string(void);

// Function returning pointer
int* allocate_array(size_t size);

// Function with variadic parameters
int printf_wrapper(const char* format, ...);

// Static function declaration
static int internal_helper(int x);

// Inline function declaration
inline int fast_add(int a, int b);

// Function with struct parameter
struct Point translate_point(struct Point p, int dx, int dy);

// Function pointer parameter
void apply_operation(int* array, int size, void (*operation)(int*));

// ============================================================================
// Function Definitions
// ============================================================================

/**
 * Simple function definition
 */
int add(int a, int b) {
    return a + b;
}

/**
 * Function with multiple statements
 */
int factorial(int n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}

/**
 * Function with local variables
 */
double calculate_average(int* numbers, int count) {
    if (count == 0) {
        return 0.0;
    }

    int sum = 0;
    for (int i = 0; i < count; i++) {
        sum += numbers[i];
    }

    return (double)sum / count;
}

/**
 * Function with pointer manipulation
 */
void swap(int* a, int* b) {
    int temp = *a;
    *a = *b;
    *b = temp;
}

/**
 * Function with struct manipulation
 */
struct Point create_point(int x, int y) {
    struct Point p;
    p.x = x;
    p.y = y;
    return p;
}

/**
 * Function with dynamic memory allocation
 */
int* create_array(size_t size) {
    int* arr = (int*)malloc(size * sizeof(int));
    if (arr != NULL) {
        for (size_t i = 0; i < size; i++) {
            arr[i] = 0;
        }
    }
    return arr;
}

/**
 * Function with string manipulation
 */
char* duplicate_string(const char* src) {
    if (src == NULL) {
        return NULL;
    }

    size_t len = strlen(src);
    char* dest = (char*)malloc(len + 1);
    if (dest != NULL) {
        strcpy(dest, src);
    }
    return dest;
}

/**
 * Static function definition
 */
static int internal_helper(int x) {
    return x * 2;
}

/**
 * Inline function definition
 */
inline int fast_add(int a, int b) {
    return a + b;
}

/**
 * Function with multiple return points
 */
int find_max(int* array, int size) {
    if (array == NULL || size <= 0) {
        return -1;
    }

    int max = array[0];
    for (int i = 1; i < size; i++) {
        if (array[i] > max) {
            max = array[i];
        }
    }
    return max;
}

/**
 * Function with switch statement
 */
const char* get_day_name(int day) {
    switch (day) {
        case 0: return "Sunday";
        case 1: return "Monday";
        case 2: return "Tuesday";
        case 3: return "Wednesday";
        case 4: return "Thursday";
        case 5: return "Friday";
        case 6: return "Saturday";
        default: return "Invalid";
    }
}

/**
 * Function with do-while loop
 */
int power(int base, int exponent) {
    int result = 1;
    int i = 0;
    do {
        result *= base;
        i++;
    } while (i < exponent);
    return result;
}

/**
 * Function with goto
 */
int safe_divide(int a, int b, int* result) {
    if (b == 0) {
        goto error;
    }

    *result = a / b;
    return 0;

error:
    *result = 0;
    return -1;
}

/**
 * Variadic function
 */
int sum_integers(int count, ...) {
    va_list args;
    va_start(args, count);

    int sum = 0;
    for (int i = 0; i < count; i++) {
        sum += va_arg(args, int);
    }

    va_end(args);
    return sum;
}

// ============================================================================
// Function Pointers
// ============================================================================

/**
 * Function that takes a function pointer
 */
void execute_callback(Callback callback) {
    if (callback != NULL) {
        callback();
    }
}

/**
 * Function returning function pointer
 */
BinaryOp get_operation(char op) {
    switch (op) {
        case '+': return add;
        case '*': return multiply;
        default: return NULL;
    }
}

/**
 * Array of function pointers
 */
typedef void (*OperationFunc)(void);

OperationFunc operations[10] = {
    NULL, NULL, NULL, NULL, NULL,
    NULL, NULL, NULL, NULL, NULL
};

// ============================================================================
// Global Variables
// ============================================================================

// Simple global variables
int global_counter = 0;
float global_pi = 3.14159f;
char global_buffer[BUFFER_SIZE];

// Static global variable (internal linkage)
static int file_scope_variable = 42;

// Extern declaration
extern int external_variable;

// Const global
const int MAX_CONNECTIONS = 100;

// Volatile global
volatile int interrupt_flag = 0;

// Global pointer
int* global_pointer = NULL;

// Global array
int global_array[MAX_SIZE];

// Global struct instance
struct Point origin = {0, 0};

// Initialized global struct
Vector3 unit_x = {1.0f, 0.0f, 0.0f};

// ============================================================================
// Complex Declarations
// ============================================================================

// Pointer to array
int (*ptr_to_array)[10];

// Array of pointers
int* array_of_pointers[10];

// Pointer to function
int (*func_ptr)(int, int);

// Array of function pointers
int (*func_array[5])(int, int);

// Pointer to pointer
int** double_pointer;

// Const pointer to const int
const int* const const_ptr_to_const;

// Volatile pointer
volatile int* volatile_ptr;

// Restrict pointer (C99)
int* restrict restrict_ptr;

// ============================================================================
// Type Casts
// ============================================================================

void demonstrate_casts(void) {
    int i = 42;
    float f = (float)i;

    void* vp = &i;
    int* ip = (int*)vp;

    long l = (long)ip;

    const char* str = "hello";
    char* mutable_str = (char*)str;  // Bad practice, but valid C
}

// ============================================================================
// Compound Literals and Designated Initializers
// ============================================================================

void demonstrate_initializers(void) {
    // Compound literal
    struct Point p1 = (struct Point){10, 20};

    // Designated initializers
    struct Point p2 = {.x = 30, .y = 40};

    // Array with designated initializers
    int arr[10] = {[0] = 1, [5] = 2, [9] = 3};

    // Nested designated initializers
    struct Rectangle rect = {
        .top_left = {.x = 0, .y = 0},
        .bottom_right = {.x = 100, .y = 100}
    };
}

// ============================================================================
// Storage Classes
// ============================================================================

// Auto storage class (rarely used explicitly)
void auto_example(void) {
    auto int local_auto = 10;
}

// Register storage class
void register_example(void) {
    register int counter;
    for (counter = 0; counter < 1000; counter++) {
        // Fast loop
    }
}

// Static local variable
void static_local_example(void) {
    static int call_count = 0;
    call_count++;
    printf("Called %d times\n", call_count);
}

// ============================================================================
// sizeof and typeof Operations
// ============================================================================

void demonstrate_operators(void) {
    int i = 42;
    size_t size = sizeof(int);
    size_t array_size = sizeof(global_array) / sizeof(global_array[0]);

    size_t struct_size = sizeof(struct Point);
    size_t ptr_size = sizeof(void*);
}

// ============================================================================
// Bitwise Operations
// ============================================================================

void demonstrate_bitwise(void) {
    unsigned int a = 0xFF00;
    unsigned int b = 0x00FF;

    unsigned int and_result = a & b;
    unsigned int or_result = a | b;
    unsigned int xor_result = a ^ b;
    unsigned int not_result = ~a;
    unsigned int left_shift = a << 4;
    unsigned int right_shift = a >> 4;
}

// ============================================================================
// Main Function
// ============================================================================

/**
 * Main entry point
 */
int main(int argc, char* argv[]) {
    printf("C Golden Corpus Test\n");
    printf("Platform: %s\n", PLATFORM);

    // Test basic operations
    int sum = add(5, 3);
    printf("5 + 3 = %d\n", sum);

    // Test struct
    struct Point p = create_point(10, 20);
    printf("Point: (%d, %d)\n", p.x, p.y);

    // Test enum
    enum Color color = RED;
    printf("Color: %d\n", color);

    // Test array
    int numbers[] = {1, 2, 3, 4, 5};
    int count = sizeof(numbers) / sizeof(numbers[0]);
    double avg = calculate_average(numbers, count);
    printf("Average: %.2f\n", avg);

    // Test factorial
    int fact = factorial(5);
    printf("5! = %d\n", fact);

    // Test union
    union Value val;
    val.i = 42;
    printf("Value as int: %d\n", val.i);
    val.f = 3.14f;
    printf("Value as float: %.2f\n", val.f);

    // Test dynamic allocation
    int* dynamic_array = create_array(10);
    if (dynamic_array != NULL) {
        printf("Dynamic array created\n");
        free(dynamic_array);
    }

    return 0;
}

// ============================================================================
// Additional Helper Functions
// ============================================================================

/**
 * Helper function for multiplication
 */
int multiply(int a, int b) {
    return a * b;
}

/**
 * Function with complex control flow
 */
int complex_function(int x, int y) {
    int result = 0;

    if (x > y) {
        result = x - y;
    } else if (x < y) {
        result = y - x;
    } else {
        result = 0;
    }

    for (int i = 0; i < result; i++) {
        if (i % 2 == 0) {
            continue;
        }
        result += i;
    }

    return result;
}

/**
 * Function with ternary operator
 */
int max(int a, int b) {
    return (a > b) ? a : b;
}

/**
 * Function with comma operator
 */
int use_comma_operator(void) {
    int a, b, c;
    return (a = 1, b = 2, c = 3, a + b + c);
}
