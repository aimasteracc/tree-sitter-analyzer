/**
 * Sample C++ file for tree-sitter-analyzer testing
 * Covers all major C++ language constructs
 */

/* ========== Preprocessor Directives ========== */
#include <iostream>
#include <string>
#include <vector>
#include <memory>
#include <functional>

/* ========== Using Declarations ========== */
using namespace std;
using std::vector;

/* ========== Namespace Definition ========== */
namespace math {

/* Constants in namespace */
constexpr double PI = 3.14159265359;

/* Template function */
template<typename T>
T max(T a, T b) {
    return (a > b) ? a : b;
}

/* Template class */
template<typename T>
class Container {
public:
    Container() : data_(nullptr) {}
    explicit Container(T value) : data_(new T(value)) {}
    ~Container() { delete data_; }

    T get() const { return data_ ? *data_ : T(); }
    void set(T value) {
        delete data_;
        data_ = new T(value);
    }

private:
    T* data_;
};

} // namespace math

/* ========== Enum Declarations ========== */

/* Traditional enum */
enum Color { RED, GREEN, BLUE };

/* C++11 enum class */
enum class Status {
    OK = 0,
    ERROR = -1,
    PENDING = 1
};

/* ========== Struct Declaration ========== */
struct Point {
    int x;
    int y;

    /* Member function in struct */
    double distance() const {
        return sqrt(x * x + y * y);
    }
};

/* ========== Abstract Base Class ========== */
class Shape {
public:
    virtual ~Shape() = default;

    /* Pure virtual function */
    virtual double area() const = 0;
    virtual double perimeter() const = 0;

    /* Virtual function with default implementation */
    virtual string name() const { return "Shape"; }
};

/* ========== Derived Class with Inheritance ========== */
class Rectangle : public Shape {
public:
    /* Constructor with initializer list */
    Rectangle(double w, double h) : width_(w), height_(h) {}

    /* Copy constructor */
    Rectangle(const Rectangle& other) : width_(other.width_), height_(other.height_) {}

    /* Move constructor */
    Rectangle(Rectangle&& other) noexcept : width_(other.width_), height_(other.height_) {
        other.width_ = 0;
        other.height_ = 0;
    }

    /* Destructor */
    ~Rectangle() override = default;

    /* Override virtual functions */
    double area() const override { return width_ * height_; }
    double perimeter() const override { return 2 * (width_ + height_); }
    string name() const override { return "Rectangle"; }

    /* Getter methods */
    double width() const { return width_; }
    double height() const { return height_; }

    /* Operator overloading */
    bool operator==(const Rectangle& other) const {
        return width_ == other.width_ && height_ == other.height_;
    }

    /* Static member function */
    static Rectangle square(double side) {
        return Rectangle(side, side);
    }

private:
    double width_;
    double height_;

    /* Static member variable */
    static int instance_count_;
};

/* Static member initialization */
int Rectangle::instance_count_ = 0;

/* ========== Class with Multiple Inheritance ========== */
class Printable {
public:
    virtual void print() const = 0;
    virtual ~Printable() = default;
};

class Circle : public Shape, public Printable {
public:
    explicit Circle(double r) : radius_(r) {}

    double area() const override { return math::PI * radius_ * radius_; }
    double perimeter() const override { return 2 * math::PI * radius_; }
    string name() const override { return "Circle"; }

    void print() const override {
        cout << "Circle(radius=" << radius_ << ")" << endl;
    }

    /* Friend function declaration */
    friend ostream& operator<<(ostream& os, const Circle& c);

private:
    double radius_;
};

/* Friend function definition */
ostream& operator<<(ostream& os, const Circle& c) {
    os << "Circle[r=" << c.radius_ << "]";
    return os;
}

/* ========== Type Aliases ========== */
typedef vector<int> IntVector;
using StringList = vector<string>;

/* ========== Global Variables ========== */
static int static_value = 5;
const string APP_NAME = "SampleApp";
constexpr int MAX_SIZE = 100;

/* ========== Function Templates ========== */
template<typename T>
void swap_values(T& a, T& b) {
    T temp = a;
    a = b;
    b = temp;
}

/* ========== Regular Functions ========== */

/* Function with default parameters */
int add(int a, int b = 0) {
    return a + b;
}

/* Overloaded function */
double add(double a, double b) {
    return a + b;
}

/* Function with lambda parameter */
void process(vector<int>& vec, function<int(int)> transformer) {
    for (auto& v : vec) {
        v = transformer(v);
    }
}

/* Function returning unique_ptr */
unique_ptr<Shape> create_shape(const string& type, double size) {
    if (type == "circle") {
        return make_unique<Circle>(size);
    } else {
        return make_unique<Rectangle>(size, size);
    }
}

/* ========== Main Function ========== */
int main() {
    /* Using namespace items */
    using namespace math;

    /* Basic types */
    auto value = 42;
    const auto& name = APP_NAME;

    /* Struct usage */
    Point p{10, 20};
    cout << "Distance: " << p.distance() << endl;

    /* Class usage */
    Rectangle rect(5.0, 3.0);
    Circle circle(2.5);

    /* Polymorphism */
    vector<unique_ptr<Shape>> shapes;
    shapes.push_back(make_unique<Rectangle>(4, 5));
    shapes.push_back(make_unique<Circle>(3));

    for (const auto& shape : shapes) {
        cout << shape->name() << ": area=" << shape->area() << endl;
    }

    /* Template usage */
    Container<int> container(100);
    cout << "Container value: " << container.get() << endl;

    /* Lambda expression */
    auto square = [](int x) { return x * x; };
    vector<int> numbers = {1, 2, 3, 4, 5};
    process(numbers, square);

    /* Enum class usage */
    Status status = Status::OK;
    if (status == Status::OK) {
        cout << "Status is OK" << endl;
    }

    /* Smart pointer */
    auto shape = create_shape("circle", 5.0);
    cout << "Created: " << shape->name() << endl;

    return 0;
}
