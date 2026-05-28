"""Java element extractor tests."""

from contextlib import ExitStack
from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor
from tree_sitter_analyzer.models import Class, Function, Variable


class TestJavaElementExtractor:
    """Test Java element extractor — optimized extraction"""

    @pytest.fixture
    def extractor(self):
        """Create a Java element extractor instance"""
        return JavaElementExtractor()

    @pytest.fixture
    def mock_tree(self):
        """Create a mock tree-sitter tree"""
        tree = Mock()
        tree.root_node = Mock()
        tree.language = Mock()
        return tree

    @pytest.fixture
    def sample_java_code(self):
        """Sample Java code for testing"""
        return """
package com.example.service;

import java.util.List;
import java.util.ArrayList;
import java.util.Map;
import java.util.HashMap;
import java.util.concurrent.CompletableFuture;
import javax.annotation.Nullable;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
import static java.util.Collections.emptyList;
import static org.junit.Assert.*;

/**
 * User service for managing user operations
 * @author John Doe
 * @version 1.0
 * @since 2023
 */
@Service
@Component
public class UserService extends BaseService implements UserOperations, Auditable {

    /**
     * Default page size for pagination
     */
    public static final int DEFAULT_PAGE_SIZE = 20;

    /**
     * Maximum allowed page size
     */
    private static final int MAX_PAGE_SIZE = 100;

    /**
     * User repository for data access
     */
    @Autowired
    private UserRepository userRepository;

    /**
     * Cache for storing user data
     */
    @Nullable
    private final Map<String, User> userCache = new HashMap<>();

    /**
     * Configuration properties
     */
    protected UserConfig config;

    /**
     * Default constructor
     */
    public UserService() {
        super();
        this.config = new UserConfig();
    }

    /**
     * Constructor with configuration
     * @param config User configuration
     */
    @Autowired
    public UserService(UserConfig config) {
        super();
        this.config = config;
    }

    /**
     * Find user by ID
     * @param userId User identifier
     * @return User object if found, null otherwise
     * @throws UserNotFoundException if user not found
     * @throws IllegalArgumentException if userId is null
     */
    @Override
    @Transactional(readOnly = true)
    public User findById(@NonNull String userId) throws UserNotFoundException {
        if (userId == null || userId.trim().isEmpty()) {
            throw new IllegalArgumentException("User ID cannot be null or empty");
        }

        // Check cache first
        User cachedUser = userCache.get(userId);
        if (cachedUser != null) {
            return cachedUser;
        }

        // Query database
        User user = userRepository.findById(userId);
        if (user == null) {
            throw new UserNotFoundException("User not found: " + userId);
        }

        // Cache the result
        userCache.put(userId, user);
        return user;
    }

    /**
     * Create new user
     * @param userData User data for creation
     * @return Created user with generated ID
     * @throws ValidationException if user data is invalid
     */
    @Transactional
    public User createUser(UserData userData) throws ValidationException {
        validateUserData(userData);

        User user = new User();
        user.setName(userData.getName());
        user.setEmail(userData.getEmail());
        user.setCreatedAt(System.currentTimeMillis());

        User savedUser = userRepository.save(user);
        userCache.put(savedUser.getId(), savedUser);

        return savedUser;
    }

    /**
     * Update existing user
     * @param userId User identifier
     * @param userData Updated user data
     * @return Updated user
     * @throws UserNotFoundException if user not found
     * @throws ValidationException if user data is invalid
     */
    @Transactional
    public User updateUser(String userId, UserData userData)
            throws UserNotFoundException, ValidationException {
        User existingUser = findById(userId);
        validateUserData(userData);

        existingUser.setName(userData.getName());
        existingUser.setEmail(userData.getEmail());
        existingUser.setUpdatedAt(System.currentTimeMillis());

        User updatedUser = userRepository.save(existingUser);
        userCache.put(userId, updatedUser);

        return updatedUser;
    }

    /**
     * Delete user by ID
     * @param userId User identifier
     * @throws UserNotFoundException if user not found
     */
    @Transactional
    public void deleteUser(String userId) throws UserNotFoundException {
        User user = findById(userId);
        userRepository.delete(user);
        userCache.remove(userId);
    }

    /**
     * Find users with pagination
     * @param page Page number (0-based)
     * @param size Page size
     * @return List of users
     * @throws IllegalArgumentException if page or size is invalid
     */
    public List<User> findUsers(int page, int size) throws IllegalArgumentException {
        if (page < 0) {
            throw new IllegalArgumentException("Page number cannot be negative");
        }
        if (size <= 0 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException("Invalid page size: " + size);
        }

        return userRepository.findAll(page, size);
    }

    /**
     * Search users by name pattern
     * @param namePattern Name pattern to search
     * @return List of matching users
     */
    public List<User> searchByName(String namePattern) {
        if (namePattern == null || namePattern.trim().isEmpty()) {
            return emptyList();
        }

        return userRepository.findByNameContaining(namePattern.trim());
    }

    /**
     * Get user statistics asynchronously
     * @return Future containing user statistics
     */
    @Async
    public CompletableFuture<UserStats> getUserStatsAsync() {
        return CompletableFuture.supplyAsync(() -> {
            UserStats stats = new UserStats();
            stats.setTotalUsers(userRepository.count());
            stats.setActiveUsers(userRepository.countActive());
            stats.setLastUpdated(System.currentTimeMillis());
            return stats;
        });
    }

    /**
     * Validate user data
     * @param userData User data to validate
     * @throws ValidationException if validation fails
     */
    private void validateUserData(UserData userData) throws ValidationException {
        if (userData == null) {
            throw new ValidationException("User data cannot be null");
        }
        if (userData.getName() == null || userData.getName().trim().isEmpty()) {
            throw new ValidationException("User name is required");
        }
        if (userData.getEmail() == null || !isValidEmail(userData.getEmail())) {
            throw new ValidationException("Valid email is required");
        }
    }

    /**
     * Check if email is valid
     * @param email Email to validate
     * @return true if valid, false otherwise
     */
    private static boolean isValidEmail(String email) {
        return email != null && email.contains("@") && email.contains(".");
    }

    /**
     * Clear user cache
     */
    protected void clearCache() {
        userCache.clear();
    }

    /**
     * Get cache size
     * @return Number of cached users
     */
    public int getCacheSize() {
        return userCache.size();
    }

    /**
     * Inner class for user statistics
     */
    public static class UserStats {
        private long totalUsers;
        private long activeUsers;
        private long lastUpdated;

        // Getters and setters
        public long getTotalUsers() { return totalUsers; }
        public void setTotalUsers(long totalUsers) { this.totalUsers = totalUsers; }

        public long getActiveUsers() { return activeUsers; }
        public void setActiveUsers(long activeUsers) { this.activeUsers = activeUsers; }

        public long getLastUpdated() { return lastUpdated; }
        public void setLastUpdated(long lastUpdated) { this.lastUpdated = lastUpdated; }
    }

    /**
     * Nested interface for audit operations
     */
    public interface AuditOperations {
        void logOperation(String operation, String userId);
        List<AuditEntry> getAuditLog(String userId);
    }

    /**
     * Enum for user status
     */
    public enum UserStatus {
        ACTIVE("Active"),
        INACTIVE("Inactive"),
        SUSPENDED("Suspended"),
        DELETED("Deleted");

        private final String displayName;

        UserStatus(String displayName) {
            this.displayName = displayName;
        }

        public String getDisplayName() {
            return displayName;
        }
    }
}

/**
 * Configuration class for user service
 */
@Configuration
class UserConfig {

    @Value("${user.cache.enabled:true}")
    private boolean cacheEnabled;

    @Value("${user.cache.ttl:3600}")
    private int cacheTtl;

    public boolean isCacheEnabled() {
        return cacheEnabled;
    }

    public int getCacheTtl() {
        return cacheTtl;
    }
}
"""

    def test_extract_class_optimized_complete(self, extractor):
        """Test complete class extraction"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)

        # Mock modifiers child with @Service annotation (AST-based extraction)
        mock_modifiers = Mock()
        mock_modifiers.type = "modifiers"
        mock_annotation = Mock()
        mock_annotation.type = "marker_annotation"
        mock_annotation.start_point = (3, 0)
        mock_ann_identifier = Mock()
        mock_ann_identifier.type = "identifier"
        mock_annotation.children = [mock_ann_identifier]
        mock_modifiers.children = [mock_annotation]

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"

        # Mock superclass child
        mock_superclass = Mock()
        mock_superclass.type = "superclass"

        # Mock super_interfaces child
        mock_interfaces = Mock()
        mock_interfaces.type = "super_interfaces"

        mock_node.children = [
            mock_modifiers,
            mock_identifier,
            mock_superclass,
            mock_interfaces,
        ]

        extractor.content_lines = [
            "/**",
            " * User service class",
            " */",
            "@Service",
            "public class UserService extends BaseService implements UserOperations {",
            "    // class body",
            "}",
        ] * 2
        extractor.current_package = "com.example.service"

        with ExitStack() as stack:
            mock_get_text = stack.enter_context(
                patch.object(extractor, "_get_node_text_optimized")
            )
            mock_modifiers_fn = stack.enter_context(
                patch.object(extractor, "_extract_modifiers_optimized")
            )
            mock_visibility = stack.enter_context(
                patch.object(extractor, "_determine_visibility")
            )
            mock_is_nested = stack.enter_context(
                patch.object(extractor, "_is_nested_class")
            )

            mock_get_text.side_effect = [
                "UserService",
                "extends BaseService",
                "implements UserOperations",
                "@Service",
                "Service",
            ]
            mock_modifiers_fn.return_value = ["public"]
            mock_visibility.return_value = "public"
            mock_is_nested.return_value = False

            result = extractor._extract_class_optimized(mock_node)

            assert isinstance(result, Class)
            assert result.name == "UserService"
            assert result.start_line == 1
            assert result.end_line == 11
            assert result.language == "java"
            assert result.class_type == "class"
            assert result.full_qualified_name == "com.example.service.UserService"
            assert result.package_name == "com.example.service"
            assert result.superclass == "BaseService"
            assert result.interfaces == ["UserOperations"]
            assert result.modifiers == ["public"]
            assert result.visibility == "public"
            assert len(result.annotations) == 1
            assert result.annotations[0]["name"] == "Service"
            assert result.is_nested is False

    def test_extract_method_optimized_complete(self, extractor):
        """Test complete method extraction"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (5, 0)

        extractor.content_lines = [
            "/**",
            " * Find user by ID",
            " * @param userId User identifier",
            " * @return User object",
            " */",
            "@Override",
            "public User findById(String userId) throws UserNotFoundException {",
            "    return userRepository.findById(userId);",
            "}",
        ]

        with ExitStack() as stack:
            mock_parse = stack.enter_context(
                patch.object(extractor, "_parse_method_signature_optimized")
            )
            mock_visibility = stack.enter_context(
                patch.object(extractor, "_determine_visibility")
            )
            mock_annotations = stack.enter_context(
                patch.object(extractor, "_find_annotations_for_line_cached")
            )
            mock_complexity = stack.enter_context(
                patch.object(extractor, "_calculate_complexity_optimized")
            )
            mock_javadoc = stack.enter_context(
                patch.object(extractor, "_extract_javadoc_for_line")
            )

            mock_parse.return_value = (
                "findById",
                "User",
                ["String userId"],
                ["public"],
                ["UserNotFoundException"],
            )
            mock_visibility.return_value = "public"
            mock_annotations.return_value = [{"name": "Override"}]
            mock_complexity.return_value = 2
            mock_javadoc.return_value = "Find user by ID"

            result = extractor._extract_method_optimized(mock_node)

            assert isinstance(result, Function)
            assert result.name == "findById"
            assert result.start_line == 1
            assert result.end_line == 6
            assert result.language == "java"
            assert result.parameters == ["String userId"]
            assert result.return_type == "User"
            assert result.modifiers == ["public"]
            assert result.is_static is False
            assert result.is_private is False
            assert result.is_public is True
            assert result.is_constructor is False
            assert result.visibility == "public"
            assert result.docstring == "Find user by ID"
            assert result.annotations == [{"name": "Override"}]
            assert result.throws == ["UserNotFoundException"]
            assert result.complexity_score == 2
            assert result.is_abstract is False
            assert result.is_final is False

    def test_extract_method_optimized_constructor(self, extractor):
        """Test constructor extraction"""
        mock_node = Mock()
        mock_node.type = "constructor_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (3, 0)

        extractor.content_lines = [
            "public UserService(UserConfig config) {",
            "    this.config = config;",
            "}",
        ]

        with ExitStack() as stack:
            mock_parse = stack.enter_context(
                patch.object(extractor, "_parse_method_signature_optimized")
            )
            mock_visibility = stack.enter_context(
                patch.object(extractor, "_determine_visibility")
            )
            mock_annotations = stack.enter_context(
                patch.object(extractor, "_find_annotations_for_line_cached")
            )
            mock_complexity = stack.enter_context(
                patch.object(extractor, "_calculate_complexity_optimized")
            )
            mock_javadoc = stack.enter_context(
                patch.object(extractor, "_extract_javadoc_for_line")
            )

            mock_parse.return_value = (
                "UserService",
                "void",
                ["UserConfig config"],
                ["public"],
                [],
            )
            mock_visibility.return_value = "public"
            mock_annotations.return_value = []
            mock_complexity.return_value = 1
            mock_javadoc.return_value = None

            result = extractor._extract_method_optimized(mock_node)

            assert isinstance(result, Function)
            assert result.name == "UserService"
            assert result.is_constructor is True
            assert result.return_type == "void"

    def test_extract_field_optimized_complete(self, extractor):
        """Test complete field extraction"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        extractor.content_lines = [
            "/**",
            " * User repository for data access",
            " */",
            "@Autowired",
            "private UserRepository userRepository;",
        ]

        with ExitStack() as stack:
            mock_parse = stack.enter_context(
                patch.object(extractor, "_parse_field_declaration_optimized")
            )
            mock_visibility = stack.enter_context(
                patch.object(extractor, "_determine_visibility")
            )
            mock_annotations = stack.enter_context(
                patch.object(extractor, "_find_annotations_for_line_cached")
            )
            mock_javadoc = stack.enter_context(
                patch.object(extractor, "_extract_javadoc_for_line")
            )

            mock_parse.return_value = (
                "UserRepository",
                ["userRepository"],
                ["private"],
            )
            mock_visibility.return_value = "private"
            mock_annotations.return_value = [{"name": "Autowired"}]
            mock_javadoc.return_value = "User repository for data access"

            result = extractor._extract_field_optimized(mock_node)

            assert isinstance(result, list)
            assert len(result) == 1

            field = result[0]
            assert isinstance(field, Variable)
            assert field.name == "userRepository"
            assert field.start_line == 1
            assert field.end_line == 3
            assert field.language == "java"
            assert field.variable_type == "UserRepository"
            assert field.modifiers == ["private"]
            assert field.is_static is False
            assert field.is_constant is False
            assert field.visibility == "private"
            assert field.docstring == "User repository for data access"
            assert field.annotations == [{"name": "Autowired"}]
            assert field.is_final is False
            assert field.field_type == "UserRepository"

    def test_extract_field_optimized_multiple_variables(self, extractor):
        """Test field extraction with multiple variables in one declaration"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 30)

        extractor.content_lines = ["private String firstName, lastName, email;"]

        with ExitStack() as stack:
            mock_parse = stack.enter_context(
                patch.object(extractor, "_parse_field_declaration_optimized")
            )
            mock_visibility = stack.enter_context(
                patch.object(extractor, "_determine_visibility")
            )
            mock_annotations = stack.enter_context(
                patch.object(extractor, "_find_annotations_for_line_cached")
            )
            mock_javadoc = stack.enter_context(
                patch.object(extractor, "_extract_javadoc_for_line")
            )

            mock_parse.return_value = (
                "String",
                ["firstName", "lastName", "email"],
                ["private"],
            )
            mock_visibility.return_value = "private"
            mock_annotations.return_value = []
            mock_javadoc.return_value = None

            result = extractor._extract_field_optimized(mock_node)

            assert isinstance(result, list)
            assert len(result) == 3

            for _i, field in enumerate(result):
                assert isinstance(field, Variable)
                assert field.variable_type == "String"
                assert field.modifiers == ["private"]
                assert field.visibility == "private"

            assert result[0].name == "firstName"
            assert result[1].name == "lastName"
            assert result[2].name == "email"
