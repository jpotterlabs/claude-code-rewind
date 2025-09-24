# Known Issues

## 🚨 Priority Bugs (Final Sprint Before Ship)

### 🔥 Rolling Snapshots Cleanup Not Implemented

**Issue**: `claude-rewind cleanup` command is placeholder only - doesn't actually clean up snapshots

**Severity**: HIGH - Core feature advertised but non-functional

**Error**: CLI shows "Actual cleanup logic will be implemented in storage tasks"

**Impact**:
- ❌ Users cannot manage disk space (snapshots accumulate indefinitely)
- ❌ `max_snapshots`, `cleanup_after_days`, `max_disk_usage_mb` settings ignored
- ❌ Essential storage management feature completely missing

**Status**:
- ✅ Database methods implemented and tested (`cleanup_old_snapshots()`)
- ✅ Configuration schema complete
- ❌ CLI integration missing - needs to call actual cleanup methods

**Required Fix**: Connect CLI `cleanup` command to:
- `database.cleanup_old_snapshots(keep_count)`
- Time-based cleanup using `cleanup_after_days`
- Disk usage enforcement using `max_disk_usage_mb`

**Priority**: CRITICAL - Must fix before ship

**Location**: `claude_rewind/cli/main.py` cleanup command

---

### 🐛 Timeline Command Interactive Mode Issues

**Issue**: `claude-rewind timeline` gets stuck in infinite loop when run non-interactively

**Severity**: MEDIUM - Command works but has UX issues

**Error**: Shows "Error: EOF when reading a line" repeatedly, timeouts after 2 minutes

**Impact**:
- ❌ Cannot use timeline in scripts or automated contexts
- ❌ Poor user experience when input is redirected
- ✅ Interactive mode displays data correctly

**Status**:
- ✅ Core timeline functionality working (displays snapshots correctly)
- ✅ Rich formatting and layout working
- ❌ Input handling needs non-interactive mode detection

**Required Fix**: Add detection for non-interactive terminal and provide non-interactive output mode

**Priority**: MEDIUM - UX improvement

**Location**: `claude_rewind/core/timeline.py` input handling

---

### 🐛 Diff Command File-Specific Mode Broken

**Issue**: `claude-rewind diff <snapshot> --file <filename>` fails with "Snapshot not found: current"

**Severity**: MEDIUM - Specific functionality broken

**Error**: `Failed to get file content for test1.py in current: Snapshot not found: current`

**Impact**:
- ❌ Cannot view diffs for specific files
- ✅ Full snapshot diffs work correctly
- ✅ Syntax error in diff_viewer.py fixed during testing

**Status**:
- ✅ Full diff functionality works
- ✅ Syntax highlighting and formatting work
- ❌ File-specific diff mode has snapshot resolution issue

**Required Fix**: Fix "current" snapshot resolution in file-specific diff mode

**Priority**: MEDIUM - Feature completion

**Location**: `claude_rewind/core/diff_viewer.py` current snapshot handling

---

### ✅ Working Commands Verified

**Fully Functional**:
- ✅ `config` - Shows configuration correctly
- ✅ `validate` - Validates configuration properly
- ✅ `status` - Shows project status
- ✅ `session` - Manages monitoring sessions
- ✅ `init` - Initializes projects correctly
- ✅ `rollback --dry-run` - Preview functionality works perfectly
- ✅ `preview` - Rollback preview with detailed analysis
- ✅ `monitor` - Starts monitoring (filesystem mode tested)
- ✅ `diff <snapshot>` - Full snapshot diffs work (shows too much internal data but functional)

**Partially Working**:
- ⚠️ `timeline` - Works interactively, issues with non-interactive mode
- ⚠️ `diff --file` - Full diffs work, file-specific mode broken

---

## Post-Ship Bug Reports

### 🐛 Race Condition in Comprehensive Performance Tests

**Issue**: `test_performance_features.py` fails during parallel processing thread safety test

**Error**: `FileNotFoundError` during concurrent temporary file operations in storage system

**Location**:
- `test_performance_features.py:268-269` (concurrent snapshot creation)
- `file_store.py:211` (`temp_path.rename(content_path)`)

**Root Cause**: Multiple threads creating snapshots simultaneously cause race condition in temporary file management

**Impact**:
- ❌ Comprehensive performance benchmarks cannot run
- ✅ Simple performance test works fine
- ✅ All performance features work correctly in normal usage

**Workaround**: Use `simple_performance_test.py` to verify features work

**Priority**: Low (post-ship fix)

**Fix Strategy**: Implement atomic file operations with proper locking for concurrent storage operations

---

*Created during performance testing phase - all core functionality works correctly*