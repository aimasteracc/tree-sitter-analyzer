package com.example.test;

/**
 * First class for multi-class testing
 */
public class FirstClass {
    private String name;

    public FirstClass(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }

    private void helper() {
        // Helper method
    }
}

/**
 * Second class for multi-class testing
 */
class SecondClass {
    protected int value;

    public SecondClass() {
        this.value = 0;
    }

    public void setValue(int value) {
        this.value = value;
    }

    protected int getValue() {
        return value;
    }
}

/**
 * Third utility class
 */
public final class ThirdClass {
    public static final String CONSTANT = "TEST";

    private ThirdClass() {
        // Private constructor
    }

    public static void staticMethod() {
        // Static utility method
    }
}
