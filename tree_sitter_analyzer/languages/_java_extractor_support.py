"""Java 提取器共用的状态、文本读取、遍历及现代节点适配。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import tree_sitter

from ..encoding_utils import extract_text_slice, safe_encode
from ..models import Class, Function, Package
from ..plugins.base import ElementExtractor
from ..utils import log_debug, log_error
from ._java_modern import (
    extract_anonymous_class as _extract_anon_class_impl,
)
from ._java_modern import (
    extract_lambda_function as _extract_lambda_impl,
)
from ._java_modern import (
    extract_module_declaration as _extract_module_decl_impl,
)
from ._java_modern import (
    extract_static_initializer as _extract_static_init_impl,
)
from .java_helpers import _process_field_batch
from .java_helpers import java_traverse_and_extract as _traverse_standalone


class _JavaExtractorSupport(ElementExtractor):
    """保存提取状态并将节点分派到唯一构造实现，具体提取入口由子类提供。"""

    def __init__(self) -> None:
        """初始化逐文件状态与按字节范围标识的缓存。"""
        self.current_package: str = ""
        self.current_file: str = ""
        self.source_code: str = ""
        self.content_lines: list[str] = []
        self.imports: list[str] = []

        self._node_text_cache: dict[tuple[int, int], str] = {}
        self._processed_nodes: set[tuple[int, int]] = set()
        self._element_cache: dict[tuple[tuple[int, int], str], Any] = {}
        self._file_encoding: str | None = None
        self._annotation_cache: dict[int, list[dict[str, Any]]] = {}
        self._signature_cache: dict[int, str] = {}
        self.annotations: list[dict[str, Any]] = []

    def _reset_caches(self) -> None:
        """清空缓存与包状态，保留提取流程已收集的注解数据。"""
        for cache in (
            self._node_text_cache,
            self._element_cache,
            self._annotation_cache,
            self._signature_cache,
        ):
            cache.clear()
        self._processed_nodes.clear()
        self.current_package = ""

    def _traverse_and_extract_iterative(
        self,
        root_node: tree_sitter.Node | None,
        extractors: dict[str, Any],
        results: list[Any],
        element_type: str,
    ) -> None:
        """将游标遍历委托给公开 facade 所使用的同一实现。"""
        _traverse_standalone(
            root_node,
            extractors,
            results,
            element_type,
            self._processed_nodes,
            self._element_cache,
        )

    def _process_field_batch(
        self, batch: list[tree_sitter.Node], extractors: dict, results: list[Any]
    ) -> None:
        """按现有缓存协议批量处理字段。"""
        _process_field_batch(
            batch, extractors, results, self._processed_nodes, self._element_cache
        )

    def _get_node_text_optimized(self, node: tree_sitter.Node) -> str:
        """按稳定字节范围缓存解码后的节点文本。"""
        cache_key = (node.start_byte, node.end_byte)
        if cache_key in self._node_text_cache:
            return self._node_text_cache[cache_key]
        try:
            encoding = self._file_encoding or "utf-8"
            content_bytes = safe_encode("\n".join(self.content_lines), encoding)
            text = extract_text_slice(
                content_bytes, node.start_byte, node.end_byte, encoding
            )
            self._node_text_cache[cache_key] = text
            return text
        except Exception as e:
            log_error(f"Error in _get_node_text_optimized: {e}")
            return self._get_node_text_fallback(node)

    def _get_node_text_fallback(self, node: tree_sitter.Node) -> str:
        """主解码失败时，沿用逐行切片的文本回退。"""
        try:
            sp, ep = node.start_point, node.end_point
            if sp[0] == ep[0]:
                return str(self.content_lines[sp[0]][sp[1] : ep[1]])
            return "\n".join(self._collect_multiline_slices(sp, ep))
        except Exception as fe:
            log_error(f"Fallback text extraction also failed: {fe}")
            return ""

    def _collect_multiline_slices(
        self, sp: tuple[int, int], ep: tuple[int, int]
    ) -> list[str]:
        """收集跨行节点的首行、内部行和末行切片。"""
        lines = []
        for i in range(sp[0], ep[0] + 1):
            if i >= len(self.content_lines):
                continue
            line = self.content_lines[i]
            if i == sp[0]:
                lines.append(line[sp[1] :])
            elif i == ep[0]:
                lines.append(line[: ep[1]])
            else:
                lines.append(line)
        return lines

    def _extract_lambda_optimized(self, node: tree_sitter.Node) -> Function | None:
        """将 lambda 节点交给现代 Java 构造器。"""
        return _extract_lambda_impl(
            node,
            self._get_node_text_optimized,
            self.content_lines,
            log_debug_func=log_debug,
            log_error_func=log_error,
        )

    def _extract_static_initializer_optimized(
        self, node: tree_sitter.Node
    ) -> Function | None:
        """将静态初始化器交给现代 Java 构造器。"""
        return _extract_static_init_impl(
            node,
            self.content_lines,
            log_debug_func=log_debug,
            log_error_func=log_error,
        )

    def _extract_anonymous_class_optimized(
        self, node: tree_sitter.Node
    ) -> Class | None:
        """仅处理注册的 class_body；以父节点区分匿名类与普通类体。"""
        if node.parent is None or node.parent.type != "object_creation_expression":
            return None
        return _extract_anon_class_impl(
            node,
            self._get_node_text_optimized,
            self.content_lines,
            self.current_package,
            log_debug_func=log_debug,
            log_error_func=log_error,
        )

    def _extract_module_declaration_optimized(
        self, node: tree_sitter.Node
    ) -> Package | None:
        """将模块声明交给唯一的模块构造器。"""
        return _extract_module_decl_impl(
            node,
            self._get_node_text_optimized,
            log_debug_func=log_debug,
        )
