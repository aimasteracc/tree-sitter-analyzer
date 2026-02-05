package com.example;

import com.example.service.UserService;

public class App {
    private UserService userService;

    public App() {
        this.userService = new UserService();
    }

    public void run() {
        userService.processUsers();
        System.out.println("App running");
    }

    public static void main(String[] args) {
        App app = new App();
        app.run();
    }
}
