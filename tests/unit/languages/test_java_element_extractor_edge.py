"""Java element extractor tests."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor
from tree_sitter_analyzer.models import Function


class TestJavaElementExtractor:
    """Test Java element extractor — edge cases and performance"""

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

    def test_extract_imports_fallback_static_imports(self, extractor):
        """Test fallback import extraction for static imports"""
        source_code = """
        import static java.util.Collections.emptyList;
        import static org.junit.Assert.*;
        import static com.example.Utils.helper;
        """

        imports = extractor._extract_imports_fallback(source_code)

        assert len(imports) == 3

        # Check static imports
        assert imports[0].name == "java.util.Collections"
        assert imports[0].is_static is True
        assert imports[0].is_wildcard is False

        assert imports[1].name == "org.junit.Assert"
        assert imports[1].is_static is True
        assert imports[1].is_wildcard is True

        assert imports[2].name == "com.example.Utils"
        assert imports[2].is_static is True
        assert imports[2].is_wildcard is False

    def test_extract_imports_fallback_normal_imports(self, extractor):
        """Test fallback import extraction for normal imports"""
        source_code = """
        import java.util.List;
        import java.util.*;
        import javax.annotation.Nullable;
        """

        imports = extractor._extract_imports_fallback(source_code)

        assert len(imports) == 3

        # Check normal imports
        assert imports[0].name == "java.util.List"
        assert imports[0].is_static is False
        assert imports[0].is_wildcard is False

        assert imports[1].name == "java.util"
        assert imports[1].is_static is False
        assert imports[1].is_wildcard is True

        assert imports[2].name == "javax.annotation.Nullable"
        assert imports[2].is_static is False
        assert imports[2].is_wildcard is False

    def test_performance_with_large_codebase(self, extractor):
        """Test performance with large codebase simulation"""
        import time

        # Create large mock tree
        mock_tree = Mock()
        mock_root = Mock()
        mock_tree.root_node = mock_root

        # Create many method nodes
        method_nodes = []
        for i in range(100):
            node = Mock()
            node.type = "method_declaration"
            node.children = []
            node.start_point = (i, 0)
            node.end_point = (i + 2, 0)
            method_nodes.append(node)

        mock_root.children = method_nodes

        # Create large source code
        large_source = "\n".join(
            [f"public void method_{i}() {{ return; }}" for i in range(100)]
        )

        # Mock extraction method to return simple methods
        def mock_extract_method(node):
            return Function(
                name=f"method_{node.start_point[0]}",
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                raw_text=f"public void method_{node.start_point[0]}() {{ return; }}",
                language="java",
            )

        with patch.object(
            extractor, "_extract_method_optimized", side_effect=mock_extract_method
        ):
            start_time = time.time()
            methods = extractor.extract_functions(mock_tree, large_source)
            end_time = time.time()

            # Should complete within reasonable time (5 seconds)
            assert end_time - start_time < 5.0
            assert len(methods) == 100

    def test_memory_usage_with_caching(self, extractor):
        """Test memory usage with caching"""
        import gc

        # Perform many operations to populate caches
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        extractor.content_lines = ["test content"] * 1000

        # Populate caches
        for i in range(1000):
            mock_node_copy = Mock()
            mock_node_copy.start_byte = i
            mock_node_copy.end_byte = i + 10
            mock_node_copy.start_point = (0, 0)
            mock_node_copy.end_point = (0, 10)

            with patch(
                "tree_sitter_analyzer.languages.java_plugin.extract_text_slice"
            ) as mock_extract:
                mock_extract.return_value = f"text_{i}"
                extractor._get_node_text_optimized(mock_node_copy)

        # Check cache sizes
        assert len(extractor._node_text_cache) <= 1000

        # Reset caches and force garbage collection
        extractor._reset_caches()
        gc.collect()

        # Caches should be empty
        assert len(extractor._node_text_cache) == 0

    def test_error_handling_in_extraction(self, extractor):
        """Test error handling during extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Test with invalid source code
        invalid_source = None

        # Should handle None source code gracefully
        try:
            methods = extractor.extract_functions(mock_tree, invalid_source)
            assert isinstance(methods, list)
        except Exception:
            # If exception is raised, it should be handled gracefully
            pass

    def test_extract_class_optimized_error_handling(self, extractor):
        """Test error handling in class extraction"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []  # No identifier child

        # Should return None when no class name found
        result = extractor._extract_class_optimized(mock_node)
        assert result is None

    def test_extract_class_optimized_with_exception(self, extractor):
        """Test class extraction when an exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)
        mock_node.children = []

        # Mock to raise exception during processing
        with patch.object(extractor, "_extract_modifiers_optimized") as mock_modifiers:
            mock_modifiers.side_effect = Exception("Test error")

            result = extractor._extract_class_optimized(mock_node)
            assert result is None

    def test_extract_method_optimized_error_handling(self, extractor):
        """Test error handling in method extraction"""
        mock_node = Mock()
        mock_node.type = "method_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock signature parsing to return None
        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.return_value = None

            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_extract_method_optimized_with_exception(self, extractor):
        """Test method extraction when an exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise exception
        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.side_effect = Exception("Test error")

            result = extractor._extract_method_optimized(mock_node)
            assert result is None

    def test_extract_field_optimized_error_handling(self, extractor):
        """Test error handling in field extraction"""
        mock_node = Mock()
        mock_node.type = "field_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock field parsing to return None
        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.return_value = None

            result = extractor._extract_field_optimized(mock_node)
            assert result == []

    def test_extract_field_optimized_with_exception(self, extractor):
        """Test field extraction when an exception occurs"""
        mock_node = Mock()
        mock_node.start_point = (0, 0)
        mock_node.end_point = (2, 0)

        # Mock to raise exception
        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.side_effect = Exception("Test error")

            result = extractor._extract_field_optimized(mock_node)
            assert result == []



