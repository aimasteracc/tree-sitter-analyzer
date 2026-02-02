"""
Unit tests for TypeScript decorator support.

Following TDD methodology:
1. RED: Write failing tests first
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Phase 2: Decorators (6 tests)
"""


class TestDecorators:
    """Tests for TypeScript decorator extraction."""

    def test_class_decorator_simple(self):
        """Test simple class decorator without arguments."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
@Component
class UserComponent {
    name: string;
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert cls["name"] == "UserComponent"
        assert "decorators" in cls
        assert len(cls["decorators"]) == 1
        assert cls["decorators"][0]["name"] == "Component"
        assert cls["decorators"][0].get("arguments") is None

    def test_class_decorator_with_arguments(self):
        """Test class decorator with arguments."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
@Component({
    selector: 'app-user',
    templateUrl: './user.component.html'
})
class UserComponent {
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert cls["name"] == "UserComponent"
        assert len(cls["decorators"]) == 1
        assert cls["decorators"][0]["name"] == "Component"
        # Arguments should be captured as raw text
        assert "arguments" in cls["decorators"][0]

    def test_method_decorator(self):
        """Test method decorator."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
class ApiController {
    @Get('/users')
    getUsers() {
        return [];
    }

    @Post('/users')
    @Auth()
    createUser() {
    }
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert len(cls["methods"]) == 2

        # getUsers method
        method1 = cls["methods"][0]
        assert method1["name"] == "getUsers"
        assert "decorators" in method1
        assert len(method1["decorators"]) == 1
        assert method1["decorators"][0]["name"] == "Get"

        # createUser method with multiple decorators
        method2 = cls["methods"][1]
        assert method2["name"] == "createUser"
        assert len(method2["decorators"]) == 2
        assert method2["decorators"][0]["name"] == "Post"
        assert method2["decorators"][1]["name"] == "Auth"

    def test_property_decorator(self):
        """Test property decorator."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
class User {
    @Column()
    name: string;

    @IsEmail()
    email: string;
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert "properties" in cls
        assert len(cls["properties"]) == 2

        # name property
        prop1 = cls["properties"][0]
        assert prop1["name"] == "name"
        assert "decorators" in prop1
        assert len(prop1["decorators"]) == 1
        assert prop1["decorators"][0]["name"] == "Column"

        # email property
        prop2 = cls["properties"][1]
        assert prop2["name"] == "email"
        assert len(prop2["decorators"]) == 1
        assert prop2["decorators"][0]["name"] == "IsEmail"

    def test_parameter_decorator(self):
        """Test parameter decorator."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
class Service {
    constructor(@Inject('TOKEN') private dependency: any) {
    }

    process(@Body() data: any, @Query('id') id: string) {
    }
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["classes"]) == 1

        cls = result["classes"][0]
        assert len(cls["methods"]) == 2

        # constructor
        constructor = cls["methods"][0]
        assert constructor["name"] == "constructor"
        assert "parameters" in constructor
        assert len(constructor["parameters"]) >= 1

        # process method
        process_method = cls["methods"][1]
        assert process_method["name"] == "process"

    def test_framework_detection_angular(self):
        """Test Angular framework detection from decorators."""
        from tree_sitter_analyzer_v2.languages import TypeScriptParser

        code = """
@Component({
    selector: 'app-root'
})
class AppComponent {
}

@Injectable()
class UserService {
}
"""
        parser = TypeScriptParser()
        result = parser.parse(code, "test.ts")

        assert len(result["classes"]) == 2

        # AppComponent
        cls1 = result["classes"][0]
        assert cls1["name"] == "AppComponent"
        assert "framework_type" in cls1
        assert cls1["framework_type"] == "angular"

        # UserService
        cls2 = result["classes"][1]
        assert cls2["name"] == "UserService"
        assert cls2["framework_type"] == "angular"
