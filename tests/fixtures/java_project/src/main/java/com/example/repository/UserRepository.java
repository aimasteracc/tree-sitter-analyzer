package com.example.repository;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * User data access layer.
 * Handles user persistence operations.
 */
public class UserRepository {
    private Map<String, String> users;

    public UserRepository() {
        this.users = new HashMap<>();
    }

    /**
     * Save a new user.
     *
     * @param email User email address
     * @return Generated user ID
     */
    public String save(String email) {
        String userId = UUID.randomUUID().toString();
        users.put(email, userId);
        System.out.println("Saved user: " + email + " with ID: " + userId);
        return userId;
    }

    /**
     * Delete a user.
     *
     * @param email User email address
     * @return true if deleted, false if not found
     */
    public boolean delete(String email) {
        if (users.containsKey(email)) {
            users.remove(email);
            System.out.println("Deleted user: " + email);
            return true;
        }
        return false;
    }

    /**
     * Find user by email.
     *
     * @param email User email address
     * @return User ID if found, null otherwise
     */
    public String findByEmail(String email) {
        return users.get(email);
    }
}
