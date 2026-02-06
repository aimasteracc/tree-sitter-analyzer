"""Query optimizer for efficient query execution"""

import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage


@dataclass
class QueryPlan:
    """Represents an optimized query execution plan"""

    root: 'PlanNode'
    estimated_cost: float
    query_string: str

    def execute(self) -> list[dict[str, Any]]:
        """Execute the query plan"""
        return self.root.execute()

    def has_join(self) -> bool:
        """Check if plan contains a join"""
        return self._has_join_recursive(self.root)

    def _has_join_recursive(self, node: 'PlanNode') -> bool:
        """Recursively check for join nodes"""
        if isinstance(node, JoinNode):
            return True
        if hasattr(node, 'child'):
            return self._has_join_recursive(node.child)
        if hasattr(node, 'left') and hasattr(node, 'right'):
            return self._has_join_recursive(node.left) or self._has_join_recursive(node.right)
        return False

    def __str__(self) -> str:
        """String representation of plan"""
        return self._node_to_string(self.root, 0)

    def _node_to_string(self, node: 'PlanNode', indent: int) -> str:
        """Convert node to string with indentation"""
        prefix = "  " * indent
        result = f"{prefix}{node.__class__.__name__}"

        if isinstance(node, IndexScanNode):
            result += f"(index={node.index_type}, key={node.key})"
        elif isinstance(node, FilterNode):
            result += f"(condition={node.condition})"

        result += f" [cost={node.cost:.1f}]\n"

        if hasattr(node, 'child'):
            result += self._node_to_string(node.child, indent + 1)
        if hasattr(node, 'left') and hasattr(node, 'right'):
            result += self._node_to_string(node.left, indent + 1)
            result += self._node_to_string(node.right, indent + 1)

        return result


class PlanNode(ABC):
    """Abstract base class for plan nodes"""

    def __init__(self, storage: CodeGraphStorage, cost: float = 0):
        self.storage = storage
        self.cost = cost

    @abstractmethod
    def execute(self) -> list[dict[str, Any]]:
        """Execute this node"""
        pass


class IndexScanNode(PlanNode):
    """Index scan operation"""

    def __init__(self, storage: CodeGraphStorage, index_type: str, key: str, cost: float = 10):
        super().__init__(storage, cost)
        self.index_type = index_type
        self.key = key

    def execute(self) -> list[dict[str, Any]]:
        """Execute index scan"""
        if self.index_type == 'by_type':
            return self.storage.query_by_type(self.key)
        elif self.index_type == 'by_file':
            return self.storage.query_by_file(self.key)
        elif self.index_type == 'by_name':
            return self.storage.query_by_name(self.key)
        else:
            return []


class FilterNode(PlanNode):
    """Filter operation"""

    def __init__(self, storage: CodeGraphStorage, child: PlanNode, condition: dict[str, Any], cost: float = 5):
        super().__init__(storage, cost)
        self.child = child
        self.condition = condition

    def execute(self) -> list[dict[str, Any]]:
        """Execute filter"""
        results = self.child.execute()

        filtered = []
        for item in results:
            if self._matches_condition(item):
                filtered.append(item)

        return filtered

    def _matches_condition(self, item: dict[str, Any]) -> bool:
        """Check if item matches filter condition"""
        for key, value in self.condition.items():
            if key not in item:
                return False

            if isinstance(value, dict):
                # Handle comparison operators
                item_value = item[key]
                for op, op_value in value.items():
                    if op == '>':
                        if not (item_value > op_value):
                            return False
                    elif op == '<':
                        if not (item_value < op_value):
                            return False
                    elif op == '>=':
                        if not (item_value >= op_value):
                            return False
                    elif op == '<=':
                        if not (item_value <= op_value):
                            return False
                    elif op == '==':
                        if item_value != op_value:
                            return False
                    elif op == '!=' and item_value == op_value:
                        return False
            else:
                # Direct equality
                if item[key] != value:
                    return False

        return True


class JoinNode(PlanNode):
    """Join operation for relationships"""

    def __init__(self, storage: CodeGraphStorage, left: PlanNode, right: PlanNode,
                 join_type: str, cost: float = 50):
        super().__init__(storage, cost)
        self.left = left
        self.right = right
        self.join_type = join_type

    def execute(self) -> list[dict[str, Any]]:
        """Execute join"""
        left_results = self.left.execute()
        right_results = self.right.execute()

        # Simple nested loop join
        joined = []
        for left_item in left_results:
            for right_item in right_results:
                if self._matches_join(left_item, right_item):
                    joined.append(right_item)

        return joined

    def _matches_join(self, left: dict[str, Any], right: dict[str, Any]) -> bool:
        """Check if items match join condition"""
        if self.join_type == 'calls':
            # Check if left calls right
            left_id = left.get('id')
            right_id = right.get('id')

            if left_id and right_id:
                edges = self.storage.get_edges_from(left_id)
                for edge in edges:
                    if edge['target'] == right_id and edge['type'] == 'calls':
                        return True

        return False


class QueryOptimizer:
    """Optimizes CQL queries for efficient execution"""

    def __init__(self, storage: CodeGraphStorage):
        self.storage = storage
        self._plan_cache: dict[str, QueryPlan] = {}

    def optimize(self, query: str) -> QueryPlan:
        """
        Optimize a CQL query

        Args:
            query: CQL query string

        Returns:
            Optimized query plan
        """
        # Check cache
        if query in self._plan_cache:
            return self._plan_cache[query]

        # Parse query
        query = query.strip().lower()

        # Build plan
        plan = self._build_plan(query)

        # Cache plan
        self._plan_cache[query] = plan

        return plan

    def _build_plan(self, query: str) -> QueryPlan:
        """Build optimized query plan"""
        # Parse query components
        if not query.startswith('find '):
            raise ValueError("Query must start with 'find'")

        query = query[5:].strip()  # Remove 'find '

        # Extract node type
        parts = query.split()
        if not parts:
            raise ValueError("Missing node type")

        node_type = parts[0]
        # Normalize plural to singular
        if node_type.endswith('s'):
            node_type = node_type[:-1]
        remaining = ' '.join(parts[1:])

        # Parse filters
        filters = []
        file_filter = None
        relationship = None

        if 'in file:' in remaining:
            idx = remaining.index('in file:')
            file_part = remaining[idx + 8:].split()[0]
            file_filter = file_part
            remaining = remaining[:idx] + remaining[idx + 8 + len(file_part):]

        if 'called_by' in remaining:
            idx = remaining.index('called_by')
            caller_name = remaining[idx + 10:].split()[0]
            relationship = ('called_by', caller_name)
            remaining = remaining[:idx]

        # Parse 'with' conditions
        while 'with ' in remaining:
            idx = remaining.index('with ')
            condition_part = remaining[idx + 5:]

            # Extract condition
            tokens = condition_part.split()
            if len(tokens) >= 3:
                field = tokens[0]
                operator = tokens[1]
                value = tokens[2]

                # Convert value to appropriate type
                try:
                    value = int(value)
                except ValueError:
                    with contextlib.suppress(ValueError):
                        value = float(value)

                filters.append((field, operator, value))
                # Remove this 'with' clause and continue
                remaining = remaining[:idx] + ' '.join(tokens[3:])
            else:
                break

        # Build plan based on selectivity
        root = None
        cost = 0

        if file_filter:
            # File index is usually most selective
            root = IndexScanNode(self.storage, 'by_file', file_filter, cost=10)
            cost += 10

            # Add type filter
            root = FilterNode(self.storage, root, {'type': node_type}, cost=5)
            cost += 5
        elif relationship:
            # Build join for relationship
            rel_type, rel_name = relationship

            # Find caller by name
            left = IndexScanNode(self.storage, 'by_name', rel_name, cost=10)
            cost += 10

            # Find all functions
            right = IndexScanNode(self.storage, 'by_type', node_type, cost=20)
            cost += 20

            # Join them
            root = JoinNode(self.storage, left, right, 'calls', cost=50)
            cost += 50
        else:
            # Simple type query
            root = IndexScanNode(self.storage, 'by_type', node_type, cost=20)
            cost += 20

        # Add additional filters
        for field, operator, value in filters:
            condition = {field: {operator: value}}
            root = FilterNode(self.storage, root, condition, cost=5)
            cost += 5

        return QueryPlan(root=root, estimated_cost=cost, query_string=query)
