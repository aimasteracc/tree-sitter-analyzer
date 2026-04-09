/**
 * Java Golden Corpus - Grammar Coverage MECE Test
 *
 * This file contains all key node types from tree-sitter-java grammar
 * to verify complete coverage of Java language features.
 *
 * Coverage includes:
 * - Class declarations (regular, abstract, final, inner, anonymous)
 * - Interface declarations (regular, functional)
 * - Enum declarations
 * - Method declarations (regular, static, abstract, synchronized, native)
 * - Constructor declarations
 * - Field declarations (instance, static, final, volatile)
 * - Annotations (built-in and custom)
 * - Annotation type declarations
 * - Generics (classes, methods, bounded type parameters)
 * - Lambda expressions
 * - Method references
 * - Record declarations (Java 14+)
 * - Pattern matching (Java 16+)
 * - Import declarations
 * - Package declaration
 */

package com.example.corpus;

import java.util.*;
import java.util.function.*;
import java.io.*;
import static java.lang.Math.*;
import java.util.concurrent.atomic.AtomicInteger;

// ============================================================================
// Annotation Type Declarations
// ============================================================================

/**
 * Custom annotation type
 */
@interface Author {
    String name();
    String date();
    int version() default 1;
}

/**
 * Marker annotation (no elements)
 */
@interface Marker {
}

/**
 * Single-element annotation
 */
@interface SingleValue {
    String value();
}

// ============================================================================
// Enum Declarations
// ============================================================================

/**
 * Simple enum
 */
enum Direction {
    NORTH, SOUTH, EAST, WEST
}

/**
 * Enum with fields and methods
 */
enum Planet {
    MERCURY(3.303e+23, 2.4397e6),
    VENUS(4.869e+24, 6.0518e6),
    EARTH(5.976e+24, 6.37814e6),
    MARS(6.421e+23, 3.3972e6);

    private final double mass;
    private final double radius;

    Planet(double mass, double radius) {
        this.mass = mass;
        this.radius = radius;
    }

    public double getMass() {
        return mass;
    }

    public double getRadius() {
        return radius;
    }

    public double surfaceGravity() {
        return 6.67300E-11 * mass / (radius * radius);
    }
}

/**
 * Enum implementing interface
 */
enum Operation implements BiFunction<Double, Double, Double> {
    ADD {
        public Double apply(Double x, Double y) {
            return x + y;
        }
    },
    SUBTRACT {
        public Double apply(Double x, Double y) {
            return x - y;
        }
    },
    MULTIPLY {
        public Double apply(Double x, Double y) {
            return x * y;
        }
    },
    DIVIDE {
        public Double apply(Double x, Double y) {
            return x / y;
        }
    }
}

// ============================================================================
// Interface Declarations
// ============================================================================

/**
 * Simple interface
 */
interface Animal {
    String getName();
    void makeSound();
    int getAge();
}

/**
 * Interface with default methods
 */
interface Describable {
    String getDescription();

    default String getFullDescription() {
        return "Description: " + getDescription();
    }
}

/**
 * Interface with static methods
 */
interface MathOperations {
    static int add(int a, int b) {
        return a + b;
    }

    static int multiply(int a, int b) {
        return a * b;
    }
}

/**
 * Functional interface
 */
@FunctionalInterface
interface Transformer<T, R> {
    R transform(T input);
}

/**
 * Interface with generics
 */
interface Container<T> {
    T get();
    void set(T value);
    <U> Container<U> map(Function<T, U> mapper);
}

/**
 * Interface extending multiple interfaces
 */
interface Pet extends Animal, Describable {
    String getOwner();
}

// ============================================================================
// Abstract Classes
// ============================================================================

/**
 * Abstract class
 */
abstract class AbstractAnimal implements Animal {
    protected String name;
    protected int age;

    public AbstractAnimal(String name, int age) {
        this.name = name;
        this.age = age;
    }

    @Override
    public String getName() {
        return name;
    }

    @Override
    public int getAge() {
        return age;
    }

    // Abstract method
    @Override
    public abstract void makeSound();

    // Concrete method
    public void sleep() {
        System.out.println(name + " is sleeping");
    }
}

// ============================================================================
// Regular Classes
// ============================================================================

/**
 * Concrete class extending abstract class
 */
@Author(name = "John Doe", date = "2024-01-01", version = 2)
class Dog extends AbstractAnimal implements Pet {
    private String breed;
    private String owner;

    public Dog(String name, int age, String breed, String owner) {
        super(name, age);
        this.breed = breed;
        this.owner = owner;
    }

    @Override
    public void makeSound() {
        System.out.println("Woof!");
    }

    @Override
    public String getDescription() {
        return "A " + breed + " named " + name;
    }

    @Override
    public String getOwner() {
        return owner;
    }

    public String getBreed() {
        return breed;
    }
}

/**
 * Class with generic type parameter
 */
class Box<T> {
    private T value;

    public Box(T value) {
        this.value = value;
    }

    public T getValue() {
        return value;
    }

    public void setValue(T value) {
        this.value = value;
    }

    public <U> Box<U> map(Function<T, U> mapper) {
        return new Box<>(mapper.apply(value));
    }
}

/**
 * Class with multiple generic parameters
 */
class Pair<K, V> {
    private K key;
    private V value;

    public Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    public K getKey() {
        return key;
    }

    public V getValue() {
        return value;
    }
}

/**
 * Class with bounded type parameters
 */
class NumberBox<T extends Number> {
    private T value;

    public NumberBox(T value) {
        this.value = value;
    }

    public double doubleValue() {
        return value.doubleValue();
    }
}

/**
 * Class with all field types
 */
class FieldExamples {
    // Instance fields
    private int privateField;
    protected String protectedField;
    public double publicField;
    String packagePrivateField;

    // Static fields
    private static int staticPrivateField;
    public static String staticPublicField = "static";

    // Final fields
    private final int finalField;
    public static final double PI = 3.14159;

    // Volatile field
    private volatile boolean volatileFlag;

    // Transient field
    private transient Object transientField;

    public FieldExamples(int finalField) {
        this.finalField = finalField;
    }
}

/**
 * Class with all method types
 */
class MethodExamples {
    // Instance method
    public void instanceMethod() {
        System.out.println("Instance method");
    }

    // Static method
    public static void staticMethod() {
        System.out.println("Static method");
    }

    // Final method (cannot be overridden)
    public final void finalMethod() {
        System.out.println("Final method");
    }

    // Synchronized method
    public synchronized void synchronizedMethod() {
        System.out.println("Synchronized method");
    }

    // Native method
    public native void nativeMethod();

    // Generic method
    public <T> T genericMethod(T value) {
        return value;
    }

    // Method with varargs
    public int sum(int... numbers) {
        int total = 0;
        for (int num : numbers) {
            total += num;
        }
        return total;
    }

    // Method with throws clause
    public void methodWithException() throws IOException, IllegalArgumentException {
        throw new IOException("Error");
    }
}

/**
 * Class with inner classes
 */
class OuterClass {
    private int outerField = 10;

    // Non-static inner class
    class InnerClass {
        public void printOuter() {
            System.out.println("Outer field: " + outerField);
        }
    }

    // Static nested class
    static class StaticNestedClass {
        private int nestedField = 20;

        public int getNestedField() {
            return nestedField;
        }
    }

    // Method with local class
    public void methodWithLocalClass() {
        class LocalClass {
            public void print() {
                System.out.println("Local class");
            }
        }

        LocalClass local = new LocalClass();
        local.print();
    }

    // Method with anonymous class
    public Runnable createRunnable() {
        return new Runnable() {
            @Override
            public void run() {
                System.out.println("Anonymous class");
            }
        };
    }
}

// ============================================================================
// Record Declaration (Java 14+)
// ============================================================================

/**
 * Simple record
 */
record Person(String name, int age, String email) {
    // Compact constructor
    public Person {
        if (age < 0) {
            throw new IllegalArgumentException("Age cannot be negative");
        }
    }

    // Additional constructor
    public Person(String name, int age) {
        this(name, age, "");
    }

    // Instance method
    public String getFullInfo() {
        return name + " (" + age + ") - " + email;
    }

    // Static method
    public static Person createAnonymous() {
        return new Person("Anonymous", 0, "");
    }
}

/**
 * Generic record
 */
record Result<T>(boolean success, T data, String message) {
    public static <T> Result<T> success(T data) {
        return new Result<>(true, data, "Success");
    }

    public static <T> Result<T> failure(String message) {
        return new Result<>(false, null, message);
    }
}

// ============================================================================
// Lambda Expressions and Method References
// ============================================================================

class LambdaExamples {
    public void demonstrateLambdas() {
        // Simple lambda
        Runnable runnable1 = () -> System.out.println("Hello");

        // Lambda with parameter
        Consumer<String> consumer = s -> System.out.println(s);

        // Lambda with multiple parameters
        BiFunction<Integer, Integer, Integer> add = (a, b) -> a + b;

        // Lambda with block body
        Predicate<String> isLong = s -> {
            return s.length() > 10;
        };

        // Method reference - static method
        Function<String, Integer> parseInt = Integer::parseInt;

        // Method reference - instance method
        String str = "hello";
        Supplier<Integer> getLength = str::length;

        // Method reference - instance method of arbitrary object
        Function<String, String> toUpper = String::toUpperCase;

        // Method reference - constructor
        Supplier<ArrayList<String>> listSupplier = ArrayList::new;
        Function<Integer, ArrayList<String>> listWithCapacity = ArrayList::new;
    }

    public void useStreams() {
        List<String> names = Arrays.asList("Alice", "Bob", "Charlie");

        // Lambda in stream operations
        names.stream()
            .filter(name -> name.length() > 3)
            .map(String::toUpperCase)
            .forEach(System.out::println);

        // Complex lambda
        Map<String, Integer> nameToLength = names.stream()
            .collect(HashMap::new,
                    (map, name) -> map.put(name, name.length()),
                    HashMap::putAll);
    }
}

// ============================================================================
// Exception Handling
// ============================================================================

class ExceptionExamples {
    // Custom exception
    static class CustomException extends Exception {
        public CustomException(String message) {
            super(message);
        }
    }

    public void tryCatchExample() {
        try {
            riskyOperation();
        } catch (IOException e) {
            e.printStackTrace();
        } catch (IllegalArgumentException e) {
            System.err.println("Invalid argument");
        } finally {
            System.out.println("Cleanup");
        }
    }

    public void tryWithResources() throws IOException {
        try (BufferedReader reader = new BufferedReader(new FileReader("file.txt"))) {
            String line = reader.readLine();
            System.out.println(line);
        }
    }

    public void multiCatch() {
        try {
            riskyOperation();
        } catch (IOException | IllegalArgumentException e) {
            e.printStackTrace();
        }
    }

    private void riskyOperation() throws IOException, IllegalArgumentException {
        throw new IOException("Error");
    }
}

// ============================================================================
// Generics with Wildcards
// ============================================================================

class WildcardExamples {
    // Unbounded wildcard
    public void printList(List<?> list) {
        for (Object item : list) {
            System.out.println(item);
        }
    }

    // Upper bounded wildcard
    public double sumOfList(List<? extends Number> list) {
        double sum = 0.0;
        for (Number num : list) {
            sum += num.doubleValue();
        }
        return sum;
    }

    // Lower bounded wildcard
    public void addNumbers(List<? super Integer> list) {
        for (int i = 1; i <= 10; i++) {
            list.add(i);
        }
    }
}

// ============================================================================
// Static Initialization Block
// ============================================================================

class InitializationExamples {
    private static Map<String, Integer> cache;

    // Static initialization block
    static {
        cache = new HashMap<>();
        cache.put("one", 1);
        cache.put("two", 2);
    }

    // Instance initialization block
    {
        System.out.println("Instance created");
    }

    private int value;

    // Constructor
    public InitializationExamples(int value) {
        this.value = value;
    }
}

// ============================================================================
// Switch Expressions (Java 14+)
// ============================================================================

class SwitchExpressions {
    public String getDayType(int day) {
        return switch (day) {
            case 1, 7 -> "Weekend";
            case 2, 3, 4, 5, 6 -> "Weekday";
            default -> "Invalid day";
        };
    }

    public int getLengthOfMonth(String month) {
        return switch (month.toLowerCase()) {
            case "january", "march", "may", "july", "august", "october", "december" -> 31;
            case "april", "june", "september", "november" -> 30;
            case "february" -> 28;
            default -> throw new IllegalArgumentException("Invalid month: " + month);
        };
    }
}

// ============================================================================
// Pattern Matching (Java 16+)
// ============================================================================

class PatternMatching {
    public void instanceofPattern(Object obj) {
        if (obj instanceof String s) {
            System.out.println("String length: " + s.length());
        } else if (obj instanceof Integer i) {
            System.out.println("Integer value: " + i);
        }
    }

    public String formatValue(Object obj) {
        return switch (obj) {
            case Integer i -> "Integer: " + i;
            case String s -> "String: " + s;
            case Double d -> "Double: " + d;
            case null -> "null value";
            default -> "Unknown type";
        };
    }
}

// ============================================================================
// Main Class for Testing
// ============================================================================

/**
 * Main class with main method
 */
public class CorpusJava {
    public static void main(String[] args) {
        // Test various constructs
        Dog dog = new Dog("Buddy", 5, "Golden Retriever", "John");
        System.out.println(dog.getDescription());
        dog.makeSound();

        // Test record
        Person person = new Person("Alice", 30, "alice@example.com");
        System.out.println(person.getFullInfo());

        // Test lambda
        Runnable task = () -> System.out.println("Task executed");
        task.run();

        // Test enum
        for (Direction dir : Direction.values()) {
            System.out.println(dir);
        }

        // Test generic class
        Box<String> stringBox = new Box<>("Hello");
        Box<Integer> intBox = stringBox.map(String::length);
        System.out.println("String length: " + intBox.getValue());

        // Test static method from interface
        int sum = MathOperations.add(5, 3);
        System.out.println("Sum: " + sum);
    }
}
