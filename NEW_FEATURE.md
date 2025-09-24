# ⚠️ DEPRECATED: Automatic Snapshotting with `watch`

> **This document describes the legacy `watch` command which has been replaced by the sophisticated `monitor` system. See `CLAUDE_INTEGRATION.md` for the current implementation.**

## The Legacy Problem

The Claude Code Rewind Tool was designed to automatically capture every change made by Claude Code, but the mechanism for doing so was not implemented. The tool would initialize successfully, but no snapshots were ever taken.

## The Legacy Solution (Now Deprecated)

The original `watch` command was a temporary solution that monitored the project directory for file changes using basic filesystem watching. When any change was detected, it would create a snapshot.

**❌ Problems with the `watch` approach:**
- Captured ALL file changes, not just Claude actions
- No context about what caused the change
- High noise-to-signal ratio
- No session management
- Generic filesystem monitoring only

## ✅ Current Solution: `claude-rewind monitor`

The `watch` command has been completely replaced by the sophisticated `monitor` system:

1. **Initialize Claude Rewind:**
   ```bash
   claude-rewind init
   ```

2. **Start Intelligent Monitoring:**
   ```bash
   claude-rewind monitor
   ```

**🎯 Benefits of the new system:**
- **Intelligent Detection**: Only captures actual Claude Code actions
- **Rich Context**: Knows which Claude tool was used and why
- **Session Management**: Tracks complete Claude Code sessions
- **Multiple Modes**: Claude-specific, filesystem, or hybrid monitoring
- **Configurable Sensitivity**: Adjust detection aggressiveness
- **Better Performance**: More efficient than generic file watching

## Migration Guide

If you were using the old `watch` command:

```bash
# Old (deprecated)
claude-rewind watch

# New (recommended)
claude-rewind monitor

# Or with options
claude-rewind monitor --mode hybrid --sensitivity high
```

## Current Implementation

The new system uses sophisticated Claude Code integration rather than simple file watching. See `CLAUDE_INTEGRATION.md` for complete documentation of the current architecture and capabilities.

---

**📚 For current documentation, see:**
- `CLAUDE_INTEGRATION.md` - Complete system overview
- `claude-rewind monitor --help` - Command options
- `claude-rewind session --help` - Session management
