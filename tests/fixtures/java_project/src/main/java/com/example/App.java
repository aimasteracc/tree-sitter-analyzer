package com.example;

import com.example.service.UserService;

/**
 * Main application entry point.
 * Orchestrates user creation workflow.
 */
public class App {
    private UserService userService;

    public App() {
        this.userService = new UserService();
    }

    /**
     * Main entry point.
     */
    public static void main(String[] args) {
        App app = new App();
        app.run();
    }

    /**
     * Run the application workflow.
     * Creates a new user and demonstrates the full call chain.
     */
    public void run() {
        System.out.println("Starting application...");

        // Cross-file call: App -> UserService
        String email = "alice@example.com";
        String result = userService.createUser(email);

        System.out.println("User creation result: " + result);
    }
}
