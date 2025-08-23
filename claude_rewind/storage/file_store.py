"""File-based storage for snapshot content with compression and deduplication."""

import hashlib
import json
import logging
import shutil
import zstandard as zstd
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime

from ..core.models import SnapshotId, ContentHash, FileState


logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Base exception for file storage operations."""
    pass


class CorruptionError(StorageError):
    """Exception raised when data corruption is detected."""
    pass


class FileStore:
    """Manages file-based storage of snapshot content with compression and deduplication."""
    
    def __init__(self, storage_root: Path, compression_level: int = 3):
        """Initialize file store.
        
        Args:
            storage_root: Root directory for snapshot storage
            compression_level: Zstandard compression level (1-22, default 3)
        """
        self.storage_root = storage_root
        self.compression_level = compression_level
        self.snapshots_dir = storage_root / "snapshots"
        self.content_dir = storage_root / "content"
        
        # Create directory structure
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize compressor
        self.compressor = zstd.ZstdCompressor(level=compression_level)
        self.decompressor = zstd.ZstdDecompressor()
        
        logger.debug(f"FileStore initialized at {storage_root}")
    
    def _get_content_path(self, content_hash: ContentHash) -> Path:
        """Get storage path for content by hash.
        
        Args:
            content_hash: SHA-256 hash of content
            
        Returns:
            Path to content file
        """
        # Use first 2 chars for directory structure to avoid too many files in one dir
        prefix = content_hash[:2]
        return self.content_dir / prefix / f"{content_hash}.zst"
    
    def _get_snapshot_dir(self, snapshot_id: SnapshotId) -> Path:
        """Get directory path for snapshot.
        
        Args:
            snapshot_id: Unique snapshot identifier
            
        Returns:
            Path to snapshot directory
        """
        return self.snapshots_dir / snapshot_id
    
    def _calculate_hash(self, content: bytes) -> ContentHash:
        """Calculate SHA-256 hash of content.
        
        Args:
            content: Content to hash
            
        Returns:
            SHA-256 hash as hex string
        """
        return hashlib.sha256(content).hexdigest()
    
    def _compress_content(self, content: bytes) -> bytes:
        """Compress content using Zstandard.
        
        Args:
            content: Content to compress
            
        Returns:
            Compressed content
        """
        try:
            return self.compressor.compress(content)
        except Exception as e:
            logger.error(f"Compression failed: {e}")
            raise StorageError(f"Failed to compress content: {e}")
    
    def _decompress_content(self, compressed_content: bytes) -> bytes:
        """Decompress content using Zstandard.
        
        Args:
            compressed_content: Compressed content
            
        Returns:
            Decompressed content
        """
        try:
            return self.decompressor.decompress(compressed_content)
        except Exception as e:
            logger.error(f"Decompression failed: {e}")
            raise StorageError(f"Failed to decompress content: {e}")
    
    def store_content(self, content: bytes) -> ContentHash:
        """Store content with deduplication and compression.
        
        Args:
            content: Content to store
            
        Returns:
            Content hash for retrieval
            
        Raises:
            StorageError: If storage operation fails
        """
        # Calculate hash for deduplication
        content_hash = self._calculate_hash(content)
        content_path = self._get_content_path(content_hash)
        
        # Skip if content already exists (deduplication)
        if content_path.exists():
            logger.debug(f"Content already exists: {content_hash}")
            return content_hash
        
        try:
            # Create directory if needed
            content_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Compress and store content
            compressed_content = self._compress_content(content)
            
            # Write to temporary file first, then rename for atomicity
            temp_path = content_path.with_suffix('.tmp')
            with open(temp_path, 'wb') as f:
                f.write(compressed_content)
            
            # Atomic rename
            temp_path.rename(content_path)
            
            logger.debug(f"Stored content: {content_hash} "
                        f"({len(content)} -> {len(compressed_content)} bytes)")
            
            return content_hash
            
        except Exception as e:
            # Clean up temporary file if it exists
            temp_path = content_path.with_suffix('.tmp')
            if temp_path.exists():
                temp_path.unlink()
            
            logger.error(f"Failed to store content: {e}")
            raise StorageError(f"Failed to store content: {e}")
    
    def retrieve_content(self, content_hash: ContentHash) -> bytes:
        """Retrieve content by hash.
        
        Args:
            content_hash: Content hash
            
        Returns:
            Decompressed content
            
        Raises:
            StorageError: If content not found or corrupted
        """
        content_path = self._get_content_path(content_hash)
        
        if not content_path.exists():
            raise StorageError(f"Content not found: {content_hash}")
        
        try:
            # Read compressed content
            with open(content_path, 'rb') as f:
                compressed_content = f.read()
            
            # Decompress content
            content = self._decompress_content(compressed_content)
            
            # Verify integrity
            actual_hash = self._calculate_hash(content)
            if actual_hash != content_hash:
                raise CorruptionError(
                    f"Content corruption detected: expected {content_hash}, "
                    f"got {actual_hash}"
                )
            
            return content
            
        except CorruptionError:
            raise
        except Exception as e:
            logger.error(f"Failed to retrieve content {content_hash}: {e}")
            raise StorageError(f"Failed to retrieve content: {e}")
    
    def content_exists(self, content_hash: ContentHash) -> bool:
        """Check if content exists in storage.
        
        Args:
            content_hash: Content hash to check
            
        Returns:
            True if content exists
        """
        return self._get_content_path(content_hash).exists()
    
    def create_snapshot(self, snapshot_id: SnapshotId, 
                       file_states: Dict[Path, FileState]) -> Dict[str, Any]:
        """Create snapshot with file states.
        
        Args:
            snapshot_id: Unique snapshot identifier
            file_states: Dictionary of file paths to file states
            
        Returns:
            Snapshot manifest with metadata
            
        Raises:
            StorageError: If snapshot creation fails
        """
        snapshot_dir = self._get_snapshot_dir(snapshot_id)
        
        if snapshot_dir.exists():
            raise StorageError(f"Snapshot already exists: {snapshot_id}")
        
        try:
            # Create snapshot directory
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            
            # Create manifest
            manifest = {
                'snapshot_id': snapshot_id,
                'created_at': datetime.now().isoformat(),
                'file_count': len(file_states),
                'files': {},
                'total_size': 0,
                'compressed_size': 0
            }
            
            total_size = 0
            compressed_size = 0
            
            # Process each file
            for file_path, file_state in file_states.items():
                if not file_state.exists:
                    # File was deleted, just record metadata
                    manifest['files'][str(file_path)] = {
                        'exists': False,
                        'content_hash': None,
                        'size': 0,
                        'modified_time': file_state.modified_time.isoformat(),
                        'permissions': file_state.permissions
                    }
                    continue
                
                # Read file content
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")
                    continue
                
                # Store content (with deduplication)
                content_hash = self.store_content(content)
                
                # Add to manifest
                manifest['files'][str(file_path)] = {
                    'exists': True,
                    'content_hash': content_hash,
                    'size': len(content),
                    'modified_time': file_state.modified_time.isoformat(),
                    'permissions': file_state.permissions
                }
                
                total_size += len(content)
                
                # Calculate compressed size (approximate)
                content_path = self._get_content_path(content_hash)
                if content_path.exists():
                    compressed_size += content_path.stat().st_size
            
            manifest['total_size'] = total_size
            manifest['compressed_size'] = compressed_size
            
            # Write manifest
            manifest_path = snapshot_dir / "manifest.json"
            with open(manifest_path, 'w') as f:
                json.dump(manifest, f, indent=2)
            
            logger.info(f"Created snapshot {snapshot_id} with {len(file_states)} files")
            return manifest
            
        except Exception as e:
            # Clean up on failure
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir, ignore_errors=True)
            
            logger.error(f"Failed to create snapshot {snapshot_id}: {e}")
            raise StorageError(f"Failed to create snapshot: {e}")
    
    def get_snapshot_manifest(self, snapshot_id: SnapshotId) -> Dict[str, Any]:
        """Get snapshot manifest.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Snapshot manifest
            
        Raises:
            StorageError: If snapshot not found
        """
        manifest_path = self._get_snapshot_dir(snapshot_id) / "manifest.json"
        
        if not manifest_path.exists():
            raise StorageError(f"Snapshot not found: {snapshot_id}")
        
        try:
            with open(manifest_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read manifest for {snapshot_id}: {e}")
            raise StorageError(f"Failed to read snapshot manifest: {e}")
    
    def restore_file(self, snapshot_id: SnapshotId, file_path: Path, 
                    target_path: Optional[Path] = None) -> bool:
        """Restore a file from snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            file_path: Path of file to restore
            target_path: Target path for restoration (defaults to original path)
            
        Returns:
            True if file was restored, False if file didn't exist in snapshot
            
        Raises:
            StorageError: If restoration fails
        """
        manifest = self.get_snapshot_manifest(snapshot_id)
        file_key = str(file_path)
        
        if file_key not in manifest['files']:
            return False
        
        file_info = manifest['files'][file_key]
        target = target_path or file_path
        
        try:
            if not file_info['exists']:
                # File was deleted in snapshot, remove if it exists
                if target.exists():
                    target.unlink()
                return True
            
            # Retrieve and write content
            content = self.retrieve_content(file_info['content_hash'])
            
            # Create parent directories
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            with open(target, 'wb') as f:
                f.write(content)
            
            # Restore permissions
            target.chmod(file_info['permissions'])
            
            logger.debug(f"Restored {file_path} from snapshot {snapshot_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore {file_path}: {e}")
            raise StorageError(f"Failed to restore file: {e}")
    
    def delete_snapshot(self, snapshot_id: SnapshotId) -> bool:
        """Delete snapshot and its files.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            True if snapshot was deleted
        """
        snapshot_dir = self._get_snapshot_dir(snapshot_id)
        
        if not snapshot_dir.exists():
            return False
        
        try:
            shutil.rmtree(snapshot_dir)
            logger.info(f"Deleted snapshot: {snapshot_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete snapshot {snapshot_id}: {e}")
            raise StorageError(f"Failed to delete snapshot: {e}")
    
    def list_snapshots(self) -> List[SnapshotId]:
        """List all available snapshots.
        
        Returns:
            List of snapshot IDs
        """
        snapshots = []
        
        if not self.snapshots_dir.exists():
            return snapshots
        
        for snapshot_dir in self.snapshots_dir.iterdir():
            if snapshot_dir.is_dir() and (snapshot_dir / "manifest.json").exists():
                snapshots.append(snapshot_dir.name)
        
        return sorted(snapshots)
    
    def cleanup_orphaned_content(self) -> int:
        """Remove content files that are not referenced by any snapshot.
        
        Returns:
            Number of orphaned files removed
        """
        # Get all content hashes referenced by snapshots
        referenced_hashes: Set[ContentHash] = set()
        
        for snapshot_id in self.list_snapshots():
            try:
                manifest = self.get_snapshot_manifest(snapshot_id)
                for file_info in manifest['files'].values():
                    if file_info['exists'] and file_info['content_hash']:
                        referenced_hashes.add(file_info['content_hash'])
            except Exception as e:
                logger.warning(f"Failed to read manifest for {snapshot_id}: {e}")
                continue
        
        # Find orphaned content files
        orphaned_count = 0
        
        if not self.content_dir.exists():
            return orphaned_count
        
        for prefix_dir in self.content_dir.iterdir():
            if not prefix_dir.is_dir():
                continue
            
            for content_file in prefix_dir.iterdir():
                if not content_file.name.endswith('.zst'):
                    continue
                
                content_hash = content_file.stem
                if content_hash not in referenced_hashes:
                    try:
                        content_file.unlink()
                        orphaned_count += 1
                        logger.debug(f"Removed orphaned content: {content_hash}")
                    except Exception as e:
                        logger.warning(f"Failed to remove {content_file}: {e}")
        
        logger.info(f"Cleaned up {orphaned_count} orphaned content files")
        return orphaned_count
    
    def validate_integrity(self, snapshot_id: SnapshotId) -> Tuple[bool, List[str]]:
        """Validate integrity of snapshot and its content.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            manifest = self.get_snapshot_manifest(snapshot_id)
        except StorageError as e:
            return False, [f"Failed to read manifest: {e}"]
        
        # Validate each file's content
        for file_path, file_info in manifest['files'].items():
            if not file_info['exists']:
                continue
            
            content_hash = file_info['content_hash']
            if not content_hash:
                errors.append(f"Missing content hash for {file_path}")
                continue
            
            # Check if content file exists
            if not self.content_exists(content_hash):
                errors.append(f"Missing content file for {file_path}: {content_hash}")
                continue
            
            # Validate content integrity
            try:
                content = self.retrieve_content(content_hash)
                if len(content) != file_info['size']:
                    errors.append(f"Size mismatch for {file_path}: "
                                f"expected {file_info['size']}, got {len(content)}")
            except (StorageError, CorruptionError) as e:
                errors.append(f"Content validation failed for {file_path}: {e}")
        
        is_valid = len(errors) == 0
        return is_valid, errors
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics.
        
        Returns:
            Dictionary with storage statistics
        """
        stats = {
            'snapshot_count': 0,
            'total_files': 0,
            'total_size': 0,
            'compressed_size': 0,
            'content_files': 0,
            'compression_ratio': 0.0
        }
        
        # Count snapshots and calculate sizes
        total_size = 0
        compressed_size = 0
        total_files = 0
        
        for snapshot_id in self.list_snapshots():
            try:
                manifest = self.get_snapshot_manifest(snapshot_id)
                stats['snapshot_count'] += 1
                total_files += manifest.get('file_count', 0)
                total_size += manifest.get('total_size', 0)
                compressed_size += manifest.get('compressed_size', 0)
            except Exception as e:
                logger.warning(f"Failed to read stats for {snapshot_id}: {e}")
        
        # Count content files
        content_files = 0
        if self.content_dir.exists():
            for prefix_dir in self.content_dir.iterdir():
                if prefix_dir.is_dir():
                    content_files += len([f for f in prefix_dir.iterdir() 
                                        if f.name.endswith('.zst')])
        
        stats.update({
            'total_files': total_files,
            'total_size': total_size,
            'compressed_size': compressed_size,
            'content_files': content_files,
            'compression_ratio': compressed_size / total_size if total_size > 0 else 0.0
        })
        
        return stats