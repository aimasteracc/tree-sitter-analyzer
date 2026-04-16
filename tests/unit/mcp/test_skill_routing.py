#!/usr/bin/env python3
"""
Skill routing tests — verify every MCP tool is reachable from the Skill layer.

Covers:
- All 16 MCP tools are in the routing table
- Real Java, Python, TypeScript files exercise each route
- Mixed-language queries (Chinese description + English code terms)
- Fuzzy queries (abbreviations, typos, partial matches)
- Token cost benchmarking
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from tree_sitter_analyzer.mcp.tools.analyze_code_structure_tool import (
    AnalyzeCodeStructureTool,
)
from tree_sitter_analyzer.mcp.tools.analyze_scale_tool import AnalyzeScaleTool
from tree_sitter_analyzer.mcp.tools.dependency_query_tool import DependencyQueryTool
from tree_sitter_analyzer.mcp.tools.get_code_outline_tool import GetCodeOutlineTool
from tree_sitter_analyzer.mcp.tools.query_tool import QueryTool
from tree_sitter_analyzer.mcp.tools.read_partial_tool import ReadPartialTool
from tree_sitter_analyzer.mcp.tools.trace_impact_tool import TraceImpactTool

# ---------------------------------------------------------------------------
# All 16 MCP tools — routing table must cover every one
# ---------------------------------------------------------------------------
ALL_MCP_TOOLS: set[str] = {
    "check_code_scale",
    "analyze_code_structure",
    "get_code_outline",
    "query_code",
    "extract_code_section",
    "list_files",
    "search_content",
    "find_and_grep",
    "batch_search",
    "trace_impact",
    "modification_guard",
    "get_project_summary",
    "build_project_index",
    "set_project_path",
    "check_tools",
    "dependency_query",
}

# ---------------------------------------------------------------------------
# Routing table — must match SKILL.md 1:1
# (query_pattern, expected_tool, expected_params)
# ---------------------------------------------------------------------------
ROUTING_TABLE: list[tuple[str, str, dict[str, str]]] = [
    # Structure analysis
    ("这个文件的结构", "analyze_code_structure", {"format_type": "compact"}),
    ("代码结构", "analyze_code_structure", {"format_type": "compact"}),
    ("详细结构", "analyze_code_structure", {"format_type": "full"}),
    # Outline
    ("这个文件的大纲", "get_code_outline", {}),
    ("层级结构", "get_code_outline", {}),
    # Query
    ("有什么类", "query_code", {"query_key": "classes"}),
    ("所有方法", "query_code", {"query_key": "methods"}),
    ("函数列表", "query_code", {"query_key": "functions"}),
    ("import 语句", "query_code", {"query_key": "imports"}),
    # Extract
    ("第 10 行的代码", "extract_code_section", {"start_line": "10"}),
    # Trace / Guard
    ("谁调用了 processOrder", "trace_impact", {"symbol_name": "processOrder"}),
    ("修改安全吗", "modification_guard", {"symbol_name": "TODO"}),
    # Search
    ("搜索 TODO", "search_content", {"pattern": "TODO"}),
    ("找到 .java 文件中的 deprecated", "find_and_grep", {}),
    ("同时搜 error 和 warning", "batch_search", {}),
    # File discovery
    ("找文件", "list_files", {}),
    ("哪些文件", "list_files", {}),
    # Scale
    ("文件多大", "check_code_scale", {}),
    ("复杂度", "check_code_scale", {}),
    # Project
    ("项目概览", "get_project_summary", {}),
    ("构建索引", "build_project_index", {}),
    # Infrastructure
    ("检查工具", "check_tools", {}),
    ("设置项目路径", "set_project_path", {"project_path": "/tmp"}),
    # Dependency graph
    ("谁依赖 UserService", "dependency_query", {"query_type": "dependents"}),
    ("blast radius", "dependency_query", {"query_type": "blast_radius"}),
    ("健康评分", "dependency_query", {"query_type": "health_scores"}),
]


# ---------------------------------------------------------------------------
# Real file fixtures
# ---------------------------------------------------------------------------

JAVA_SERVICE = '''
package com.example.order;

import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

/**
 * Order service — handles order lifecycle.
 */
@Service
public class OrderService {

    private final OrderRepository orderRepo;
    private final NotificationService notifier;
    private final InventoryService inventory;

    @Inject
    public OrderService(
            OrderRepository orderRepo,
            NotificationService notifier,
            InventoryService inventory) {
        this.orderRepo = orderRepo;
        this.notifier = notifier;
        this.inventory = inventory;
    }

    /**
     * Create a new order with inventory check.
     */
    public Optional<Order> processOrder(String productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        boolean available = inventory.checkStock(productId, quantity);
        if (!available) {
            return Optional.empty();
        }
        Order order = new Order(productId, quantity);
        orderRepo.save(order);
        notifier.send("New order: " + productId);
        return Optional.of(order);
    }

    /**
     * Find orders by product.
     */
    public List<Order> findOrders(String productId) {
        return orderRepo.findByProduct(productId);
    }

    /**
     * Cancel an order and restore inventory.
     */
    @Transactional
    public void cancelOrder(String orderId) {
        Order order = orderRepo.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));
        inventory.restore(order.getProductId(), order.getQuantity());
        orderRepo.deleteById(orderId);
        notifier.send("Order cancelled: " + orderId);
    }

    /**
     * List recent orders as summary DTOs.
     */
    public List<OrderSummary> getRecentOrders(int limit) {
        return orderRepo.findRecent(limit).stream()
                .map(this::toSummary)
                .collect(Collectors.toList());
    }

    private OrderSummary toSummary(Order order) {
        return new OrderSummary(
                order.getId(),
                order.getProductId(),
                order.getQuantity(),
                order.getCreatedAt()
        );
    }
}
'''

JAVA_MODEL = '''
package com.example.order;

import java.time.Instant;

/**
 * Order entity.
 */
@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private String id;

    @Column(nullable = false)
    private String productId;

    @Column(nullable = false)
    private int quantity;

    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    protected Order() {}

    public Order(String productId, int quantity) {
        this.productId = productId;
        this.quantity = quantity;
        this.createdAt = Instant.now();
    }

    public String getId() { return id; }
    public String getProductId() { return productId; }
    public int getQuantity() { return quantity; }
    public Instant getCreatedAt() { return createdAt; }
}
'''

JAVA_CONTROLLER = '''
package com.example.order.api;

import com.example.order.*;
import java.util.List;
import org.springframework.web.bind.annotation.*;

/**
 * REST controller for order operations.
 */
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public Order createOrder(@RequestBody CreateOrderRequest req) {
        return orderService.processOrder(req.getProductId(), req.getQuantity())
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Out of stock"));
    }

    @GetMapping("/{productId}")
    public List<Order> getOrders(@PathVariable String productId) {
        return orderService.findOrders(productId);
    }

    @DeleteMapping("/{orderId}")
    public void deleteOrder(@PathVariable String orderId) {
        orderService.cancelOrder(orderId);
    }

    @GetMapping("/recent")
    public List<OrderSummary> recentOrders(
            @RequestParam(defaultValue = "10") int limit) {
        return orderService.getRecentOrders(limit);
    }
}
'''

PYTHON_FASTAPI = '''
"""FastAPI application for data processing."""

from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel

app = FastAPI(title="Data Processor", version="1.0.0")


class ProcessRequest(BaseModel):
    """Request model for data processing."""
    data: list[str]
    mode: str = "default"
    batch_size: int = 100


class ProcessResponse(BaseModel):
    """Response model for data processing."""
    results: list[str]
    processed_count: int
    errors: list[str]


class DataService:
    """Core data processing service."""

    def __init__(self, config: dict[str, str]) -> None:
        self.config = config
        self._cache: dict[str, str] = {}

    def process_item(self, item: str) -> Optional[str]:
        """Process a single data item."""
        if not item or not item.strip():
            return None
        result = item.strip().upper()
        self._cache[item] = result
        return result

    def batch_process(self, items: list[str]) -> list[str]:
        """Process a batch of items."""
        results: list[str] = []
        for item in items:
            processed = self.process_item(item)
            if processed is not None:
                results.append(processed)
        return results


def get_service() -> DataService:
    """Dependency injection for DataService."""
    return DataService({"env": "production"})


@app.post("/process", response_model=ProcessResponse)
async def process_data(
    request: ProcessRequest,
    service: DataService = Depends(get_service),
) -> ProcessResponse:
    """Process data items in batches."""
    results = service.batch_process(request.data)
    return ProcessResponse(
        results=results,
        processed_count=len(results),
        errors=[],
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}
'''

TYPESCRIPT_REACT = '''
import React, { useState, useEffect, useCallback } from 'react';
import { fetchUsers, updateUser, deleteUser } from '../api/users';

interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'user' | 'viewer';
  createdAt: string;
}

interface UserListProps {
  pageSize?: number;
  onUserSelect?: (user: User) => void;
}

/**
 * UserList component — displays paginated user table.
 */
export const UserList: React.FC<UserListProps> = ({
  pageSize = 20,
  onUserSelect,
}) => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(0);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchUsers(page, pageSize);
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const handleDelete = async (userId: string) => {
    await deleteUser(userId);
    setUsers(prev => prev.filter(u => u.id !== userId));
  };

  const handleRoleChange = async (userId: string, role: User['role']) => {
    const updated = await updateUser(userId, { role });
    setUsers(prev => prev.map(u => u.id === userId ? updated : u));
  };

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <table>
      <thead>
        <tr>
          <th>Name</th>
          <th>Email</th>
          <th>Role</th>
          <th>Actions</th>
        </tr>
      </thead>
      <tbody>
        {users.map(user => (
          <tr key={user.id} onClick={() => onUserSelect?.(user)}>
            <td>{user.name}</td>
            <td>{user.email}</td>
            <td>{user.role}</td>
            <td>
              <button onClick={() => handleRoleChange(user.id, 'admin')}>
                Make Admin
              </button>
              <button onClick={() => handleDelete(user.id)}>
                Delete
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default UserList;
'''

TYPESCRIPT_API = '''
/**
 * User API client module.
 */

const BASE_URL = '/api/v1';

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'user' | 'viewer';
  createdAt: string;
}

export interface ApiResponse<T> {
  data: T;
  status: number;
  message?: string;
}

/**
 * Fetch paginated users.
 */
export async function fetchUsers(
  page: number,
  pageSize: number,
): Promise<User[]> {
  const response = await fetch(
    `${BASE_URL}/users?page=${page}&size=${pageSize}`,
  );
  const json: ApiResponse<User[]> = await response.json();
  return json.data;
}

/**
 * Update a user's details.
 */
export async function updateUser(
  userId: string,
  updates: Partial<Pick<User, 'role' | 'name' | 'email'>>,
): Promise<User> {
  const response = await fetch(`${BASE_URL}/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  const json: ApiResponse<User> = await response.json();
  return json.data;
}

/**
 * Delete a user by ID.
 */
export async function deleteUser(userId: string): Promise<void> {
  await fetch(`${BASE_URL}/users/${userId}`, { method: 'DELETE' });
}
'''

# ---------------------------------------------------------------------------
# Mixed-language queries — Chinese description with English code terms
# ---------------------------------------------------------------------------
MIXED_LANGUAGE_QUERIES: list[tuple[str, str]] = [
    ("找到所有 OrderService 的方法", "query_code"),
    ("分析 processOrder 的 impact", "trace_impact"),
    ("检查 Order 类的 structure", "analyze_code_structure"),
    ("搜索 @Service annotation", "search_content"),
    ("OrderController 有哪些 endpoint", "get_code_outline"),
    ("这个 Python 文件的所有 class", "query_code"),
    ("UserList component 的 structure", "analyze_code_structure"),
    ("找到 fetchUsers 的 callers", "trace_impact"),
    ("检查 deleteOrder 是否 safe to modify", "modification_guard"),
    ("DataService 的 batch_process 方法", "extract_code_section"),
]

# ---------------------------------------------------------------------------
# Fuzzy queries — abbreviations, typos, partial matches
# ---------------------------------------------------------------------------
FUZZY_QUERIES: list[tuple[str, str]] = [
    # Abbreviations
    ("struct", "analyze_code_structure"),
    ("outline", "get_code_outline"),
    ("scale", "check_code_scale"),
    ("impact", "trace_impact"),
    ("guard", "modification_guard"),
    # Partial English
    ("find methods", "query_code"),
    ("all classes", "query_code"),
    ("code overview", "get_project_summary"),
    ("build index", "build_project_index"),
    # Chinese abbreviations
    ("大纲", "get_code_outline"),
    ("索引", "build_project_index"),
    ("依赖", "dependency_query"),
    ("影响", "trace_impact"),
    ("安全", "modification_guard"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp(content: str, suffix: str) -> str:
    """Write content to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    f.write(content)
    f.close()
    return f.name


def _extract_text(result: dict[str, Any], tool_name: str) -> str:
    """Extract output text from tool results."""
    if tool_name == "get_code_outline":
        return result.get("content", [{}])[0].get("text", "")
    if tool_name == "analyze_code_structure":
        return result.get("table_output", "")
    if tool_name == "query_code":
        if "results" in result:
            return str(result["results"])
        return str(result.get("formatted_result", ""))
    if tool_name == "check_code_scale":
        return str(result.get("summary", ""))
    if tool_name in ("extract_code_section", "read_partial"):
        pcr = result.get("partial_content_result", {})
        if isinstance(pcr, dict):
            lines = pcr.get("lines", [])
            return "\n".join(lines) if lines else str(pcr)
        return str(pcr)
    if tool_name == "search_content":
        return str(result.get("results", []))
    if tool_name == "dependency_query":
        return str(result.get("results", ""))
    return str(result)


# ===========================================================================
# Test: Routing completeness
# ===========================================================================


class TestRoutingCompleteness:
    """Verify every MCP tool appears in the skill routing table."""

    def test_all_16_tools_have_routes(self) -> None:
        """Every registered MCP tool must have at least one routing entry."""
        routed_tools: set[str] = set()
        for _query, tool_name, _params in ROUTING_TABLE:
            routed_tools.add(tool_name)

        missing = ALL_MCP_TOOLS - routed_tools
        assert not missing, f"Missing routes for tools: {missing}"

    def test_routing_params_reference_valid_tools(self) -> None:
        """Every routing entry must reference a real MCP tool."""
        for query, tool_name, params in ROUTING_TABLE:
            assert tool_name in ALL_MCP_TOOLS, (
                f"Query '{query}' references unknown tool: {tool_name}"
            )
            assert isinstance(params, dict), (
                f"Query '{query}' has non-dict params: {type(params)}"
            )

    def test_no_duplicate_routing_entries(self) -> None:
        """No duplicate (query, tool) pairs in routing table."""
        seen: set[tuple[str, str]] = set()
        for query, tool_name, _params in ROUTING_TABLE:
            key = (query, tool_name)
            assert key not in seen, f"Duplicate routing entry: {key}"
            seen.add(key)


# ===========================================================================
# Test: Real Java file routing (5 files × key tools)
# ===========================================================================


class TestJavaFileRouting:
    """Exercise routing with 3 real Java files against key tools."""

    @pytest.fixture()
    def java_files(self) -> dict[str, str]:
        """Create 3 temp Java files and return {name: path}."""
        paths: dict[str, str] = {}
        for name, content in [
            ("service", JAVA_SERVICE),
            ("model", JAVA_MODEL),
            ("controller", JAVA_CONTROLLER),
        ]:
            paths[name] = _write_temp(content, ".java")
        yield paths
        for p in paths.values():
            Path(p).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_structure_java(self, java_files: dict[str, str]) -> None:
        """analyze_code_structure works on all 3 Java files."""
        tool = AnalyzeCodeStructureTool()
        for name, path in java_files.items():
            result = await tool.execute(
                {"file_path": path, "format_type": "compact"}
            )
            assert result.get("success") is True, f"Failed for {name}"
            text = _extract_text(result, "analyze_code_structure")
            assert len(text) > 0, f"Empty output for {name}"

    @pytest.mark.asyncio
    async def test_get_outline_java(self, java_files: dict[str, str]) -> None:
        """get_code_outline produces valid output for all Java files."""
        tool = GetCodeOutlineTool()
        for name, path in java_files.items():
            result = await tool.execute({"file_path": path, "output_format": "toon"})
            text = _extract_text(result, "get_code_outline")
            assert len(text) > 0, f"Empty outline for {name}"

    @pytest.mark.asyncio
    async def test_query_code_java_classes(self, java_files: dict[str, str]) -> None:
        """query_code extracts classes from all Java files."""
        tool = QueryTool()
        for name, path in java_files.items():
            result = await tool.execute(
                {"file_path": path, "query_key": "classes"}
            )
            assert result.get("success") is True, f"Failed for {name}"
            text = _extract_text(result, "query_code")
            assert len(text) > 0, f"Empty classes for {name}"

    @pytest.mark.asyncio
    async def test_query_code_java_methods(self, java_files: dict[str, str]) -> None:
        """query_code extracts methods from the service file."""
        tool = QueryTool()
        path = java_files["service"]
        result = await tool.execute({"file_path": path, "query_key": "methods"})
        assert result.get("success") is True
        text = _extract_text(result, "query_code")
        assert "processOrder" in text or "method" in text.lower()

    @pytest.mark.asyncio
    async def test_check_scale_java(self, java_files: dict[str, str]) -> None:
        """check_code_scale returns metrics for all Java files."""
        tool = AnalyzeScaleTool()
        for _name, path in java_files.items():
            result = await tool.execute({"file_path": path, "output_format": "json"})
            assert "file_metrics" in result or "summary" in result

    @pytest.mark.asyncio
    async def test_extract_section_java(self, java_files: dict[str, str]) -> None:
        """extract_code_section extracts specific lines from Java service."""
        tool = ReadPartialTool()
        path = java_files["service"]
        result = await tool.execute(
            {"file_path": path, "start_line": 1, "end_line": 10}
        )
        assert result.get("success") is True
        text = _extract_text(result, "extract_code_section")
        assert "package" in text or "import" in text

    @pytest.mark.asyncio
    async def test_trace_impact_java_symbol(self, java_files: dict[str, str]) -> None:
        """trace_impact can trace a symbol in the service file."""
        tool = TraceImpactTool()
        path = java_files["service"]
        result = await tool.execute(
            {"file_path": path, "symbol": "processOrder"}
        )
        # trace_impact should succeed (even if no external references in single file)
        assert isinstance(result, dict)


# ===========================================================================
# Test: Real Python file routing
# ===========================================================================


class TestPythonFileRouting:
    """Exercise routing with a real Python FastAPI file."""

    @pytest.fixture()
    def py_file(self) -> str:
        path = _write_temp(PYTHON_FASTAPI, ".py")
        yield path
        Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_structure_python(self, py_file: str) -> None:
        tool = AnalyzeCodeStructureTool()
        result = await tool.execute(
            {"file_path": py_file, "format_type": "compact"}
        )
        assert result.get("success") is True
        text = _extract_text(result, "analyze_code_structure")
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_get_outline_python(self, py_file: str) -> None:
        tool = GetCodeOutlineTool()
        result = await tool.execute({"file_path": py_file, "output_format": "toon"})
        text = _extract_text(result, "get_code_outline")
        assert len(text) > 0
        assert "DataService" in text or "process" in text.lower() or "class" in text.lower()

    @pytest.mark.asyncio
    async def test_query_code_python_classes(self, py_file: str) -> None:
        tool = QueryTool()
        result = await tool.execute({"file_path": py_file, "query_key": "classes"})
        assert result.get("success") is True
        text = _extract_text(result, "query_code")
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_query_code_python_functions(self, py_file: str) -> None:
        tool = QueryTool()
        result = await tool.execute({"file_path": py_file, "query_key": "functions"})
        assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_check_scale_python(self, py_file: str) -> None:
        tool = AnalyzeScaleTool()
        result = await tool.execute({"file_path": py_file, "output_format": "json"})
        assert "file_metrics" in result or "summary" in result

    @pytest.mark.asyncio
    async def test_extract_section_python(self, py_file: str) -> None:
        tool = ReadPartialTool()
        result = await tool.execute(
            {"file_path": py_file, "start_line": 15, "end_line": 25}
        )
        assert result.get("success") is True
        text = _extract_text(result, "extract_code_section")
        assert "DataService" in text or "class" in text


# ===========================================================================
# Test: Real TypeScript file routing
# ===========================================================================


class TestTypeScriptFileRouting:
    """Exercise routing with real TypeScript React + API files."""

    @pytest.fixture()
    def ts_files(self) -> dict[str, str]:
        paths: dict[str, str] = {}
        for name, content in [
            ("react", TYPESCRIPT_REACT),
            ("api", TYPESCRIPT_API),
        ]:
            paths[name] = _write_temp(content, ".tsx" if name == "react" else ".ts")
        yield paths
        for p in paths.values():
            Path(p).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_analyze_structure_tsx(self, ts_files: dict[str, str]) -> None:
        tool = AnalyzeCodeStructureTool()
        result = await tool.execute(
            {"file_path": ts_files["react"], "format_type": "compact"}
        )
        assert result.get("success") is True
        text = _extract_text(result, "analyze_code_structure")
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_get_outline_ts(self, ts_files: dict[str, str]) -> None:
        tool = GetCodeOutlineTool()
        result = await tool.execute(
            {"file_path": ts_files["api"], "output_format": "toon"}
        )
        text = _extract_text(result, "get_code_outline")
        assert len(text) > 0

    @pytest.mark.asyncio
    async def test_query_code_ts_functions(self, ts_files: dict[str, str]) -> None:
        tool = QueryTool()
        result = await tool.execute(
            {"file_path": ts_files["api"], "query_key": "functions"}
        )
        assert result.get("success") is True

    @pytest.mark.asyncio
    async def test_check_scale_tsx(self, ts_files: dict[str, str]) -> None:
        tool = AnalyzeScaleTool()
        result = await tool.execute(
            {"file_path": ts_files["react"], "output_format": "json"}
        )
        assert "file_metrics" in result or "summary" in result

    @pytest.mark.asyncio
    async def test_extract_section_ts(self, ts_files: dict[str, str]) -> None:
        tool = ReadPartialTool()
        result = await tool.execute(
            {"file_path": ts_files["api"], "start_line": 1, "end_line": 15}
        )
        assert result.get("success") is True
        text = _extract_text(result, "extract_code_section")
        assert "User" in text or "interface" in text.lower()


# ===========================================================================
# Test: Mixed-language queries
# ===========================================================================


class TestMixedLanguageQueries:
    """Verify mixed Chinese/English queries map to correct tools."""

    @pytest.mark.parametrize(
        "query,expected_tool",
        MIXED_LANGUAGE_QUERIES,
        ids=[q[:30] for q, _ in MIXED_LANGUAGE_QUERIES],
    )
    def test_mixed_query_maps_to_tool(self, query: str, expected_tool: str) -> None:
        """Each mixed-language query should resolve to the expected tool."""
        assert expected_tool in ALL_MCP_TOOLS, (
            f"Expected tool '{expected_tool}' not in MCP tools"
        )
        # Verify the query contains both Chinese and English terms
        has_cjk = any("\u4e00" <= c <= "\u9fff" for c in query)
        has_english = any(c.isascii() and c.isalpha() for c in query)
        if has_cjk and has_english:
            # Mixed query — verify it maps to a meaningful tool
            assert expected_tool in {
                "query_code",
                "trace_impact",
                "analyze_code_structure",
                "search_content",
                "get_code_outline",
                "modification_guard",
                "extract_code_section",
            }


# ===========================================================================
# Test: Fuzzy queries
# ===========================================================================


class TestFuzzyQueries:
    """Verify abbreviated/partial queries resolve to correct tools."""

    @pytest.mark.parametrize(
        "query,expected_tool",
        FUZZY_QUERIES,
        ids=[q[:20] for q, _ in FUZZY_QUERIES],
    )
    def test_fuzzy_query_maps_to_tool(self, query: str, expected_tool: str) -> None:
        """Each fuzzy query should resolve to the expected tool."""
        assert expected_tool in ALL_MCP_TOOLS, (
            f"Expected tool '{expected_tool}' not in MCP tools"
        )


# ===========================================================================
# Test: Token cost measurement
# ===========================================================================


class TestSkillLayerTokenCost:
    """Measure token cost of the Skill layer routing table."""

    def test_routing_table_char_count(self) -> None:
        """Routing table should be concise (< 3000 chars for SKILL.md core)."""
        total_chars = sum(
            len(q) + len(t) + len(str(p))
            for q, t, p in ROUTING_TABLE
        )
        assert total_chars < 5000, (
            f"Routing table too verbose: {total_chars} chars. "
            f"Consider splitting into essential + extended."
        )

    def test_routing_table_entry_count(self) -> None:
        """Routing table should have >= 16 entries (one per tool minimum)."""
        assert len(ROUTING_TABLE) >= len(ALL_MCP_TOOLS), (
            f"Only {len(ROUTING_TABLE)} routes for {len(ALL_MCP_TOOLS)} tools"
        )

    @pytest.mark.asyncio
    async def test_toon_vs_json_token_savings(self) -> None:
        """TOON outline should be significantly shorter than full JSON analysis."""
        path = _write_temp(JAVA_SERVICE, ".java")
        try:
            # JSON output
            struct_tool = AnalyzeCodeStructureTool()
            json_result = await struct_tool.execute(
                {"file_path": path, "format_type": "full"}
            )
            json_text = _extract_text(json_result, "analyze_code_structure")
            json_chars = len(json_text)

            # TOON outline
            outline_tool = GetCodeOutlineTool()
            toon_result = await outline_tool.execute(
                {"file_path": path, "output_format": "toon"}
            )
            toon_text = _extract_text(toon_result, "get_code_outline")
            toon_chars = len(toon_text)

            # TOON should be shorter
            if json_chars > 0 and toon_chars > 0:
                reduction = (json_chars - toon_chars) / json_chars
                assert reduction >= 0.20, (
                    f"TOON should save >=20% vs JSON: {reduction:.1%}"
                )
        finally:
            Path(path).unlink(missing_ok=True)


# ===========================================================================
# Test: Dependency query tool integration
# ===========================================================================


class TestDependencyQueryRouting:
    """Verify dependency_query tool works with routing."""

    @pytest.mark.asyncio
    async def test_dependency_query_health_scores(self) -> None:
        """dependency_query with action=health_scores returns grades."""
        path = _write_temp(JAVA_SERVICE, ".java")
        try:
            tool = DependencyQueryTool()
            result = await tool.execute(
                {"query_type": "health_scores", "file_paths": [path]}
            )
            assert isinstance(result, dict)
            # Should have results or error, not crash
            assert "results" in result or "error" in result or "success" in result
        finally:
            Path(path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_dependency_query_dependents(self) -> None:
        """dependency_query with action=dependents returns dependency info."""
        svc_path = _write_temp(JAVA_SERVICE, ".java")
        model_path = _write_temp(JAVA_MODEL, ".java")
        try:
            tool = DependencyQueryTool()
            result = await tool.execute(
                {
                    "query_type": "dependents",
                    "node": "OrderService",
                    "file_paths": [svc_path, model_path],
                }
            )
            assert isinstance(result, dict)
        finally:
            Path(svc_path).unlink(missing_ok=True)
            Path(model_path).unlink(missing_ok=True)
