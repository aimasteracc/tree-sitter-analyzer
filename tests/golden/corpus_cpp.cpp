/**
 * C++ Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-cpp grammar
 * to verify complete coverage of C++ language features.
 *
 * Coverage includes:
 * - Function definitions (regular, template, lambda)
 * - Class definitions (class, struct, template class)
 * - Namespaces and using declarations
 * - Field and parameter declarations
 * - Operators (operator overloading, new/delete, operator cast)
 * - Modern C++ features (auto, constexpr, variadic templates)
 */

#include <iostream>
#include <string>
#include <vector>
#include <memory>
#include <functional>

// ============================================================================
// Namespace Definitions
// ============================================================================

namespace MyNamespace {
    namespace Nested {
        int nested_var = 42;
    }
}

// Using declarations
using std::string;
using std::vector;
using namespace std;

// ============================================================================
// Forward Declarations
// ============================================================================

class ForwardDeclared;
struct ForwardStruct;

// ============================================================================
// Function Definitions
// ============================================================================

/**
 * Regular function definition
 */
int regular_function(int a, int b) {
    return a + b;
}

/**
 * Function with default parameters
 */
double function_with_defaults(double x, double y = 10.0, double z = 20.0) {
    return x + y + z;
}

/**
 * Function with references
 */
void swap_values(int& a, int& b) {
    int temp = a;
    a = b;
    b = temp;
}

/**
 * Const function
 */
const int* get_const_pointer(const int* ptr) {
    return ptr;
}

/**
 * Inline function
 */
inline int inline_function(int x) {
    return x * 2;
}

/**
 * Constexpr function
 */
constexpr int constexpr_factorial(int n) {
    return n <= 1 ? 1 : n * constexpr_factorial(n - 1);
}

// ============================================================================
// Template Functions
// ============================================================================

/**
 * Simple template function
 */
template<typename T>
T template_max(T a, T b) {
    return (a > b) ? a : b;
}

/**
 * Template function with multiple parameters
 */
template<typename T, typename U>
auto template_add(T a, U b) -> decltype(a + b) {
    return a + b;
}

/**
 * Variadic template function
 */
template<typename... Args>
void variadic_print(Args... args) {
    (std::cout << ... << args) << std::endl;
}

/**
 * Template function with template parameter pack
 */
template<typename T, typename... Args>
T sum(T first, Args... rest) {
    if constexpr (sizeof...(rest) > 0) {
        return first + sum(rest...);
    } else {
        return first;
    }
}

// ============================================================================
// Lambda Expressions
// ============================================================================

/**
 * Function demonstrating various lambda expressions
 */
void lambda_examples() {
    // Simple lambda
    auto simple_lambda = [](int x) { return x * 2; };

    // Lambda with capture by value
    int y = 10;
    auto capture_value = [y](int x) { return x + y; };

    // Lambda with capture by reference
    auto capture_ref = [&y](int x) { y = x; return y; };

    // Lambda with default capture
    auto capture_all = [=]() { return y; };

    // Lambda with mutable
    auto mutable_lambda = [y]() mutable { return ++y; };

    // Lambda with return type
    auto typed_lambda = [](int x) -> double { return x * 1.5; };

    // Generic lambda (C++14)
    auto generic_lambda = [](auto x, auto y) { return x + y; };

    // Lambda in algorithm
    vector<int> vec = {1, 2, 3, 4, 5};
    auto result = std::find_if(vec.begin(), vec.end(),
                               [](int x) { return x > 3; });
}

// ============================================================================
// Struct Definitions
// ============================================================================

/**
 * Simple struct
 */
struct Point {
    double x;
    double y;

    Point(double x_val, double y_val) : x(x_val), y(y_val) {}

    double distance() const {
        return sqrt(x * x + y * y);
    }
};

/**
 * Struct with nested struct
 */
struct OuterStruct {
    int value;

    struct InnerStruct {
        string name;
        int id;
    };

    InnerStruct inner;
};

// ============================================================================
// Class Definitions
// ============================================================================

/**
 * Basic class with various member types
 */
class BaseClass {
private:
    int private_field;

protected:
    string protected_field;

public:
    double public_field;

    // Constructor
    BaseClass(int val) : private_field(val), protected_field("base"), public_field(0.0) {}

    // Destructor
    virtual ~BaseClass() {}

    // Virtual function
    virtual void virtual_method() {
        std::cout << "Base virtual method" << std::endl;
    }

    // Pure virtual function
    virtual int pure_virtual_method() const = 0;

    // Static method
    static void static_method() {
        std::cout << "Static method" << std::endl;
    }

    // Const method
    int get_value() const {
        return private_field;
    }

    // Friend function declaration
    friend void friend_function(const BaseClass& obj);
};

/**
 * Derived class with inheritance
 */
class DerivedClass : public BaseClass {
private:
    vector<int> data;

public:
    DerivedClass(int val, const vector<int>& d)
        : BaseClass(val), data(d) {}

    // Override virtual method
    void virtual_method() override {
        std::cout << "Derived virtual method" << std::endl;
    }

    // Implement pure virtual
    int pure_virtual_method() const override {
        return 42;
    }

    // Final method
    virtual void final_method() final {
        std::cout << "Final method" << std::endl;
    }
};

/**
 * Multiple inheritance
 */
class Interface1 {
public:
    virtual void interface1_method() = 0;
};

class Interface2 {
public:
    virtual void interface2_method() = 0;
};

class MultipleInheritance : public Interface1, public Interface2 {
public:
    void interface1_method() override {}
    void interface2_method() override {}
};

// ============================================================================
// Template Classes
// ============================================================================

/**
 * Simple template class
 */
template<typename T>
class Stack {
private:
    vector<T> elements;

public:
    void push(const T& elem) {
        elements.push_back(elem);
    }

    T pop() {
        T elem = elements.back();
        elements.pop_back();
        return elem;
    }

    bool empty() const {
        return elements.empty();
    }
};

/**
 * Template class with multiple parameters
 */
template<typename K, typename V>
class Pair {
private:
    K key;
    V value;

public:
    Pair(const K& k, const V& v) : key(k), value(v) {}

    K get_key() const { return key; }
    V get_value() const { return value; }
};

/**
 * Template class with non-type parameter
 */
template<typename T, int Size>
class FixedArray {
private:
    T data[Size];

public:
    T& operator[](int index) {
        return data[index];
    }

    constexpr int size() const {
        return Size;
    }
};

/**
 * Variadic template class
 */
template<typename... Types>
class Tuple;

// Template specialization
template<>
class Tuple<> {};

template<typename Head, typename... Tail>
class Tuple<Head, Tail...> : private Tuple<Tail...> {
private:
    Head head;
public:
    Tuple(Head h, Tail... t) : Tuple<Tail...>(t...), head(h) {}
};

// ============================================================================
// Operator Overloading
// ============================================================================

/**
 * Class demonstrating operator overloading
 */
class Complex {
private:
    double real;
    double imag;

public:
    Complex(double r = 0.0, double i = 0.0) : real(r), imag(i) {}

    // Arithmetic operators
    Complex operator+(const Complex& other) const {
        return Complex(real + other.real, imag + other.imag);
    }

    Complex operator-(const Complex& other) const {
        return Complex(real - other.real, imag - other.imag);
    }

    Complex operator*(const Complex& other) const {
        return Complex(real * other.real - imag * other.imag,
                      real * other.imag + imag * other.real);
    }

    // Unary operator
    Complex operator-() const {
        return Complex(-real, -imag);
    }

    // Comparison operator
    bool operator==(const Complex& other) const {
        return real == other.real && imag == other.imag;
    }

    // Assignment operator
    Complex& operator=(const Complex& other) {
        if (this != &other) {
            real = other.real;
            imag = other.imag;
        }
        return *this;
    }

    // Compound assignment
    Complex& operator+=(const Complex& other) {
        real += other.real;
        imag += other.imag;
        return *this;
    }

    // Stream operator (friend)
    friend ostream& operator<<(ostream& os, const Complex& c);

    // Subscript operator
    double& operator[](int index) {
        return (index == 0) ? real : imag;
    }

    // Function call operator
    double operator()() const {
        return sqrt(real * real + imag * imag);
    }

    // Type conversion operator (operator cast)
    operator double() const {
        return sqrt(real * real + imag * imag);
    }

    operator bool() const {
        return real != 0.0 || imag != 0.0;
    }
};

ostream& operator<<(ostream& os, const Complex& c) {
    os << c.real;
    if (c.imag >= 0) os << "+";
    os << c.imag << "i";
    return os;
}

// ============================================================================
// New and Delete Expressions
// ============================================================================

void memory_management_examples() {
    // New expression
    int* ptr = new int(42);
    int* arr = new int[10];

    // New with placement
    char buffer[sizeof(Complex)];
    Complex* c = new (buffer) Complex(1.0, 2.0);

    // Delete expression
    delete ptr;
    delete[] arr;

    // Explicit destructor call (for placement new)
    c->~Complex();

    // Smart pointers
    unique_ptr<int> smart_ptr = make_unique<int>(42);
    shared_ptr<string> shared = make_shared<string>("hello");
}

// ============================================================================
// Enums
// ============================================================================

/**
 * Traditional enum
 */
enum Color {
    RED,
    GREEN,
    BLUE
};

/**
 * Enum class (scoped enum)
 */
enum class Status {
    OK,
    ERROR,
    PENDING
};

/**
 * Enum with explicit type
 */
enum class Priority : unsigned char {
    LOW = 1,
    MEDIUM = 2,
    HIGH = 3
};

// ============================================================================
// Type Aliases and Using
// ============================================================================

// Type alias with using
using IntVector = vector<int>;
using StringMap = std::map<string, string>;

// Function pointer alias
using FunctionPtr = int(*)(int, int);

// Template alias
template<typename T>
using VectorPtr = shared_ptr<vector<T>>;

// ============================================================================
// Field and Parameter Declarations
// ============================================================================

class FieldsExample {
private:
    // Field declarations
    int field_int;
    double field_double;
    string field_string;
    const int const_field = 100;
    static int static_field;
    static const int static_const_field = 200;
    mutable int mutable_field;

public:
    FieldsExample(int i, double d, string s)
        : field_int(i), field_double(d), field_string(s), mutable_field(0) {}

    // Method with various parameter types
    void method_with_params(
        int param_int,                    // parameter_declaration
        const int& param_const_ref,       // parameter_declaration
        int* param_ptr,                   // parameter_declaration
        const vector<int>& param_vector,  // parameter_declaration
        int param_default = 10            // parameter_declaration with default
    ) {
        // Method body
    }
};

// Static field definition
int FieldsExample::static_field = 0;

// ============================================================================
// Modern C++ Features
// ============================================================================

/**
 * Auto type deduction
 */
void auto_examples() {
    auto x = 42;           // int
    auto y = 3.14;         // double
    auto z = "hello";      // const char*
    auto vec = vector<int>{1, 2, 3};

    // Auto with references
    int value = 10;
    auto& ref = value;
    const auto& const_ref = value;

    // Auto in range-based for
    for (auto& elem : vec) {
        elem *= 2;
    }
}

/**
 * Decltype
 */
void decltype_examples() {
    int x = 10;
    decltype(x) y = 20;

    vector<int> vec;
    decltype(vec)::iterator it = vec.begin();
}

/**
 * Structured bindings (C++17)
 */
void structured_binding_examples() {
    std::pair<int, string> p = {1, "one"};
    auto [num, str] = p;

    std::map<int, string> map = {{1, "one"}, {2, "two"}};
    for (const auto& [key, value] : map) {
        // Use key and value
    }
}

/**
 * Concepts (C++20)
 */
#if __cplusplus >= 202002L
template<typename T>
concept Numeric = std::is_arithmetic_v<T>;

template<Numeric T>
T concept_function(T a, T b) {
    return a + b;
}
#endif

// ============================================================================
// Main Function
// ============================================================================

int main() {
    // Test various features
    std::cout << "Regular function: " << regular_function(10, 20) << std::endl;

    // Template function
    std::cout << "Template max: " << template_max(10, 20) << std::endl;

    // Lambda
    auto lambda = [](int x) { return x * 2; };
    std::cout << "Lambda: " << lambda(5) << std::endl;

    // Class
    DerivedClass derived(42, {1, 2, 3});
    derived.virtual_method();

    // Template class
    Stack<int> stack;
    stack.push(10);
    stack.push(20);

    // Operator overloading
    Complex c1(1.0, 2.0);
    Complex c2(3.0, 4.0);
    Complex c3 = c1 + c2;
    std::cout << "Complex: " << c3 << std::endl;

    // New/delete
    int* ptr = new int(42);
    delete ptr;

    return 0;
}
