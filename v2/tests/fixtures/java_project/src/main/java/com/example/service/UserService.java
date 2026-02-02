package com.example.service;

import com.example.repository.UserRepository;

/**
 * User management service.
 * Handles user creation, deletion, and validation.
 */
public class UserService {
    private UserRepository repository;
    private EmailService emailService;

    public UserService() {
        this.repository = new UserRepository();
        this.emailService = new EmailService();
    }

    /**
     * Create a new user.
     * Validates email, saves to repository, and sends welcome email.
     *
     * @param email User email address
     * @return User ID if successful, error message otherwise
     */
    public String createUser(String email) {
        // Intra-file call: createUser -> validateEmail
        if (!validateEmail(email)) {
            return "Error: Invalid email";
        }

        // Cross-file call: UserService -> UserRepository
        String userId = repository.save(email);

        // Cross-file call: UserService -> EmailService
        emailService.sendWelcomeEmail(email);

        return userId;
    }

    /**
     * Delete a user.
     * Validates email, deletes from repository, and sends goodbye email.
     *
     * @param email User email address
     * @return true if deleted, false otherwise
     */
    public boolean deleteUser(String email) {
        // Intra-file call: deleteUser -> validateEmail
        if (!validateEmail(email)) {
            return false;
        }

        // Cross-file call: UserService -> UserRepository
        boolean deleted = repository.delete(email);

        if (deleted) {
            // Cross-file call: UserService -> EmailService
            emailService.sendGoodbyeEmail(email);
        }

        return deleted;
    }

    /**
     * Validate email format.
     * Private helper method.
     *
     * @param email Email to validate
     * @return true if valid, false otherwise
     */
    private boolean validateEmail(String email) {
        if (email == null || email.isEmpty()) {
            return false;
        }
        return email.contains("@") && email.contains(".");
    }
}
