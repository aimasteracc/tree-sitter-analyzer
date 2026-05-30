"""Java element extractor tests."""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor


class TestJavaElementExtractor:
    """Test Java element extractor — core functionality"""

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

    def test_initialization(self, extractor):
        """Test extractor initialization"""
        assert extractor.current_package == ""
        assert extractor.current_file == ""
        assert extractor.source_code == ""
        assert extractor.content_lines == []
        assert extractor.imports == []
        assert isinstance(extractor._node_text_cache, dict)
        assert isinstance(extractor._processed_nodes, set)
        assert isinstance(extractor._element_cache, dict)
        assert extractor._file_encoding is None
        assert isinstance(extractor._annotation_cache, dict)
        assert isinstance(extractor._signature_cache, dict)
        assert isinstance(extractor.annotations, list)

    def test_reset_caches(self, extractor):
        """Test cache reset functionality.

        _reset_caches() clears performance caches (node-text, processed-nodes,
        element-cache, annotation-cache, signature-cache) but deliberately
        preserves self.annotations — that list is extracted data, not a cache,
        and must survive across calls so annotations populated by
        extract_annotations() remain available during extract_classes().
        """
        # Populate caches
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"
        extractor._annotation_cache[1] = [{"name": "Test"}]
        extractor._signature_cache[1] = "signature"
        extractor.annotations.append({"name": "Test"})

        # Reset caches
        extractor._reset_caches()

        # Verify performance caches are empty
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._annotation_cache) == 0
        assert len(extractor._signature_cache) == 0
        # annotations are preserved — they are extracted data, not a cache
        assert len(extractor.annotations) == 1

    def test_extract_functions_basic(self, extractor, mock_tree, sample_java_code):
        """Test basic method extraction"""
        # Mock tree structure for method extraction
        mock_method_node = Mock()
        mock_method_node.type = "method_declaration"
        mock_method_node.start_point = (10, 0)
        mock_method_node.end_point = (15, 0)
        mock_method_node.children = []

        mock_tree.root_node.children = [mock_method_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            functions = extractor.extract_functions(mock_tree, sample_java_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(functions, list)

    def test_extract_classes_basic(self, extractor, mock_tree, sample_java_code):
        """Test basic class extraction"""
        # Mock tree structure for class extraction
        mock_class_node = Mock()
        mock_class_node.type = "class_declaration"
        mock_class_node.start_point = (5, 0)
        mock_class_node.end_point = (25, 0)
        mock_class_node.children = []

        mock_tree.root_node.children = [mock_class_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            classes = extractor.extract_classes(mock_tree, sample_java_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(classes, list)

    def test_extract_classes_with_package_extraction(
        self, extractor, mock_tree, sample_java_code
    ):
        """Test class extraction with automatic package extraction"""
        # Mock package node
        mock_package_node = Mock()
        mock_package_node.type = "package_declaration"

        # Mock class node
        mock_class_node = Mock()
        mock_class_node.type = "class_declaration"
        mock_class_node.children = []

        mock_tree.root_node.children = [mock_package_node, mock_class_node]

        # Mock package extraction
        with patch.object(
            extractor, "_extract_package_from_tree"
        ) as mock_extract_package:
            with patch.object(
                extractor, "_traverse_and_extract_iterative"
            ) as mock_traverse:
                extractor.current_package = ""  # Ensure package is empty

                extractor.extract_classes(mock_tree, sample_java_code)

                # Should call package extraction when current_package is empty
                mock_extract_package.assert_called_once_with(mock_tree)
                mock_traverse.assert_called_once()

    def test_extract_variables_basic(self, extractor, mock_tree, sample_java_code):
        """Test basic field extraction"""
        # Mock tree structure for field extraction
        mock_field_node = Mock()
        mock_field_node.type = "field_declaration"
        mock_field_node.start_point = (1, 0)
        mock_field_node.end_point = (1, 20)
        mock_field_node.children = []

        mock_tree.root_node.children = [mock_field_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            variables = extractor.extract_variables(mock_tree, sample_java_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(variables, list)

    def test_extract_imports_basic(self, extractor, mock_tree, sample_java_code):
        """Test basic import extraction"""
        # Mock package and import nodes
        mock_package_node = Mock()
        mock_package_node.type = "package_declaration"

        mock_import_node = Mock()
        mock_import_node.type = "import_declaration"

        mock_class_node = Mock()
        mock_class_node.type = "class_declaration"

        mock_tree.root_node.children = [
            mock_package_node,
            mock_import_node,
            mock_class_node,
        ]

        # extract_imports delegates to standalone helper; verify it returns a list
        imports = extractor.extract_imports(mock_tree, sample_java_code)
        assert isinstance(imports, list)

    def test_extract_imports_with_fallback(self, extractor, mock_tree):
        """Test import extraction with regex fallback"""
        # Mock tree with no import nodes
        mock_tree.root_node.children = []

        # Source code with imports
        source_with_imports = """
        import java.util.List;
        import static java.util.Collections.emptyList;
        import javax.annotation.*;
        """

        imports = extractor.extract_imports(mock_tree, source_with_imports)

        # Should return imports via regex fallback when tree-sitter finds none
        assert isinstance(imports, list)

    def test_extract_packages_basic(self, extractor, mock_tree, sample_java_code):
        """Test basic package extraction"""
        # Mock package node
        mock_package_node = Mock()
        mock_package_node.type = "package_declaration"
        mock_package_node.children = []

        mock_tree.root_node.children = [mock_package_node]

        packages = extractor.extract_packages(mock_tree, sample_java_code)

        assert isinstance(packages, list)

    def test_extract_annotations_basic(self, extractor, mock_tree, sample_java_code):
        """Test basic annotation extraction"""
        # Mock annotation node
        mock_annotation_node = Mock()
        mock_annotation_node.type = "annotation"
        mock_annotation_node.children = []

        mock_tree.root_node.children = [mock_annotation_node]

        # Mock the extraction method
        with patch.object(
            extractor, "_traverse_and_extract_iterative"
        ) as mock_traverse:
            annotations = extractor.extract_annotations(mock_tree, sample_java_code)

            # Verify traversal was called
            mock_traverse.assert_called_once()
            assert isinstance(annotations, list)

    def test_get_node_text_optimized_caching(self, extractor):
        """Test node text extraction with caching"""
        # Create mock node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10

        # Set up extractor state
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        # Mock extract_text_slice to return test text
        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.return_value = "test text"

            # First call should extract and cache
            result1 = extractor._get_node_text_optimized(mock_node)
            assert result1 == "test text"
            # Cache uses (start_byte, end_byte) tuple as key
            assert (
                mock_node.start_byte,
                mock_node.end_byte,
            ) in extractor._node_text_cache

            # Second call should use cache
            result2 = extractor._get_node_text_optimized(mock_node)
            assert result2 == "test text"
            assert mock_extract.call_count == 1  # Should only be called once

    def test_get_node_text_optimized_fallback(self, extractor):
        """Test node text extraction fallback mechanism"""
        # Create mock node
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10
        mock_node.start_point = (0, 0)
        mock_node.end_point = (0, 10)

        # Set up extractor state
        extractor.content_lines = ["test content line"]
        extractor._file_encoding = "utf-8"

        # Mock extract_text_slice to raise exception
        with patch(
            "tree_sitter_analyzer.languages.java_plugin.extract_text_slice"
        ) as mock_extract:
            mock_extract.side_effect = Exception("Test error")

            # Should fallback to simple extraction
            result = extractor._get_node_text_optimized(mock_node)
            assert result == "test conte"  # Characters 0-10 from first line
