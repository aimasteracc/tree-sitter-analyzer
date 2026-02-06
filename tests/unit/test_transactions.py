"""Tests for transaction support"""

import pytest
from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage
from tree_sitter_analyzer_v2.graph.transactions import (
    Transaction,
    TransactionManager,
    TransactionError,
    IsolationLevel,
)


class TestTransaction:
    """Test transaction operations"""

    def test_simple_transaction_commit(self):
        """Test committing a simple transaction"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.add_node('f1', 'function', {'name': 'main'})
        tx.commit()
        
        # Verify node was added
        assert storage.get_node('f1') is not None

    def test_simple_transaction_rollback(self):
        """Test rolling back a transaction"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.add_node('f1', 'function', {'name': 'main'})
        tx.rollback()
        
        # Verify node was not added
        assert storage.get_node('f1') is None

    def test_multiple_operations_in_transaction(self):
        """Test multiple operations in one transaction"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.add_node('f1', 'function', {'name': 'main'})
        tx.add_node('f2', 'function', {'name': 'helper'})
        tx.add_edge('f1', 'f2', 'calls', {})
        tx.commit()
        
        # Verify all operations
        assert storage.get_node('f1') is not None
        assert storage.get_node('f2') is not None
        edges = storage.get_edges_from('f1')
        assert len(edges) == 1

    def test_transaction_isolation(self):
        """Test that uncommitted changes are not visible"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.add_node('f1', 'function', {'name': 'main'})
        
        # Should not be visible before commit
        assert storage.get_node('f1') is None
        
        tx.commit()
        
        # Now visible
        assert storage.get_node('f1') is not None

    def test_nested_transactions(self):
        """Test nested transaction support"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx1 = tx_manager.begin()
        tx1.add_node('f1', 'function', {'name': 'main'})
        
        tx2 = tx_manager.begin()
        tx2.add_node('f2', 'function', {'name': 'helper'})
        tx2.commit()
        
        tx1.commit()
        
        # Both should be committed
        assert storage.get_node('f1') is not None
        assert storage.get_node('f2') is not None

    def test_transaction_error_on_double_commit(self):
        """Test error when committing twice"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.add_node('f1', 'function', {'name': 'main'})
        tx.commit()
        
        with pytest.raises(TransactionError):
            tx.commit()

    def test_transaction_context_manager(self):
        """Test using transaction as context manager"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        with tx_manager.begin() as tx:
            tx.add_node('f1', 'function', {'name': 'main'})
        
        # Auto-committed
        assert storage.get_node('f1') is not None

    def test_transaction_context_manager_rollback_on_exception(self):
        """Test auto-rollback on exception"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        try:
            with tx_manager.begin() as tx:
                tx.add_node('f1', 'function', {'name': 'main'})
                raise ValueError("Test error")
        except ValueError:
            pass
        
        # Should be rolled back
        assert storage.get_node('f1') is None

    def test_update_node_in_transaction(self):
        """Test updating node in transaction"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main', 'lines': 10})
        
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.update_node('f1', {'lines': 20})
        tx.commit()
        
        # Verify update
        node = storage.get_node('f1')
        assert node['lines'] == 20

    def test_delete_node_in_transaction(self):
        """Test deleting node in transaction"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.delete_node('f1')
        tx.commit()
        
        # Verify deletion
        assert storage.get_node('f1') is None

    def test_concurrent_transactions(self):
        """Test concurrent transaction handling"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx1 = tx_manager.begin()
        tx2 = tx_manager.begin()
        
        tx1.add_node('f1', 'function', {'name': 'main'})
        tx2.add_node('f2', 'function', {'name': 'helper'})
        
        tx1.commit()
        tx2.commit()
        
        # Both should be committed
        assert storage.get_node('f1') is not None
        assert storage.get_node('f2') is not None

    def test_transaction_statistics(self):
        """Test collecting transaction statistics"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.add_node('f1', 'function', {'name': 'main'})
        tx.add_node('f2', 'function', {'name': 'helper'})
        tx.add_edge('f1', 'f2', 'calls', {})
        
        stats = tx.get_stats()
        
        assert stats['operations'] == 3
        assert stats['nodes_added'] == 2
        assert stats['edges_added'] == 1

    def test_savepoint_support(self):
        """Test savepoint functionality"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        tx = tx_manager.begin()
        tx.add_node('f1', 'function', {'name': 'main'})
        
        savepoint = tx.savepoint()
        tx.add_node('f2', 'function', {'name': 'helper'})
        
        tx.rollback_to(savepoint)
        tx.commit()
        
        # f1 should exist, f2 should not
        assert storage.get_node('f1') is not None
        assert storage.get_node('f2') is None

    def test_isolation_level_read_committed(self):
        """Test READ_COMMITTED isolation level"""
        storage = CodeGraphStorage()
        tx_manager = TransactionManager(storage)
        
        storage.add_node('f1', 'function', {'name': 'main', 'version': 1})
        
        tx = tx_manager.begin(isolation=IsolationLevel.READ_COMMITTED)
        
        # Read current value
        node = tx.read_node('f1')
        assert node['version'] == 1
        
        # External update
        storage.update_node('f1', {'version': 2})
        
        # Should see new value (READ_COMMITTED)
        node = tx.read_node('f1')
        assert node['version'] == 2
        
        tx.commit()
