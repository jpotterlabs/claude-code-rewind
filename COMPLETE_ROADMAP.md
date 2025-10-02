# 🚀 Claude Code Rewind - Complete Roadmap (v1.5 → v2.5)

## 🎯 Vision: From CLI Tool to First-Class Claude Code Citizen

**Evolution Path**:
1. **v1.0** ✅: Solid CLI foundation with automatic snapshots
2. **v1.5**: Native hooks + Web dashboard (event-driven + visual)
3. **v2.0**: SDK integration (conversational interface)
4. **v2.5**: First-class IDE integration (native UI)

`★ Insight ─────────────────────────────────────`
The roadmap follows a natural evolution: **reliable foundation** → **event-driven integration** → **conversational interface** → **native IDE experience**. Each phase builds on the previous, transforming Claude Code Rewind from an external tool to an integrated part of the Claude Code experience.
`─────────────────────────────────────────────────`

---

## ✅ v1.0 - Solid Foundation (Complete)

### What We Built
- CLI-driven time travel debugging
- Automatic snapshot capture
- Granular rollback with selective file support
- Interactive timeline
- Smart cleanup system
- Hook architecture (polling-based)
- Git integration

### Current State
- **12/12 CLI commands** fully functional
- **Production-ready** with comprehensive testing
- **Cross-platform** Windows/Mac/Linux support
- **Well-documented** with usage guides

---

## 🔄 v1.5 - Native Hooks + Web Dashboard

**Duration**: ~5 weeks total

**Strategic Goal**: Move from polling to event-driven architecture + add visual interface

---

### v1.5a: Native Hooks Support (Weeks 1-2)

**Goal**: Event-driven integration with Claude Code 2.0's native hook system

#### What Users See

```bash
$ claude-rewind init
# Output:
# ✓ Configured .claude/settings.json with hooks
# ✓ PostToolUse → automatic snapshots
# ✓ SubagentStop → subagent tracking
# ✓ SessionStart/End → lifecycle management
# 🎉 Claude Code Rewind is now event-driven!
```

#### Architecture Shift

**Before (v1.0 - Polling)**:
```
┌─────────────────────────────────────────────┐
│  Rewind Monitor (polls every 2 seconds)     │
│    └─> Checks for Claude activity           │
│         └─> Creates snapshot if detected     │
└─────────────────────────────────────────────┘
```

**After (v1.5a - Event-Driven)**:
```
┌─────────────────────────────────────────────┐
│       Claude Code fires native hooks         │
│  PostToolUse → SubagentStop → Error         │
└─────────────────────────────────────────────┘
                    ▼
┌─────────────────────────────────────────────┐
│    Rewind Hook Handlers (instant)           │
│      └─> Create snapshot with rich context  │
└─────────────────────────────────────────────┘
```

#### Benefits

✅ **Zero Latency**: Snapshots created instantly when events fire
✅ **Rich Context**: Access to extended thinking, confidence scores, subagent info
✅ **Reliable**: No polling = no missed actions
✅ **Efficient**: Only runs when Claude actually does something

#### Implementation

**Week 1: Hook Registration**
```python
# claude_rewind/native_hooks/registration.py

def register_native_hooks():
    """Configure .claude/settings.json with Rewind hooks."""

    hooks_config = {
        "hooks": {
            "SessionStart": {
                "command": "claude-rewind",
                "args": ["hook-handler", "session-start"],
                "background": True
            },
            "PreToolUse": {
                "command": "claude-rewind",
                "args": ["hook-handler", "pre-tool-use"],
                "background": True
            },
            "PostToolUse": {
                "command": "claude-rewind",
                "args": ["hook-handler", "post-tool-use"],
                "background": True
            },
            "SubagentStart": {
                "command": "claude-rewind",
                "args": ["hook-handler", "subagent-start"],
                "background": True
            },
            "SubagentStop": {
                "command": "claude-rewind",
                "args": ["hook-handler", "subagent-stop"],
                "background": True
            },
            "Error": {
                "command": "claude-rewind",
                "args": ["hook-handler", "error"],
                "background": True
            },
            "SessionEnd": {
                "command": "claude-rewind",
                "args": ["hook-handler", "session-end"],
                "background": True
            }
        }
    }

    write_claude_settings(hooks_config)
```

**Week 2: Event Handlers**
```python
# claude_rewind/native_hooks/handlers.py

@hook_handler("PostToolUse")
def on_post_tool_use(event_data: dict):
    """Create snapshot after Claude uses a tool."""

    snapshot_engine.create_snapshot(
        action_type=event_data['tool_name'],
        files=event_data['modified_files'],
        context={
            'tool': event_data['tool_name'],
            'prompt': event_data['prompt_context'],
            'reasoning': event_data.get('extended_thinking'),
            'confidence': event_data.get('confidence_score'),
            'session_id': event_data['session_id'],
            'timestamp': event_data['timestamp']
        }
    )

@hook_handler("SubagentStop")
def on_subagent_stop(event_data: dict):
    """Track subagent work completion."""

    snapshot_engine.create_subagent_snapshot(
        subagent_name=event_data['subagent_name'],
        parent_session=event_data['parent_session'],
        changes=event_data['changes'],
        delegation_reason=event_data['reason'],
        context={
            'subagent_type': event_data['subagent_type'],
            'duration': event_data['duration'],
            'success': event_data['success']
        }
    )

@hook_handler("Error")
def on_error(event_data: dict):
    """Auto-suggest rollback when Claude encounters error."""

    # Analyze recent snapshots
    suggestions = rollback_analyzer.suggest_fix(
        error=event_data['error'],
        recent_snapshots=snapshot_engine.get_recent(limit=10)
    )

    # Log suggestion for user
    logger.info(f"Error detected. Suggested rollback: {suggestions[0].snapshot_id}")
```

#### CLI Commands

```bash
# Setup
claude-rewind init                        # Configure native hooks
claude-rewind test-hooks                  # Validate hook configuration

# Hook handlers (called by Claude)
claude-rewind hook-handler session-start  # Initialize session tracking
claude-rewind hook-handler post-tool-use  # Create snapshot
claude-rewind hook-handler subagent-stop  # Track subagent work
claude-rewind hook-handler error          # Handle errors

# Status
claude-rewind hooks status                # Show registered hooks
claude-rewind hooks disable               # Temporarily disable hooks
claude-rewind hooks enable                # Re-enable hooks
```

#### Deliverables
- [ ] Native hook registration system
- [ ] Event-driven snapshot creation
- [ ] Subagent-aware tracking
- [ ] Rich context capture (extended thinking, confidence)
- [ ] CLI commands for hook management
- [ ] Migration guide from polling to events

---

### v1.5b: Web Dashboard (Weeks 3-5)

**Goal**: Visual, interactive timeline alongside CLI

#### What Users See

```bash
$ claude-rewind dashboard
# Output:
# 🌐 Starting dashboard server...
# ✓ Server running at http://localhost:8080
# ✓ Opening browser...
# 📊 Monitoring 47 snapshots across 3 sessions
```

#### Features

**Interactive Timeline**:
- D3.js visualization of snapshot history
- Zoom/pan through time
- Filter by session, subagent, file type
- Click to see detailed diff

**Real-Time Updates**:
- WebSocket connection shows live changes
- See Claude's actions as they happen
- Live diff streaming as files are modified

**Advanced Diff Viewer**:
- Monaco Editor for syntax highlighting
- Side-by-side comparison
- File tree navigation
- Search across diffs

#### Architecture

```
┌─────────────────────────────────────────────┐
│         Web Dashboard (Browser)              │
│  Timeline | Diff Viewer | Snapshot Details  │
└─────────────────────────────────────────────┘
                    ▲
                    │ REST API + WebSocket
                    ▼
┌─────────────────────────────────────────────┐
│          FastAPI Server                      │
│  /api/snapshots | /api/diff | /ws/monitor   │
└─────────────────────────────────────────────┘
                    ▲
                    │
                    ▼
┌─────────────────────────────────────────────┐
│      Existing SnapshotEngine (v1.0)          │
│      (No changes needed - just expose)       │
└─────────────────────────────────────────────┘
```

#### Implementation

**Week 3: Backend**
- FastAPI server with REST endpoints
- WebSocket for real-time updates
- Snapshot/diff/rollback API

**Week 4: Frontend**
- React + TypeScript
- D3.js timeline visualization
- Monaco Editor diff viewer
- WebSocket client

**Week 5: Polish**
- CLI integration (`serve`, `dashboard` commands)
- Responsive design
- Documentation and screenshots

#### CLI Commands

```bash
# Server management
claude-rewind serve                      # Start backend server
claude-rewind serve --port 3000          # Custom port
claude-rewind dashboard                  # Start server + open browser

# Status
claude-rewind server status              # Check if running
claude-rewind server stop                # Stop server
```

#### Deliverables
- [ ] FastAPI backend with REST + WebSocket
- [ ] React dashboard with interactive timeline
- [ ] Monaco Editor diff viewer
- [ ] CLI integration
- [ ] Documentation and screenshots

---

### v1.5c: Real-Time Diff Streaming (Week 6-7)

**Goal**: Show live diffs as Claude makes changes

#### What Users See

```bash
# Dashboard view shows:
#
# 🔴 LIVE: Claude is modifying auth.py
#
# ┌─ Line 45 ────────────────────────────┐
# │ - def login(username, password):      │
# │ + def login(username: str,            │
# │ +           password: str) -> Token:  │
# └───────────────────────────────────────┘
#
# Added type hints (14:35:23)
```

#### Implementation

**File Watcher** + **Diff Streaming Engine** + **WebSocket Broadcast**

```python
# claude_rewind/streaming/diff_streamer.py

class DiffStreamingEngine:
    def __init__(self, snapshot_engine, websocket_manager):
        self.snapshot_engine = snapshot_engine
        self.ws_manager = websocket_manager
        self._pre_change_states = {}  # In-memory cache

    def start_streaming(self):
        """Watch for file changes and stream diffs."""
        observer = Observer()
        observer.schedule(self._event_handler, path=self.project_root, recursive=True)
        observer.start()

    def _on_file_modified(self, file_path):
        """Generate and stream diff when file changes."""
        pre_state = self._pre_change_states.get(file_path)
        post_state = self._read_file(file_path)

        diff = self._generate_incremental_diff(pre_state, post_state)

        self.ws_manager.broadcast({
            'type': 'live_diff',
            'file': file_path,
            'diff': diff,
            'timestamp': time.time()
        })

        # Update cache
        self._pre_change_states[file_path] = post_state
```

#### Deliverables
- [ ] File watcher with diff generation
- [ ] WebSocket streaming
- [ ] Dashboard live diff view
- [ ] Performance optimization for large files

---

## 🎯 v2.0 - SDK Integration (Conversational Rewind)

**Duration**: ~3 months

**Strategic Goal**: Transform from CLI tool to conversational companion

---

### What Users See

```bash
$ claude-rewind install-agent
# Output:
# ✓ Registered 'rewind-manager' as Claude Agent
# ✓ Conversational interface enabled
# ✓ Deep lifecycle integration active
# 🤖 You can now talk to Rewind through Claude!
```

### Conversational Examples

```bash
# During Claude Code session
User: "Show me what changed in the last hour"
Claude: "Here's what I changed recently:

• 14:30 - Refactored auth system (auth.py, utils.py)
  Added type hints and improved error handling

• 14:25 - Fixed payment bug (payment.py)
  Corrected currency conversion logic

• 14:20 - Updated tests (test_auth.py)
  Added 3 new test cases

Would you like to see detailed diffs for any of these?"

User: "Something broke after your last changes"
Claude: "Let me analyze recent snapshots...

I found the likely issue in snapshot cr_abc123 (14:30):
- File: auth.py
- Change: Refactored login function
- Impact: 3 dependent files affected
- Safety score: 85%

I recommend rolling back just auth.py to the previous version.
This will preserve your manual changes in other files.

Should I proceed with this selective rollback?"

User: "Yes"
Claude: "✅ Rolled back auth.py to snapshot cr_abc122.

What I did:
• Reverted auth.py to 14:25 state
• Preserved config.py (your manual edits)
• Preserved README.md (your documentation)

The auth system is now restored. Let me try a different approach
to the refactoring..."
```

### Implementation

**Conversational Agent Core**:
```python
# claude_rewind/agent/conversational.py

class RewindConversationalAgent:
    """Natural language interface for Rewind."""

    def handle_query(self, user_message: str) -> str:
        """Parse natural language and route to action."""

        intent = self._classify_intent(user_message)

        if intent == "show_timeline":
            return self._generate_timeline_response()
        elif intent == "show_diff":
            return self._generate_diff_response()
        elif intent == "rollback":
            return self._generate_rollback_response()
        elif intent == "analyze_changes":
            return self._analyze_recent_changes()
        elif intent == "find_issue":
            return self._diagnose_issue()
```

### Features

1. **Natural Language Timeline Queries**
2. **Conversational Diff Explanations**
3. **Smart Rollback Suggestions** (conversational)
4. **Issue Diagnosis** ("Something broke, help me")
5. **Subagent-Aware Rollback** ("Undo what code-reviewer did")

### Deliverables
- [ ] Claude Agent SDK integration
- [ ] Conversational agent core
- [ ] Intent classification system
- [ ] Natural language response generation
- [ ] Smart rollback suggestions (AI-powered)
- [ ] Complete documentation

---

## 🏆 v2.5 - First-Class Citizen (Future Vision)

**Duration**: TBD (dependent on Anthropic partnership)

**Strategic Goal**: Native integration into Claude Code IDE

---

### What Users See

**Native Timeline UI**:
```
┌─ Claude Code IDE ──────────────────────────────┐
│                                                 │
│  ┌─ Sidebar: Rewind Timeline ─────────────┐   │
│  │                                          │   │
│  │  🕐 14:35 │ auth.py refactored           │   │
│  │  🕐 14:30 │ payment bug fixed            │   │
│  │  🕐 14:25 │ tests updated                │   │
│  │                                          │   │
│  │  [Show Diff] [Rollback] [Compare]       │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌─ Editor ─────────────────────────────────┐  │
│  │  auth.py                                  │  │
│  │                                          │  │
│  │  45 │ def login(username: str,          │  │
│  │  46 │           password: str) -> Token:│  │
│  │     │ ← Changed by Claude 2min ago      │  │
│  │                                          │  │
│  │  [⟲ Undo this change]                   │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### Features

**Native Timeline Sidebar**:
- Integrated into Claude Code IDE
- Always visible, no external tools
- Click to see diff inline

**One-Click Rollback**:
- Rollback button next to each change
- Preview before applying
- Undo/redo support

**Inline Diff Visualization**:
- Gutter indicators for changed lines
- Hover to see previous version
- Click to revert individual changes

**Subagent-Aware Conflict Resolution**:
- Visual indicator: "Changed by code-reviewer"
- Selective rollback by subagent
- Conflict resolution UI

### Integration Points

- Claude Code Extension API
- Native timeline panel
- Editor decorations API
- Command palette integration
- Status bar integration

---

## 📊 Complete Roadmap Timeline

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│   v1.0      │    v1.5     │    v2.0     │    v2.5     │
│ Foundation  │ Hooks + Web │ Conversational│ Native IDE  │
├─────────────┼─────────────┼─────────────┼─────────────┤
│ ✅ Complete │ 7 weeks     │ 3 months    │ TBD         │
├─────────────┼─────────────┼─────────────┼─────────────┤
│ • CLI       │ • Native    │ • SDK       │ • Native UI │
│ • Snapshots │   hooks     │   agent     │ • Sidebar   │
│ • Rollback  │ • Dashboard │ • NL        │ • Inline    │
│ • Timeline  │ • Streaming │   queries   │   diff      │
│ • Cleanup   │             │ • Smart     │ • One-click │
│             │             │   rollback  │   rollback  │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

---

## 🎯 Strategic Priorities

### v1.5 (Next 7 weeks)
1. **Week 1-2**: Native Hooks Support
   - Event-driven architecture
   - Zero latency snapshots
   - Rich context capture

2. **Week 3-5**: Web Dashboard
   - Visual timeline
   - Interactive diff viewer
   - Real-time WebSocket updates

3. **Week 6-7**: Real-Time Streaming
   - Live diff streaming
   - File watcher integration
   - Dashboard streaming view

### v2.0 (Next 3 months)
1. **Month 1**: Conversational Agent Core
   - Intent classification
   - Natural language responses
   - Timeline/diff/rollback queries

2. **Month 2**: Smart Features
   - AI-powered rollback suggestions
   - Issue diagnosis
   - Subagent-aware rollback

3. **Month 3**: SDK Integration
   - Claude Agent registration
   - Deep lifecycle hooks
   - Polish and testing

### v2.5 (Future)
- Partnership with Anthropic
- Native Claude Code IDE integration
- First-class citizen status

---

## 🔄 Revised Feature Priority Matrix

| Feature | Version | Priority | Duration | Status |
|---------|---------|----------|----------|--------|
| **Native Hooks** | v1.5a | P0 | 2 weeks | 📋 Next |
| **Web Dashboard** | v1.5b | P0 | 3 weeks | 📋 After hooks |
| **Real-Time Streaming** | v1.5c | P0 | 2 weeks | 📋 After dashboard |
| **Conversational Agent** | v2.0a | P0 | 4 weeks | 🔮 Future |
| **SDK Integration** | v2.0b | P0 | 4 weeks | 🔮 Future |
| **Smart Rollback** | v2.0c | P1 | 4 weeks | 🔮 Future |
| **Native IDE UI** | v2.5 | P2 | TBD | 🔮 Vision |

**P0** = Critical path
**P1** = High value
**P2** = Future vision

---

## 📝 Next Steps

1. ✅ **v1.0 Complete** - Merged to master
2. 🚀 **Start v1.5a: Native Hooks** (2 weeks)
   - Week 1: Hook registration system
   - Week 2: Event handlers + CLI commands
3. 📊 **Continue v1.5b: Web Dashboard** (3 weeks)
   - Week 3: FastAPI backend
   - Week 4: React frontend
   - Week 5: Polish + integration
4. 🔄 **Implement v1.5c: Real-Time Streaming** (2 weeks)
   - Week 6: File watcher + diff engine
   - Week 7: WebSocket streaming + UI
5. 🎯 **Begin v2.0: Conversational Rewind** (3 months)
   - SDK integration
   - Conversational agent
   - Smart features

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
