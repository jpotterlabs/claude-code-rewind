# Native Hooks Guide

**Event-Driven Snapshots for Claude Code 2.0+**

---

## Table of Contents

- [Overview](#overview)
- [Why Native Hooks?](#why-native-hooks)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Hook Events Reference](#hook-events-reference)
- [CLI Commands](#cli-commands)
- [Migration Guide](#migration-guide)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Overview

Native Hooks integration transforms Claude Code Rewind from a **polling-based** system to an **event-driven** system. Instead of checking for changes every 2 seconds, Claude Code 2.0 **instantly notifies** Rewind when events occur.

### Key Benefits

- ⚡ **Zero Latency** - Snapshots created instantly when Claude acts
- 🧠 **Rich Context** - Capture extended thinking, confidence scores, prompt context
- 🤖 **Subagent-Aware** - Track subagent delegation and completion separately
- 🎯 **Precise** - Know exactly which tool caused each snapshot
- 💾 **Efficient** - No background polling process needed

### Compatibility

- **Requires**: Claude Code 2.0+ with native hooks support
- **Falls back to**: Polling-based `monitor` command for older versions
- **Coexists with**: Original `init` command (still required for setup)

---

## Why Native Hooks?

### The Old Way (Polling)

```bash
$ claude-rewind monitor
👀 Watching for changes every 2 seconds...
# Background process checks git status repeatedly
# 2-second delay between change and snapshot
# No context about what Claude was thinking
```

**Problems:**
- 2-second latency (or longer if CPU is busy)
- No insight into Claude's reasoning
- Can't distinguish between tools
- Resource overhead from constant polling

### The New Way (Event-Driven)

```bash
$ claude-rewind hooks init
✓ Configured .claude/settings.json
🎉 Claude Code Rewind is now event-driven!

# Claude automatically calls hooks when events fire:
# - PostToolUse: Instant snapshot after Edit/Write/Bash
# - SubagentStop: Capture subagent's work
# - Error: Auto-suggest rollback
# - SessionStart/End: Track entire sessions
```

**Advantages:**
- **Instant** snapshots (no polling delay)
- **Rich context** (extended thinking, confidence scores)
- **Tool-specific** tracking (know which tool made changes)
- **Subagent-aware** (separate snapshots for subagents)
- **Error handling** (automatic rollback suggestions)
- **No background process** needed

---

## Quick Start

### Step 1: Initialize Rewind (One-Time)

```bash
cd your-project
claude-rewind init
```

This creates:
- `.claude-rewind/` directory
- SQLite database for metadata
- Configuration file
- Git integration (if applicable)

### Step 2: Enable Native Hooks

```bash
claude-rewind hooks init
```

**Output:**
```
✓ Configured .claude/settings.json
✓ Registered 7 native hooks:
  • SessionStart → session tracking
  • SessionEnd → session finalization
  • PreToolUse → pre-change state capture
  • PostToolUse → automatic snapshots
  • SubagentStart → subagent delegation tracking
  • SubagentStop → subagent work completion
  • Error → auto-rollback suggestions

🎉 Claude Code Rewind is now event-driven!

Next steps:
  1. Start using Claude Code normally
  2. View snapshots: claude-rewind timeline
  3. Check hook status: claude-rewind hooks status
```

### Step 3: Verify Configuration

```bash
claude-rewind hooks status
```

**Example Output:**
```
Status: ✓ Registered
Configuration: /home/user/project/.claude/settings.json

Active hooks: 7
  ✓ SessionStart    - Initialize session tracking
  ✓ SessionEnd      - Finalize session tracking
  ✓ PreToolUse      - Capture pre-change state
  ✓ PostToolUse     - Create automatic snapshot
  ✓ SubagentStart   - Track subagent delegation
  ✓ SubagentStop    - Capture subagent work completion
  ✓ Error           - Auto-suggest rollback on errors

✨ All hooks working correctly!
```

### Step 4: Use Claude Code Normally

That's it! Claude Code Rewind now automatically captures snapshots whenever Claude:
- Edits a file
- Creates a new file
- Runs a command
- Delegates to a subagent
- Encounters an error

View your timeline:
```bash
claude-rewind timeline
claude-rewind diff latest
```

---

## Architecture

### How It Works

```
┌─────────────────────────────────────────────────┐
│              Claude Code 2.0                     │
│  (User interacts with Claude)                    │
└─────────────────────────────────────────────────┘
                    │
                    │ 1. Action occurs (Edit, Write, etc.)
                    ▼
┌─────────────────────────────────────────────────┐
│         Native Hooks System                      │
│  (Configured in .claude/settings.json)           │
└─────────────────────────────────────────────────┘
                    │
                    │ 2. Hook fires instantly
                    ▼
┌─────────────────────────────────────────────────┐
│      claude-rewind hook-handler                  │
│  (Entry point for all hook events)               │
└─────────────────────────────────────────────────┘
                    │
                    │ 3. Parse event data
                    ▼
┌─────────────────────────────────────────────────┐
│       NativeHookDispatcher                       │
│  (Routes events to appropriate handlers)         │
└─────────────────────────────────────────────────┘
                    │
                    │ 4. Create snapshot with rich context
                    ▼
┌─────────────────────────────────────────────────┐
│          SnapshotEngine                          │
│  (Existing v1.0 snapshot creation logic)         │
└─────────────────────────────────────────────────┘
                    │
                    │ 5. Store snapshot + metadata
                    ▼
┌─────────────────────────────────────────────────┐
│    .claude-rewind/snapshots/ + database          │
└─────────────────────────────────────────────────┘
```

### Configuration File

`.claude/settings.json` (created by `hooks init`):

```json
{
  "hooks": {
    "SessionStart": {
      "command": "claude-rewind",
      "args": ["hook-handler", "session-start"],
      "background": true,
      "description": "Initialize Claude Code Rewind session tracking"
    },
    "PostToolUse": {
      "command": "claude-rewind",
      "args": ["hook-handler", "post-tool-use"],
      "background": true,
      "description": "Create automatic snapshot after tool use"
    },
    "SubagentStop": {
      "command": "claude-rewind",
      "args": ["hook-handler", "subagent-stop"],
      "background": true,
      "description": "Capture subagent work completion"
    },
    "Error": {
      "command": "claude-rewind",
      "args": ["hook-handler", "error"],
      "background": true,
      "description": "Auto-suggest rollback on errors"
    }
    // ... 3 more hooks
  }
}
```

---

## Hook Events Reference

### 1. SessionStart

**Fires**: When Claude Code session begins

**Captures**:
- Session ID
- Session start timestamp
- Initial project state

**Snapshot Tags**:
- `session-start`
- `session:{session_id}`

**Example Snapshot**:
```
ID: abc123
Description: Session start: session-2025-10-02-1430
Tags: session-start, session:session-2025-10-02-1430
Time: 2025-10-02 14:30:00
```

---

### 2. SessionEnd

**Fires**: When Claude Code session ends

**Captures**:
- Session ID
- Session end timestamp
- Total session duration
- Final project state

**Snapshot Tags**:
- `session-end`
- `session:{session_id}`

**Example Snapshot**:
```
ID: abc456
Description: Session end: session-2025-10-02-1430 (duration: 3600.5s)
Tags: session-end, session:session-2025-10-02-1430
Time: 2025-10-02 15:30:00
```

---

### 3. PreToolUse

**Fires**: Before Claude uses a tool (Edit, Write, Bash, etc.)

**Captures**:
- Tool name
- Project state before change
- (Currently logged, not creating snapshots to reduce overhead)

**Future Use**:
- Calculate precise diffs by comparing pre/post states
- Detect concurrent changes from other sources

---

### 4. PostToolUse ⭐

**Fires**: After Claude successfully uses a tool

**Captures**:
- Tool name (e.g., "Edit", "Write", "Bash")
- Prompt context (truncated to 100 chars)
- Extended thinking (Claude's reasoning)
- Confidence score (0.0-1.0)
- Modified files
- Project state after change

**Snapshot Tags**:
- `auto` - Automatic snapshot
- `tool:{tool_name}` - Which tool was used
- `session:{session_id}` - Which session
- `confidence:{score}` - Confidence level (if available)

**Example Snapshot**:
```
ID: abc789
Description: Edit: Fix authentication bug in login.py
Tags: auto, tool:Edit, session:session-2025-10-02-1430, confidence:0.87
Time: 2025-10-02 14:45:23
Files: 1 changed (login.py)
```

**This is the primary hook** that creates automatic snapshots for most Claude actions.

---

### 5. SubagentStart

**Fires**: When Claude delegates to a subagent

**Captures**:
- Subagent name
- Subagent type (e.g., "code-reviewer", "test-runner")
- Delegation reason (why subagent was invoked)
- Parent session ID
- Project state before subagent

**Snapshot Tags**:
- `subagent-start`
- `subagent:{name}`
- `type:{type}`
- `session:{session_id}`

**Example Snapshot**:
```
ID: sub123
Description: Subagent code-reviewer started: Review recent changes
Tags: subagent-start, subagent:code-reviewer, type:code-reviewer, session:session-2025-10-02-1430
Time: 2025-10-02 14:50:00
```

---

### 6. SubagentStop ⭐

**Fires**: When subagent completes its work

**Captures**:
- Subagent name
- Subagent type
- Parent session ID
- All changes made by subagent
- Project state after subagent

**Snapshot Tags**:
- `subagent-stop`
- `subagent:{name}`
- `type:{type}`
- `parent:{parent_session}`
- `session:{session_id}`

**Example Snapshot**:
```
ID: sub456
Description: Subagent code-reviewer completed
Tags: subagent-stop, subagent:code-reviewer, type:code-reviewer, parent:session-2025-10-02-1430
Time: 2025-10-02 14:55:00
Files: 3 changed (auth.py, tests.py, README.md)
```

**Why This Matters**:
- You can rollback subagent changes independently from main Claude actions
- See exactly what the subagent did vs what main Claude did
- Useful when subagent makes unwanted changes

---

### 7. Error ⭐

**Fires**: When Claude encounters an error

**Captures**:
- Error type
- Error message
- Stack trace (if available)
- Project state when error occurred

**Snapshot Tags**:
- `error`
- `error-type:{type}`
- `session:{session_id}`

**Auto-Rollback Suggestion**:
- Analyzes recent snapshots
- Suggests most recent working state
- Logs suggestion for user review

**Example Snapshot**:
```
ID: err789
Description: Error: TypeError
Tags: error, error-type:TypeError, session:session-2025-10-02-1430
Time: 2025-10-02 15:00:00

💡 Suggestion: Consider rolling back to snapshot abc789 (Edit: Fix authentication bug)
```

**Use Case**:
```bash
# After error occurs, check suggestions
claude-rewind timeline --tags error

# Rollback to suggested snapshot
claude-rewind rollback abc789
```

---

## CLI Commands

### `claude-rewind hooks init`

**Description**: Initialize native hooks integration

**Usage**:
```bash
claude-rewind hooks init [--force]
```

**Options**:
- `--force` - Overwrite existing hooks configuration

**What It Does**:
1. Creates `.claude/` directory (if needed)
2. Creates or updates `.claude/settings.json`
3. Registers 7 native hooks
4. Preserves any existing hooks you may have configured
5. Validates configuration

**Output**:
```
✓ Configured .claude/settings.json
✓ Registered 7 native hooks
🎉 Claude Code Rewind is now event-driven!
```

**Notes**:
- Safe to run multiple times (idempotent)
- Preserves user's custom hooks
- Only modifies hooks that call `claude-rewind`

---

### `claude-rewind hooks status`

**Description**: Show status of registered hooks

**Usage**:
```bash
claude-rewind hooks status
```

**Output**:
```
Status: ✓ Registered
Configuration: /home/user/project/.claude/settings.json

Active hooks: 7
  ✓ SessionStart    - Initialize session tracking
  ✓ SessionEnd      - Finalize session tracking
  ✓ PreToolUse      - Capture pre-change state
  ✓ PostToolUse     - Create automatic snapshot
  ✓ SubagentStart   - Track subagent delegation
  ✓ SubagentStop    - Capture subagent work completion
  ✓ Error           - Auto-suggest rollback on errors

✨ All hooks working correctly!
```

**Exit Codes**:
- `0` - All hooks registered and working
- `1` - Some or all hooks missing

---

### `claude-rewind hooks test`

**Description**: Test native hooks configuration

**Usage**:
```bash
claude-rewind hooks test
```

**What It Does**:
1. Checks if `.claude/settings.json` exists
2. Validates JSON syntax
3. Verifies all 7 expected hooks are present
4. Checks hook command paths are correct
5. Confirms `claude-rewind` is in PATH

**Output (Success)**:
```
✅ All hooks are registered correctly!

Registered hooks: 7/7
  ✓ SessionStart
  ✓ SessionEnd
  ✓ PreToolUse
  ✓ PostToolUse
  ✓ SubagentStart
  ✓ SubagentStop
  ✓ Error

Configuration: Valid
Command path: claude-rewind (found in PATH)
```

**Output (Failure)**:
```
❌ Hook configuration has issues:

Missing hooks: 2
  ✗ PostToolUse
  ✗ Error

Registered hooks: 5/7

Please run: claude-rewind hooks init --force
```

**Use Case**:
- Debugging hook issues
- Verifying installation
- CI/CD validation

---

### `claude-rewind hooks disable`

**Description**: Disable native hooks (revert to polling)

**Usage**:
```bash
claude-rewind hooks disable [--confirm]
```

**Options**:
- `--confirm` - Skip confirmation prompt

**What It Does**:
1. Removes all `claude-rewind` hooks from `.claude/settings.json`
2. Preserves any other hooks you may have
3. Keeps `.claude-rewind/` data intact
4. Does not affect existing snapshots

**Output**:
```
⚠️  This will disable event-driven snapshots.
You can re-enable with: claude-rewind hooks init

Removed 7 hooks from .claude/settings.json
✓ Hooks disabled

To continue using Rewind, run: claude-rewind monitor
```

**Use Cases**:
- Troubleshooting hook issues
- Temporarily reverting to polling
- Testing performance differences
- Uninstalling Rewind

---

### `claude-rewind hook-handler`

**Description**: Handle hook event (called by Claude Code)

**Usage**:
```bash
claude-rewind hook-handler <event-type> <event-data>
```

**⚠️ Internal Command**: This is called automatically by Claude Code. You should not run it manually.

**Arguments**:
- `event-type` - Type of event (e.g., "PostToolUse", "Error")
- `event-data` - JSON string with event data

**Example (how Claude calls it)**:
```bash
claude-rewind hook-handler post-tool-use '{"session_id":"abc","tool_name":"Edit","prompt_context":"Fix bug",...}'
```

**What It Does**:
1. Parses event type and data
2. Creates `HookEvent` object
3. Dispatches to `NativeHookDispatcher`
4. Appropriate handler creates snapshot
5. Logs outcome

**Exit Codes**:
- `0` - Event handled successfully
- `1` - Event parsing or handling failed

---

## Migration Guide

### From Polling to Native Hooks

If you're currently using `claude-rewind monitor` (polling), here's how to migrate:

#### Step 1: Stop Monitor (if running)

```bash
# Find and kill monitor process
ps aux | grep "claude-rewind monitor"
kill <pid>
```

#### Step 2: Enable Native Hooks

```bash
cd your-project
claude-rewind hooks init
```

#### Step 3: Verify

```bash
claude-rewind hooks status
claude-rewind hooks test
```

#### Step 4: Test with Claude

1. Start a Claude Code session
2. Ask Claude to make a simple change
3. Check timeline:
   ```bash
   claude-rewind timeline
   ```
4. Verify new snapshot was created instantly

#### Step 5: Remove Monitor from Startup (Optional)

If you had `monitor` running automatically (e.g., in shell RC file), remove it:

```bash
# Remove from ~/.bashrc or ~/.zshrc
# OLD:
# claude-rewind monitor &

# No longer needed with native hooks!
```

### Coexistence Mode

You can run **both** hooks and monitor simultaneously (though redundant):

```bash
# Enable hooks
claude-rewind hooks init

# Also run monitor (for backup/testing)
claude-rewind monitor
```

**Why you might do this:**
- Testing hooks reliability
- Gradual migration
- Comparing performance

**Downsides:**
- Duplicate snapshots
- Higher resource usage
- Redundant disk I/O

### Fallback to Polling

If hooks aren't working, easily fallback:

```bash
# Disable hooks
claude-rewind hooks disable --confirm

# Resume polling
claude-rewind monitor
```

Your existing snapshots remain intact.

---

## Troubleshooting

### Hooks Not Creating Snapshots

**Symptom**: `claude-rewind timeline` shows no new snapshots after enabling hooks

**Diagnosis**:
```bash
# Check hook status
claude-rewind hooks status

# Test configuration
claude-rewind hooks test

# Check Claude Code can find claude-rewind
which claude-rewind

# Check logs (if configured)
tail -f ~/.claude-rewind/logs/hooks.log
```

**Common Causes**:

1. **`claude-rewind` not in PATH**
   - Solution: Ensure `pip install -e .` completed successfully
   - Test: `which claude-rewind` should show path

2. **Hooks not registered**
   - Solution: `claude-rewind hooks init --force`

3. **Claude Code version too old**
   - Solution: Update Claude Code to 2.0+
   - Fallback: Use `claude-rewind monitor`

4. **Permissions issue**
   - Solution: Check `.claude/settings.json` is writable
   - Test: `ls -la .claude/settings.json`

---

### Hooks Registered But Not Firing

**Symptom**: `hooks status` shows "✓ Registered" but no snapshots created

**Diagnosis**:
```bash
# Manually trigger a hook
claude-rewind hook-handler post-tool-use '{"session_id":"test","tool_name":"Edit","timestamp":"2025-10-02T14:30:00"}'

# Check if snapshot was created
claude-rewind timeline
```

**Common Causes**:

1. **Invalid JSON in event data**
   - Solution: Check `.claude/settings.json` syntax
   - Test: `cat .claude/settings.json | python -m json.tool`

2. **Background flag preventing output**
   - Hooks run with `"background": true`, so errors are silent
   - Solution: Temporarily set to `false` for debugging

3. **Claude Code not sending event data**
   - May be a Claude Code bug
   - Solution: Report to Claude Code team, use `monitor` as fallback

---

### Duplicate Snapshots

**Symptom**: Two snapshots created for each Claude action

**Cause**: Both hooks and monitor are running

**Solution**:
```bash
# Choose one:

# Option 1: Disable hooks, use monitor
claude-rewind hooks disable --confirm
claude-rewind monitor

# Option 2: Keep hooks, stop monitor
# (kill monitor process)
ps aux | grep "claude-rewind monitor" | grep -v grep | awk '{print $2}' | xargs kill
```

---

### ".claude/settings.json" Not Found

**Symptom**: `hooks status` shows "Configuration file not found"

**Cause**: `.claude/` directory doesn't exist (rare in Claude Code 2.0+)

**Solution**:
```bash
# Manually create directory
mkdir -p .claude

# Initialize hooks (will create settings.json)
claude-rewind hooks init
```

---

### Hooks Disabled After Git Pull

**Symptom**: Hooks work locally but not after pulling changes

**Cause**: `.claude/settings.json` is not committed to git (by design)

**Solution**:
```bash
# Re-run hooks init on each machine
claude-rewind hooks init
```

**Best Practice**: Add to project README:
```markdown
## Setup

1. Install dependencies
2. Initialize Rewind: `claude-rewind init`
3. Enable hooks: `claude-rewind hooks init`
```

---

## Advanced Usage

### Custom Hook Logging

Enable detailed logging for debugging:

```python
# In your .claude-rewind/config.yaml
logging:
  level: DEBUG
  file: ~/.claude-rewind/logs/hooks.log
```

Then tail the log:
```bash
tail -f ~/.claude-rewind/logs/hooks.log
```

---

### Selective Hook Registration

If you only want specific hooks, manually edit `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": {
      "command": "claude-rewind",
      "args": ["hook-handler", "post-tool-use"],
      "background": true
    },
    "Error": {
      "command": "claude-rewind",
      "args": ["hook-handler", "error"],
      "background": true
    }
    // Only these 2 hooks, not all 7
  }
}
```

**Use Case**: Reduce overhead by only tracking critical events

---

### Filtering Snapshots by Hook Event

Use tags to filter snapshots by event type:

```bash
# Only session start/end snapshots
claude-rewind timeline --tags session-start,session-end

# Only error snapshots
claude-rewind timeline --tags error

# Only subagent snapshots
claude-rewind timeline --tags subagent-stop

# Only Edit tool snapshots
claude-rewind timeline --tags tool:Edit

# High confidence snapshots (requires parsing)
claude-rewind timeline --tags confidence:0.8
```

---

### Programmatic Access to Hook Data

Hook events are stored in snapshot metadata:

```python
from claude_rewind.storage.database import DatabaseManager
from pathlib import Path

db = DatabaseManager(Path(".claude-rewind/metadata.db"))

# Get all snapshots with extended thinking
snapshots = db.list_snapshots()
for snap in snapshots:
    if 'extended-thinking' in snap.get('tags', []):
        print(f"{snap['id']}: {snap['description']}")
```

---

### Integration with CI/CD

Validate hooks in CI:

```yaml
# .github/workflows/validate-rewind.yml
name: Validate Claude Rewind

on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install Rewind
        run: pip install -e .
      - name: Test hooks
        run: |
          claude-rewind hooks test
          if [ $? -ne 0 ]; then
            echo "Hooks not configured correctly"
            exit 1
          fi
```

---

## Summary

Native Hooks transform Claude Code Rewind into a **zero-latency, context-rich, event-driven** time machine:

| Feature | Polling (`monitor`) | Native Hooks |
|---------|-------------------|--------------|
| **Latency** | 2+ seconds | Instant (0ms) |
| **Context** | File changes only | Extended thinking, confidence, prompts |
| **Overhead** | Background process | No process needed |
| **Subagent Tracking** | No | Yes |
| **Error Detection** | No | Auto-rollback suggestions |
| **Tool Attribution** | No | Yes (know which tool made changes) |

**Next Steps**:
1. Enable hooks: `claude-rewind hooks init`
2. Verify: `claude-rewind hooks status`
3. Use Claude normally - snapshots created automatically
4. Explore timeline: `claude-rewind timeline`

**Need Help?**
- GitHub Issues: https://github.com/jpotterlabs/claude-code-rewind/issues
- Documentation: See `USAGE_GUIDE.md` for general Rewind usage
