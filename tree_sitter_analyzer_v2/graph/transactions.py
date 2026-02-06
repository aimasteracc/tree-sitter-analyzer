"""Transaction support for ACID operations"""

import copy
from enum import Enum
from typing import Any

from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage


class TransactionError(Exception):
    """Transaction-related errors"""
    pass


class IsolationLevel(Enum):
    """Transaction isolation levels"""
    READ_UNCOMMITTED = "read_uncommitted"
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"
    SERIALIZABLE = "serializable"


class Transaction:
    """Represents a database transaction"""

    def __init__(
        self,
        storage: CodeGraphStorage,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED
    ):
        self.storage = storage
        self.isolation = isolation
        self._committed = False
        self._rolled_back = False

        # Track operations
        self._operations: list[dict[str, Any]] = []
        self._nodes_added = 0
        self._edges_added = 0
        self._nodes_updated = 0
        self._nodes_deleted = 0

        # Savepoints
        self._savepoints: dict[str, int] = {}
        self._savepoint_counter = 0

        # Snapshot for isolation
        self._snapshot: dict[str, Any] = {}
        if isolation == IsolationLevel.REPEATABLE_READ:
            self._snapshot = {
                'nodes': copy.deepcopy(storage.nodes),
                'edges': copy.deepcopy(storage.edges)
            }

    def add_node(self, node_id: str, node_type: str, attributes: dict[str, Any]) -> None:
        """Add node in transaction"""
        self._check_active()

        self._operations.append({
            'type': 'add_node',
            'node_id': node_id,
            'node_type': node_type,
            'attributes': attributes
        })
        self._nodes_added += 1

    def update_node(self, node_id: str, attributes: dict[str, Any]) -> None:
        """Update node in transaction"""
        self._check_active()

        self._operations.append({
            'type': 'update_node',
            'node_id': node_id,
            'attributes': attributes
        })
        self._nodes_updated += 1

    def delete_node(self, node_id: str) -> None:
        """Delete node in transaction"""
        self._check_active()

        self._operations.append({
            'type': 'delete_node',
            'node_id': node_id
        })
        self._nodes_deleted += 1

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        attributes: dict[str, Any]
    ) -> None:
        """Add edge in transaction"""
        self._check_active()

        self._operations.append({
            'type': 'add_edge',
            'source': source,
            'target': target,
            'edge_type': edge_type,
            'attributes': attributes
        })
        self._edges_added += 1

    def read_node(self, node_id: str) -> dict[str, Any] | None:
        """Read node with isolation"""
        if self.isolation == IsolationLevel.REPEATABLE_READ:
            # Read from snapshot
            return self._snapshot['nodes'].get(node_id)
        else:
            # Read committed data
            return self.storage.get_node(node_id)

    def commit(self) -> None:
        """Commit transaction"""
        self._check_active()

        # Apply all operations
        for op in self._operations:
            if op['type'] == 'add_node':
                self.storage.add_node(
                    op['node_id'],
                    op['node_type'],
                    op['attributes']
                )
            elif op['type'] == 'update_node':
                self.storage.update_node(
                    op['node_id'],
                    op['attributes']
                )
            elif op['type'] == 'delete_node':
                # Delete node by removing from storage
                if op['node_id'] in self.storage.nodes:
                    del self.storage.nodes[op['node_id']]
            elif op['type'] == 'add_edge':
                self.storage.add_edge(
                    op['source'],
                    op['target'],
                    op['edge_type'],
                    op['attributes']
                )

        self._committed = True

    def rollback(self) -> None:
        """Rollback transaction"""
        self._check_active()

        # Discard all operations
        self._operations.clear()
        self._rolled_back = True

    def savepoint(self) -> str:
        """Create a savepoint"""
        self._check_active()

        savepoint_name = f"sp_{self._savepoint_counter}"
        self._savepoints[savepoint_name] = len(self._operations)
        self._savepoint_counter += 1

        return savepoint_name

    def rollback_to(self, savepoint: str) -> None:
        """Rollback to a savepoint"""
        self._check_active()

        if savepoint not in self._savepoints:
            raise TransactionError(f"Savepoint not found: {savepoint}")

        # Discard operations after savepoint
        position = self._savepoints[savepoint]
        self._operations = self._operations[:position]

        # Remove later savepoints
        self._savepoints = {
            name: pos
            for name, pos in self._savepoints.items()
            if pos <= position
        }

    def get_stats(self) -> dict[str, Any]:
        """Get transaction statistics"""
        return {
            'operations': len(self._operations),
            'nodes_added': self._nodes_added,
            'edges_added': self._edges_added,
            'nodes_updated': self._nodes_updated,
            'nodes_deleted': self._nodes_deleted,
            'committed': self._committed,
            'rolled_back': self._rolled_back
        }

    def _check_active(self) -> None:
        """Check if transaction is active"""
        if self._committed:
            raise TransactionError("Transaction already committed")
        if self._rolled_back:
            raise TransactionError("Transaction already rolled back")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is None:
            # No exception, commit
            if not self._committed and not self._rolled_back:
                self.commit()
        else:
            # Exception occurred, rollback
            if not self._committed and not self._rolled_back:
                self.rollback()

        return False  # Don't suppress exceptions


class TransactionManager:
    """Manages transactions for a storage"""

    def __init__(self, storage: CodeGraphStorage):
        self.storage = storage
        self._active_transactions: list[Transaction] = []

    def begin(
        self,
        isolation: IsolationLevel = IsolationLevel.READ_COMMITTED
    ) -> Transaction:
        """Begin a new transaction"""
        tx = Transaction(self.storage, isolation)
        self._active_transactions.append(tx)
        return tx

    def get_active_count(self) -> int:
        """Get number of active transactions"""
        return len([
            tx for tx in self._active_transactions
            if not tx._committed and not tx._rolled_back
        ])

    def cleanup(self) -> None:
        """Clean up completed transactions"""
        self._active_transactions = [
            tx for tx in self._active_transactions
            if not tx._committed and not tx._rolled_back
        ]
