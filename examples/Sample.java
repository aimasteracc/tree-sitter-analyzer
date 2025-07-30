package com.example;

import java.util.List;
import java.util.ArrayList;

// 抽象クラスの例
abstract class AbstractParentClass {
    // 抽象メソッド
    abstract void abstractMethod();
    
    // 具象メソッド
    void concreteMethod() {
        System.out.println("Concrete method in abstract class");
    }
}

// 通常の親クラス
class ParentClass extends AbstractParentClass {
    // static フィールド
    static final String CONSTANT = "Parent constant";
    
    // インスタンスフィールド
    protected String parentField;
    
    // コンストラクタ
    public ParentClass() {
        this.parentField = "Default";
    }
    
    // static メソッド
    static void staticParentMethod() {
        System.out.println("Static parent method");
    }
    
    // 抽象メソッドの実装
    @Override
    void abstractMethod() {
        System.out.println("Implementation of abstract method");
    }
    
    // 通常メソッド
    void parentMethod() {
        System.out.println("Parent method");
    }
}

// インターフェース
interface TestInterface {
    // 定数
    String INTERFACE_CONSTANT = "Interface constant";
    
    // 抽象メソッド
    void doSomething();
    
    // デフォルトメソッド
    default void defaultMethod() {
        System.out.println("Default method in interface");
    }
    
    // staticメソッド
    static void staticInterfaceMethod() {
        System.out.println("Static method in interface");
    }
}

// 別のインターフェース
interface AnotherInterface {
    void anotherMethod();
}

// メインクラス（public）
public class Test extends ParentClass implements TestInterface, AnotherInterface {
    // private フィールド
    private int value;
    
    // static フィールド
    public static int staticValue = 10;
    
    // final フィールド
    private final String finalField;
    
    // 内部クラス（ネストクラス）
    public class InnerClass {
        public void innerMethod() {
            System.out.println("Inner class method, value: " + value);
        }
    }
    
    // static 内部クラス
    public static class StaticNestedClass {
        public void nestedMethod() {
            System.out.println("Static nested class method");
        }
    }
    
    // コンストラクタ
    public Test(int value) {
        this.value = value;
        this.finalField = "Cannot be changed";
    }
    
    // オーバーロードされたコンストラクタ
    public Test() {
        this(0);
    }
    
    // public メソッド
    public String getValue() {
        return "Value: " + value;
    }
    
    // protected メソッド
    protected void setValue(int value) {
        this.value = value;
    }
    
    // package-private メソッド
    void packageMethod() {
        System.out.println("Package method");
    }
    
    // private メソッド
    private void privateMethod() {
        System.out.println("Private method");
    }
    
    // static メソッド
    public static void staticMethod() {
        System.out.println("Static method");
    }
    
    // final メソッド
    public final void finalMethod() {
        System.out.println("This method cannot be overridden");
    }
    
    // インターフェースメソッドの実装
    @Override
    public void doSomething() {
        System.out.println("Implementation of TestInterface method");
    }
    
    @Override
    public void anotherMethod() {
        System.out.println("Implementation of AnotherInterface method");
    }
    
    // ジェネリクスの使用例
    public <T> void genericMethod(T input) {
        System.out.println("Generic input: " + input);
    }
    
    // ジェネリクス型を返すメソッド
    public <T> List<T> createList(T item) {
        List<T> list = new ArrayList<>();
        list.add(item);
        return list;
    }
}

// 列挙型
enum TestEnum {
    A("First"), 
    B("Second"), 
    C("Third");
    
    private final String description;
    
    // 列挙型コンストラクタ
    TestEnum(String description) {
        this.description = description;
    }
    
    // 列挙型メソッド
    public String getDescription() {
        return description;
    }
} 