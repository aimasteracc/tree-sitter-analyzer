"""
API Endpoint Discovery Module

Discovers and catalogs API endpoints from web frameworks:
- Flask: @app.route, @bp.route, Blueprint()
- FastAPI: @app.get, @app.post, @router.*, APIRouter()
- Django: urlpatterns, @api_view, path(), re_path()
- Express: app.get, app.post, router.*, express.Router
- Spring: @GetMapping, @PostMapping, @RequestMapping
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class FrameworkType(Enum):
    """Types of web frameworks that can be detected."""

    FLASK = "flask"
    FASTAPI = "fastapi"
    DJANGO = "django"
    EXPRESS = "express"
    SPRING = "spring"


@dataclass(frozen=True)
class ApiEndpoint:
    """A discovered API endpoint."""

    framework: FrameworkType
    path: str
    methods: tuple[str, ...]
    handler: str
    file: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "framework": self.framework.value,
            "path": self.path,
            "methods": list(self.methods),
            "handler": self.handler,
            "file": self.file,
            "line": self.line,
        }


def discover_endpoints(
    project_root: str,
    frameworks: set[FrameworkType] | None = None,
) -> list[ApiEndpoint]:
    """Discover API endpoints in a project.

    Args:
        project_root: Root directory of the project
        frameworks: Optional set of frameworks to detect. If None, detect all.

    Returns:
        List of discovered API endpoints
    """
    if frameworks is None:
        frameworks = set(FrameworkType)

    endpoints: list[ApiEndpoint] = []
    root_path = Path(project_root)

    # Python files for Flask/FastAPI/Django
    for py_file in root_path.rglob("*.py"):
        try:
            if FrameworkType.FLASK in frameworks:
                flask_endpoints = _detect_flask_routes(str(py_file))
                endpoints.extend(flask_endpoints)

            if FrameworkType.FASTAPI in frameworks:
                fastapi_endpoints = _detect_fastapi_endpoints(str(py_file))
                endpoints.extend(fastapi_endpoints)

            if FrameworkType.DJANGO in frameworks:
                django_endpoints = _detect_django_urls(str(py_file))
                endpoints.extend(django_endpoints)

        except Exception:
            # Skip files that can't be parsed
            continue

    # JavaScript/TypeScript files for Express
    for js_file in root_path.rglob("*.js"):
        try:
            if FrameworkType.EXPRESS in frameworks:
                express_endpoints = _detect_express_routes(str(js_file))
                endpoints.extend(express_endpoints)
        except Exception:
            continue

    for ts_file in root_path.rglob("*.ts"):
        try:
            if FrameworkType.EXPRESS in frameworks:
                express_endpoints = _detect_express_routes(str(ts_file))
                endpoints.extend(express_endpoints)
        except Exception:
            continue

    # Java files for Spring Boot
    for java_file in root_path.rglob("*.java"):
        try:
            if FrameworkType.SPRING in frameworks:
                spring_endpoints = _detect_spring_endpoints(str(java_file))
                endpoints.extend(spring_endpoints)
        except Exception:
            continue

    return endpoints


def _detect_flask_routes(file_path: str) -> list[ApiEndpoint]:
    """Detect Flask routes using decorator and function analysis.

    Flask patterns:
    - @app.route("/path")
    - @app.get("/path") - but NOT if FastAPI is imported
    - @app.post("/path") - but NOT if FastAPI is imported
    - @bp.route("/path")  # Blueprint
    - @router.route("/path"), @router.get("/path")  # Common router naming
    """
    endpoints: list[ApiEndpoint] = []

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return endpoints

    # Check if FastAPI is imported (to avoid false positives)
    has_fastapi = "from fastapi" in content or "import fastapi" in content
    has_flask = "from flask" in content or "import flask" in content

    if has_fastapi:
        # Skip Flask detection in FastAPI files
        return endpoints

    lines = content.split("\n")

    for i, line in enumerate(lines):
        line_stripped = line.strip()

        # Match @app.route("/path"), @bp.route("/path")
        if "@app.route(" in line or "@bp.route(" in line:
            path = _extract_route_path(line)
            methods = _extract_http_methods(line, default=("GET",))
            handler = _find_handler_function(lines, i)

            if path and handler:
                endpoints.append(ApiEndpoint(
                    framework=FrameworkType.FLASK,
                    path=path,
                    methods=methods,
                    handler=handler,
                    file=file_path,
                    line=i + 1,
                ))

        # Match @app.get/post/etc (Flask 2.0+)
        elif "@app." in line and has_flask:
            for method in ("get", "post", "put", "delete", "patch", "options", "head"):
                pattern = f"@app.{method}("
                if pattern in line:
                    path = _extract_route_path(line)
                    http_method = method.upper()
                    handler = _find_handler_function(lines, i)

                    if path and handler:
                        endpoints.append(ApiEndpoint(
                            framework=FrameworkType.FLASK,
                            path=path,
                            methods=(http_method,),
                            handler=handler,
                            file=file_path,
                            line=i + 1,
                        ))
                    break

        # Match @bp.get/post/etc or @router.get/post/etc
        elif ("@bp." in line or "@router." in line):
            for method in ("get", "post", "put", "delete", "patch", "options", "head"):
                pattern = f"@bp.{method}("
                if pattern in line or f"@router.{method}(" in line:
                    path = _extract_route_path(line)
                    http_method = method.upper()
                    handler = _find_handler_function(lines, i)

                    if path and handler:
                        endpoints.append(ApiEndpoint(
                            framework=FrameworkType.FLASK,
                            path=path,
                            methods=(http_method,),
                            handler=handler,
                            file=file_path,
                            line=i + 1,
                        ))
                    break

    return endpoints


def _detect_fastapi_endpoints(file_path: str) -> list[ApiEndpoint]:
    """Detect FastAPI endpoints using decorator analysis.

    FastAPI patterns:
    - @app.get("/path")
    - @app.post("/path")
    - @router.get("/path")
    - @router.post("/path")
    - APIRouter()
    """
    endpoints: list[ApiEndpoint] = []

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return endpoints

    # Check if FastAPI is imported
    has_fastapi = "from fastapi" in content or "import fastapi" in content

    if not has_fastapi:
        return endpoints

    lines = content.split("\n")

    for i, line in enumerate(lines):
        for method in ("get", "post", "put", "delete", "patch", "options", "head", "trace"):
            # Check if the line contains the decorator pattern (handle leading spaces)
            if f"@app.{method}(" in line or f"@router.{method}(" in line or f"@app.{method}(\"" in line:
                path = _extract_route_path(line)
                http_method = method.upper()
                handler = _find_handler_function(lines, i)

                if path and handler:
                    endpoints.append(ApiEndpoint(
                        framework=FrameworkType.FASTAPI,
                        path=path,
                        methods=(http_method,),
                        handler=handler,
                        file=file_path,
                        line=i + 1,
                    ))

    return endpoints


def _detect_django_urls(file_path: str) -> list[ApiEndpoint]:
    """Detect Django URL patterns.

    Django patterns:
    - path("/api/", views.handler)
    - re_path(r"^/api/", views.handler)
    - urlpatterns list
    - @api_view decorator
    """
    endpoints: list[ApiEndpoint] = []

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return endpoints

    # Check if this is a Django file
    has_django = "from django" in content or "import django" in content or "urlpatterns" in content

    if not has_django:
        return endpoints

    lines = content.split("\n")

    # Check if this is a urls.py file
    is_urls_file = "urlpatterns" in content or "path(" in content or "re_path(" in content

    if is_urls_file:
        for i, line in enumerate(lines):
            if "path(" in line:
                path = _extract_django_path(line)
                handler = _extract_django_handler(line)

                if path and handler:
                    endpoints.append(ApiEndpoint(
                        framework=FrameworkType.DJANGO,
                        path=path,
                        methods=("GET",),  # Django path defaults to GET
                        handler=handler,
                        file=file_path,
                        line=i + 1,
                    ))
            elif "re_path(" in line:
                path = _extract_django_path_re(line)
                handler = _extract_django_handler(line)

                if path and handler:
                    endpoints.append(ApiEndpoint(
                        framework=FrameworkType.DJANGO,
                        path=path,
                        methods=("GET",),
                        handler=handler,
                        file=file_path,
                        line=i + 1,
                    ))

    # Check for @api_view decorators
    for i, line in enumerate(lines):
        if "@api_view" in line:
            methods = _extract_api_view_methods(line)
            handler = _find_handler_function(lines, i)

            # Look for route in previous lines or use inferred path
            if handler and methods:
                endpoints.append(ApiEndpoint(
                    framework=FrameworkType.DJANGO,
                    path=f"/{handler}/",  # Fallback path
                    methods=methods,
                    handler=handler,
                    file=file_path,
                    line=i + 1,
                ))

    return endpoints


def _detect_express_routes(file_path: str) -> list[ApiEndpoint]:
    """Detect Express.js routes.

    Express patterns:
    - app.get("/path", handler)
    - app.post("/path", handler)
    - router.get("/path", handler)
    - app.use("/path", middleware)
    """
    endpoints: list[ApiEndpoint] = []

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return endpoints

    lines = content.split("\n")

    for i, line in enumerate(lines):
        for method in ("get", "post", "put", "delete", "patch", "options", "head", "use"):
            pattern = f"app.{method}(" if method != "use" else f"app.use("
            if pattern in line or f"router.{method}(" in line:
                path = _extract_js_route_path(line)
                handler = _extract_js_handler(line)
                http_method = "ALL" if method == "use" else method.upper()

                if path and handler:
                    endpoints.append(ApiEndpoint(
                        framework=FrameworkType.EXPRESS,
                        path=path,
                        methods=(http_method,),
                        handler=handler,
                        file=file_path,
                        line=i + 1,
                    ))

    return endpoints


def _detect_spring_endpoints(file_path: str) -> list[ApiEndpoint]:
    """Detect Spring Boot endpoints.

    Spring patterns:
    - @GetMapping("/path")
    - @PostMapping("/path")
    - @RequestMapping(path="/path", method=GET)
    """
    endpoints: list[ApiEndpoint] = []

    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
    except (OSError, UnicodeDecodeError):
        return endpoints

    # Check if this is a Spring file
    has_spring = ("@GetMapping" in content or "@PostMapping" in content or
                   "@RequestMapping" in content or "@RestController" in content)

    if not has_spring:
        return endpoints

    lines = content.split("\n")

    # Find all public methods as potential handlers
    method_map: dict[int, str] = {}
    for i, line in enumerate(lines):
        # Match Java method declarations
        # Pattern: public <return_type> <method_name>(<params>)
        match = re.search(r'public\s+(?:\w+(?:<[^>]+>)?\s+)?(\w+)\s*\(', line)
        if match:
            method_map[i] = match.group(1)

    # Now find annotations and map them to the nearest following method
    for i, line in enumerate(lines):
        if "@GetMapping(" in line:
            path = _extract_java_annotation_value(line)
            handler = _find_java_handler_after(lines, i, method_map)
            if path and handler:
                endpoints.append(ApiEndpoint(
                    framework=FrameworkType.SPRING,
                    path=path,
                    methods=("GET",),
                    handler=handler,
                    file=file_path,
                    line=i + 1,
                ))

        elif "@PostMapping(" in line:
            path = _extract_java_annotation_value(line)
            handler = _find_java_handler_after(lines, i, method_map)
            if path and handler:
                endpoints.append(ApiEndpoint(
                    framework=FrameworkType.SPRING,
                    path=path,
                    methods=("POST",),
                    handler=handler,
                    file=file_path,
                    line=i + 1,
                ))

        elif "@PutMapping(" in line:
            path = _extract_java_annotation_value(line)
            handler = _find_java_handler_after(lines, i, method_map)
            if path and handler:
                endpoints.append(ApiEndpoint(
                    framework=FrameworkType.SPRING,
                    path=path,
                    methods=("PUT",),
                    handler=handler,
                    file=file_path,
                    line=i + 1,
                ))

        elif "@DeleteMapping(" in line:
            path = _extract_java_annotation_value(line)
            handler = _find_java_handler_after(lines, i, method_map)
            if path and handler:
                endpoints.append(ApiEndpoint(
                    framework=FrameworkType.SPRING,
                    path=path,
                    methods=("DELETE",),
                    handler=handler,
                    file=file_path,
                    line=i + 1,
                ))

        elif "@RequestMapping(" in line:
            # Skip class-level @RequestMapping (has path but no method=, followed by "class")
            # Method-level has method= RequestMethod.XXX
            is_class_level = False
            if "method=" not in line:
                # Check if next non-empty line contains "class"
                for j in range(i + 1, min(i + 3, len(lines))):
                    if "class " in lines[j]:
                        is_class_level = True
                        break

            if not is_class_level:
                path = _extract_java_annotation_value(line)
                methods = _extract_request_mapping_methods(line)
                handler = _find_java_handler_after(lines, i, method_map)
                # Method-level @RequestMapping without path inherits from class
                if path is None and handler and methods:
                    path = "/"
                if path and handler and methods:
                    for method in methods:
                        endpoints.append(ApiEndpoint(
                            framework=FrameworkType.SPRING,
                            path=path,
                            methods=(method,),
                            handler=handler,
                            file=file_path,
                            line=i + 1,
                        ))

    return endpoints


def _find_java_handler_after(
    lines: list[str], annotation_line: int, method_map: dict[int, str]
) -> str | None:
    """Find the Java method that follows an annotation."""
    # Look for the next method within 5 lines
    for i in range(annotation_line + 1, min(annotation_line + 10, len(lines))):
        if i in method_map:
            return method_map[i]
    return None


# Helper functions

def _extract_route_path(line: str) -> str | None:
    """Extract route path from decorator line."""
    # Find the first quoted string after the decorator
    match = re.search(r'["\']([^"\']+)["\']', line)
    if match:
        return match.group(1)
    return None


def _extract_django_path(line: str) -> str | None:
    """Extract path from Django path() call."""
    match = re.search(r'path\(["\']([^"\']+)["\']', line)
    if match:
        return match.group(1)
    return None


def _extract_django_path_re(line: str) -> str | None:
    """Extract path from Django re_path() call."""
    import re
    match = re.search(r're_path\([rr]?["\']([^"\']+)["\']', line)
    if match:
        return match.group(1)
    return None


def _extract_django_handler(line: str) -> str | None:
    """Extract handler from Django path() call."""
    import re
    match = re.search(r',\s*(\w+|\w+\.\w+)', line)
    if match:
        return match.group(1)
    return None


def _extract_http_methods(line: str, default: tuple[str, ...] = ("GET",)) -> tuple[str, ...]:
    """Extract HTTP methods from decorator line."""
    import re
    methods_match = re.search(r'methods=\[([^\]]+)\]', line)
    if methods_match:
        methods_str = methods_match.group(1)
        methods = [m.strip().strip('"\'') for m in methods_str.split(',')]
        return tuple(m.upper() for m in methods if m)
    return default


def _extract_api_view_methods(line: str) -> tuple[str, ...]:
    """Extract methods from @api_view decorator."""
    import re
    # Match both @api_view(["GET", "POST"]) and @api_view("GET", "POST")
    match = re.search(r'@api_view\((?:\[([^\]]+)\]|(["\'][^"\']+["\']))\)', line)
    if match:
        methods_str = match.group(1) or match.group(2)
        if methods_str:
            # Clean up quotes and split
            methods = [m.strip().strip('"\'') for m in methods_str.split(',')]
            return tuple(m.upper() for m in methods if m)
    return ("GET",)


def _find_handler_function(lines: list[str], decorator_line: int) -> str | None:
    """Find the handler function name after a decorator.

    Searches up to 10 lines ahead to handle stacked decorators.
    """
    for i in range(decorator_line + 1, min(decorator_line + 10, len(lines))):
        line = lines[i].strip()
        if line.startswith("def "):
            # Python function definition
            import re
            match = re.search(r'def\s+(\w+)\s*\(', line)
            if match:
                return match.group(1)
        elif line.startswith("async def "):
            import re
            match = re.search(r'async def\s+(\w+)\s*\(', line)
            if match:
                return match.group(1)
    return None


def _extract_js_route_path(line: str) -> str | None:
    """Extract route path from Express route call."""
    import re
    match = re.search(r'["\']([^"\']+)["\']', line)
    if match:
        path = match.group(1)
        # Remove query parameters if present
        if "?" in path:
            path = path.split("?")[0]
        return path
    return None


def _extract_js_handler(line: str) -> str | None:
    """Extract handler name from Express route call."""
    import re
    # Match function name after the path
    match = re.search(r',\s*(\w+)\s*(?:\)|,)', line)
    if match:
        return match.group(1)
    # Match arrow function
    if "=>" in line:
        match = re.search(r'(\w+)\s*=>', line)
        if match:
            return f"<{match.group(1)}>"
    return "<anonymous>"


def _extract_java_method_name(line: str) -> str | None:
    """Extract method name from Java method declaration."""
    import re
    match = re.search(r'(?:def|fun)\s+(\w+)\s*\(', line)
    if match:
        return match.group(1)
    return None


def _extract_java_annotation_value(line: str) -> str | None:
    """Extract path value from Java annotation."""
    import re
    match = re.search(r'value\s*=\s*["\']([^"\']+)["\']', line)
    if match:
        return match.group(1)
    # Try without value= prefix
    match = re.search(r'["\']([^"\']+)["\']', line)
    if match:
        return match.group(1)
    return None


def _extract_request_mapping_methods(line: str) -> tuple[str, ...]:
    """Extract methods from @RequestMapping."""
    import re
    match = re.search(r'method\s*=\s*{([^}]+)}', line)
    if match:
        methods_str = match.group(1)
        methods = [m.strip().split('.')[-1] for m in methods_str.split(',')]
        return tuple(m.upper() for m in methods if m)
    return ("GET", "POST")  # Default methods


def calculate_metrics(endpoints: list[ApiEndpoint]) -> dict[str, Any]:
    """Calculate metrics for discovered endpoints.

    Args:
        endpoints: List of discovered endpoints

    Returns:
        Dictionary with metrics
    """
    by_framework: dict[str, int] = {}
    by_method: dict[str, int] = {}
    by_file: dict[str, int] = {}

    for endpoint in endpoints:
        # Count by framework
        framework = endpoint.framework.value
        by_framework[framework] = by_framework.get(framework, 0) + 1

        # Count by HTTP method
        for method in endpoint.methods:
            by_method[method] = by_method.get(method, 0) + 1

        # Count by file
        file_key = f"{Path(endpoint.file).name}"
        by_file[file_key] = by_file.get(file_key, 0) + 1

    return {
        "total_endpoints": len(endpoints),
        "by_framework": by_framework,
        "by_method": by_method,
        "by_file": by_file,
    }
