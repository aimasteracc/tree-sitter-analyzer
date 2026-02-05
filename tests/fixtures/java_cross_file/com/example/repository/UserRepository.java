package com.example.repository;

public class UserRepository {
    private String[] users;

    public UserRepository() {
        this.users = new String[]{"Alice", "Bob", "Charlie"};
    }

    public String[] getAllUsers() {
        return users;
    }

    public void addUser(String user) {
        // Add user logic
    }
}
