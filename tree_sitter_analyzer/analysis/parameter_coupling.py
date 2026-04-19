#!/usr/bin/env python3
"""
Function Parameter Coupling Analyzer.

Detects functions with too many parameters, complex parameter types,
and Data Clumps (multiple functions sharing the same parameter groups).

Supports Python, JavaScript/TypeScript, Java, and Go.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter

from tree_sitter_analyzer.analysis.base import BaseAnalyzer
from tree_sitter_analyzer.utils import setup_logger

if TYPE_CHECKING:
    pass

logger = setup_logger(__name__)

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go",
}

DEFAULT_MAX_PARAMS = 5
DEFAULT_MIN_CLUMP_SIZE = 3

@dataclass(frozen=True)
class ParameterInfo:
    """Information about a single function parameter."""

    name: str
    type_annotation: str | None = None
    default_value: str | None = None
    position: int = 0
    is_variadic: bool = False
    is_optional: bool = False

@dataclass(frozen=True)
class FunctionSignature:
    """A function/method signature with its parameters."""

    name: str
    file_path: str
    line_number: int
    parameters: tuple[ParameterInfo, ...]
    element_type: str = "function"  # function, method, constructor

    @property
    def param_count(self) -> int:
        return len(self.parameters)

    @property
    def param_names(self) -> frozenset[str]:
        return frozenset(p.name for p in self.parameters)

    @property
    def has_many_params(self) -> bool:
        return self.param_count > DEFAULT_MAX_PARAMS

@dataclass(frozen=True)
class DataClump:
    """A group of functions sharing the same parameter set."""

    param_names: frozenset[str]
    functions: tuple[FunctionSignature, ...]
    similarity: float = 0.0

    @property
    def function_count(self) -> int:
        return len(self.functions)

    @property
    def file_paths(self) -> frozenset[str]:
        return frozenset(f.file_path for f in self.functions)

@dataclass(frozen=True)
class CouplingResult:
    """Result of parameter coupling analysis."""

    functions: tuple[FunctionSignature, ...]
    high_param_functions: tuple[FunctionSignature, ...]
    data_clumps: tuple[DataClump, ...]
    total_functions: int
    total_parameters: int
    avg_params_per_function: float

    def get_warnings(self) -> list[str]:
        warnings: list[str] = []
        for func in self.high_param_functions:
            warnings.append(
                f"{func.file_path}:{func.line_number} - "
                f"'{func.name}' has {func.param_count} parameters (>{DEFAULT_MAX_PARAMS})"
            )
        for clump in self.data_clumps:
            params_str = ", ".join(sorted(clump.param_names))
            warnings.append(
                f"Data Clump: {clump.function_count} functions share "
                f"[{params_str}] across {len(clump.file_paths)} file(s)"
            )
        return warnings

def _jaccard_similarity(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union

class ParameterCouplingAnalyzer(BaseAnalyzer):
    """Analyzes function parameter coupling across source files."""

    def __init__(
        self,
        max_params: int = DEFAULT_MAX_PARAMS,
        min_clump_size: int = DEFAULT_MIN_CLUMP_SIZE,
        clump_threshold: float = 0.6,
    ) -> None:
        self._max_params = max_params
        self._min_clump_size = min_clump_size
        self._clump_threshold = clump_threshold
        super().__init__()

    def analyze_file(self, file_path: Path | str) -> CouplingResult:
        path = Path(file_path)
        if not path.exists():
            return CouplingResult(
                functions=(),
                high_param_functions=(),
                data_clumps=(),
                total_functions=0,
                total_parameters=0,
                avg_params_per_function=0.0,
            )

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return CouplingResult(
                functions=(),
                high_param_functions=(),
                data_clumps=(),
                total_functions=0,
                total_parameters=0,
                avg_params_per_function=0.0,
            )

        sigs = self._extract_signatures(path, ext)
        return self._build_result(sigs)

    def analyze_directory(self, dir_path: Path | str) -> CouplingResult:
        path = Path(dir_path)
        all_sigs: list[FunctionSignature] = []

        for ext in SUPPORTED_EXTENSIONS:
            for fp in path.rglob(f"*{ext}"):
                if ".git" in fp.parts or "node_modules" in fp.parts:
                    continue
                sigs = self._extract_signatures(fp, ext)
                all_sigs.extend(sigs)

        return self._build_result(all_sigs)

    def _build_result(self, sigs: list[FunctionSignature]) -> CouplingResult:
        high_param = tuple(s for s in sigs if s.param_count > self._max_params)
        clumps = self._detect_data_clumps(sigs)
        total_params = sum(s.param_count for s in sigs)
        avg = (total_params / len(sigs)) if sigs else 0.0

        return CouplingResult(
            functions=tuple(sigs),
            high_param_functions=high_param,
            data_clumps=clumps,
            total_functions=len(sigs),
            total_parameters=total_params,
            avg_params_per_function=round(avg, 2),
        )

    def _detect_data_clumps(self, sigs: list[FunctionSignature]) -> tuple[DataClump, ...]:
        if len(sigs) < 2:
            return ()

        clumps: list[DataClump] = []
        seen: set[frozenset[str]] = set()

        for i, sig_a in enumerate(sigs):
            if sig_a.param_count < self._min_clump_size:
                continue
            for j in range(i + 1, len(sigs)):
                sig_b = sigs[j]
                if sig_b.param_count < self._min_clump_size:
                    continue

                shared = sig_a.param_names & sig_b.param_names
                if len(shared) < self._min_clump_size:
                    continue

                similarity = _jaccard_similarity(sig_a.param_names, sig_b.param_names)
                if similarity < self._clump_threshold:
                    continue

                if shared in seen:
                    continue
                seen.add(shared)

                matching = [
                    s for s in sigs
                    if len(s.param_names & shared) >= self._min_clump_size
                    and _jaccard_similarity(s.param_names, shared) >= self._clump_threshold
                ]

                if len(matching) >= 2:
                    clumps.append(DataClump(
                        param_names=shared,
                        functions=tuple(matching),
                        similarity=similarity,
                    ))

        return tuple(clumps)

    def _extract_signatures(self, path: Path, ext: str) -> list[FunctionSignature]:
        language, parser = self._get_parser(ext)
        if language is None or parser is None:
            return []

        content = path.read_bytes()
        tree = parser.parse(content)

        if ext == ".py":
            return self._extract_python(tree.root_node, content, str(path))
        if ext in {".js", ".ts", ".tsx", ".jsx"}:
            return self._extract_js(tree.root_node, content, str(path))
        if ext == ".java":
            return self._extract_java(tree.root_node, content, str(path))
        if ext == ".go":
            return self._extract_go(tree.root_node, content, str(path))
        return []

    def _extract_python(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionSignature]:
        results: list[FunctionSignature] = []
        self._walk_python(root, content, file_path, results)
        return results

    def _walk_python(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionSignature],
    ) -> None:
        if node.type == "function_definition":
            sig = self._parse_python_function(node, content, file_path, "function")
            if sig is not None:
                results.append(sig)
            return
        if node.type == "class_definition":
            self._walk_python_class(node, content, file_path, results)
            return
        if node.type == "decorated_definition":
            for child in node.children:
                self._walk_python(child, content, file_path, results)
            return

        for child in node.children:
            self._walk_python(child, content, file_path, results)

    def _walk_python_class(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionSignature],
    ) -> None:
        class_children: list[tree_sitter.Node] = []
        for child in node.children:
            if child.type == "block":
                class_children.extend(child.children)
            else:
                class_children.append(child)

        for child in class_children:
            if child.type == "function_definition":
                name_node = child.child_by_field_name("name")
                if name_node:
                    raw_name = content[name_node.start_byte:name_node.end_byte].decode(
                        "utf-8", errors="replace"
                    )
                    element_type = "constructor" if raw_name == "__init__" else "method"
                else:
                    element_type = "method"
                sig = self._parse_python_function(child, content, file_path, element_type)
                if sig is not None:
                    results.append(sig)
            elif child.type == "decorated_definition":
                for inner in child.children:
                    if inner.type == "function_definition":
                        name_node = inner.child_by_field_name("name")
                        raw_name = (
                            content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                            if name_node
                            else ""
                        )
                        element_type = "constructor" if raw_name == "__init__" else "method"
                        sig = self._parse_python_function(inner, content, file_path, element_type)
                        if sig is not None:
                            results.append(sig)

    def _parse_python_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        element_type: str,
    ) -> FunctionSignature | None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            return FunctionSignature(
                name=name,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                parameters=(),
                element_type=element_type,
            )

        params = self._parse_python_params(params_node, content)
        return FunctionSignature(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            parameters=tuple(params),
            element_type=element_type,
        )

    def _parse_python_params(
        self, params_node: tree_sitter.Node, content: bytes
    ) -> list[ParameterInfo]:
        params: list[ParameterInfo] = []
        pos = 0
        for child in params_node.children:
            if child.type == "identifier":
                name = content[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                params.append(ParameterInfo(name=name, position=pos))
                pos += 1
            elif child.type == "typed_parameter":
                name = self._get_child_text(child, "identifier", content) or ""
                type_ann = self._get_node_text_by_type(child, "type", content)
                params.append(ParameterInfo(
                    name=name, type_annotation=type_ann, position=pos
                ))
                pos += 1
            elif child.type == "default_parameter":
                name = self._get_child_text(child, "identifier", content) or ""
                type_ann = self._get_node_text_by_type(child, "type", content)
                default = self._get_child_text(child, "value", content)
                params.append(ParameterInfo(
                    name=name, type_annotation=type_ann,
                    default_value=default, position=pos,
                ))
                pos += 1
            elif child.type == "typed_default_parameter":
                name = self._get_child_text(child, "identifier", content) or ""
                type_ann = self._get_node_text_by_type(child, "type", content)
                default = self._get_child_text(child, "value", content)
                params.append(ParameterInfo(
                    name=name, type_annotation=type_ann,
                    default_value=default, position=pos,
                ))
                pos += 1
            elif child.type in {"list_splat_pattern", "dictionary_splat_pattern"}:
                inner = child.children[1] if len(child.children) > 1 else None
                param_name = (
                    content[inner.start_byte:inner.end_byte].decode("utf-8", errors="replace")
                    if inner
                    else "*"
                )
                params.append(ParameterInfo(
                    name=param_name, position=pos,
                    is_variadic=True,
                ))
                pos += 1
        return params

    def _extract_js(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionSignature]:
        results: list[FunctionSignature] = []
        self._walk_js(root, content, file_path, results)
        return results

    def _walk_js(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionSignature],
    ) -> None:
        if node.type in {"function_declaration", "generator_function_declaration"}:
            sig = self._parse_js_function(node, content, file_path, "function")
            if sig is not None:
                results.append(sig)
        elif node.type == "method_definition":
            sig = self._parse_js_function(node, content, file_path, "method")
            if sig is not None:
                results.append(sig)
        elif node.type == "arrow_function":
            sig = self._parse_js_arrow(node, content, file_path)
            if sig is not None:
                results.append(sig)
        elif node.type in {"public_field_definition", "property_definition"}:
            for child in node.children:
                if child.type == "arrow_function":
                    name_node = node.child_by_field_name("name")
                    name = (
                        content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                        if name_node
                        else "<anonymous>"
                    )
                    sig = self._parse_js_params_only(child, content, file_path, name, "method")
                    if sig is not None:
                        results.append(sig)

        for child in node.children:
            self._walk_js(child, content, file_path, results)

    def _parse_js_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        element_type: str,
    ) -> FunctionSignature | None:
        name_node = node.child_by_field_name("name")
        name = (
            content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if name_node
            else "<anonymous>"
        )
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            return FunctionSignature(
                name=name,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                parameters=(),
                element_type=element_type,
            )
        params = self._parse_js_params(params_node, content)
        return FunctionSignature(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            parameters=tuple(params),
            element_type=element_type,
        )

    def _parse_js_arrow(
        self, node: tree_sitter.Node, content: bytes, file_path: str
    ) -> FunctionSignature | None:
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            return None
        params = self._parse_js_params(params_node, content)
        return FunctionSignature(
            name="<arrow>",
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            parameters=tuple(params),
            element_type="function",
        )

    def _parse_js_params_only(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        name: str,
        element_type: str,
    ) -> FunctionSignature | None:
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            return None
        params = self._parse_js_params(params_node, content)
        return FunctionSignature(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            parameters=tuple(params),
            element_type=element_type,
        )

    def _parse_js_params(
        self, params_node: tree_sitter.Node, content: bytes
    ) -> list[ParameterInfo]:
        params: list[ParameterInfo] = []
        pos = 0
        for child in params_node.children:
            if child.type == "identifier":
                name = content[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                params.append(ParameterInfo(name=name, position=pos))
                pos += 1
            elif child.type == "required_parameter":
                p = self._parse_js_single_param(child, content, pos)
                params.append(p)
                pos += 1
            elif child.type == "optional_parameter":
                p = self._parse_js_single_param(child, content, pos, is_optional=True)
                params.append(p)
                pos += 1
            elif child.type in {"rest_parameter", "rest_pattern"}:
                inner = child.child_by_field_name("name")
                if inner is None:
                    for sub in child.children:
                        if sub.type == "identifier":
                            inner = sub
                            break
                param_name = (
                    content[inner.start_byte:inner.end_byte].decode("utf-8", errors="replace")
                    if inner
                    else "...rest"
                )
                type_ann = self._get_js_type_annotation(child, content)
                params.append(ParameterInfo(
                    name=param_name, type_annotation=type_ann,
                    position=pos, is_variadic=True,
                ))
                pos += 1
            elif child.type == "assignment_pattern":
                first = child.child(0)
                if first:
                    param_name = content[first.start_byte:first.end_byte].decode("utf-8", errors="replace")
                    params.append(ParameterInfo(
                        name=param_name, position=pos, is_optional=True,
                    ))
                pos += 1
        return params

    def _parse_js_single_param(
        self, node: tree_sitter.Node, content: bytes, pos: int, is_optional: bool = False
    ) -> ParameterInfo:
        name_node = node.child_by_field_name("name") or node.child(0)
        name = (
            content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
            if name_node
            else ""
        )
        type_ann = self._get_js_type_annotation(node, content)
        return ParameterInfo(
            name=name, type_annotation=type_ann,
            position=pos, is_optional=is_optional,
        )

    def _get_js_type_annotation(
        self, node: tree_sitter.Node, content: bytes
    ) -> str | None:
        for child in node.children:
            if child.type == "type_annotation":
                return content[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return None

    def _extract_java(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionSignature]:
        results: list[FunctionSignature] = []
        self._walk_java(root, content, file_path, results)
        return results

    def _walk_java(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionSignature],
    ) -> None:
        if node.type == "method_declaration":
            sig = self._parse_java_method(node, content, file_path, "method")
            if sig is not None:
                results.append(sig)
        elif node.type == "constructor_declaration":
            sig = self._parse_java_method(node, content, file_path, "constructor")
            if sig is not None:
                results.append(sig)

        for child in node.children:
            self._walk_java(child, content, file_path, results)

    def _parse_java_method(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        element_type: str,
    ) -> FunctionSignature | None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
        params_node = node.child_by_field_name("parameters")
        if params_node is None:
            return FunctionSignature(
                name=name,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                parameters=(),
                element_type=element_type,
            )

        params = self._parse_java_params(params_node, content)
        return FunctionSignature(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            parameters=tuple(params),
            element_type=element_type,
        )

    def _parse_java_params(
        self, params_node: tree_sitter.Node, content: bytes
    ) -> list[ParameterInfo]:
        params: list[ParameterInfo] = []
        pos = 0
        for child in params_node.children:
            if child.type == "formal_parameter" or child.type == "spread_parameter":
                type_node = child.child_by_field_name("type")
                name_node = child.child_by_field_name("name")
                if name_node is None:
                    continue
                param_name = content[name_node.start_byte:name_node.end_byte].decode(
                    "utf-8", errors="replace"
                )
                type_ann = (
                    content[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="replace")
                    if type_node
                    else None
                )
                is_var = child.type == "spread_parameter"
                params.append(ParameterInfo(
                    name=param_name, type_annotation=type_ann,
                    position=pos, is_variadic=is_var,
                ))
                pos += 1
        return params

    def _extract_go(
        self, root: tree_sitter.Node, content: bytes, file_path: str
    ) -> list[FunctionSignature]:
        results: list[FunctionSignature] = []
        self._walk_go(root, content, file_path, results)
        return results

    def _walk_go(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        results: list[FunctionSignature],
    ) -> None:
        if node.type == "function_declaration":
            sig = self._parse_go_function(node, content, file_path, "function")
            if sig is not None:
                results.append(sig)
        elif node.type == "method_declaration":
            sig = self._parse_go_function(node, content, file_path, "method")
            if sig is not None:
                results.append(sig)

        for child in node.children:
            self._walk_go(child, content, file_path, results)

    def _parse_go_function(
        self,
        node: tree_sitter.Node,
        content: bytes,
        file_path: str,
        element_type: str,
    ) -> FunctionSignature | None:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")

        params_node = None
        for child in node.children:
            if child.type == "parameter_list":
                params_node = child
                break

        if params_node is None:
            return FunctionSignature(
                name=name,
                file_path=file_path,
                line_number=node.start_point[0] + 1,
                parameters=(),
                element_type=element_type,
            )

        params = self._parse_go_params(params_node, content)
        return FunctionSignature(
            name=name,
            file_path=file_path,
            line_number=node.start_point[0] + 1,
            parameters=tuple(params),
            element_type=element_type,
        )

    def _parse_go_params(
        self, params_node: tree_sitter.Node, content: bytes
    ) -> list[ParameterInfo]:
        params: list[ParameterInfo] = []
        pos = 0
        for child in params_node.children:
            if child.type == "parameter_declaration":
                name_node = child.child_by_field_name("name")
                type_node = child.child_by_field_name("type")
                param_name = (
                    content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    if name_node
                    else ""
                )
                type_ann = (
                    content[type_node.start_byte:type_node.end_byte].decode("utf-8", errors="replace")
                    if type_node
                    else None
                )
                is_var = False
                if type_node is not None and type_node.type == "variadic_type":
                    is_var = True
                    if type_node.child_count > 0:
                        inner_node = type_node.child(type_node.child_count - 1)
                        if inner_node is not None:
                            type_ann = content[inner_node.start_byte:inner_node.end_byte].decode(
                                "utf-8", errors="replace"
                            )
                params.append(ParameterInfo(
                    name=param_name, type_annotation=type_ann,
                    position=pos, is_variadic=is_var,
                ))
                pos += 1
            elif child.type == "variadic_parameter_declaration":
                name_node = child.child_by_field_name("name")
                param_name = (
                    content[name_node.start_byte:name_node.end_byte].decode("utf-8", errors="replace")
                    if name_node
                    else ""
                )
                type_parts: list[str] = []
                for sub in child.children:
                    if sub.type == "type_identifier":
                        type_parts.append(
                            content[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                        )
                type_ann = type_parts[0] if type_parts else None
                params.append(ParameterInfo(
                    name=param_name, type_annotation=type_ann,
                    position=pos, is_variadic=True,
                ))
                pos += 1
        return params

    def _get_child_text(
        self, node: tree_sitter.Node, field_name: str, content: bytes
    ) -> str | None:
        child = node.child_by_field_name(field_name)
        if child is None:
            return None
        return content[child.start_byte:child.end_byte].decode("utf-8", errors="replace")

    def _get_node_text_by_type(
        self, node: tree_sitter.Node, node_type: str, content: bytes
    ) -> str | None:
        for child in node.children:
            if child.type == node_type:
                return content[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return None
