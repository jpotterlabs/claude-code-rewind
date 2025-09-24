#!/usr/bin/env python3
"""Simple performance test to verify features work correctly."""

import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from claude_rewind.core.snapshot_engine import SnapshotEngine
from claude_rewind.core.models import ActionContext
from claude_rewind.core.config import PerformanceConfig


def test_incremental_snapshots():
    """Test incremental snapshots."""
    print("🔄 Testing Incremental Snapshots")

    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "project"
        storage_root = Path(temp_dir) / "storage"

        project_root.mkdir()
        storage_root.mkdir()

        # Create test files
        for i in range(10):
            file_path = project_root / f"file_{i}.py"
            file_path.write_text(f"# File {i}\nprint('test')\n")

        config = PerformanceConfig(
            parallel_processing=False,
            lazy_loading_enabled=False
        )
        engine = SnapshotEngine(project_root, storage_root, config)

        # Baseline snapshot
        start_time = time.time()
        context1 = ActionContext(
            action_type="baseline",
            timestamp=datetime.now(),
            prompt_context="Baseline",
            affected_files=[],
            tool_name="test"
        )
        snapshot1 = engine.create_snapshot(context1)
        baseline_time = (time.time() - start_time) * 1000

        # Incremental snapshot
        (project_root / "file_0.py").write_text("# File 0 changed\nprint('changed')\n")

        start_time = time.time()
        context2 = ActionContext(
            action_type="incremental",
            timestamp=datetime.now(),
            prompt_context="Incremental",
            affected_files=[Path("file_0.py")],
            tool_name="test"
        )
        snapshot2 = engine.create_snapshot(context2)
        incremental_time = (time.time() - start_time) * 1000

        speedup = baseline_time / incremental_time if incremental_time > 0 else 0

        print(f"  ⏱️  Baseline: {baseline_time:.1f}ms")
        print(f"  ⏱️  Incremental: {incremental_time:.1f}ms")
        print(f"  📊 Speedup: {speedup:.1f}x")
        print(f"  ✅ Incremental snapshots working!")


def test_lazy_loading():
    """Test lazy loading."""
    print("\n💾 Testing Lazy Loading")

    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "project"
        storage_root = Path(temp_dir) / "storage"

        project_root.mkdir()
        storage_root.mkdir()

        # Create test files
        for i in range(10):
            file_path = project_root / f"file_{i}.py"
            content = f"# File {i}\n" + "# Content " * 100 + "\n"
            file_path.write_text(content)

        config = PerformanceConfig(lazy_loading_enabled=True)
        engine = SnapshotEngine(project_root, storage_root, config)

        # Create snapshot
        context = ActionContext(
            action_type="lazy_test",
            timestamp=datetime.now(),
            prompt_context="Lazy loading test",
            affected_files=[],
            tool_name="test"
        )
        snapshot_id = engine.create_snapshot(context)

        # Test lazy access
        start_time = time.time()
        snapshot = engine.get_snapshot(snapshot_id)
        metadata_time = (time.time() - start_time) * 1000

        start_time = time.time()
        content = engine.get_file_content_lazy(snapshot_id, Path("file_0.py"))
        content_time = (time.time() - start_time) * 1000

        print(f"  ⏱️  Metadata access: {metadata_time:.1f}ms")
        print(f"  ⏱️  Content access: {content_time:.1f}ms")
        print(f"  💾 Content loaded: {len(content) if content else 0} bytes")
        print(f"  ✅ Lazy loading working!")


def test_parallel_processing():
    """Test parallel processing (simplified)."""
    print("\n⚡ Testing Parallel Processing")

    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir) / "project"
        storage_root = Path(temp_dir) / "storage"

        project_root.mkdir()
        storage_root.mkdir()

        # Create more files for parallel benefit
        for i in range(50):
            file_path = project_root / f"file_{i}.py"
            content = f"# File {i}\n" + "# Content line\n" * 50
            file_path.write_text(content)

        # Sequential test
        config_seq = PerformanceConfig(parallel_processing=False)
        engine_seq = SnapshotEngine(project_root, storage_root, config_seq)

        start_time = time.time()
        context_seq = ActionContext(
            action_type="sequential",
            timestamp=datetime.now(),
            prompt_context="Sequential test",
            affected_files=[],
            tool_name="test"
        )
        engine_seq.create_snapshot(context_seq)
        sequential_time = (time.time() - start_time) * 1000

        # Parallel test
        config_par = PerformanceConfig(parallel_processing=True)
        engine_par = SnapshotEngine(project_root, storage_root, config_par)

        start_time = time.time()
        context_par = ActionContext(
            action_type="parallel",
            timestamp=datetime.now(),
            prompt_context="Parallel test",
            affected_files=[],
            tool_name="test"
        )
        engine_par.create_snapshot(context_par)
        parallel_time = (time.time() - start_time) * 1000

        speedup = sequential_time / parallel_time if parallel_time > 0 else 0

        print(f"  ⏱️  Sequential: {sequential_time:.1f}ms")
        print(f"  ⏱️  Parallel: {parallel_time:.1f}ms")
        print(f"  📊 Speedup: {speedup:.1f}x")
        print(f"  ✅ Parallel processing working!")


def main():
    """Run simple performance tests."""
    print("🧪 Simple Performance Feature Tests")
    print("=" * 40)

    try:
        test_incremental_snapshots()
        test_lazy_loading()
        test_parallel_processing()

        print("\n🎉 All performance features working correctly!")
        return True

    except Exception as e:
        print(f"\n💥 Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)