"""Unit tests for file-based storage system."""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, mock_open

from claude_rewind.storage.file_store import FileStore, StorageError, CorruptionError
from claude_rewind.core.models import FileState


class TestFileStore:
    """Test cases for FileStore."""
    
    @pytest.fixture
    def temp_storage_root(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    @pytest.fixture
    def file_store(self, temp_storage_root):
        """Create FileStore instance."""
        return FileStore(temp_storage_root)
    
    @pytest.fixture
    def sample_content(self):
        """Sample file content for testing."""
        return b"def hello_world():\n    print('Hello, World!')\n"
    
    @pytest.fixture
    def sample_file_states(self, temp_storage_root):
        """Create sample file states for testing."""
        # Create test files
        test_file1 = temp_storage_root / "test1.py"
        test_file2 = temp_storage_root / "test2.py"
        
        test_file1.write_text("print('test1')")
        test_file2.write_text("print('test2')")
        
        return {
            test_file1: FileState(
                path=test_file1,
                content_hash="hash1",
                size=test_file1.stat().st_size,
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            ),
            test_file2: FileState(
                path=test_file2,
                content_hash="hash2",
                size=test_file2.stat().st_size,
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            )
        }
    
    def test_initialization(self, temp_storage_root):
        """Test FileStore initialization."""
        file_store = FileStore(temp_storage_root)
        
        # Check directory structure
        assert file_store.storage_root == temp_storage_root
        assert file_store.snapshots_dir.exists()
        assert file_store.content_dir.exists()
        assert file_store.compression_level == 3
    
    def test_custom_compression_level(self, temp_storage_root):
        """Test FileStore with custom compression level."""
        file_store = FileStore(temp_storage_root, compression_level=9)
        assert file_store.compression_level == 9
    
    def test_content_path_generation(self, file_store):
        """Test content path generation."""
        content_hash = "abcdef1234567890"
        path = file_store._get_content_path(content_hash)
        
        expected = file_store.content_dir / "ab" / f"{content_hash}.zst"
        assert path == expected
    
    def test_hash_calculation(self, file_store, sample_content):
        """Test content hash calculation."""
        hash1 = file_store._calculate_hash(sample_content)
        hash2 = file_store._calculate_hash(sample_content)
        
        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
        
        # Different content should produce different hash
        different_content = b"different content"
        hash3 = file_store._calculate_hash(different_content)
        assert hash1 != hash3
    
    def test_compression_decompression(self, file_store, sample_content):
        """Test content compression and decompression."""
        compressed = file_store._compress_content(sample_content)
        decompressed = file_store._decompress_content(compressed)
        
        assert decompressed == sample_content
        # Note: Small content might not compress well, so just verify it works
    
    def test_store_content(self, file_store, sample_content):
        """Test content storage."""
        content_hash = file_store.store_content(sample_content)
        
        # Check hash format
        assert len(content_hash) == 64
        
        # Check file was created
        content_path = file_store._get_content_path(content_hash)
        assert content_path.exists()
        
        # Verify content can be retrieved
        retrieved = file_store.retrieve_content(content_hash)
        assert retrieved == sample_content
    
    def test_content_deduplication(self, file_store, sample_content):
        """Test that identical content is deduplicated."""
        hash1 = file_store.store_content(sample_content)
        hash2 = file_store.store_content(sample_content)
        
        # Should return same hash
        assert hash1 == hash2
        
        # Should only create one file
        content_path = file_store._get_content_path(hash1)
        assert content_path.exists()
    
    def test_retrieve_nonexistent_content(self, file_store):
        """Test retrieving non-existent content."""
        with pytest.raises(StorageError, match="Content not found"):
            file_store.retrieve_content("nonexistent_hash")
    
    def test_content_exists(self, file_store, sample_content):
        """Test content existence check."""
        content_hash = file_store.store_content(sample_content)
        
        assert file_store.content_exists(content_hash)
        assert not file_store.content_exists("nonexistent_hash")
    
    def test_create_snapshot(self, file_store, sample_file_states):
        """Test snapshot creation."""
        snapshot_id = "test_snapshot_001"
        
        manifest = file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # Check manifest structure
        assert manifest['snapshot_id'] == snapshot_id
        assert manifest['file_count'] == len(sample_file_states)
        assert 'created_at' in manifest
        assert 'files' in manifest
        assert manifest['total_size'] > 0
        
        # Check snapshot directory exists
        snapshot_dir = file_store._get_snapshot_dir(snapshot_id)
        assert snapshot_dir.exists()
        assert (snapshot_dir / "manifest.json").exists()
    
    def test_create_duplicate_snapshot(self, file_store, sample_file_states):
        """Test creating duplicate snapshot raises error."""
        snapshot_id = "test_snapshot_001"
        
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        with pytest.raises(StorageError, match="Snapshot already exists"):
            file_store.create_snapshot(snapshot_id, sample_file_states)
    
    def test_get_snapshot_manifest(self, file_store, sample_file_states):
        """Test retrieving snapshot manifest."""
        snapshot_id = "test_snapshot_001"
        
        original_manifest = file_store.create_snapshot(snapshot_id, sample_file_states)
        retrieved_manifest = file_store.get_snapshot_manifest(snapshot_id)
        
        assert retrieved_manifest == original_manifest
    
    def test_get_nonexistent_snapshot_manifest(self, file_store):
        """Test retrieving non-existent snapshot manifest."""
        with pytest.raises(StorageError, match="Snapshot not found"):
            file_store.get_snapshot_manifest("nonexistent")
    
    def test_restore_file(self, file_store, sample_file_states, temp_storage_root):
        """Test file restoration from snapshot."""
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # Get a test file
        test_file = list(sample_file_states.keys())[0]
        original_content = test_file.read_bytes()
        
        # Delete the file
        test_file.unlink()
        assert not test_file.exists()
        
        # Restore the file
        restored = file_store.restore_file(snapshot_id, test_file)
        assert restored is True
        assert test_file.exists()
        
        # Verify content
        restored_content = test_file.read_bytes()
        assert restored_content == original_content
    
    def test_restore_nonexistent_file(self, file_store, sample_file_states):
        """Test restoring file that doesn't exist in snapshot."""
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        nonexistent_file = Path("nonexistent.py")
        restored = file_store.restore_file(snapshot_id, nonexistent_file)
        assert restored is False
    
    def test_restore_deleted_file(self, file_store, temp_storage_root):
        """Test restoring file that was deleted in snapshot."""
        # Create file state for deleted file
        deleted_file = temp_storage_root / "deleted.py"
        deleted_file.write_text("to be deleted")
        
        file_states = {
            deleted_file: FileState(
                path=deleted_file,
                content_hash="",
                size=0,
                modified_time=datetime.now(),
                permissions=0o644,
                exists=False  # File was deleted
            )
        }
        
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, file_states)
        
        # File should be removed during restoration
        restored = file_store.restore_file(snapshot_id, deleted_file)
        assert restored is True
        assert not deleted_file.exists()
    
    def test_delete_snapshot(self, file_store, sample_file_states):
        """Test snapshot deletion."""
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # Verify snapshot exists
        snapshot_dir = file_store._get_snapshot_dir(snapshot_id)
        assert snapshot_dir.exists()
        
        # Delete snapshot
        deleted = file_store.delete_snapshot(snapshot_id)
        assert deleted is True
        assert not snapshot_dir.exists()
        
        # Try deleting again
        deleted_again = file_store.delete_snapshot(snapshot_id)
        assert deleted_again is False
    
    def test_list_snapshots(self, file_store, sample_file_states):
        """Test listing snapshots."""
        # Initially empty
        snapshots = file_store.list_snapshots()
        assert snapshots == []
        
        # Create snapshots
        snapshot_ids = ["snapshot_001", "snapshot_002", "snapshot_003"]
        for snapshot_id in snapshot_ids:
            file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # List snapshots
        snapshots = file_store.list_snapshots()
        assert len(snapshots) == 3
        assert set(snapshots) == set(snapshot_ids)
        assert snapshots == sorted(snapshot_ids)  # Should be sorted
    
    def test_cleanup_orphaned_content(self, file_store, sample_file_states):
        """Test cleanup of orphaned content files."""
        # Create snapshot
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # Store additional content that won't be referenced
        orphaned_content = b"orphaned content"
        orphaned_hash = file_store.store_content(orphaned_content)
        
        # Verify orphaned content exists
        assert file_store.content_exists(orphaned_hash)
        
        # Delete snapshot to make content orphaned
        file_store.delete_snapshot(snapshot_id)
        
        # Cleanup orphaned content
        cleaned_count = file_store.cleanup_orphaned_content()
        
        # All content should be cleaned up since snapshot was deleted
        assert cleaned_count > 0
        assert not file_store.content_exists(orphaned_hash)
    
    def test_validate_integrity_valid(self, file_store, sample_file_states):
        """Test integrity validation for valid snapshot."""
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        is_valid, errors = file_store.validate_integrity(snapshot_id)
        assert is_valid is True
        assert errors == []
    
    def test_validate_integrity_missing_content(self, file_store, sample_file_states):
        """Test integrity validation with missing content."""
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # Remove a content file
        manifest = file_store.get_snapshot_manifest(snapshot_id)
        first_file_info = list(manifest['files'].values())[0]
        if first_file_info['exists']:
            content_hash = first_file_info['content_hash']
            content_path = file_store._get_content_path(content_hash)
            content_path.unlink()
        
        is_valid, errors = file_store.validate_integrity(snapshot_id)
        assert is_valid is False
        assert len(errors) > 0
        assert "Missing content file" in errors[0]
    
    def test_validate_integrity_corrupted_content(self, file_store, sample_file_states):
        """Test integrity validation with corrupted content."""
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # Corrupt a content file
        manifest = file_store.get_snapshot_manifest(snapshot_id)
        first_file_info = list(manifest['files'].values())[0]
        if first_file_info['exists']:
            content_hash = first_file_info['content_hash']
            content_path = file_store._get_content_path(content_hash)
            
            # Write corrupted data
            with open(content_path, 'wb') as f:
                f.write(b"corrupted data")
        
        is_valid, errors = file_store.validate_integrity(snapshot_id)
        assert is_valid is False
        assert len(errors) > 0
    
    def test_get_storage_stats(self, file_store, sample_file_states):
        """Test storage statistics."""
        # Initially empty
        stats = file_store.get_storage_stats()
        assert stats['snapshot_count'] == 0
        assert stats['total_files'] == 0
        assert stats['content_files'] == 0
        
        # Create snapshot
        snapshot_id = "test_snapshot_001"
        file_store.create_snapshot(snapshot_id, sample_file_states)
        
        # Check updated stats
        stats = file_store.get_storage_stats()
        assert stats['snapshot_count'] == 1
        assert stats['total_files'] == len(sample_file_states)
        assert stats['total_size'] > 0
        assert stats['compressed_size'] > 0
        assert stats['content_files'] > 0
        assert stats['compression_ratio'] >= 0  # Ratio can be > 1 for small files
    
    def test_compression_error_handling(self, file_store):
        """Test compression error handling."""
        with patch.object(file_store, '_compress_content', side_effect=Exception("Compression failed")):
            with pytest.raises(StorageError, match="Failed to store content"):
                file_store.store_content(b"test content")
    
    def test_decompression_error_handling(self, file_store, sample_content):
        """Test decompression error handling."""
        content_hash = file_store.store_content(sample_content)
        
        with patch.object(file_store, '_decompress_content', side_effect=Exception("Decompression failed")):
            with pytest.raises(StorageError, match="Failed to retrieve content"):
                file_store.retrieve_content(content_hash)
    
    def test_corruption_detection(self, file_store, sample_content):
        """Test content corruption detection."""
        content_hash = file_store.store_content(sample_content)
        content_path = file_store._get_content_path(content_hash)
        
        # Corrupt the stored content by modifying hash calculation
        with patch.object(file_store, '_calculate_hash', return_value="wrong_hash"):
            with pytest.raises(CorruptionError, match="Content corruption detected"):
                file_store.retrieve_content(content_hash)
    
    def test_atomic_content_storage(self, file_store, sample_content):
        """Test that content storage is atomic."""
        # Mock file write to fail after creating temp file
        original_rename = Path.rename
        
        def failing_rename(self, target):
            if str(self).endswith('.tmp'):
                raise OSError("Simulated failure")
            return original_rename(self, target)
        
        with patch.object(Path, 'rename', failing_rename):
            with pytest.raises(StorageError):
                file_store.store_content(sample_content)
        
        # Verify no partial files remain
        content_hash = file_store._calculate_hash(sample_content)
        content_path = file_store._get_content_path(content_hash)
        temp_path = content_path.with_suffix('.tmp')
        
        assert not content_path.exists()
        assert not temp_path.exists()
    
    def test_file_read_error_handling(self, file_store, temp_storage_root):
        """Test handling of file read errors during snapshot creation."""
        # Create a file that will cause read error
        problem_file = temp_storage_root / "problem.py"
        problem_file.write_text("test content")
        
        file_states = {
            problem_file: FileState(
                path=problem_file,
                content_hash="hash1",
                size=100,
                modified_time=datetime.now(),
                permissions=0o644,
                exists=True
            )
        }
        
        # Mock only the file reading part, not all open calls
        original_open = open
        def mock_open_func(file_path, mode='r', *args, **kwargs):
            if str(file_path) == str(problem_file) and mode == 'rb':
                raise PermissionError("Access denied")
            return original_open(file_path, mode, *args, **kwargs)
        
        with patch('builtins.open', side_effect=mock_open_func):
            # Should not raise error, just skip the file
            manifest = file_store.create_snapshot("test_snapshot", file_states)
            
            # File should not be in manifest
            assert str(problem_file) not in manifest['files']


if __name__ == "__main__":
    pytest.main([__file__])