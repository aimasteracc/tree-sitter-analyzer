package com.example.service;

import com.example.repository.UserRepository;

public class UserService {
    private UserRepository repository;

    public UserService() {
        this.repository = new UserRepository();
    }

    public void processUsers() {
        String[] users = repository.getAllUsers();
        for (String user : users) {
            validate(user);
        }
    }

    private void validate(String user) {
        if (user == null || user.isEmpty()) {
            throw new IllegalArgumentException("Invalid user");
        }
    }
}
