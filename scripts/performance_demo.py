#!/usr/bin/env python3
"""Performance demonstration script for Claude Rewind Tool optimizations."""

import os
import tempfile
import time
from pathlib import Path
from datetime import datetime

from claude_rewind.core.snapshot_engine import SnapshotEngine
from claude_rewind.core.config import PerformanceConfig
from claude_rewind.core.models import ActionContext


def create_test_project(project_root: Path, num_files: int = 100, file_size_kb: int = 10):
    """Create a test project with specified number and size of files."""
    project_root.mkdir(exist_ok=True)
    
    print(f"Creating test project with {num_files} files of ~{file_size_kb}KB each...")
    
    # Create main files
    for i in range(num_files):
        file_path = project_root / f"file_{i:03d}.py"
        content = f"# File {i}\n" + "print('test code')\n" * (file_size_kb * 10)
        file_path.write_text(content)
    
    # Create directory structure
    for dir_name in ["src", "tests", "docs"]:
        dir_path = project_root / dir_name
        dir_path.mkdir(exist_ok=True)
        
        for i in range(20):
            file_path = dir_path / f"{dir_name}_file_{i}.py"
            content = f"# {dir_name} file {i}\n" + "def function(): pass\n" * 20
            file_path.write_text(content)
    
    total_files = num_files + 60  # main files + directory files
    total_size_mb = (num_files * file_size_kb + 60 * 2) / 1024
    print(f"Created {total_files} files, ~{total_size_mb:.1f}MB total")
    
    return total_files, total_size_mb


def benchmark_snapshot_creation(engine: SnapshotEngine, context: ActionContext, 
                               description: str) -> tuple[str, float]:
    """Benchmark snapshot creation and return ID and time taken."""
    print(f"\n{description}")
    start_time = time.time()
    snapshot_id = engine.create_snapshot(context)
    elapsed_time = time.time() - start_time
    
    print(f"  Snapshot ID: {snapshot_id}")
    print(f"  Time taken: {elapsed_time:.3f}s")
    
    return snapshot_id, elapsed_time


def demonstrate_performance_optimizations():
    """Demonstrate the performance optimizations."""
    print("=== Claude Rewind Tool Performance Demonstration ===\n")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "demo_project"
        storage_root = Path(temp_dir) / "storage"
        
        # Create test project
        total_files, total_size_mb = create_test_project(project_root, num_files=150, file_size_kb=5)
        
        print(f"\n1. Testing with FAST compression (level 1) - optimized for speed")
        fast_config = PerformanceConfig(
            compression_level=1,
            parallel_processing=True,
            max_file_size_mb=50,
            target_snapshot_time_ms=500
        )
        
        fast_engine = SnapshotEngine(project_root, storage_root / "fast", fast_config)
        
        context1 = ActionContext(
            action_type="initial_snapshot",
            timestamp=datetime.now(),
            prompt_context="Initial project snapshot with fast compression",
            affected_files=[Path("file_001.py")],
            tool_name="demo"
        )
        
        snapshot_id1, fast_time = benchmark_snapshot_creation(
            fast_engine, context1, "Creating initial snapshot (fast compression):"
        )
        
        # Test incremental snapshot
        (project_root / "file_001.py").write_text("# Modified file\nprint('updated content')")
        
        context2 = ActionContext(
            action_type="file_edit",
            timestamp=datetime.now(),
            prompt_context="Modified single file",
            affected_files=[Path("file_001.py")],
            tool_name="demo"
        )
        
        snapshot_id2, incremental_time = benchmark_snapshot_creation(
            fast_engine, context2, "Creating incremental snapshot (1 file changed):"
        )
        
        print(f"\n2. Testing with BALANCED compression (level 3)")
        balanced_config = PerformanceConfig(
            compression_level=3,
            parallel_processing=True,
            max_file_size_mb=50
        )
        
        balanced_engine = SnapshotEngine(project_root, storage_root / "balanced", balanced_config)
        
        context3 = ActionContext(
            action_type="initial_snapshot",
            timestamp=datetime.now(),
            prompt_context="Initial project snapshot with balanced compression",
            affected_files=[Path("file_001.py")],
            tool_name="demo"
        )
        
        snapshot_id3, balanced_time = benchmark_snapshot_creation(
            balanced_engine, context3, "Creating initial snapshot (balanced compression):"
        )
        
        print(f"\n3. Testing lazy loading functionality")
        print("Demonstrating lazy loading of file content...")
        
        start_time = time.time()
        content = fast_engine.get_file_content_lazy(snapshot_id1, Path("file_001.py"))
        lazy_load_time = time.time() - start_time
        
        print(f"  Lazy loaded file content in {lazy_load_time:.4f}s")
        print(f"  Content size: {len(content)} bytes")
        
        # Test cached access
        start_time = time.time()
        cached_content = fast_engine.get_file_content_lazy(snapshot_id1, Path("file_001.py"))
        cached_time = time.time() - start_time
        
        print(f"  Cached access time: {cached_time:.4f}s (should be much faster)")
        
        print(f"\n4. Cache statistics")
        cache_stats = fast_engine.get_cache_stats()
        print(f"  Hash cache entries: {cache_stats['hash_cache_entries']}")
        print(f"  Content cache entries: {cache_stats['content_cache_entries']}")
        print(f"  Content cache memory: {cache_stats['content_cache_memory_mb']:.2f}MB")
        
        print(f"\n5. Storage efficiency comparison")
        fast_stats = fast_engine.file_store.get_storage_stats()
        balanced_stats = balanced_engine.file_store.get_storage_stats()
        
        print(f"  Fast compression (level 1):")
        print(f"    Compression ratio: {fast_stats['compression_ratio']:.3f}")
        print(f"    Compressed size: {fast_stats['compressed_size'] / (1024*1024):.2f}MB")
        
        print(f"  Balanced compression (level 3):")
        print(f"    Compression ratio: {balanced_stats['compression_ratio']:.3f}")
        print(f"    Compressed size: {balanced_stats['compressed_size'] / (1024*1024):.2f}MB")
        
        print(f"\n6. Performance summary")
        print(f"  Project size: {total_files} files, {total_size_mb:.1f}MB")
        print(f"  Initial snapshot (fast): {fast_time:.3f}s")
        print(f"  Initial snapshot (balanced): {balanced_time:.3f}s")
        print(f"  Incremental snapshot: {incremental_time:.3f}s")
        print(f"  Speed improvement (incremental): {fast_time/incremental_time:.1f}x faster")
        
        # Check if we meet the 500ms target for projects under 1GB
        if total_size_mb < 1000:  # Under 1GB
            target_met = fast_time < 0.5
            print(f"  500ms target for <1GB projects: {'✓ MET' if target_met else '✗ MISSED'}")
        
        print(f"\n7. Optimization features demonstrated:")
        print(f"  ✓ Parallel file processing")
        print(f"  ✓ Hash caching for unchanged files")
        print(f"  ✓ Incremental snapshots")
        print(f"  ✓ Configurable compression levels")
        print(f"  ✓ Lazy loading of file content")
        print(f"  ✓ Memory-efficient caching")
        print(f"  ✓ Performance monitoring and stats")


if __name__ == "__main__":
    demonstrate_performance_optimizations()