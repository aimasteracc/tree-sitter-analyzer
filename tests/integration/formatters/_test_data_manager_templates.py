"""Language templates used by the formatter test data generator."""


def get_language_templates() -> dict[str, dict[str, str]]:
    """Return source templates keyed by language name."""
    return {
        "python": _get_python_templates(),
        "java": _get_java_templates(),
        "javascript": _get_javascript_templates(),
        "typescript": _get_typescript_templates(),
    }


def _get_python_templates() -> dict[str, str]:
    return {
        "simple_class": """class {class_name}:
    def __init__(self):
        self.{field_name} = "value"

    def {method_name}(self):
        return self.{field_name}
""",
        "medium_class": """class {base_class}:
    def __init__(self):
        self.{field1} = "base_value"

class {class_name}({base_class}):
    def __init__(self):
        super().__init__()
        self.{field2} = "derived_value"

    def {method1}(self):
        return self.{field1}

    def {method2}(self):
        return self.{field2}
""",
        "complex_class": """class {class_name}:
    {fields}

    def __init__(self):
        pass

    {methods}
""",
        "method": '''def {method_name}(self):
        return "result"''',
        "field": '''self.{field_name} = "value"''',
    }


def _get_java_templates() -> dict[str, str]:
    return {
        "simple_class": """public class {class_name} {{
    private String {field_name};

    public {class_name}() {{
        this.{field_name} = "value";
    }}

    public String {method_name}() {{
        return this.{field_name};
    }}
}}""",
        "medium_class": """public class {base_class} {{
    protected String {field1};

    public {base_class}() {{
        this.{field1} = "base_value";
    }}
}}

public class {class_name} extends {base_class} {{
    private String {field2};

    public {class_name}() {{
        super();
        this.{field2} = "derived_value";
    }}

    public String {method1}() {{
        return this.{field1};
    }}

    public String {method2}() {{
        return this.{field2};
    }}
}}""",
        "complex_class": """public class {class_name} {{
    {fields}

    public {class_name}() {{
        // Constructor
    }}

    {methods}
}}""",
        "method": """public String {method_name}() {{
        return "result";
    }}""",
        "field": """private String {field_name};""",
    }


def _get_javascript_templates() -> dict[str, str]:
    return {
        "simple_class": """class {class_name} {{
    constructor() {{
        this.{field_name} = "value";
    }}

    {method_name}() {{
        return this.{field_name};
    }}
}}""",
        "medium_class": """class {base_class} {{
    constructor() {{
        this.{field1} = "base_value";
    }}
}}

class {class_name} extends {base_class} {{
    constructor() {{
        super();
        this.{field2} = "derived_value";
    }}

    {method1}() {{
        return this.{field1};
    }}

    {method2}() {{
        return this.{field2};
    }}
}}""",
        "complex_class": """class {class_name} {{
    constructor() {{
        {fields}
    }}

    {methods}
}}""",
        "method": """{method_name}() {{
        return "result";
    }}""",
        "field": """this.{field_name} = "value";""",
    }


def _get_typescript_templates() -> dict[str, str]:
    return {
        "simple_class": """class {class_name} {{
    private {field_name}: string;

    constructor() {{
        this.{field_name} = "value";
    }}

    public {method_name}(): string {{
        return this.{field_name};
    }}
}}""",
        "medium_class": """class {base_class} {{
    protected {field1}: string;

    constructor() {{
        this.{field1} = "base_value";
    }}
}}

class {class_name} extends {base_class} {{
    private {field2}: string;

    constructor() {{
        super();
        this.{field2} = "derived_value";
    }}

    public {method1}(): string {{
        return this.{field1};
    }}

    public {method2}(): string {{
        return this.{field2};
    }}
}}""",
        "complex_class": """class {class_name} {{
    {fields}

    constructor() {{
        // Constructor
    }}

    {methods}
}}""",
        "method": """public {method_name}(): string {{
        return "result";
    }}""",
        "field": """private {field_name}: string;""",
    }
