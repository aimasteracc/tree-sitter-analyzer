package com.example.service;

/**
 * Email notification service.
 * Sends welcome and goodbye emails to users.
 */
public class EmailService {

    public EmailService() {
        // Initialize email service
    }

    /**
     * Send welcome email to new user.
     *
     * @param email User email address
     */
    public void sendWelcomeEmail(String email) {
        // Intra-file call: sendWelcomeEmail -> formatMessage
        String message = formatMessage("Welcome", email);
        System.out.println("Sending email: " + message);
    }

    /**
     * Send goodbye email to departing user.
     *
     * @param email User email address
     */
    public void sendGoodbyeEmail(String email) {
        String message = "Goodbye, " + email + "! We'll miss you.";
        System.out.println("Sending email: " + message);
    }

    /**
     * Format email message.
     * Private helper method.
     *
     * @param type Message type (e.g., "Welcome", "Goodbye")
     * @param email User email address
     * @return Formatted message
     */
    private String formatMessage(String type, String email) {
        return type + ", " + email + "! Thank you for using our service.";
    }
}
