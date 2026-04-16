"""
Java pattern analysis — lambda expressions, Stream API, and Spring annotations.

Provides regex-based extraction for common Java patterns that are not
easily captured by tree-sitter grammar queries alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from tree_sitter_analyzer.utils import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Lambda expression extraction
# ---------------------------------------------------------------------------

_LAMBDA_PATTERN = re.compile(
    r"(?:\((?:[^()]*|\([^()]*\))*\)|(\w+))\s*->\s*"
    r"(.+?)(?:;\s*$|[,\s\)]+(?=(?:\.|;|\)|\n)))",
    re.MULTILINE,
)

_LAMBDA_TYPED_PARAM = re.compile(
    r"\(\s*(?:final\s+)?(\w+(?:<[^>]+>)?)\s+\w+"
)

_LAMBDA_METHOD_REF = re.compile(r"(\w+)::(\w+)")

# ---------------------------------------------------------------------------
# Stream API call chain
# ---------------------------------------------------------------------------

_STREAM_START = re.compile(r"\.\s*stream\s*\(\s*\)")

_STREAM_INTERMEDIATE: frozenset[str] = frozenset({
    "filter", "map", "flatMap", "mapToInt", "mapToLong", "mapToDouble",
    "sorted", "distinct", "peek", "limit", "skip", "takeWhile", "dropWhile",
    "sequential", "parallel", "unordered", "onClose",
})

_STREAM_TERMINAL: frozenset[str] = frozenset({
    "collect", "forEach", "forEachOrdered", "toArray", "reduce",
    "min", "max", "count", "anyMatch", "allMatch", "noneMatch",
    "findFirst", "findAny", "iterator", "spliterator",
})

_STREAM_START_PATTERN = re.compile(
    r"([\w]+(?:\.\w+(?:\([^)]*\))?)*)\s*\.\s*stream\s*\(\s*\)"
)

_CHAIN_STEP = re.compile(r"\.\s*(\w+)\s*\(")

_METHOD_REF_IN_CHAIN = re.compile(r"(\w+)::(\w+)")

# ---------------------------------------------------------------------------
# Spring annotations
# ---------------------------------------------------------------------------

_SPRING_COMPONENT_ANNOTATIONS: frozenset[str] = frozenset({
    "Component", "Service", "Repository", "Controller", "RestController",
    "Configuration", "Bean", "ComponentScan", "ConfigurationProperties",
    "EnableAutoConfiguration", "SpringBootApplication",
})

_SPRING_DI_ANNOTATIONS: frozenset[str] = frozenset({
    "Autowired", "Inject", "Resource", "Value", "Qualifier",
})

_SPRING_WEB_ANNOTATIONS: frozenset[str] = frozenset({
    "RequestMapping", "GetMapping", "PostMapping", "PutMapping",
    "DeleteMapping", "PatchMapping", "ExceptionHandler",
    "ControllerAdvice", "RestControllerAdvice", "ResponseStatus",
    "RequestBody", "ResponseBody", "PathVariable", "RequestParam",
    "RequestHeader", "CookieValue", "CrossOrigin",
})

_SPRING_DATA_ANNOTATIONS: frozenset[str] = frozenset({
    "Entity", "Table", "Id", "GeneratedValue", "Column",
    "OneToMany", "ManyToOne", "ManyToMany", "OneToOne",
    "JoinColumn", "JoinTable", "MappedSuperclass", "Embeddable",
    "Embedded", "NamedQuery", "Transactional",
})

_SPRING_ANNOTATION_PATTERN = re.compile(r"@(\w+)(?:\([^)]*\))?")

_DI_FIELD_MULTILINE = re.compile(
    r"@(Autowired|Inject|Resource)(?:\([^)]*\))?\s+"
    r"(?:private\s+|protected\s+|public\s+)?"
    r"(\w+(?:<[^>]+>)?)\s+\w+\s*[;=]",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LambdaInfo:
    """Extracted Java lambda expression."""

    raw: str
    line: int
    parameters: int
    has_typed_params: bool
    body: str
    method_references: tuple[str, ...]


@dataclass(frozen=True)
class StreamChain:
    """Extracted Stream API call chain."""

    source_type: str
    operations: tuple[str, ...]
    method_refs: tuple[str, ...]
    is_terminal: bool
    raw: str
    line: int


@dataclass(frozen=True)
class SpringComponent:
    """Detected Spring component."""

    annotation: str
    class_name: str
    line: int
    is_primary: bool


@dataclass(frozen=True)
class SpringInjection:
    """Detected Spring DI injection point."""

    annotation: str
    field_type: str
    line: int


@dataclass
class JavaPatternResult:
    """Aggregated Java pattern analysis result."""

    lambdas: list[LambdaInfo] = field(default_factory=list)
    stream_chains: list[StreamChain] = field(default_factory=list)
    spring_components: list[SpringComponent] = field(default_factory=list)
    spring_injections: list[SpringInjection] = field(default_factory=list)
    spring_endpoints: list[tuple[str, str]] = field(default_factory=list)

    @property
    def lambda_count(self) -> int:
        return len(self.lambdas)

    @property
    def stream_count(self) -> int:
        return len(self.stream_chains)

    @property
    def is_spring_component(self) -> bool:
        return len(self.spring_components) > 0

    @property
    def injection_count(self) -> int:
        return len(self.spring_injections)

    def to_dict(self) -> dict[str, object]:
        return {
            "lambda_count": self.lambda_count,
            "stream_count": self.stream_count,
            "is_spring_component": self.is_spring_component,
            "injection_count": self.injection_count,
            "lambdas": [
                {"line": la.line, "params": la.parameters, "body": la.body}
                for la in self.lambdas
            ],
            "stream_chains": [
                {"line": sc.line, "source": sc.source_type, "ops": list(sc.operations)}
                for sc in self.stream_chains
            ],
            "spring_components": [
                {"class": sc.class_name, "annotation": sc.annotation, "line": sc.line}
                for sc in self.spring_components
            ],
            "spring_injections": [
                {"type": si.field_type, "annotation": si.annotation, "line": si.line}
                for si in self.spring_injections
            ],
        }


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------


def extract_lambdas(source: str) -> list[LambdaInfo]:
    """Extract lambda expressions from Java source code."""
    results: list[LambdaInfo] = []
    lines = source.split("\n")

    for line_idx, line_text in enumerate(lines):
        stripped = line_text.strip()
        if "->" not in stripped:
            continue

        for m in _LAMBDA_PATTERN.finditer(stripped):
            raw = m.group(0).rstrip(";").strip()
            body_match = re.search(r"->\s*(.+)", raw)
            body = body_match.group(1).strip() if body_match else ""
            method_refs = tuple(
                f"{mr.group(1)}::{mr.group(2)}"
                for mr in _LAMBDA_METHOD_REF.finditer(body)
            )

            param_part = raw.split("->")[0].strip()
            if param_part.startswith("("):
                inner = param_part[1:-1].strip()
                params = len([p.strip() for p in inner.split(",") if p.strip()]) if inner else 0
            elif param_part:
                params = 1
            else:
                params = 0

            typed = bool(_LAMBDA_TYPED_PARAM.search(raw))

            results.append(LambdaInfo(
                raw=raw,
                line=line_idx + 1,
                parameters=params,
                has_typed_params=typed,
                body=body,
                method_references=method_refs,
            ))

    return results


def extract_stream_chains(source: str) -> list[StreamChain]:
    """Extract Stream API call chains from Java source code."""
    results: list[StreamChain] = []
    lines = source.split("\n")

    for line_idx, line_text in enumerate(lines):
        stripped = line_text.strip()
        if ".stream()" not in stripped:
            continue

        for m in _STREAM_START_PATTERN.finditer(stripped):
            source_type = m.group(1)
            start_pos = m.end()
            chain_part = stripped[start_pos:]

            steps = [s.group(1) for s in _CHAIN_STEP.finditer(chain_part)]
            ops = tuple(steps)

            refs = tuple(
                f"{mr.group(1)}::{mr.group(2)}"
                for mr in _METHOD_REF_IN_CHAIN.finditer(chain_part)
            )

            is_terminal = any(
                s in _STREAM_TERMINAL for s in steps
            ) if steps else False

            raw = stripped[m.start():].rstrip(";")
            results.append(StreamChain(
                source_type=source_type,
                operations=ops,
                method_refs=refs,
                is_terminal=is_terminal,
                raw=raw,
                line=line_idx + 1,
            ))

    return results


def extract_spring_patterns(source: str) -> tuple[list[SpringComponent], list[SpringInjection], list[tuple[str, str]]]:
    """Extract Spring annotations, DI injections, and web endpoints.

    Returns:
        (components, injections, endpoints) where endpoints are
        (http_method, path) tuples.
    """
    components: list[SpringComponent] = []
    injections: list[SpringInjection] = []
    endpoints: list[tuple[str, str]] = []

    lines = source.split("\n")
    current_class: str | None = None

    class_pattern = re.compile(
        r"(?:public\s+|abstract\s+)*class\s+(\w+)"
    )

    annotation_buffer: list[str] = []

    for line_idx, line_text in enumerate(lines):
        stripped = line_text.strip()
        line_num = line_idx + 1

        new_annotations: list[str] = []
        for am in _SPRING_ANNOTATION_PATTERN.finditer(stripped):
            new_annotations.append(am.group(1))

        if not new_annotations:
            if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
                annotation_buffer = []
                continue

        annotation_buffer.extend(new_annotations)

        cls_match = class_pattern.search(stripped)
        if cls_match:
            current_class = cls_match.group(1)
            for ann in annotation_buffer:
                if ann in _SPRING_COMPONENT_ANNOTATIONS:
                    is_primary = ann in ("Service", "Controller", "RestController")
                    components.append(SpringComponent(
                        annotation=ann,
                        class_name=current_class,
                        line=line_num,
                        is_primary=is_primary,
                    ))
            annotation_buffer = []
            continue

        if not new_annotations:
            annotation_buffer = []

        for ann in annotation_buffer:
            endpoint = _extract_endpoint(ann, stripped)
            if endpoint:
                endpoints.append(endpoint)

    # Multi-line DI field matching (annotation and field may be on separate lines)
    for di_m in _DI_FIELD_MULTILINE.finditer(source):
        annotation = di_m.group(1)
        field_type = di_m.group(2)
        pos = di_m.start()
        line_num = source[:pos].count("\n") + 1
        # Avoid duplicates from same-line matches already captured
        if not any(si.field_type == field_type and si.line == line_num for si in injections):
            injections.append(SpringInjection(
                annotation=annotation,
                field_type=field_type,
                line=line_num,
            ))

    return components, injections, endpoints


_ENDPOINT_MAP: dict[str, str] = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": "ANY",
}

_PATH_PATTERN = re.compile(r'(?:value|path)\s*=\s*"([^"]+)"')
_PATH_SHORT = re.compile(r'"([^"]+)"')


def _extract_endpoint(annotation: str, line: str) -> tuple[str, str] | None:
    """Extract HTTP method and path from a mapping annotation line."""
    method = _ENDPOINT_MAP.get(annotation)
    if method is None:
        return None

    path_match = _PATH_PATTERN.search(line)
    if not path_match:
        path_match = _PATH_SHORT.search(line)
    path = path_match.group(1) if path_match else "/"

    return (method, path)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def analyze_java_patterns(source: str) -> JavaPatternResult:
    """Analyze Java source code for lambda, stream, and Spring patterns.

    Args:
        source: Java source code as a string.

    Returns:
        JavaPatternResult with all detected patterns.
    """
    lambdas = extract_lambdas(source)
    stream_chains = extract_stream_chains(source)
    components, injections, endpoints = extract_spring_patterns(source)

    return JavaPatternResult(
        lambdas=lambdas,
        stream_chains=stream_chains,
        spring_components=components,
        spring_injections=injections,
        spring_endpoints=endpoints,
    )
