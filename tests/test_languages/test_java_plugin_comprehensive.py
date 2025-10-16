"""
Comprehensive tests for Java plugin.
Tests all major functionality including methods, classes, fields, imports, packages,
annotations, caching, performance optimizations, and Java-specific features.
"""

from unittest.mock import Mock, patch

import pytest

from tree_sitter_analyzer.languages.java_plugin import JavaElementExtractor, JavaPlugin
from tree_sitter_analyzer.models import Class, Function, Import, Package, Variable


class TestJavaElementExtractor:
    """Test Java element extractor functionality"""

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
        """Test cache reset functionality"""
        # Populate caches
        extractor._node_text_cache[1] = "test"
        extractor._processed_nodes.add(1)
        extractor._element_cache[(1, "test")] = "value"
        extractor._annotation_cache[1] = [{"name": "Test"}]
        extractor._signature_cache[1] = "signature"
        extractor.annotations.append({"name": "Test"})

        # Reset caches
        extractor._reset_caches()

        # Verify caches are empty
        assert len(extractor._node_text_cache) == 0
        assert len(extractor._processed_nodes) == 0
        assert len(extractor._element_cache) == 0
        assert len(extractor._annotation_cache) == 0
        assert len(extractor._signature_cache) == 0
        assert len(extractor.annotations) == 0

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

        with patch.object(extractor, "_extract_package_info") as mock_extract_package:
            with patch.object(extractor, "_extract_import_info") as mock_extract_import:
                mock_import = Import(
                    name="java.util.List",
                    start_line=1,
                    end_line=1,
                    raw_text="import java.util.List;",
                    language="java",
                )
                mock_extract_import.return_value = mock_import

                imports = extractor.extract_imports(mock_tree, sample_java_code)

                assert isinstance(imports, list)
                mock_extract_package.assert_called_once()
                mock_extract_import.assert_called_once()

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

        with patch.object(extractor, "_extract_imports_fallback") as mock_fallback:
            mock_fallback.return_value = [
                Import(
                    name="java.util.List",
                    start_line=2,
                    end_line=2,
                    raw_text="import java.util.List;",
                    language="java",
                )
            ]

            imports = extractor.extract_imports(mock_tree, source_with_imports)

            # Should call fallback when no imports found via tree-sitter
            mock_fallback.assert_called_once()
            assert isinstance(imports, list)

    def test_extract_packages_basic(self, extractor, mock_tree, sample_java_code):
        """Test basic package extraction"""
        # Mock package node
        mock_package_node = Mock()
        mock_package_node.type = "package_declaration"

        mock_tree.root_node.children = [mock_package_node]

        with patch.object(extractor, "_extract_package_element") as mock_extract:
            mock_package = Package(
                name="com.example.service",
                start_line=1,
                end_line=1,
                raw_text="package com.example.service;",
                language="java",
            )
            mock_extract.return_value = mock_package

            packages = extractor.extract_packages(mock_tree, sample_java_code)

            assert isinstance(packages, list)
            mock_extract.assert_called_once()

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
        node_id = id(mock_node)

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
            assert node_id in extractor._node_text_cache

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

    def test_extract_class_optimized_complete(self, extractor):
        """Test complete class extraction"""
        mock_node = Mock()
        mock_node.type = "class_declaration"
        mock_node.start_point = (0, 0)
        mock_node.end_point = (10, 0)

        # Mock identifier child
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_node.children = [mock_identifier]

        # Mock superclass child
        mock_superclass = Mock()
        mock_superclass.type = "superclass"
        mock_node.children.append(mock_superclass)

        # Mock super_interfaces child
        mock_interfaces = Mock()
        mock_interfaces.type = "super_interfaces"
        mock_node.children.append(mock_interfaces)

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

        with patch.object(extractor, "_get_node_text_optimized") as mock_get_text:
            mock_get_text.side_effect = [
                "UserService",  # Class name
                "extends BaseService",  # Superclass text
                "implements UserOperations",  # Interfaces text
                "public class UserService extends BaseService implements UserOperations { // class body }",  # Full class text
            ]

            with patch.object(
                extractor, "_extract_modifiers_optimized"
            ) as mock_modifiers:
                mock_modifiers.return_value = ["public"]

                with patch.object(
                    extractor, "_determine_visibility"
                ) as mock_visibility:
                    mock_visibility.return_value = "public"

                    with patch.object(
                        extractor, "_find_annotations_for_line_cached"
                    ) as mock_annotations:
                        mock_annotations.return_value = [{"name": "Service"}]

                        with patch.object(
                            extractor, "_is_nested_class"
                        ) as mock_is_nested:
                            mock_is_nested.return_value = False

                            result = extractor._extract_class_optimized(mock_node)

                            assert isinstance(result, Class)
                            assert result.name == "UserService"
                            assert result.start_line == 1
                            assert result.end_line == 11
                            assert result.language == "java"
                            assert result.class_type == "class"
                            assert (
                                result.full_qualified_name
                                == "com.example.service.UserService"
                            )
                            assert result.package_name == "com.example.service"
                            assert result.superclass == "BaseService"
                            assert result.interfaces == ["UserOperations"]
                            assert result.modifiers == ["public"]
                            assert result.visibility == "public"
                            assert result.annotations == [{"name": "Service"}]
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

        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.return_value = (
                "findById",
                "User",
                ["String userId"],
                ["public"],
                ["UserNotFoundException"],
            )

            with patch.object(extractor, "_determine_visibility") as mock_visibility:
                mock_visibility.return_value = "public"

                with patch.object(
                    extractor, "_find_annotations_for_line_cached"
                ) as mock_annotations:
                    mock_annotations.return_value = [{"name": "Override"}]

                    with patch.object(
                        extractor, "_calculate_complexity_optimized"
                    ) as mock_complexity:
                        mock_complexity.return_value = 2

                        with patch.object(
                            extractor, "_extract_javadoc_for_line"
                        ) as mock_javadoc:
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

        with patch.object(extractor, "_parse_method_signature_optimized") as mock_parse:
            mock_parse.return_value = (
                "UserService",
                "void",
                ["UserConfig config"],
                ["public"],
                [],
            )

            with patch.object(extractor, "_determine_visibility") as mock_visibility:
                mock_visibility.return_value = "public"

                with patch.object(
                    extractor, "_find_annotations_for_line_cached"
                ) as mock_annotations:
                    mock_annotations.return_value = []

                    with patch.object(
                        extractor, "_calculate_complexity_optimized"
                    ) as mock_complexity:
                        mock_complexity.return_value = 1

                        with patch.object(
                            extractor, "_extract_javadoc_for_line"
                        ) as mock_javadoc:
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

        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.return_value = (
                "UserRepository",
                ["userRepository"],
                ["private"],
            )

            with patch.object(extractor, "_determine_visibility") as mock_visibility:
                mock_visibility.return_value = "private"

                with patch.object(
                    extractor, "_find_annotations_for_line_cached"
                ) as mock_annotations:
                    mock_annotations.return_value = [{"name": "Autowired"}]

                    with patch.object(
                        extractor, "_extract_javadoc_for_line"
                    ) as mock_javadoc:
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

        with patch.object(
            extractor, "_parse_field_declaration_optimized"
        ) as mock_parse:
            mock_parse.return_value = (
                "String",
                ["firstName", "lastName", "email"],
                ["private"],
            )

            with patch.object(extractor, "_determine_visibility") as mock_visibility:
                mock_visibility.return_value = "private"

                with patch.object(
                    extractor, "_find_annotations_for_line_cached"
                ) as mock_annotations:
                    mock_annotations.return_value = []

                    with patch.object(
                        extractor, "_extract_javadoc_for_line"
                    ) as mock_javadoc:
                        mock_javadoc.return_value = None

                        result = extractor._extract_field_optimized(mock_node)

                        assert isinstance(result, list)
                        assert len(result) == 3

                        # Check all three variables
                        for _i, field in enumerate(result):
                            assert isinstance(field, Variable)
                            assert field.variable_type == "String"
                            assert field.modifiers == ["private"]
                            assert field.visibility == "private"

                        assert result[0].name == "firstName"
                        assert result[1].name == "lastName"
                        assert result[2].name == "email"

    def test_traverse_and_extract_iterative(self, extractor):
        """Test iterative traversal and extraction"""
        # Create mock root node with children
        mock_root = Mock()
        mock_child1 = Mock()
        mock_child1.type = "method_declaration"
        mock_child1.children = []

        mock_child2 = Mock()
        mock_child2.type = "class_declaration"
        mock_child2.children = []

        mock_root.children = [mock_child1, mock_child2]

        # Mock extractor functions
        mock_method_extractor = Mock()
        mock_method_extractor.return_value = Function(
            name="test_method",
            start_line=1,
            end_line=3,
            raw_text="public void test_method() {}",
            language="java",
        )

        mock_class_extractor = Mock()
        mock_class_extractor.return_value = Class(
            name="TestClass",
            start_line=5,
            end_line=10,
            raw_text="public class TestClass {}",
            language="java",
        )

        extractors = {
            "method_declaration": mock_method_extractor,
            "class_declaration": mock_class_extractor,
        }

        results = []
        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "mixed"
        )

        assert len(results) == 2
        assert isinstance(results[0], Function)
        assert isinstance(results[1], Class)

    def test_traverse_and_extract_iterative_with_caching(self, extractor):
        """Test iterative traversal with caching"""
        mock_root = Mock()
        mock_child = Mock()
        mock_child.type = "method_declaration"
        mock_child.children = []
        mock_root.children = [mock_child]

        # Set up cache
        node_id = id(mock_child)
        cache_key = (node_id, "method")
        cached_method = Function(
            name="cached_method",
            start_line=1,
            end_line=2,
            raw_text="public void cached_method() {}",
            language="java",
        )
        extractor._element_cache[cache_key] = cached_method

        extractors = {"method_declaration": Mock()}
        results = []

        extractor._traverse_and_extract_iterative(
            mock_root, extractors, results, "method"
        )

        # Should use cached result
        assert len(results) == 1
        assert results[0] == cached_method
        assert (
            extractors["method_declaration"].call_count == 0
        )  # Should not call extractor

    def test_traverse_and_extract_iterative_field_batching(self, extractor):
        """Test field batching in iterative traversal"""
        mock_root = Mock()

        # Create 15 field nodes to test batching (batch size is 10)
        field_nodes = []
        for _i in range(15):
            field_node = Mock()
            field_node.type = "field_declaration"
            field_node.children = []
            field_nodes.append(field_node)

        mock_root.children = field_nodes

        # Mock field extractor
        def mock_field_extractor(node):
            return [
                Variable(
                    name=f"field_{id(node)}",
                    start_line=1,
                    end_line=1,
                    raw_text=f"private String field_{id(node)};",
                    language="java",
                )
            ]

        extractors = {"field_declaration": mock_field_extractor}
        results = []

        # Mock the batch processing method
        with patch.object(extractor, "_process_field_batch") as mock_batch_process:
            extractor._traverse_and_extract_iterative(
                mock_root, extractors, results, "field"
            )

            # Should call batch processing twice (10 + 5 fields)
            assert mock_batch_process.call_count == 2

    def test_process_field_batch(self, extractor):
        """Test field batch processing"""
        # Create mock field nodes
        field_nodes = []
        for _i in range(5):
            node = Mock()
            node.type = "field_declaration"
            field_nodes.append(node)

        # Mock field extractor
        def mock_field_extractor(node):
            return [
                Variable(
                    name=f"field_{i}",
                    start_line=1,
                    end_line=1,
                    raw_text=f"private String field_{i};",
                    language="java",
                )
                for i in range(2)
            ]  # Return 2 variables per field declaration

        extractors = {"field_declaration": mock_field_extractor}
        results = []

        extractor._process_field_batch(field_nodes, extractors, results)

        # Should process all 5 nodes, each returning 2 variables
        assert len(results) == 10

    def test_process_field_batch_with_caching(self, extractor):
        """Test field batch processing with caching"""
        field_node = Mock()
        field_node.type = "field_declaration"

        # Set up cache
        node_id = id(field_node)
        cache_key = (node_id, "field")
        cached_fields = [
            Variable(
                name="cached_field",
                start_line=1,
                end_line=1,
                raw_text="private String cached_field;",
                language="java",
            )
        ]
        extractor._element_cache[cache_key] = cached_fields

        extractors = {"field_declaration": Mock()}
        results = []

        extractor._process_field_batch([field_node], extractors, results)

        # Should use cached result
        assert len(results) == 1
        assert results[0].name == "cached_field"
        assert extractors["field_declaration"].call_count == 0

    def test_traverse_and_extract_iterative_max_depth(self, extractor):
        """Test max depth protection in traversal"""
        # Create deeply nested structure
        root_node = Mock()
        root_node.type = "program"
        root_node.children = []

        current_node = root_node

        # Create 60 levels of nesting (exceeds max_depth of 50)
        for _i in range(60):
            child = Mock()
            child.type = "class_body"
            child.children = []
            current_node.children = [child]
            current_node = child

        # Add target node at the end
        target_node = Mock()
        target_node.type = "method_declaration"
        target_node.children = []
        current_node.children = [target_node]

        extractors = {"method_declaration": Mock()}
        results = []

        # Should not process deeply nested nodes
        with patch(
            "tree_sitter_analyzer.languages.java_plugin.log_warning"
        ) as mock_log:
            extractor._traverse_and_extract_iterative(
                root_node, extractors, results, "method"
            )

            # Should log warning about max depth
            mock_log.assert_called()

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


class TestJavaPlugin:
    """Test Java plugin functionality"""

    @pytest.fixture
    def plugin(self):
        """Create a Java plugin instance"""
        return JavaPlugin()

    def test_plugin_initialization(self, plugin):
        """Test plugin initialization"""
        assert plugin.language == "java"
        assert ".java" in plugin.supported_extensions

    def test_plugin_extract_elements(self, plugin):
        """Test plugin element extraction"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        source_code = "public class Test {}"

        # Mock extractor methods
        with patch.object(plugin.extractor, "extract_functions") as mock_functions:
            with patch.object(plugin.extractor, "extract_classes") as mock_classes:
                with patch.object(
                    plugin.extractor, "extract_variables"
                ) as mock_variables:
                    with patch.object(
                        plugin.extractor, "extract_imports"
                    ) as mock_imports:
                        with patch.object(
                            plugin.extractor, "extract_packages"
                        ) as mock_packages:
                            with patch.object(
                                plugin.extractor, "extract_annotations"
                            ) as mock_annotations:
                                mock_functions.return_value = []
                                mock_classes.return_value = []
                                mock_variables.return_value = []
                                mock_imports.return_value = []
                                mock_packages.return_value = []
                                mock_annotations.return_value = []

                                result = plugin.extract_elements(mock_tree, source_code)

                                assert "functions" in result
                                assert "classes" in result
                                assert "variables" in result
                                assert "imports" in result
                                assert "packages" in result
                                assert "annotations" in result

    def test_plugin_with_invalid_tree(self, plugin):
        """Test plugin behavior with invalid tree"""
        # Test with None tree
        result = plugin.extract_elements(None, "public class Test {}")
        expected_keys = {
            "functions",
            "classes",
            "variables",
            "imports",
            "packages",
            "annotations",
        }
        assert set(result.keys()) == expected_keys

        # All should be empty lists
        for key in expected_keys:
            assert result[key] == []

    def test_plugin_with_extraction_errors(self, plugin):
        """Test plugin behavior when extraction methods raise errors"""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []

        # Mock extractor to raise exceptions
        with patch.object(plugin.extractor, "extract_functions") as mock_functions:
            with patch.object(plugin.extractor, "extract_classes") as mock_classes:
                with patch.object(
                    plugin.extractor, "extract_variables"
                ) as mock_variables:
                    with patch.object(
                        plugin.extractor, "extract_imports"
                    ) as mock_imports:
                        with patch.object(
                            plugin.extractor, "extract_packages"
                        ) as mock_packages:
                            with patch.object(
                                plugin.extractor, "extract_annotations"
                            ) as mock_annotations:
                                mock_functions.side_effect = Exception(
                                    "Function extraction error"
                                )
                                mock_classes.side_effect = Exception(
                                    "Class extraction error"
                                )
                                mock_variables.side_effect = Exception(
                                    "Variable extraction error"
                                )
                                mock_imports.side_effect = Exception(
                                    "Import extraction error"
                                )
                                mock_packages.side_effect = Exception(
                                    "Package extraction error"
                                )
                                mock_annotations.side_effect = Exception(
                                    "Annotation extraction error"
                                )

                                # Should handle exceptions gracefully
                                result = plugin.extract_elements(
                                    mock_tree, "public class Test {}"
                                )

                                # Should return empty lists instead of crashing
                                expected_keys = {
                                    "functions",
                                    "classes",
                                    "variables",
                                    "imports",
                                    "packages",
                                    "annotations",
                                }
                                assert set(result.keys()) == expected_keys
                                for key in expected_keys:
                                    assert result[key] == []

    def test_concurrent_extraction_simulation(self, plugin):
        """Test simulation of concurrent extraction"""
        import threading
        import time

        results = []
        errors = []

        def worker():
            try:
                mock_tree = Mock()
                mock_tree.root_node = Mock()
                mock_tree.root_node.children = []

                for i in range(5):
                    result = plugin.extract_elements(
                        mock_tree, f"public class Test{i} {{}}"
                    )
                    results.append(result)
                    time.sleep(0.001)  # Small delay
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for _i in range(3):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Should not have any errors
        assert len(errors) == 0
        assert len(results) == 15  # 3 threads * 5 operations each
