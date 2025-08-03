package com.example;

import java.util.List;
import java.util.ArrayList;

// Example of abstract class
abstract class AbstractParentClass {
    // Abstract method
    abstract void abstractMethod();

    // Concrete method
    void concreteMethod() {
        System.out.println("Concrete method in abstract class");
    }
}

// Regular parent class
class ParentClass extends AbstractParentClass {
    // Static field
    static final String CONSTANT = "Parent constant";

    // Instance field
    protected String parentField;

    // Constructor
    public ParentClass() {
        this.parentField = "Default";
    }

    // Static method
    static void staticParentMethod() {
        System.out.println("Static parent method");
    }

    // Implementation of abstract method
    @Override
    void abstractMethod() {
        System.out.println("Implementation of abstract method");
    }

    // Regular method
    void parentMethod() {
        System.out.println("Parent method");
    }
}

// Interface
interface TestInterface {
    // Constant
    String INTERFACE_CONSTANT = "Interface constant";

    // Abstract method
    void doSomething();

    // Default method
    default void defaultMethod() {
        System.out.println("Default method in interface");
    }

    // Static method
    static void staticInterfaceMethod() {
        System.out.println("Static method in interface");
    }
}

// Another interface
interface AnotherInterface {
    void anotherMethod();
}

// Main class (public)
public class Test extends ParentClass implements TestInterface, AnotherInterface {
    // Private field
    private int value;

    // Static field
    public static int staticValue = 10;

    // Final field
    private final String finalField;

    // Inner class (nested class)
    public class InnerClass {
        public void innerMethod() {
            System.out.println("Inner class method, value: " + value);
        }
    }

    // Static inner class
    public static class StaticNestedClass {
        public void nestedMethod() {
            System.out.println("Static nested class method");
        }
    }

    // Constructor
    public Test(int value) {
        this.value = value;
        this.finalField = "Cannot be changed";
    }

    // Overloaded constructor
    public Test() {
        this(0);
    }

    // Public method
    public String getValue() {
        return "Value: " + value;
    }

    // Protected method
    protected void setValue(int value) {
        this.value = value;
    }

    // Package-private method
    void packageMethod() {
        System.out.println("Package method");
    }

    // Private method
    private void privateMethod() {
        System.out.println("Private method");
    }

    // Static method
    public static void staticMethod() {
        System.out.println("Static method");
    }

    // Final method
    public final void finalMethod() {
        System.out.println("This method cannot be overridden");
    }

    // Implementation of interface method
    @Override
    public void doSomething() {
        System.out.println("Implementation of TestInterface method");
    }

    @Override
    public void anotherMethod() {
        System.out.println("Implementation of AnotherInterface method");
    }

    // Example of generics usage
    public <T> void genericMethod(T input) {
        System.out.println("Generic input: " + input);
    }

    // Method returning generic type
    public <T> List<T> createList(T item) {
        List<T> list = new ArrayList<>();
        list.add(item);
        return list;
    }
}

// Enumeration
enum TestEnum {
    A("First"),
    B("Second"),
    C("Third");

    private final String description;

    // Enum constructor
    TestEnum(String description) {
        this.description = description;
    }

    // Enum method
    public String getDescription() {
        return description;
    }
}
