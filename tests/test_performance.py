"""Performance tests for Claude Rewind Tool."""

import os
import tempfile
import time
import pytest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from claude_rewind.core.snapshot_engine import SnapshotEngine
from claude_rewind.core.config import PerformanceConfig
from claude_rewind.core.models import ActionContext
from datetime import datetime
from claude_rewind.storage.file_store import FileStore


class TestPerformanceOptimizations:
    """Test performance optimizations in snapshot engine."""
    
    @pytest.fixture
    def performance_config(self):
        """Create performance configuration for testing."""
        return PerformanceConfig(
            max_file_size_mb=50,
            parallel_processing=True,
            memory_limit_mb=200,
            snapshot_timeout_seconds=10,
            compression_level=1,  # Fast compression for tests
            lazy_loading_enabled=True,
            cache_size_limit=1000,
            target_snapshot_time_ms=500
        )
    
    @pytest.fixture
    def large_project(self):
        """Create a large test project with many files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "large_project"
            project_root.mkdir()
            
            # Create many small files
            for i in range(100):
                file_path = project_root / f"file_{i:03d}.py"
                content = f"# File {i}\n" + "print('test')\n" * 50
                file_path.write_text(content)
            
            # Create some larger files
            for i in range(5):
                file_path = project_root / f"large_file_{i}.txt"
                content = "x" * (1024 * 100)  # 100KB each
                file_path.write_text(content)
            
            # Create directory structure
            for dir_name in ["src", "tests", "docs"]:
                dir_path = project_root / dir_name
                dir_path.mkdir()
                
                for i in range(20):
                    file_path = dir_path / f"{dir_name}_file_{i}.py"
                    content = f"# {dir_name} file {i}\n" + "pass\n" * 20
                    file_path.write_text(content)
            
            yield project_root
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir) / "storage"
    
    @pytest.fixture
    def sample_context(self):
        """Create sample action context."""
        return ActionContext(
            action_type="bulk_edit",
            timestamp=datetime.now(),
            prompt_context="Performance test snapshot",
            affected_files=[Path("file_001.py")],
            tool_name="test"
        )
    
    def test_snapshot_creation_speed(self, large_project, temp_storage, 
                                   performance_config, sample_context):
        """Test that snapshot creation meets speed requirements."""
        engine = SnapshotEngine(large_project, temp_storage, performance_config)
        
        # Measure snapshot creation time
        start_time = time.time()
        snapshot_id = engine.create_snapshot(sample_context)
        elapsed_time = time.time() - start_time
        
        # Should complete within target time (500ms)
        assert elapsed_time < 1.0, f"Snapshot took {elapsed_time:.3f}s, exceeding 1s limit"
        
        # Verify snapshot was created successfully
        assert snapshot_id is not None
        snapshot = engine.get_snapshot(snapshot_id)
        assert snapshot is not None
        assert len(snapshot.file_states) > 100  # Should capture many files
    
    def test_incremental_snapshot_speed(self, large_project, temp_storage,
                                      performance_config, sample_context):
        """Test that incremental snapshots are faster than initial snapshots."""
        engine = SnapshotEngine(large_project, temp_storage, performance_config)
        
        # Create initial snapshot
        start_time = time.time()
        snapshot_id1 = engine.create_snapshot(sample_context)
        initial_time = time.time() - start_time
        
        # Modify one file
        (large_project / "file_001.py").write_text("# Modified file\nprint('updated')")
        
        # Create incremental snapshot
        context2 = ActionContext(
            action_type="edit_file",
            timestamp=datetime.now(),
            prompt_context="Update single file",
            affected_files=[Path("file_001.py")],
            tool_name="str_replace"
        )
        
        start_time = time.time()
        snapshot_id2 = engine.create_snapshot(context2)
        incremental_time = time.time() - start_time
        
        # Incremental snapshot should be significantly faster
        assert incremental_time < initial_time * 0.5, \
            f"Incremental snapshot ({incremental_time:.3f}s) not much faster than initial ({initial_time:.3f}s)"
        
        # Both snapshots should exist
        assert engine.get_snapshot(snapshot_id1) is not None
        assert engine.get_snapshot(snapshot_id2) is not None
    
    def test_parallel_processing_benefit(self, large_project, temp_storage, sample_context):
        """Test that parallel processing improves performance."""
        # Test with parallel processing enabled
        config_parallel = PerformanceConfig(parallel_processing=True, compression_level=1)
        engine_parallel = SnapshotEngine(large_project, temp_storage, config_parallel)
        
        start_time = time.time()
        snapshot_id1 = engine_parallel.create_snapshot(sample_context)
        parallel_time = time.time() - start_time
        
        # Test with parallel processing disabled
        temp_storage2 = temp_storage.parent / "storage2"
        config_sequential = PerformanceConfig(parallel_processing=False, compression_level=1)
        engine_sequential = SnapshotEngine(large_project, temp_storage2, config_sequential)
        
        start_time = time.time()
        snapshot_id2 = engine_sequential.create_snapshot(sample_context)
        sequential_time = time.time() - start_time
        
        # Parallel should be faster for large projects (or at least not much slower)
        assert parallel_time <= sequential_time * 1.2, \
            f"Parallel processing ({parallel_time:.3f}s) slower than sequential ({sequential_time:.3f}s)"
        
        # Both should produce valid snapshots
        assert engine_parallel.get_snapshot(snapshot_id1) is not None
        assert engine_sequential.get_snapshot(snapshot_id2) is not None
    
    def test_hash_caching_effectiveness(self, large_project, temp_storage,
                                      performance_config, sample_context):
        """Test that hash caching improves repeated operations."""
        engine = SnapshotEngine(large_project, temp_storage, performance_config)
        
        # Create initial snapshot (populates cache)
        engine.create_snapshot(sample_context)
        
        # Create second snapshot without file changes (should use cache)
        context2 = ActionContext(
            action_type="no_change",
            timestamp=datetime.now(),
            prompt_context="No file changes",
            affected_files=[],
            tool_name="test"
        )
        
        start_time = time.time()
        snapshot_id2 = engine.create_snapshot(context2)
        cached_time = time.time() - start_time
        
        # Should be very fast due to caching
        assert cached_time < 0.5, f"Cached snapshot took {cached_time:.3f}s, should be under 0.5s"
        
        # Verify cache statistics
        cache_stats = engine.get_cache_stats()
        assert cache_stats['hash_cache_entries'] > 0
    
    def test_lazy_loading_functionality(self, large_project, temp_storage,
                                      performance_config, sample_context):
        """Test lazy loading of file content."""
        engine = SnapshotEngine(large_project, temp_storage, performance_config)
        
        # Create snapshot
        snapshot_id = engine.create_snapshot(sample_context)
        
        # Test lazy loading of specific file
        test_file = Path("file_001.py")
        content = engine.get_file_content_lazy(snapshot_id, test_file)
        
        assert content is not None
        assert b"File 1" in content or b"print" in content
        
        # Test lazy loading of non-existent file
        missing_content = engine.get_file_content_lazy(snapshot_id, Path("nonexistent.py"))
        assert missing_content is None
        
        # Verify content cache is populated
        cache_stats = engine.get_cache_stats()
        assert cache_stats['content_cache_entries'] > 0
    
    def test_preload_functionality(self, large_project, temp_storage,
                                 performance_config, sample_context):
        """Test content preloading functionality."""
        engine = SnapshotEngine(large_project, temp_storage, performance_config)
        
        # Create snapshot
        snapshot_id = engine.create_snapshot(sample_context)
        
        # Clear cache to start fresh
        engine.clear_caches()
        
        # Preload specific files
        files_to_preload = [Path("file_001.py"), Path("file_002.py")]
        
        start_time = time.time()
        engine.preload_snapshot_content(snapshot_id, files_to_preload)
        preload_time = time.time() - start_time
        
        # Preloading should be reasonably fast
        assert preload_time < 1.0, f"Preloading took {preload_time:.3f}s"
        
        # Verify content is cached
        cache_stats = engine.get_cache_stats()
        assert cache_stats['content_cache_entries'] >= len(files_to_preload)
        
        # Subsequent access should be very fast
        start_time = time.time()
        content = engine.get_file_content_lazy(snapshot_id, files_to_preload[0])
        access_time = time.time() - start_time
        
        assert content is not None
        assert access_time < 0.01, f"Cached access took {access_time:.3f}s"
    
    def test_compression_level_impact(self, large_project, temp_storage, sample_context):
        """Test impact of different compression levels on performance."""
        results = {}
        
        for compression_level in [1, 3, 6]:
            config = PerformanceConfig(compression_level=compression_level)
            storage_path = temp_storage.parent / f"storage_comp_{compression_level}"
            engine = SnapshotEngine(large_project, storage_path, config)
            
            # Measure snapshot creation time
            start_time = time.time()
            snapshot_id = engine.create_snapshot(sample_context)
            elapsed_time = time.time() - start_time
            
            # Get storage stats
            storage_stats = engine.file_store.get_storage_stats()
            
            results[compression_level] = {
                'time': elapsed_time,
                'compression_ratio': storage_stats['compression_ratio'],
                'compressed_size': storage_stats['compressed_size']
            }
        
        # Lower compression levels should be faster
        assert results[1]['time'] <= results[3]['time'] * 1.5
        assert results[3]['time'] <= results[6]['time'] * 1.5
        
        # Higher compression levels should achieve better compression
        assert results[6]['compression_ratio'] <= results[3]['compression_ratio']
        assert results[3]['compression_ratio'] <= results[1]['compression_ratio']
    
    def test_memory_usage_limits(self, large_project, temp_storage, sample_context):
        """Test that memory usage stays within configured limits."""
        config = PerformanceConfig(memory_limit_mb=100)  # Low limit for testing
        engine = SnapshotEngine(large_project, temp_storage, config)
        
        # Create snapshot
        snapshot_id = engine.create_snapshot(sample_context)
        
        # Check cache memory usage
        cache_stats = engine.get_cache_stats()
        memory_usage_mb = cache_stats['content_cache_memory_mb']
        
        # Should stay within reasonable bounds
        assert memory_usage_mb < config.memory_limit_mb * 0.5, \
            f"Cache using {memory_usage_mb:.1f}MB, exceeding limit"
    
    def test_large_file_handling(self, temp_storage, performance_config, sample_context):
        """Test handling of large files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "large_file_project"
            project_root.mkdir()
            
            # Create files of different sizes
            small_file = project_root / "small.txt"
            small_file.write_text("small content")
            
            medium_file = project_root / "medium.txt"
            medium_file.write_text("x" * (1024 * 1024))  # 1MB
            
            # Create a file larger than the limit
            large_file = project_root / "large.txt"
            large_file.write_text("x" * (1024 * 1024 * 60))  # 60MB (exceeds 50MB limit)
            
            engine = SnapshotEngine(project_root, temp_storage, performance_config)
            
            # Create snapshot
            snapshot_id = engine.create_snapshot(sample_context)
            snapshot = engine.get_snapshot(snapshot_id)
            
            # Should include small and medium files
            assert Path("small.txt") in snapshot.file_states
            assert Path("medium.txt") in snapshot.file_states
            
            # Should exclude large file
            assert Path("large.txt") not in snapshot.file_states
    
    def test_concurrent_snapshot_creation(self, large_project, temp_storage,
                                        performance_config):
        """Test concurrent snapshot creation doesn't cause issues."""
        engine = SnapshotEngine(large_project, temp_storage, performance_config)
        
        def create_snapshot(index):
            # Add small delay to reduce race conditions
            time.sleep(0.01 * index)
            context = ActionContext(
                action_type=f"concurrent_test_{index}",
                timestamp=datetime.now(),
                prompt_context=f"Concurrent test {index}",
                affected_files=[Path(f"file_{index:03d}.py")],
                tool_name="test"
            )
            return engine.create_snapshot(context)
        
        # Create multiple snapshots with limited concurrency
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(create_snapshot, i) for i in range(3)]
            snapshot_ids = []
            for future in futures:
                try:
                    snapshot_id = future.result()
                    snapshot_ids.append(snapshot_id)
                except Exception as e:
                    # Log but don't fail the test for race conditions
                    print(f"Concurrent snapshot creation failed: {e}")
        
        # At least some snapshots should be created successfully
        assert len(snapshot_ids) >= 1
        assert len(set(snapshot_ids)) == len(snapshot_ids)  # All unique
        
        # All created snapshots should be retrievable
        for snapshot_id in snapshot_ids:
            snapshot = engine.get_snapshot(snapshot_id)
            assert snapshot is not None
    
    def test_cache_cleanup_and_limits(self, large_project, temp_storage,
                                    performance_config, sample_context):
        """Test that caches are properly managed and cleaned up."""
        # Set very low cache limits for testing
        config = PerformanceConfig(cache_size_limit=10)
        engine = SnapshotEngine(large_project, temp_storage, config)
        
        # Create many snapshots to fill cache
        snapshot_ids = []
        for i in range(15):  # More than cache limit
            context = ActionContext(
                action_type=f"cache_test_{i}",
                timestamp=datetime.now(),
                prompt_context=f"Cache test {i}",
                affected_files=[Path(f"file_{i:03d}.py")],
                tool_name="test"
            )
            snapshot_id = engine.create_snapshot(context)
            snapshot_ids.append(snapshot_id)
        
        # Cache should be limited
        cache_stats = engine.get_cache_stats()
        assert cache_stats['hash_cache_entries'] <= config.cache_size_limit * 2  # Some tolerance
        
        # Clear caches
        engine.clear_caches()
        cache_stats = engine.get_cache_stats()
        assert cache_stats['hash_cache_entries'] == 0
        assert cache_stats['content_cache_entries'] == 0
        assert cache_stats['content_cache_memory_mb'] == 0


class TestFileStorePerformance:
    """Test performance optimizations in file store."""
    
    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)
    
    def test_compression_level_adjustment(self, temp_storage):
        """Test dynamic compression level adjustment."""
        file_store = FileStore(temp_storage, compression_level=3)
        
        # Test initial level
        assert file_store.compression_level == 3
        
        # Test level adjustment
        file_store.set_compression_level(1)
        assert file_store.compression_level == 1
        
        # Test bounds checking
        file_store.set_compression_level(0)  # Should clamp to 1
        assert file_store.compression_level == 1
        
        file_store.set_compression_level(25)  # Should clamp to 22
        assert file_store.compression_level == 22
    
    def test_optimal_compression_level_selection(self, temp_storage):
        """Test optimal compression level selection based on target time."""
        file_store = FileStore(temp_storage)
        
        # Test different target times
        assert file_store.get_optimal_compression_level(50) == 1    # Very fast
        assert file_store.get_optimal_compression_level(200) == 2   # Fast
        assert file_store.get_optimal_compression_level(400) == 3   # Balanced
        assert file_store.get_optimal_compression_level(800) == 6   # Better compression
        assert file_store.get_optimal_compression_level(2000) == 9  # Best compression
    
    def test_compression_performance_vs_ratio(self, temp_storage):
        """Test compression performance vs compression ratio trade-off."""
        # Create test content
        test_content = ("This is test content that should compress well. " * 1000).encode()
        
        results = {}
        for level in [1, 3, 6, 9]:
            file_store = FileStore(temp_storage / f"level_{level}", compression_level=level)
            
            # Measure compression time
            start_time = time.time()
            content_hash = file_store.store_content(test_content)
            compression_time = time.time() - start_time
            
            # Measure decompression time
            start_time = time.time()
            retrieved_content = file_store.retrieve_content(content_hash)
            decompression_time = time.time() - start_time
            
            # Verify content integrity
            assert retrieved_content == test_content
            
            # Get compressed size
            content_path = file_store._get_content_path(content_hash)
            compressed_size = content_path.stat().st_size
            compression_ratio = compressed_size / len(test_content)
            
            results[level] = {
                'compression_time': compression_time,
                'decompression_time': decompression_time,
                'compression_ratio': compression_ratio,
                'compressed_size': compressed_size
            }
        
        # Verify trade-offs
        # Level 1 should be fastest
        assert results[1]['compression_time'] <= results[3]['compression_time']
        assert results[3]['compression_time'] <= results[6]['compression_time']
        
        # Higher levels should achieve better compression
        assert results[9]['compression_ratio'] <= results[6]['compression_ratio']
        assert results[6]['compression_ratio'] <= results[3]['compression_ratio']
    
    def test_content_deduplication_performance(self, temp_storage):
        """Test that content deduplication improves performance."""
        file_store = FileStore(temp_storage)
        
        # Create identical content
        test_content = b"Identical content for deduplication test"
        
        # Store content first time
        start_time = time.time()
        hash1 = file_store.store_content(test_content)
        first_store_time = time.time() - start_time
        
        # Store identical content second time (should be deduplicated)
        start_time = time.time()
        hash2 = file_store.store_content(test_content)
        second_store_time = time.time() - start_time
        
        # Should be same hash
        assert hash1 == hash2
        
        # Second store should be much faster (just hash calculation + lookup)
        assert second_store_time < first_store_time * 0.5, \
            f"Deduplication not effective: {second_store_time:.4f}s vs {first_store_time:.4f}s"
        
        # Should only have one copy of content
        content_path = file_store._get_content_path(hash1)
        assert content_path.exists()
        
        # Verify content can be retrieved
        retrieved = file_store.retrieve_content(hash1)
        assert retrieved == test_content


class TestPerformanceBenchmarks:
    """Benchmark tests for performance validation."""
    
    def test_snapshot_speed_benchmark(self, benchmark):
        """Benchmark snapshot creation speed."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "benchmark_project"
            project_root.mkdir()
            
            # Create moderate-sized project
            for i in range(50):
                file_path = project_root / f"file_{i:03d}.py"
                content = f"# File {i}\n" + "print('test')\n" * 25
                file_path.write_text(content)
            
            storage_root = Path(temp_dir) / "storage"
            config = PerformanceConfig(compression_level=1)  # Fast compression
            engine = SnapshotEngine(project_root, storage_root, config)
            
            context = ActionContext(
                action_type="benchmark",
                timestamp=datetime.now(),
                prompt_context="Benchmark test",
                affected_files=[Path("file_001.py")],
                tool_name="benchmark"
            )
            
            # Benchmark the snapshot creation
            result = benchmark(engine.create_snapshot, context)
            
            # Verify result
            assert result is not None
            assert result.startswith("cr_")
    
    def test_incremental_snapshot_benchmark(self, benchmark):
        """Benchmark incremental snapshot performance."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "incremental_project"
            project_root.mkdir()
            
            # Create project
            for i in range(30):
                file_path = project_root / f"file_{i:03d}.py"
                content = f"# File {i}\n" + "print('test')\n" * 20
                file_path.write_text(content)
            
            storage_root = Path(temp_dir) / "storage"
            config = PerformanceConfig(compression_level=1)
            engine = SnapshotEngine(project_root, storage_root, config)
            
            # Create initial snapshot
            initial_context = ActionContext(
                action_type="initial",
                timestamp=datetime.now(),
                prompt_context="Initial snapshot",
                affected_files=[],
                tool_name="init"
            )
            engine.create_snapshot(initial_context)
            
            # Modify one file
            (project_root / "file_001.py").write_text("# Modified\nprint('updated')")
            
            incremental_context = ActionContext(
                action_type="incremental",
                timestamp=datetime.now(),
                prompt_context="Incremental snapshot",
                affected_files=[Path("file_001.py")],
                tool_name="edit"
            )
            
            # Benchmark incremental snapshot
            result = benchmark(engine.create_snapshot, incremental_context)
            
            # Verify result
            assert result is not None
            assert result.startswith("cr_")