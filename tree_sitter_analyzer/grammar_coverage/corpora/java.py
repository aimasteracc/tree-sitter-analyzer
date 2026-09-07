"""Built-in Java corpus for grammar coverage auto-discovery."""

CORPUS: str = """\
package com.example;

import java.util.List;
import java.util.Optional;

@SuppressWarnings("unused")
public class Example {
    private static final int CONSTANT = 42;
    private final String name;
    private int value;

    public Example(String name, int value) {
        this.name = name;
        this.value = value;
    }

    @Override
    public String toString() {
        return "Example{name=" + name + "}";
    }

    public static <T> Optional<T> findFirst(List<T> items) {
        return items.stream().findFirst();
    }

    public void controlFlow(int x) {
        assert x >= 0 : "must be non-negative";
        if (x > 0) {
        } else if (x < 0) {
        } else {
        }
        for (int i = 0; i < x; i++) {
            if (i == 3) continue;
            if (i == 7) break;
        }
        for (String s : List.of("a", "b")) { }
        while (x > 0) { x--; }
        do { x++; } while (x < 5);
        switch (x) {
            case 1: break;
            default: break;
        }
        label: for (int i = 0; i < 10; i++) { break label; }
        try {
            throw new Exception("oops");
        } catch (Exception e) {
        } finally { }
        try (var res = openResource()) { }
        synchronized (this) { }
        int result = switch (x) { case 1 -> 1; default -> { yield 0; } };
    }
}

interface Processor<T, R> {
    R process(T input) throws Exception;
    default void validate(T input) { }
}

enum Status {
    ACTIVE("active"), INACTIVE("inactive");
    private final String label;
    Status(String label) { this.label = label; }
    public String getLabel() { return label; }
}

record Point(double x, double y) {
    public Point {
        assert x >= 0;
    }
}

@interface CustomAnnotation {
    String value() default "";
    int count() default 1;
}

module com.example {
    exports com.example;
}

interface WithConstants {
    int CONSTANT = 42;
    String NAME = "hello";
}

class LambdaExamples {
    void run() {
        Runnable r = () -> System.out.println("lambda");
        java.util.function.Function<String, Integer> f = String::length;
        java.util.List.of("a","b","c").stream()
            .filter(s -> s.startsWith("a"))
            .map(String::toUpperCase)
            .forEach(System.out::println);
    }
}

sealed class Shape permits Circle, Rectangle {}
final class Circle extends Shape { double radius; }
final class Rectangle extends Shape { double width, height; }
class PatternMatch {
    static double area(Shape s) {
        return switch (s) {
            case Circle c -> Math.PI * c.radius * c.radius;
            case Rectangle r -> r.width * r.height;
        };
    }
    static boolean checkString(Object obj) {
        return obj instanceof String str && str.length() > 0;
    }
}

class TextBlockExample {
    String json = \"""
            {"key": "value"}
            \""";
}
record Range(int min, int max) {
    Range {
        if (min > max) throw new IllegalArgumentException();
    }
}

class InitializerExample {
    static final java.util.Map<String, Integer> MAP;
    static {
        MAP = new java.util.HashMap<>();
        MAP.put("a", 1);
    }
    void run() {
        Runnable anon = new Runnable() {
            @Override
            public void run() { System.out.println("anonymous"); }
        };
    }
}
"""
