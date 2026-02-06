"""Tests for backup and restore functionality"""

import pytest
import tempfile
import os
from pathlib import Path

from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage
from tree_sitter_analyzer_v2.graph.backup import (
    BackupManager,
    IncrementalBackup,
    BackupMetadata,
)


class TestBackupManager:
    """Test backup and restore operations"""

    def test_full_backup(self):
        """Test creating a full backup"""
        storage = CodeGraphStorage()
        for i in range(10):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            assert os.path.exists(backup_path)
            assert os.path.getsize(backup_path) > 0

    def test_restore_from_backup(self):
        """Test restoring from backup"""
        storage = CodeGraphStorage()
        for i in range(10):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            # Create new empty storage
            new_storage = CodeGraphStorage()
            assert len(new_storage.nodes) == 0
            
            # Restore
            new_backup_mgr = BackupManager(new_storage, tmpdir)
            new_backup_mgr.restore(backup_path)
            
            # Verify restoration
            assert len(new_storage.nodes) == 10
            for i in range(10):
                assert new_storage.get_node(f'f_{i}') is not None

    def test_incremental_backup(self):
        """Test incremental backup"""
        storage = CodeGraphStorage()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            
            # Initial backup
            for i in range(5):
                storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
            
            backup1 = backup_mgr.create_backup(name="backup1.bak")
            
            # Add more nodes
            for i in range(5, 10):
                storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
            
            # Incremental backup
            backup2 = backup_mgr.create_incremental_backup(backup1, name="backup2.bak")
            
            assert os.path.exists(backup2)
            # Both backups should exist
            assert os.path.exists(backup1)

    def test_backup_metadata(self):
        """Test backup metadata"""
        storage = CodeGraphStorage()
        for i in range(5):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            metadata = backup_mgr.get_metadata(backup_path)
            
            assert metadata.node_count == 5
            assert metadata.edge_count == 0
            assert metadata.timestamp is not None
            assert metadata.backup_type in ['full', 'incremental']

    def test_list_backups(self):
        """Test listing available backups"""
        storage = CodeGraphStorage()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            
            # Create multiple backups with unique names
            storage.add_node('f1', 'function', {'name': 'func1'})
            backup1 = backup_mgr.create_backup(name="backup1.bak")
            
            storage.add_node('f2', 'function', {'name': 'func2'})
            backup2 = backup_mgr.create_backup(name="backup2.bak")
            
            backups = backup_mgr.list_backups()
            
            assert len(backups) == 2
            assert backup1 in [b['path'] for b in backups]
            assert backup2 in [b['path'] for b in backups]

    def test_delete_backup(self):
        """Test deleting a backup"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'func1'})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            assert os.path.exists(backup_path)
            
            backup_mgr.delete_backup(backup_path)
            
            assert not os.path.exists(backup_path)

    def test_backup_compression(self):
        """Test that backups are compressed"""
        storage = CodeGraphStorage()
        for i in range(100):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'docstring': 'This is a test function' * 10
            })
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            # Backup should be compressed (much smaller than raw data)
            backup_size = os.path.getsize(backup_path)
            assert backup_size < 50000  # Should be well compressed

    def test_point_in_time_recovery(self):
        """Test restoring to a specific point in time"""
        storage = CodeGraphStorage()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            
            # State 1
            storage.add_node('f1', 'function', {'name': 'func1'})
            backup1 = backup_mgr.create_backup(name="state1.bak")
            
            # State 2
            storage.add_node('f2', 'function', {'name': 'func2'})
            backup2 = backup_mgr.create_backup(name="state2.bak")
            
            # State 3
            storage.add_node('f3', 'function', {'name': 'func3'})
            
            # Restore to state 1
            new_storage = CodeGraphStorage()
            new_backup_mgr = BackupManager(new_storage, tmpdir)
            new_backup_mgr.restore(backup1)
            
            assert len(new_storage.nodes) == 1
            assert new_storage.get_node('f1') is not None
            assert new_storage.get_node('f2') is None

    def test_backup_with_edges(self):
        """Test backup includes edges"""
        storage = CodeGraphStorage()
        storage.add_node('f1', 'function', {'name': 'main'})
        storage.add_node('f2', 'function', {'name': 'helper'})
        storage.add_edge('f1', 'f2', 'calls', {})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            # Restore
            new_storage = CodeGraphStorage()
            new_backup_mgr = BackupManager(new_storage, tmpdir)
            new_backup_mgr.restore(backup_path)
            
            # Verify edges
            edges = new_storage.get_edges_from('f1')
            assert len(edges) == 1
            assert edges[0]['target'] == 'f2'

    def test_backup_large_graph(self):
        """Test backup of large graph"""
        storage = CodeGraphStorage()
        
        # Create 1000 nodes
        for i in range(1000):
            storage.add_node(f'f_{i}', 'function', {
                'name': f'func_{i}',
                'file': f'file_{i % 10}.py'
            })
        
        # Add 5000 edges
        for i in range(5000):
            source = f'f_{i % 1000}'
            target = f'f_{(i + 1) % 1000}'
            storage.add_edge(source, target, 'calls', {})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            # Restore
            new_storage = CodeGraphStorage()
            new_backup_mgr = BackupManager(new_storage, tmpdir)
            new_backup_mgr.restore(backup_path)
            
            # Verify
            assert len(new_storage.nodes) == 1000
            assert len(new_storage.edges) >= 1000

    def test_backup_speed(self):
        """Test backup performance"""
        import time
        
        storage = CodeGraphStorage()
        for i in range(1000):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            
            start = time.time()
            backup_path = backup_mgr.create_backup()
            backup_time = time.time() - start
            
            # Should be fast (<1s for 1000 nodes)
            assert backup_time < 1.0

    def test_restore_speed(self):
        """Test restore performance"""
        import time
        
        storage = CodeGraphStorage()
        for i in range(1000):
            storage.add_node(f'f_{i}', 'function', {'name': f'func_{i}'})
        
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_mgr = BackupManager(storage, tmpdir)
            backup_path = backup_mgr.create_backup()
            
            new_storage = CodeGraphStorage()
            new_backup_mgr = BackupManager(new_storage, tmpdir)
            
            start = time.time()
            new_backup_mgr.restore(backup_path)
            restore_time = time.time() - start
            
            # Should be fast (<1s for 1000 nodes)
            assert restore_time < 1.0
