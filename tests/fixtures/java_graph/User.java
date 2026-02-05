package com.example;

public class User {
    private String name;
    private int age;

    public User(String name, int age) {
        this.name = name;
        this.age = age;
        validate();
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    private void validate() {
        if (name == null) {
            throw new IllegalArgumentException("Name cannot be null");
        }
    }
}
