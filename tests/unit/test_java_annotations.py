"""
Unit tests for Java annotation processing and framework detection.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 1: Annotation Processing (7 tests)
"""


class TestSpringAnnotations:
    """Tests for Spring Framework annotation detection."""

    def test_spring_rest_controller_annotation(self):
        """Test @RestController annotation detection."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
@RestController
@RequestMapping("/api")
public class UserController {
    @GetMapping("/users")
    public List<User> getUsers() {
        return null;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "UserController.java")

        assert result["errors"] is False
        assert len(result["classes"]) == 1

        user_class = result["classes"][0]
        assert user_class["name"] == "UserController"

        # Check annotations
        assert "annotations" in user_class
        assert len(user_class["annotations"]) >= 2

        # Check RestController annotation
        rest_ann = next(
            (a for a in user_class["annotations"] if a["name"] == "RestController"), None
        )
        assert rest_ann is not None
        assert rest_ann["type"] in ["spring-web", "spring"]

        # Check framework type detection
        assert "framework_type" in user_class
        assert user_class["framework_type"] in ["spring-web", "spring"]

        # Check method annotations
        assert len(user_class["methods"]) == 1
        get_users = user_class["methods"][0]
        assert "annotations" in get_users
        get_mapping = next((a for a in get_users["annotations"] if a["name"] == "GetMapping"), None)
        assert get_mapping is not None

    def test_spring_service_annotation(self):
        """Test @Service annotation detection."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
@Service
public class UserService {
    @Autowired
    private UserRepository userRepository;

    public void saveUser(User user) {
        userRepository.save(user);
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "UserService.java")

        user_service = result["classes"][0]
        assert user_service["name"] == "UserService"

        # Check @Service annotation
        service_ann = next((a for a in user_service["annotations"] if a["name"] == "Service"), None)
        assert service_ann is not None
        assert service_ann["type"] == "spring"

        # Check framework type
        assert user_service["framework_type"] == "spring"


class TestJPAAnnotations:
    """Tests for JPA annotation detection."""

    def test_jpa_entity_annotation(self):
        """Test @Entity annotation detection."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;
}
"""
        parser = JavaParser()
        result = parser.parse(code, "User.java")

        user_class = result["classes"][0]
        assert user_class["name"] == "User"

        # Check @Entity annotation
        entity_ann = next((a for a in user_class["annotations"] if a["name"] == "Entity"), None)
        assert entity_ann is not None
        assert entity_ann["type"] == "jpa"

        # Check @Table annotation
        table_ann = next((a for a in user_class["annotations"] if a["name"] == "Table"), None)
        assert table_ann is not None
        assert table_ann["type"] == "jpa"

        # Check framework type
        assert user_class["framework_type"] == "jpa"


class TestLombokAnnotations:
    """Tests for Lombok annotation detection."""

    def test_lombok_data_annotation(self):
        """Test @Data annotation detection."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
@Data
@Builder
public class UserDTO {
    private String name;
    private String email;
}
"""
        parser = JavaParser()
        result = parser.parse(code, "UserDTO.java")

        user_dto = result["classes"][0]
        assert user_dto["name"] == "UserDTO"

        # Check @Data annotation
        data_ann = next((a for a in user_dto["annotations"] if a["name"] == "Data"), None)
        assert data_ann is not None
        assert data_ann["type"] == "lombok"

        # Check @Builder annotation
        builder_ann = next((a for a in user_dto["annotations"] if a["name"] == "Builder"), None)
        assert builder_ann is not None
        assert builder_ann["type"] == "lombok"

        # Check framework type
        assert user_dto["framework_type"] == "lombok"


class TestAnnotationArguments:
    """Tests for annotation with arguments."""

    def test_request_mapping_with_value(self):
        """Test @RequestMapping with value argument."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
@RestController
@RequestMapping("/api/v1")
public class ApiController {
    @PostMapping(value = "/users", produces = "application/json")
    public User createUser(@RequestBody User user) {
        return user;
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "ApiController.java")

        api_class = result["classes"][0]

        # Check @RequestMapping with arguments
        req_mapping = next(
            (a for a in api_class["annotations"] if a["name"] == "RequestMapping"), None
        )
        assert req_mapping is not None
        assert "arguments" in req_mapping

        # Check method annotation with arguments
        create_user = api_class["methods"][0]
        post_mapping = next(
            (a for a in create_user["annotations"] if a["name"] == "PostMapping"), None
        )
        assert post_mapping is not None
        assert "arguments" in post_mapping


class TestFrameworkDetection:
    """Tests for framework type detection logic."""

    def test_framework_type_detection_priority(self):
        """Test framework type priority: spring-web > spring > jpa > lombok."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        # Test 1: spring-web wins
        code1 = """
@RestController
@Service
public class Mixed1 {}
"""
        result1 = JavaParser().parse(code1, "Mixed1.java")
        assert result1["classes"][0]["framework_type"] == "spring-web"

        # Test 2: spring wins over jpa
        code2 = """
@Service
@Entity
public class Mixed2 {}
"""
        result2 = JavaParser().parse(code2, "Mixed2.java")
        assert result2["classes"][0]["framework_type"] == "spring"

        # Test 3: jpa wins over lombok
        code3 = """
@Entity
@Data
public class Mixed3 {}
"""
        result3 = JavaParser().parse(code3, "Mixed3.java")
        assert result3["classes"][0]["framework_type"] == "jpa"

    def test_mixed_annotations(self):
        """Test class with annotations from multiple frameworks."""
        from tree_sitter_analyzer_v2.languages import JavaParser

        code = """
@RestController
@RequestMapping("/api")
public class UserController {
    @Autowired
    private UserService userService;

    @GetMapping("/users")
    public List<User> getUsers() {
        return userService.findAll();
    }

    @PostMapping("/users")
    public User createUser(@RequestBody User user) {
        return userService.save(user);
    }
}
"""
        parser = JavaParser()
        result = parser.parse(code, "UserController.java")

        controller = result["classes"][0]

        # Should have multiple annotations
        assert len(controller["annotations"]) >= 2

        # Framework type should be spring-web (highest priority)
        assert controller["framework_type"] == "spring-web"

        # Methods should have endpoint annotations
        assert len(controller["methods"]) == 2

        get_users = controller["methods"][0]
        assert any(a["name"] == "GetMapping" for a in get_users["annotations"])

        create_user = controller["methods"][1]
        assert any(a["name"] == "PostMapping" for a in create_user["annotations"])
