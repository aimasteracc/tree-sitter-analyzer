"""Built-in C++ corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
#include <iostream>
#include <vector>
#include <memory>
#include <concepts>

template<typename T>
concept Printable = requires(T t) {
    { std::cout << t } -> std::same_as<std::ostream&>;
};

template<typename T>
class Container {
public:
    friend class ContainerHelper;
    using iterator = typename std::vector<T>::iterator;
    explicit Container(size_t cap = 16) { data_.reserve(cap); }
    void push(T item) { data_.push_back(std::move(item)); }
    [[nodiscard]] size_t size() const noexcept { return data_.size(); }
    iterator begin() { return data_.begin(); }
    iterator end() { return data_.end(); }
private:
    std::vector<T> data_;
};

struct Point {
    double x, y;
    Point operator+(const Point& o) const { return {x+o.x, y+o.y}; }
    auto operator<=>(const Point&) const = default;
};

namespace alias = std::vector<int>;
namespace N = std::chrono;
using MyInt = int;
using std::string;

typedef unsigned long ulong;

static_assert(sizeof(int) == 4, "int must be 4 bytes");

template<typename T, typename... Args>
class Variadic { };

template<typename... Ts>
void variadic_func(Ts... args) { }

template<int N>
struct TemplateInt { };

class Base {
public:
    virtual ~Base() = default;
    virtual double area() const = 0;
};

class Circle final : public Base {
public:
    explicit Circle(double r) : radius_(r) {}
    double area() const override { return 3.14159 * radius_ * radius_; }
private:
    double radius_;
};

void control_flow(int x) {
    if (x > 0) { } else if (x < 0) { } else { }
    for (int i = 0; i < x; i++) {
        if (i == 3) continue;
        if (i == 7) break;
    }
    while (x > 0) { x--; }
    do { x++; } while (x < 5);
    switch (x) { case 1: break; default: break; }
    label: goto label;
    try { throw std::runtime_error("oops"); }
    catch (const std::exception& e) { }
    catch (...) { }
    __try { __leave; } __finally { }

    if (int y = x * 2; y > 10) { }

    namespace MyNS { void foo() {} }
    namespace alias2 = MyNS;

    template<template<typename> class C>
    void tmpl_tmpl_func() {}

    template<typename T = int>
    void opt_tmpl() {}

    auto coro = []() -> std::coroutine_handle<> {
        co_return;
        co_yield 1;
    };

    [[nodiscard]] int attr_stmt = 0;
    [[maybe_unused]] ;
}

int main() {
    auto circle = std::make_unique<Circle>(5.0);
    auto lambda = [](int x) -> int { return x * x; };
    std::cout << lambda(4) << "\\n";
    return 0;
}
"""
