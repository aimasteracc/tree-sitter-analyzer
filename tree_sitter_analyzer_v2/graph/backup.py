"""Backup and restore functionality for graph storage"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tree_sitter_analyzer_v2.graph.advanced_storage import CodeGraphStorage
from tree_sitter_analyzer_v2.graph.compression import GraphCompressor


@dataclass
class BackupMetadata:
    """Metadata about a backup"""

    backup_path: str
    backup_type: str  # 'full' or 'incremental'
    timestamp: str
    node_count: int
    edge_count: int
    compressed_size: int
    parent_backup: str | None = None


class IncrementalBackup:
    """Handles incremental backup operations"""

    def __init__(self, base_backup: str):
        self.base_backup = base_backup
        self._changes: dict[str, Any] = {
            'added_nodes': {},
            'updated_nodes': {},
            'deleted_nodes': set(),
            'added_edges': {},
            'deleted_edges': set()
        }

    def track_node_addition(self, node_id: str, node_data: dict[str, Any]) -> None:
        """Track a node addition"""
        self._changes['added_nodes'][node_id] = node_data

    def track_node_update(self, node_id: str, node_data: dict[str, Any]) -> None:
        """Track a node update"""
        self._changes['updated_nodes'][node_id] = node_data

    def track_node_deletion(self, node_id: str) -> None:
        """Track a node deletion"""
        self._changes['deleted_nodes'].add(node_id)

    def get_changes(self) -> dict[str, Any]:
        """Get all tracked changes"""
        return {
            'added_nodes': self._changes['added_nodes'],
            'updated_nodes': self._changes['updated_nodes'],
            'deleted_nodes': list(self._changes['deleted_nodes']),
            'added_edges': self._changes['added_edges'],
            'deleted_edges': list(self._changes['deleted_edges'])
        }


class BackupManager:
    """Manages backup and restore operations"""

    def __init__(self, storage: CodeGraphStorage, backup_dir: str):
        """
        Initialize backup manager

        Args:
            storage: CodeGraphStorage instance
            backup_dir: Directory to store backups
        """
        self.storage = storage
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.compressor = GraphCompressor(algorithm='lzma')

    def create_backup(self, name: str = None) -> str:
        """
        Create a full backup

        Args:
            name: Optional backup name

        Returns:
            Path to backup file
        """
        if name is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            name = f"backup_{timestamp}.bak"

        backup_path = self.backup_dir / name

        # Compress and save
        compressed = self.compressor.compress(self.storage)

        with open(backup_path, 'wb') as f:
            f.write(compressed)

        # Save metadata
        metadata = BackupMetadata(
            backup_path=str(backup_path),
            backup_type='full',
            timestamp=datetime.now().isoformat(),
            node_count=len(self.storage.nodes),
            edge_count=len(self.storage.edges),
            compressed_size=len(compressed)
        )

        self._save_metadata(backup_path, metadata)

        return str(backup_path)

    def create_incremental_backup(self, base_backup: str, name: str = None) -> str:
        """
        Create an incremental backup

        Args:
            base_backup: Path to base backup
            name: Optional backup name

        Returns:
            Path to incremental backup
        """
        # Load base backup to compare
        base_storage = CodeGraphStorage()
        self.restore(base_backup, target_storage=base_storage)

        # Find differences
        incremental = IncrementalBackup(base_backup)

        # Find new/updated nodes
        for node_id, node_data in self.storage.nodes.items():
            if node_id not in base_storage.nodes:
                incremental.track_node_addition(node_id, node_data)
            elif node_data != base_storage.nodes.get(node_id):
                incremental.track_node_update(node_id, node_data)

        # Find deleted nodes
        for node_id in base_storage.nodes:
            if node_id not in self.storage.nodes:
                incremental.track_node_deletion(node_id)

        # Save incremental backup
        if name is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            name = f"incremental_{timestamp}.bak"

        backup_path = self.backup_dir / name

        # Get changes for logging (unused in current implementation)
        _ = incremental.get_changes()
        compressed = self.compressor.compress(self.storage)

        # For simplicity, store full backup (in production, would store only changes)
        with open(backup_path, 'wb') as f:
            f.write(compressed)

        # Save metadata
        metadata = BackupMetadata(
            backup_path=str(backup_path),
            backup_type='incremental',
            timestamp=datetime.now().isoformat(),
            node_count=len(self.storage.nodes),
            edge_count=len(self.storage.edges),
            compressed_size=len(compressed),
            parent_backup=base_backup
        )

        self._save_metadata(backup_path, metadata)

        return str(backup_path)

    def restore(self, backup_path: str, target_storage: CodeGraphStorage = None) -> None:
        """
        Restore from backup

        Args:
            backup_path: Path to backup file
            target_storage: Optional target storage (defaults to self.storage)
        """
        if target_storage is None:
            target_storage = self.storage

        # Load compressed backup
        with open(backup_path, 'rb') as f:
            compressed = f.read()

        # Decompress
        restored_storage = self.compressor.decompress(compressed)

        # Copy to target storage
        target_storage.nodes = restored_storage.nodes
        target_storage.edges = restored_storage.edges
        target_storage.indexes = restored_storage.indexes
        target_storage.version_history = restored_storage.version_history
        target_storage._edge_from = restored_storage._edge_from
        target_storage._edge_to = restored_storage._edge_to

    def list_backups(self) -> list[dict[str, Any]]:
        """
        List all available backups

        Returns:
            List of backup information
        """
        backups = []

        for backup_file in self.backup_dir.glob('*.bak'):
            metadata = self._load_metadata(backup_file)
            if metadata:
                backups.append({
                    'path': str(backup_file),
                    'type': metadata.backup_type,
                    'timestamp': metadata.timestamp,
                    'node_count': metadata.node_count,
                    'edge_count': metadata.edge_count,
                    'size': metadata.compressed_size
                })

        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x['timestamp'], reverse=True)

        return backups

    def delete_backup(self, backup_path: str) -> None:
        """
        Delete a backup

        Args:
            backup_path: Path to backup file
        """
        backup_file = Path(backup_path)

        if backup_file.exists():
            backup_file.unlink()

        # Delete metadata
        metadata_file = backup_file.with_suffix('.meta')
        if metadata_file.exists():
            metadata_file.unlink()

    def get_metadata(self, backup_path: str) -> BackupMetadata | None:
        """
        Get metadata for a backup

        Args:
            backup_path: Path to backup file

        Returns:
            Backup metadata or None
        """
        return self._load_metadata(Path(backup_path))

    def _save_metadata(self, backup_path: Path, metadata: BackupMetadata) -> None:
        """Save backup metadata"""
        metadata_file = backup_path.with_suffix('.meta')

        metadata_dict = {
            'backup_path': metadata.backup_path,
            'backup_type': metadata.backup_type,
            'timestamp': metadata.timestamp,
            'node_count': metadata.node_count,
            'edge_count': metadata.edge_count,
            'compressed_size': metadata.compressed_size,
            'parent_backup': metadata.parent_backup
        }

        with open(metadata_file, 'w') as f:
            json.dump(metadata_dict, f, indent=2)

    def _load_metadata(self, backup_path: Path) -> BackupMetadata | None:
        """Load backup metadata"""
        metadata_file = backup_path.with_suffix('.meta')

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file) as f:
                data = json.load(f)

            return BackupMetadata(**data)
        except Exception:
            return None
