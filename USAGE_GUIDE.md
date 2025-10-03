# 📖 Claude Rewind Complete Usage Guide

The definitive guide to mastering the Claude Code Rewind Tool - your time machine for Claude Code sessions.

## 📋 Table of Contents

1. [Quick Start](#-quick-start)
2. [Core Concepts](#-core-concepts)
3. [Command Reference](#-command-reference)
4. [Native Hooks (Event-Driven)](#-native-hooks-event-driven)
5. [Monitoring & Sessions](#-monitoring--sessions)
6. [Timeline Navigation](#-timeline-navigation)
7. [Diff Analysis](#-diff-analysis)
8. [Rollback Operations](#-rollback-operations)
9. [Advanced Workflows](#-advanced-workflows)
10. [Configuration](#-configuration)
11. [Tips & Tricks](#-tips--tricks)
12. [Troubleshooting](#-troubleshooting)
13. [Real-World Examples](#-real-world-examples)

---

## 🚀 Quick Start

### 1. Installation & Setup
```bash
# Install the package
git clone https://github.com/jpotterlabs/claude-code-rewind.git
cd claude-code-rewind
pip install -e .

# Initialize your project
cd your-project
claude-rewind init

# Choose your monitoring approach:

# Option A: Event-driven (recommended for Claude Code 2.0+)
claude-rewind hooks init
# Snapshots created instantly by Claude Code

# Option B: Polling (fallback for older versions)
claude-rewind monitor
# Background monitoring every 2 seconds
```

### 2. Basic Workflow
```bash
# Use Claude Code normally in another terminal
# Claude Rewind automatically detects and captures actions

# View what happened
claude-rewind timeline

# See detailed changes
claude-rewind diff <snapshot-id>

# Roll back if needed
claude-rewind rollback <snapshot-id>
```

---

## 🧠 Core Concepts

### Snapshots
**What**: Point-in-time captures of your project state
**When**: Created automatically when Claude Code actions are detected
**Contains**:
- File states (content, metadata)
- Action context (tool used, timing, affected files)
- Session information (ID, sequence)

### Sessions
**What**: A continuous period of Claude Code monitoring
**Duration**: From `monitor` start to stop (or interruption)
**Tracking**: Unique session ID, action count, statistics

### Action Detection
**Method**: Multi-modal intelligence (not just file watching)
- Environment monitoring (processes, variables)
- Content analysis (AI-generated patterns)
- File correlation (timing, patterns, types)
- Confidence scoring (0.0-1.0 reliability)

### Rich Context
**Beyond file changes**: Know exactly what Claude did:
- Which tool (`edit_file`, `write_file`, `create_file`, etc.)
- When it happened (precise timestamps)
- Why it happened (prompt context when available)
- Which files were affected

---

## 📋 Command Reference

### Core Commands

#### `claude-rewind init`
**Purpose**: Initialize Claude Rewind in a project
**Usage**:
```bash
claude-rewind init [OPTIONS]
```

**Options**:
- `--skip-git-check`: Skip git repository validation
- `--config-only`: Only create configuration, skip database

**Examples**:
```bash
# Basic initialization
claude-rewind init

# Skip git integration
claude-rewind init --skip-git-check

# Only create config (advanced)
claude-rewind init --config-only
```

**What it creates**:
- `.claude-rewind/` directory
- `config.yml` - Configuration file
- `metadata.db` - SQLite database
- `snapshots/` - Snapshot storage directory

---

#### `claude-rewind monitor`
**Purpose**: Start intelligent Claude Code monitoring
**Usage**:
```bash
claude-rewind monitor [OPTIONS]
```

**Options**:
- `--mode {claude,filesystem,hybrid}` - Detection mode (default: claude)
- `--sensitivity {low,medium,high}` - Detection sensitivity (default: medium)
- `--no-backup` - Skip creating backup snapshot on start

**Detection Modes**:
- **`claude`**: Only detect actual Claude Code actions (recommended)
- **`filesystem`**: Traditional file watching (broad coverage)
- **`hybrid`**: Both methods combined (maximum coverage)

**Sensitivity Levels**:
- **`low`**: Only high-confidence Claude actions (0.8+ confidence)
- **`medium`**: Balanced detection (0.7+ confidence)
- **`high`**: Aggressive detection (0.6+ confidence)

**Examples**:
```bash
# Start standard monitoring
claude-rewind monitor

# Use hybrid mode with high sensitivity
claude-rewind monitor --mode hybrid --sensitivity high

# Monitor without initial backup
claude-rewind monitor --no-backup

# Monitor with specific settings
claude-rewind monitor --mode claude --sensitivity low
```

**Runtime Controls**:
- `Ctrl+C` - Stop monitoring gracefully
- `--verbose` (global) - Show detailed detection info

---

#### `claude-rewind session`
**Purpose**: Manage and inspect Claude Code sessions
**Usage**:
```bash
claude-rewind session [OPTIONS]
```

**Options**:
- `--action {start,stop,status,stats}` - Action to perform (default: status)
- `--show-recent INTEGER` - Number of recent actions to show (default: 5)

**Actions**:
- **`status`**: Quick monitoring status check
- **`stats`**: Detailed session statistics
- **`start`**: Start monitoring session (alternative to `monitor`)
- **`stop`**: Stop active monitoring session

**Examples**:
```bash
# Check if monitoring is active
claude-rewind session

# Get detailed statistics
claude-rewind session --action stats

# Show last 10 actions
claude-rewind session --action stats --show-recent 10

# Start/stop sessions programmatically
claude-rewind session --action start
claude-rewind session --action stop
```

**Session Information**:
- Session ID (unique identifier)
- Start time and duration
- Action count and types
- Recent actions list
- Monitoring status

---

## 🎣 Native Hooks (Event-Driven)

**Available in v1.5a+ for Claude Code 2.0+**

Native hooks provide **instant, zero-latency** snapshot creation by integrating directly with Claude Code's event system.

### Overview

Instead of polling for changes every 2 seconds, Claude Code **instantly notifies** Rewind when events occur, providing:
- ⚡ Zero latency (snapshots created immediately)
- 🧠 Rich context (extended thinking, confidence scores, prompt context)
- 🤖 Subagent tracking (separate snapshots for subagent work)
- 🎯 Tool attribution (know exactly which tool made changes)
- 💾 No background process (event-driven, not polling)

### Hook Commands

#### `claude-rewind hooks init`
**Purpose**: Enable native hooks integration

```bash
claude-rewind hooks init [--force]
```

**What it does**:
- Creates/updates `.claude/settings.json`
- Registers 7 native hooks with Claude Code
- Preserves existing user hooks

**Output**:
```
✓ Configured .claude/settings.json
✓ Registered 7 native hooks
🎉 Claude Code Rewind is now event-driven!
```

---

#### `claude-rewind hooks status`
**Purpose**: Show hook registration status

```bash
claude-rewind hooks status
```

**Example output**:
```
Status: ✓ Registered
Active hooks: 7
  ✓ SessionStart    - Initialize session tracking
  ✓ SessionEnd      - Finalize session tracking
  ✓ PostToolUse     - Create automatic snapshot
  ✓ SubagentStop    - Capture subagent work completion
  ✓ Error           - Auto-suggest rollback on errors
  ...
```

---

#### `claude-rewind hooks test`
**Purpose**: Validate hook configuration

```bash
claude-rewind hooks test
```

Checks:
- `.claude/settings.json` exists and is valid
- All 7 hooks are registered correctly
- `claude-rewind` command is in PATH

---

#### `claude-rewind hooks disable`
**Purpose**: Disable native hooks (revert to polling)

```bash
claude-rewind hooks disable [--confirm]
```

**Use cases**:
- Troubleshooting hook issues
- Testing performance differences
- Temporarily reverting to polling

---

### Event Types

Native hooks capture these Claude Code events:

| Event | When | Creates Snapshot | Tags |
|-------|------|------------------|------|
| **SessionStart** | Session begins | Yes | `session-start` |
| **SessionEnd** | Session ends | Yes | `session-end` |
| **PreToolUse** | Before tool execution | No (logged) | - |
| **PostToolUse** | After tool use | Yes ⭐ | `auto`, `tool:{name}` |
| **SubagentStart** | Subagent delegated | Yes | `subagent-start` |
| **SubagentStop** | Subagent completes | Yes ⭐ | `subagent-stop` |
| **Error** | Error occurs | Yes | `error`, `error-type:{type}` |

**Primary snapshot sources**: `PostToolUse` (most frequent) and `SubagentStop`

---

### Filtering by Hook Events

Use tags to filter snapshots by event type:

```bash
# Only error snapshots
claude-rewind timeline --tags error

# Only Edit tool snapshots
claude-rewind timeline --tags tool:Edit

# Only subagent snapshots
claude-rewind timeline --tags subagent-stop

# Session lifecycle
claude-rewind timeline --tags session-start,session-end
```

---

### Hooks vs Monitor Comparison

| Feature | `hooks init` (Event-Driven) | `monitor` (Polling) |
|---------|------------------------------|----------------------|
| **Latency** | 0ms (instant) | 2+ seconds |
| **Context** | Rich (thinking, confidence) | File changes only |
| **Overhead** | No background process | Background process |
| **Subagent Tracking** | Yes (separate snapshots) | No |
| **Error Detection** | Yes (auto-rollback suggestions) | No |
| **Claude Version** | 2.0+ required | All versions |

**Recommendation**: Use `hooks init` for Claude Code 2.0+, fall back to `monitor` for older versions.

---

### Complete Documentation

For comprehensive native hooks documentation, see:
- 📚 [Native Hooks Guide](NATIVE_HOOKS_GUIDE.md) - User guide with examples
- 🔧 [Hooks API Reference](HOOKS_API_REFERENCE.md) - Technical reference for developers

---

#### `claude-rewind timeline`
**Purpose**: Navigate and explore snapshot history
**Usage**:
```bash
claude-rewind timeline [OPTIONS]
```

**Options**:
- `--limit INTEGER` - Maximum snapshots to show
- `--filter-action TEXT` - Filter by action type
- `--filter-date TEXT` - Filter by date (YYYY-MM-DD)
- `--search TEXT` - Search in context/descriptions
- `--bookmarked-only` - Show only bookmarked snapshots

**Interactive Commands** (when running interactively):
- `next` / `prev` - Navigate pages
- `filter` - Apply filters
- `search` - Search snapshots
- `bookmark` - Bookmark current snapshot
- `details` - Show detailed info
- `reset` - Clear all filters
- `help` - Show command help
- `quit` - Exit timeline

**Examples**:
```bash
# Interactive timeline (recommended)
claude-rewind timeline

# Show last 10 snapshots
claude-rewind timeline --limit 10

# Filter by action type
claude-rewind timeline --filter-action edit_file

# Filter by date
claude-rewind timeline --filter-date 2025-09-23

# Search for specific changes
claude-rewind timeline --search "added function"

# Show only important snapshots
claude-rewind timeline --bookmarked-only
```

**Timeline Display**:
```
┌─────────────────────────────────────────────────────────────────┐
│                 Claude Rewind Timeline - 15 snapshots          │
└─────────────────────────────────────────────────────────────────┘

#   ID          Timestamp      Action         Files  Size    Bookmark
────────────────────────────────────────────────────────────────────
1   cr_a1b2c3   2025-09-23     edit_file      3      2.1KB   ⭐
                14:30:15
2   cr_d4e5f6   2025-09-23     write_file     1      856B
                14:28:42
```

---

#### `claude-rewind diff`
**Purpose**: Show detailed changes in snapshots
**Usage**:
```bash
claude-rewind diff [OPTIONS] <snapshot-id> [second-snapshot-id]
```

**Options**:
- `--format {unified,side-by-side,context}` - Diff display format
- `--file PATH` - Show diff for specific file only
- `--no-color` - Disable syntax highlighting
- `--context INTEGER` - Lines of context around changes (default: 3)

**Diff Types**:
- **Single snapshot**: Changes since previous snapshot
- **Two snapshots**: Changes between two specific points
- **File-specific**: Changes to one file only

**Examples**:
```bash
# Show changes in latest snapshot
claude-rewind diff cr_abc123

# Compare two snapshots
claude-rewind diff cr_abc123 cr_def456

# Show only changes to specific file
claude-rewind diff cr_abc123 --file src/main.py

# Side-by-side comparison
claude-rewind diff cr_abc123 --format side-by-side

# More context lines
claude-rewind diff cr_abc123 --context 10

# Plain text (no colors)
claude-rewind diff cr_abc123 --no-color
```

**Diff Output**:
```diff
📸 Snapshot: cr_abc123 (edit_file)
🕐 Time: 2025-09-23 14:30:15
📝 Context: Claude edited main.py to add error handling

📁 main.py
───────────────────────────────────────────────────────
@@ -15,6 +15,12 @@
 def process_data(data):
     """Process the input data."""
+    try:
+        if not data:
+            raise ValueError("Data cannot be empty")
+
         result = transform(data)
+    except ValueError as e:
+        logger.error(f"Data processing error: {e}")
+        return None
     return result
```

---

#### `claude-rewind rollback`
**Purpose**: Restore project to a previous state
**Usage**:
```bash
claude-rewind rollback [OPTIONS] <snapshot-id>
```

**Options**:
- `--dry-run` - Show what would be changed without applying
- `--selective` - Choose which files to rollback
- `--preserve-changes` - Keep current changes, merge intelligently
- `--force` - Skip confirmation prompts
- `--backup` - Create backup before rollback

**Rollback Modes**:
- **Full rollback**: Restore entire project state
- **Selective rollback**: Choose specific files
- **Smart merge**: Preserve some current changes

**Examples**:
```bash
# Preview rollback changes
claude-rewind rollback cr_abc123 --dry-run

# Full rollback with confirmation
claude-rewind rollback cr_abc123

# Selective file rollback
claude-rewind rollback cr_abc123 --selective

# Rollback with current changes preserved
claude-rewind rollback cr_abc123 --preserve-changes

# Force rollback without prompts
claude-rewind rollback cr_abc123 --force

# Safe rollback with backup
claude-rewind rollback cr_abc123 --backup
```

**Interactive Selection** (with `--selective`):
```
Select files to rollback:
☑ src/main.py (modified)
☐ src/utils.py (new file)
☑ README.md (modified)
☐ tests/test_main.py (new file)

Continue with rollback? [y/N]:
```

---

#### `claude-rewind preview`
**Purpose**: Preview rollback changes without applying them
**Usage**:
```bash
claude-rewind preview [OPTIONS] <snapshot-id>
```

**Options**:
- `--detailed` - Show file-by-file changes
- `--files-only` - List affected files only
- `--stats` - Show summary statistics

**Examples**:
```bash
# Quick preview
claude-rewind preview cr_abc123

# Detailed file changes
claude-rewind preview cr_abc123 --detailed

# Just list files that would change
claude-rewind preview cr_abc123 --files-only

# Show statistics
claude-rewind preview cr_abc123 --stats
```

**Preview Output**:
```
🔍 Rollback Preview: cr_abc123 → current

📊 Summary:
  • 3 files would be modified
  • 1 file would be deleted
  • 0 files would be created
  • 2 conflicts detected

📁 Files that would change:
  📝 src/main.py (142 lines → 98 lines)
  📝 src/config.py (67 lines → 45 lines)
  📝 README.md (23 lines → 19 lines)
  🗑️  src/temp.py (would be deleted)

⚠️  Conflicts:
  • src/main.py: Current changes would be lost
  • src/config.py: New configuration added since snapshot

Use --preserve-changes to keep current modifications
```

---

#### `claude-rewind status`
**Purpose**: Show current system status and health
**Usage**:
```bash
claude-rewind status [OPTIONS]
```

**Options**:
- `--detailed` - Show detailed system information
- `--health-check` - Run system health diagnostics

**Examples**:
```bash
# Basic status
claude-rewind status

# Detailed information
claude-rewind status --detailed

# Health diagnostics
claude-rewind status --health-check
```

**Status Information**:
- Initialization status
- Configuration file location
- Database status and size
- Snapshot count and storage usage
- Monitoring status
- Git integration status

---

### Utility Commands

#### `claude-rewind config`
**Purpose**: View and manage configuration
**Usage**:
```bash
claude-rewind config [OPTIONS]
```

**Options**:
- `--show-defaults` - Show default configuration values
- `--validate-only` - Only validate, don't display

**Examples**:
```bash
# Show current configuration
claude-rewind config

# Show defaults
claude-rewind config --show-defaults

# Validate configuration
claude-rewind config --validate-only
```

---

#### `claude-rewind cleanup`
**Purpose**: Clean up old snapshots and optimize storage
**Usage**:
```bash
claude-rewind cleanup [OPTIONS]
```

**Options**:
- `--dry-run` - Show what would be cleaned without doing it
- `--force` - Skip confirmation prompts

**Examples**:
```bash
# Preview cleanup
claude-rewind cleanup --dry-run

# Clean up old snapshots
claude-rewind cleanup

# Force cleanup without confirmation
claude-rewind cleanup --force
```

---

#### `claude-rewind validate`
**Purpose**: Validate system integrity and configuration
**Usage**:
```bash
claude-rewind validate [OPTIONS]
```

**Examples**:
```bash
# Validate everything
claude-rewind validate

# Quick validation
claude-rewind validate --quick
```

---

## 🎯 Monitoring & Sessions

### Understanding Detection Modes

#### Claude Mode (Recommended)
```bash
claude-rewind monitor --mode claude
```

**What it detects**:
- Actual Claude Code tool usage
- File modifications with AI patterns
- Multi-file coordinated changes
- Environment indicators of Claude activity

**Best for**:
- Pure Claude Code projects
- Minimal noise/false positives
- Context-rich snapshots

**Detection signals**:
- Content analysis (AI-generated code patterns)
- File timing correlation (multiple files changed simultaneously)
- Environment monitoring (Claude processes, variables)
- Confidence scoring (only high-probability actions)

#### Filesystem Mode
```bash
claude-rewind monitor --mode filesystem
```

**What it detects**:
- Any file change in the project
- Traditional file system monitoring
- Broad coverage of all modifications

**Best for**:
- Mixed development (Claude + manual coding)
- Catching everything (high noise tolerance)
- Debugging detection issues

#### Hybrid Mode
```bash
claude-rewind monitor --mode hybrid
```

**What it detects**:
- Combines both Claude and filesystem detection
- Smart deduplication of overlapping detections
- Maximum coverage with intelligence

**Best for**:
- Complex projects with mixed workflows
- Maximum safety (don't miss anything)
- Development and testing phases

### Session Management Workflows

#### Long-Running Sessions
```bash
# Start session in background
nohup claude-rewind monitor &

# Check session status
claude-rewind session --action stats

# Stop gracefully
claude-rewind session --action stop
```

#### Session Statistics Tracking
```bash
# Basic stats
claude-rewind session

# Detailed analysis
claude-rewind session --action stats --show-recent 20

# Export session data (via timeline)
claude-rewind timeline --limit 100 > session_report.txt
```

#### Multiple Project Management
```bash
# Project A
cd /path/to/project-a
claude-rewind monitor &

# Project B
cd /path/to/project-b
claude-rewind monitor &

# Check all sessions
ps aux | grep claude-rewind
```

---

## 🕐 Timeline Navigation

### Basic Navigation
```bash
# Start interactive timeline
claude-rewind timeline

# Navigate with commands:
# next - Next page
# prev - Previous page
# details 1 - Show details for snapshot #1
# quit - Exit
```

### Advanced Filtering

#### By Action Type
```bash
# Show only file edits
claude-rewind timeline --filter-action edit_file

# Show only new files
claude-rewind timeline --filter-action create_file

# Show only deletions
claude-rewind timeline --filter-action delete_file
```

#### By Date Range
```bash
# Today's changes
claude-rewind timeline --filter-date $(date +%Y-%m-%d)

# Specific date
claude-rewind timeline --filter-date 2025-09-23

# Interactive filtering
claude-rewind timeline
# Then use: filter date 2025-09-23
```

#### By Content Search
```bash
# Search in context descriptions
claude-rewind timeline --search "error handling"

# Search for file patterns
claude-rewind timeline --search "main.py"

# Search for specific changes
claude-rewind timeline --search "added function"
```

### Bookmarking Important Snapshots
```bash
# Interactive bookmarking
claude-rewind timeline
# Navigate to important snapshot
# Run: bookmark "Important milestone"

# View bookmarked snapshots
claude-rewind timeline --bookmarked-only
```

---

## 🔍 Diff Analysis

### Understanding Diff Formats

#### Unified Format (Default)
```bash
claude-rewind diff cr_abc123
```
Shows changes in traditional unified diff format with context lines.

#### Side-by-Side Format
```bash
claude-rewind diff cr_abc123 --format side-by-side
```
Shows before/after side-by-side for easy comparison.

#### Context Format
```bash
claude-rewind diff cr_abc123 --format context
```
Shows changes with more surrounding context.

### File-Specific Analysis
```bash
# Focus on one file
claude-rewind diff cr_abc123 --file src/main.py

# Compare specific file across snapshots
claude-rewind diff cr_abc123 cr_def456 --file config.yml
```

### Advanced Diff Techniques

#### Large Changes Analysis
```bash
# More context for complex changes
claude-rewind diff cr_abc123 --context 10

# Focus on specific parts
claude-rewind diff cr_abc123 --file src/core.py
```

#### Change Evolution Tracking
```bash
# See how a file evolved
claude-rewind timeline --search "main.py"
# Then diff each snapshot that modified main.py
claude-rewind diff cr_001
claude-rewind diff cr_002
claude-rewind diff cr_003
```

---

## ⏪ Rollback Operations

### Safe Rollback Practices

#### Always Preview First
```bash
# Never rollback without previewing
claude-rewind preview cr_abc123
claude-rewind rollback cr_abc123 --dry-run
claude-rewind rollback cr_abc123
```

#### Backup Current State
```bash
# Create safety snapshot before rollback
claude-rewind monitor --no-backup  # Stop monitoring
# Make a manual change to trigger snapshot
echo "# Backup before rollback" >> README.md
claude-rewind monitor &  # This creates a snapshot
claude-rewind rollback cr_abc123
```

### Selective Rollbacks

#### Interactive File Selection
```bash
claude-rewind rollback cr_abc123 --selective
```

This shows an interactive menu:
```
Select files to rollback:
☑ src/main.py (modified - 45 lines changed)
☐ src/utils.py (new file - would be deleted)
☑ README.md (modified - 3 lines changed)
☐ tests/test_new.py (new file - would be deleted)

[Space] Toggle selection, [Enter] Continue, [q] Quit
```

#### Smart Merging
```bash
# Keep current changes where possible
claude-rewind rollback cr_abc123 --preserve-changes
```

This attempts to:
- Merge non-conflicting changes
- Preserve current modifications
- Show conflicts for manual resolution

### Rollback Strategies

#### Progressive Rollback
```bash
# Roll back one step at a time
claude-rewind timeline --limit 5
claude-rewind rollback cr_latest_minus_1
# Test the changes
claude-rewind rollback cr_latest_minus_2
# Continue until you find the good state
```

#### Targeted Rollback
```bash
# Rollback only specific files that had issues
claude-rewind timeline --search "error"
claude-rewind preview cr_before_error
claude-rewind rollback cr_before_error --selective
# Choose only the problematic files
```

#### Emergency Rollback
```bash
# Quick rollback to last known good state
claude-rewind timeline --bookmarked-only
claude-rewind rollback <last-bookmark> --force
```

---

## 🚀 Advanced Workflows

### Development Workflows

#### Feature Development Protection
```bash
# Start feature development
claude-rewind monitor
echo "# Starting feature X" >> CHANGELOG.md
# This creates a baseline snapshot

# Use Claude Code for feature development
# All changes are automatically tracked

# Review feature completion
claude-rewind timeline --limit 10
claude-rewind diff <baseline-snapshot>

# Rollback if feature needs changes
claude-rewind rollback <baseline-snapshot> --selective
```

#### Code Review Preparation
```bash
# Capture current state
claude-rewind monitor  # Ensure monitoring is active
echo "# Code review checkpoint" >> .gitignore

# Generate review materials
claude-rewind timeline --limit 20 > review_timeline.txt
claude-rewind diff <start-snapshot> > review_changes.diff

# Create summary of all changes
for snapshot in $(claude-rewind timeline --limit 10 | grep "cr_" | cut -d' ' -f2); do
    echo "=== $snapshot ===" >> review_summary.txt
    claude-rewind diff $snapshot >> review_summary.txt
done
```

#### Experiment Management
```bash
# Baseline before experiments
claude-rewind timeline
# Note the current snapshot ID

# Experiment 1
# Use Claude Code for changes
claude-rewind timeline --limit 3  # Check new snapshots

# Experiment 2 (rollback and try different approach)
claude-rewind rollback <baseline>
# Use Claude Code for different changes

# Compare experiments
claude-rewind diff <experiment1-snapshot> <experiment2-snapshot>

# Choose best approach
claude-rewind rollback <chosen-experiment>
```

### Team Collaboration

#### Shared History Analysis
```bash
# Export team-readable timeline
claude-rewind timeline --limit 50 | tee team_timeline.txt

# Create change summary for standups
claude-rewind timeline --filter-date $(date +%Y-%m-%d) \
    --search "Claude" > todays_ai_changes.txt

# Generate weekly AI usage report
for day in {0..6}; do
    date_str=$(date -d "$day days ago" +%Y-%m-%d)
    echo "=== $date_str ===" >> weekly_report.txt
    claude-rewind timeline --filter-date $date_str >> weekly_report.txt
done
```

#### Safe Integration Patterns
```bash
# Before pulling from remote
claude-rewind monitor  # Ensure monitoring active
git status  # Check current state
# Create snapshot of current state
echo "# Before git pull" >> .gitignore

# After problematic pull/merge
claude-rewind timeline --limit 5
# If AI changes were lost or corrupted:
claude-rewind rollback <pre-pull-snapshot> --selective
# Choose only the AI-generated files to restore
```

### Debugging Workflows

#### AI-Introduced Bug Hunting
```bash
# When you discover a bug, trace back through AI changes
claude-rewind timeline --search "function_with_bug"

# Test each snapshot where the function was modified
claude-rewind rollback cr_suspect1
# Test the code
claude-rewind rollback cr_suspect2
# Test the code
# Continue until you find where the bug was introduced

# Once found, examine the exact change
claude-rewind diff cr_bug_introduced
```

#### Performance Regression Analysis
```bash
# When performance degrades, check recent AI changes
claude-rewind timeline --limit 20

# Rollback to test performance at different points
for snapshot in $(claude-rewind timeline --limit 10 | grep "cr_" | cut -d' ' -f2); do
    echo "Testing performance at $snapshot"
    claude-rewind rollback $snapshot --force
    # Run your performance tests here
    echo "Results for $snapshot: $(run_performance_test)"
done

# Return to current state when done
claude-rewind timeline --limit 1
claude-rewind rollback <latest-snapshot>
```

---

## ⚙️ Configuration

### Configuration File Location
- **Per-project**: `.claude-rewind/config.yml`
- **Global**: `~/.claude-rewind/config.yml` (if exists)

### Key Configuration Options

#### Storage Settings
```yaml
storage:
  max_snapshots: 100                    # Keep last 100 snapshots
  compression_enabled: true             # Compress snapshots (recommended)
  cleanup_after_days: 30               # Auto-cleanup after 30 days
  max_disk_usage_mb: 1000               # Limit storage to 1GB
```

#### Monitoring Settings
```yaml
hooks:
  claude_integration_enabled: true      # Enable Claude detection
  auto_snapshot_enabled: true           # Auto-create snapshots
  pre_snapshot_script: null             # Script to run before snapshots
  post_rollback_script: null            # Script to run after rollbacks
```

#### Performance Settings
```yaml
performance:
  max_file_size_mb: 100                 # Skip files larger than 100MB
  parallel_processing: true             # Use multiple cores
  memory_limit_mb: 500                  # Memory usage limit
  snapshot_timeout_seconds: 30          # Timeout for snapshot creation
  lazy_loading_enabled: true            # Load data on demand
  cache_size_limit: 10000               # Cache size for performance
  target_snapshot_time_ms: 500          # Target time for snapshots
```

#### Git Integration
```yaml
git_integration:
  respect_gitignore: true               # Honor .gitignore patterns
  auto_commit_rollbacks: false          # Auto-commit after rollbacks
```

#### Display Settings
```yaml
display:
  theme: "auto"                         # auto, light, dark
  show_file_sizes: true                 # Show file sizes in timeline
  max_diff_lines: 1000                  # Limit diff output
  syntax_highlighting: true             # Enable colors
  timestamp_format: "%Y-%m-%d %H:%M:%S" # Timestamp display format
```

### Customizing Configuration

#### View Current Config
```bash
claude-rewind config
```

#### Edit Configuration
```bash
# Edit with your preferred editor
nano .claude-rewind/config.yml
# or
vim .claude-rewind/config.yml
# or
code .claude-rewind/config.yml
```

#### Validate Configuration
```bash
claude-rewind validate
```

### Common Configuration Patterns

#### High-Performance Setup
```yaml
performance:
  max_file_size_mb: 50              # Smaller limit for speed
  parallel_processing: true
  memory_limit_mb: 1000             # More memory if available
  target_snapshot_time_ms: 200      # Faster snapshots
  lazy_loading_enabled: true
```

#### Space-Constrained Setup
```yaml
storage:
  max_snapshots: 25                 # Fewer snapshots
  compression_enabled: true         # Always compress
  cleanup_after_days: 7             # Aggressive cleanup
  max_disk_usage_mb: 200            # Small storage limit
```

#### Team/Shared Setup
```yaml
display:
  show_file_sizes: true
  syntax_highlighting: true
git_integration:
  respect_gitignore: true
  auto_commit_rollbacks: false       # Manual commits only
hooks:
  auto_snapshot_enabled: true
```

---

## 💡 Tips & Tricks

### Monitoring Tips

#### Optimize Detection Sensitivity
```bash
# Start with medium sensitivity
claude-rewind monitor --mode claude --sensitivity medium

# If missing changes, increase sensitivity
claude-rewind monitor --mode hybrid --sensitivity high

# If too noisy, decrease sensitivity
claude-rewind monitor --mode claude --sensitivity low
```

#### Background Monitoring
```bash
# Run in background with output to file
nohup claude-rewind monitor --verbose > claude-monitor.log 2>&1 &

# Check status
claude-rewind session

# Stop background monitoring
claude-rewind session --action stop
```

#### Multiple Projects
```bash
# Use screen/tmux for multiple projects
screen -S project1
cd /path/to/project1
claude-rewind monitor
# Ctrl+A, D to detach

screen -S project2
cd /path/to/project2
claude-rewind monitor
# Ctrl+A, D to detach

# List active sessions
screen -ls
```

### Timeline Navigation Tips

#### Quick Navigation
```bash
# Show recent activity
claude-rewind timeline --limit 5

# Find specific changes
claude-rewind timeline --search "error" --limit 20

# Show today's work
claude-rewind timeline --filter-date $(date +%Y-%m-%d)
```

#### Bookmarking Strategy
- Bookmark before major changes
- Bookmark after completing features
- Bookmark known-good states
- Bookmark before experimenting

#### Search Patterns
```bash
# Find file-specific changes
claude-rewind timeline --search "main.py"

# Find by action type
claude-rewind timeline --filter-action create_file

# Find by content
claude-rewind timeline --search "function"
```

### Diff Analysis Tips

#### Compare Strategies
```bash
# See what changed recently
claude-rewind diff $(claude-rewind timeline --limit 1 | grep cr_ | head -1)

# Compare to known good state
claude-rewind diff cr_known_good cr_current

# Focus on specific files
claude-rewind diff cr_abc123 --file src/main.py
```

#### Large Changes
```bash
# For big changes, use more context
claude-rewind diff cr_abc123 --context 10

# Break down by file
for file in $(claude-rewind preview cr_abc123 --files-only); do
    echo "=== $file ==="
    claude-rewind diff cr_abc123 --file "$file"
done
```

### Rollback Safety Tips

#### Always Preview
```bash
# Never rollback blindly
claude-rewind preview cr_abc123
claude-rewind rollback cr_abc123 --dry-run
claude-rewind rollback cr_abc123
```

#### Create Checkpoint
```bash
# Before major rollback, create a checkpoint
echo "# Checkpoint before rollback" >> .gitignore
claude-rewind monitor  # This creates a snapshot
claude-rewind rollback cr_target
```

#### Selective Rollback
```bash
# Only rollback problematic files
claude-rewind rollback cr_abc123 --selective
# Choose only the files that need reverting
```

### Performance Tips

#### Storage Management
```bash
# Regular cleanup
claude-rewind cleanup --dry-run  # Preview
claude-rewind cleanup            # Execute

# Monitor storage usage
claude-rewind status --detailed
```

#### Speed Optimization
```bash
# Reduce file size limits for faster snapshots
# Edit .claude-rewind/config.yml:
# performance:
#   max_file_size_mb: 25
#   target_snapshot_time_ms: 200
```

#### Memory Usage
```bash
# For large projects, increase memory limit
# Edit .claude-rewind/config.yml:
# performance:
#   memory_limit_mb: 1000
#   lazy_loading_enabled: true
```

---

## 🛠️ Troubleshooting

### Common Issues

#### Command Not Found
```bash
# Check installation
pip show claude-rewind

# Check PATH
echo $PATH | grep -o '/[^:]*bin'

# Reinstall if needed
pip uninstall claude-rewind
pip install -e .
```

#### Monitoring Not Detecting Changes
```bash
# Check sensitivity
claude-rewind monitor --mode hybrid --sensitivity high --verbose

# Check session status
claude-rewind session --action stats

# Check recent actions
claude-rewind session --show-recent 10
```

#### Timeline Empty or Missing Snapshots
```bash
# Check database
claude-rewind status --detailed

# Check if monitoring was active
claude-rewind session

# Validate system
claude-rewind validate
```

#### Rollback Conflicts
```bash
# Use preview to understand conflicts
claude-rewind preview cr_abc123 --detailed

# Use selective rollback
claude-rewind rollback cr_abc123 --selective

# Preserve current changes
claude-rewind rollback cr_abc123 --preserve-changes
```

#### Performance Issues
```bash
# Check storage usage
claude-rewind status --detailed

# Clean up old snapshots
claude-rewind cleanup

# Optimize configuration
claude-rewind config
# Edit performance settings
```

#### Database Corruption
```bash
# Validate system integrity
claude-rewind validate

# Check database status
claude-rewind status --health-check

# If corrupted, backup and reinitialize
cp .claude-rewind/metadata.db .claude-rewind/metadata.db.backup
claude-rewind init --skip-git-check
```

### Debug Mode

#### Verbose Monitoring
```bash
# Run with maximum verbosity
claude-rewind monitor --verbose --mode hybrid --sensitivity high
```

#### Debug Information
```bash
# Get detailed status
claude-rewind status --detailed

# Validate configuration and system
claude-rewind validate

# Check session statistics
claude-rewind session --action stats --show-recent 20
```

#### Log Analysis
```bash
# Monitor with logging
claude-rewind monitor --verbose 2>&1 | tee debug.log

# Analyze logs
grep -i "error\|warning\|failed" debug.log
grep -i "detected\|snapshot\|action" debug.log
```

### Recovery Procedures

#### Recover from Corrupted State
```bash
# 1. Backup current state
cp -r .claude-rewind .claude-rewind.backup

# 2. Try validation and repair
claude-rewind validate

# 3. If validation fails, reinitialize
mv .claude-rewind .claude-rewind.broken
claude-rewind init

# 4. If snapshots are recoverable, restore them
cp .claude-rewind.backup/snapshots/* .claude-rewind/snapshots/
```

#### Recover Specific Snapshots
```bash
# If timeline is broken but snapshots exist
ls .claude-rewind/snapshots/

# Manually inspect snapshot
cat .claude-rewind/snapshots/cr_abc123.json | jq '.'

# Create new timeline entry (advanced)
# This requires manual database manipulation
```

---

## 🌟 Real-World Examples

### Example 1: Feature Development Session

**Scenario**: Developing a new authentication system with Claude Code

```bash
# 1. Start monitoring
cd my-app
claude-rewind monitor --mode claude --sensitivity medium

# 2. Begin feature development with Claude Code
# (Claude creates auth.py, updates main.py, adds tests)

# 3. Review what was built
claude-rewind timeline --limit 10
```

**Timeline Output**:
```
#   ID          Timestamp      Action         Files  Size    Context
────────────────────────────────────────────────────────────────────
1   cr_f1a2b3   2025-09-23     create_file    1      2.1KB   Claude created auth.py with login system
                14:30:15
2   cr_g4h5i6   2025-09-23     edit_file      1      856B    Claude updated main.py to import auth
                14:32:42
3   cr_j7k8l9   2025-09-23     create_file    1      1.5KB   Claude added test_auth.py with unit tests
                14:35:18
```

```bash
# 4. Review the complete feature
claude-rewind diff cr_f1a2b3  # See all changes since feature start

# 5. Test the feature
# (discover bug in authentication logic)

# 6. Rollback to fix the issue
claude-rewind rollback cr_g4h5i6 --selective
# Select only auth.py to rollback

# 7. Have Claude fix the authentication
# (Claude makes corrections)

# 8. Verify the fix
claude-rewind timeline --limit 3
claude-rewind diff cr_j7k8l9  # See the fix
```

### Example 2: Debugging Session

**Scenario**: Application suddenly has errors after Claude Code changes

```bash
# 1. Identify when errors started
git log --oneline -10  # Check recent commits
# Notice errors started after recent Claude session

# 2. Find Claude changes around that time
claude-rewind timeline --filter-date 2025-09-23

# 3. Test different points in time
claude-rewind rollback cr_suspected_good
npm test  # Tests pass

claude-rewind rollback cr_suspected_bad
npm test  # Tests fail - found the problematic change!

# 4. Analyze the problematic change
claude-rewind diff cr_suspected_bad

# 5. See what exactly broke
claude-rewind diff cr_suspected_good cr_suspected_bad --file src/utils.py

# 6. Selective fix - keep good changes, fix the bug
claude-rewind rollback cr_suspected_good --selective
# Choose only the files that need to be reverted

# 7. Have Claude fix the specific issue
# (Provide Claude with the diff showing the problem)
```

### Example 3: Code Review Preparation

**Scenario**: Preparing for team code review after AI-assisted development

```bash
# 1. Generate comprehensive change summary
claude-rewind timeline --limit 50 > review_timeline.txt

# 2. Create detailed diff of all changes
BASELINE=$(claude-rewind timeline --limit 50 | tail -1 | grep -o 'cr_[a-f0-9]\+')
claude-rewind diff $BASELINE > review_changes.diff

# 3. Categorize changes by type
claude-rewind timeline --filter-action create_file > new_files.txt
claude-rewind timeline --filter-action edit_file > modified_files.txt

# 4. Create per-file change summary
for file in $(claude-rewind timeline --limit 20 | grep -o 'src/[^[:space:]]*' | sort | uniq); do
    echo "=== Changes to $file ===" >> file_changes.txt
    claude-rewind timeline --search "$file" >> file_changes.txt
    echo "" >> file_changes.txt
done

# 5. Bookmark important milestones for review
claude-rewind timeline
# Use interactive mode to bookmark key snapshots

# 6. Generate reviewable documentation
echo "# AI-Assisted Development Summary" > REVIEW.md
echo "" >> REVIEW.md
echo "## Timeline" >> REVIEW.md
cat review_timeline.txt >> REVIEW.md
echo "" >> REVIEW.md
echo "## Key Changes" >> REVIEW.md
cat file_changes.txt >> REVIEW.md
```

### Example 4: Experiment Management

**Scenario**: Trying different AI-generated approaches to solve a problem

```bash
# 1. Capture baseline
claude-rewind monitor
echo "# Experiment baseline" >> EXPERIMENTS.md
BASELINE=$(claude-rewind timeline --limit 1 | grep -o 'cr_[a-f0-9]\+')

# 2. Experiment 1: AI approach using recursion
# (Use Claude to implement recursive solution)
claude-rewind timeline --limit 3
EXP1=$(claude-rewind timeline --limit 1 | grep -o 'cr_[a-f0-9]\+')

# Test performance
python benchmark.py  # Record results
echo "Experiment 1 (recursive): 245ms" >> EXPERIMENTS.md

# 3. Experiment 2: AI approach using iteration
claude-rewind rollback $BASELINE
# (Use Claude to implement iterative solution)
EXP2=$(claude-rewind timeline --limit 1 | grep -o 'cr_[a-f0-9]\+')

# Test performance
python benchmark.py  # Record results
echo "Experiment 2 (iterative): 89ms" >> EXPERIMENTS.md

# 4. Experiment 3: AI hybrid approach
claude-rewind rollback $BASELINE
# (Use Claude to implement hybrid solution)
EXP3=$(claude-rewind timeline --limit 1 | grep -o 'cr_[a-f0-9]\+')

# Test performance
python benchmark.py  # Record results
echo "Experiment 3 (hybrid): 156ms" >> EXPERIMENTS.md

# 5. Compare all approaches
echo "## Comparison" >> EXPERIMENTS.md
claude-rewind diff $BASELINE $EXP1 > exp1_changes.diff
claude-rewind diff $BASELINE $EXP2 > exp2_changes.diff
claude-rewind diff $BASELINE $EXP3 > exp3_changes.diff

# 6. Choose best approach (Experiment 2)
claude-rewind rollback $EXP2
echo "Selected iterative approach (best performance)" >> EXPERIMENTS.md
```

### Example 5: Team Collaboration

**Scenario**: Multiple developers using Claude Code on shared project

```bash
# 1. Daily AI change review (in team standup)
claude-rewind timeline --filter-date $(date +%Y-%m-%d) > daily_ai_changes.txt
echo "AI Changes from $(date +%Y-%m-%d):" >> team_report.txt
cat daily_ai_changes.txt >> team_report.txt

# 2. Weekly AI usage analysis
for day in {0..6}; do
    date_str=$(date -d "$day days ago" +%Y-%m-%d)
    count=$(claude-rewind timeline --filter-date $date_str | grep "cr_" | wc -l)
    echo "$date_str: $count AI actions" >> weekly_stats.txt
done

# 3. Before git pull (protect AI changes)
claude-rewind monitor  # Ensure monitoring
echo "# Before git pull $(date)" >> .gitignore  # Create snapshot
PRE_PULL=$(claude-rewind timeline --limit 1 | grep -o 'cr_[a-f0-9]\+')

git pull origin main

# If conflicts or lost AI changes:
claude-rewind timeline --limit 5
claude-rewind rollback $PRE_PULL --selective
# Choose AI-generated files to restore

# 4. Share AI-generated solutions with team
claude-rewind diff cr_solution > ai_solution.patch
# Send ai_solution.patch to team
# Others can review the AI-generated changes

# 5. Document AI contributions for project history
claude-rewind timeline --limit 100 | \
    grep -E "(create_file|edit_file)" | \
    awk '{print $3, $4, $5}' > ai_contributions.log
```

---

## 🎓 Advanced Usage Patterns

### Pattern 1: Continuous Integration with AI
```bash
# Pre-commit hook to verify AI changes
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
# Verify recent AI changes don't break tests

if claude-rewind session | grep -q "ACTIVE"; then
    echo "Verifying recent AI changes..."

    # Get recent AI snapshots
    recent_snapshots=$(claude-rewind timeline --limit 5 | grep "cr_" | head -3)

    for snapshot in $recent_snapshots; do
        echo "Testing state at $snapshot"
        claude-rewind rollback $snapshot --force

        if ! npm test; then
            echo "Tests fail at $snapshot"
            echo "Review AI changes: claude-rewind diff $snapshot"
            exit 1
        fi
    done

    # Return to current state
    claude-rewind timeline --limit 1
    current=$(claude-rewind timeline --limit 1 | grep -o 'cr_[a-f0-9]\+')
    claude-rewind rollback $current --force
fi
EOF

chmod +x .git/hooks/pre-commit
```

### Pattern 2: AI Change Documentation
```bash
# Auto-generate change documentation
cat > document_ai_changes.sh << 'EOF'
#!/bin/bash
# Generate documentation for AI changes

echo "# AI Development Log - $(date +%Y-%m-%d)" > AI_CHANGELOG.md
echo "" >> AI_CHANGELOG.md

# Get today's AI changes
claude-rewind timeline --filter-date $(date +%Y-%m-%d) | \
while read line; do
    if echo "$line" | grep -q "cr_"; then
        snapshot=$(echo "$line" | grep -o 'cr_[a-f0-9]\+')
        action=$(echo "$line" | awk '{print $4}')
        time=$(echo "$line" | awk '{print $3}')

        echo "## $time - $action ($snapshot)" >> AI_CHANGELOG.md
        echo "" >> AI_CHANGELOG.md

        # Get the diff for this change
        claude-rewind diff $snapshot | head -20 >> AI_CHANGELOG.md
        echo "" >> AI_CHANGELOG.md
        echo "---" >> AI_CHANGELOG.md
        echo "" >> AI_CHANGELOG.md
    fi
done
EOF

chmod +x document_ai_changes.sh
```

### Pattern 3: Smart Backup Strategy
```bash
# Intelligent backup before major changes
cat > smart_backup.sh << 'EOF'
#!/bin/bash
# Create intelligent backups before major operations

backup_before_major_change() {
    local change_type="$1"
    local description="$2"

    # Create a marked checkpoint
    echo "# CHECKPOINT: $change_type - $description - $(date)" >> .claude_checkpoints

    # Ensure monitoring is active
    if ! claude-rewind session | grep -q "ACTIVE"; then
        claude-rewind monitor &
        sleep 2
    fi

    # Get the snapshot ID
    checkpoint_id=$(claude-rewind timeline --limit 1 | grep -o 'cr_[a-f0-9]\+')

    # Bookmark it
    echo "Created checkpoint: $checkpoint_id for $change_type"

    # Store in recovery file
    echo "$checkpoint_id:$change_type:$description:$(date)" >> .claude_recovery
}

# Usage examples:
# backup_before_major_change "refactor" "Converting to async/await"
# backup_before_major_change "feature" "Adding authentication system"
# backup_before_major_change "fix" "Resolving memory leak issue"
EOF
```

---

This comprehensive guide covers every aspect of using Claude Rewind effectively. From basic usage to advanced workflows, you now have the knowledge to master this powerful tool for Claude Code development safety and productivity.

Remember: **The key to mastering Claude Rewind is regular practice with real projects. Start with basic monitoring and gradually incorporate advanced features as you become comfortable with the tool.**