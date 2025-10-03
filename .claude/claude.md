# Claude Code Rewind - Git Ceremony Protocol

## Approved Git Workflow

### When User Says: "ok lets commit the changes" or similar phrases

Trigger phrases:
- "ok lets commit the changes"
- "let's commit"
- "commit the changes"
- "ready to commit"
- "create a PR"
- "make a pull request"

### Execute This Ceremony:

#### Step 1: Create Feature Branch
```bash
git checkout main
git pull origin main
git checkout -b feature/<descriptive-name>
```

**Branch naming convention:**
- `feature/<feature-name>` - For new features
- `fix/<bug-name>` - For bug fixes
- `docs/<doc-name>` - For documentation only
- `refactor/<component-name>` - For refactoring

#### Step 2: Commit Changes
```bash
git add -A
git status  # Show what will be committed
git commit -m "$(cat <<'EOF'
<Title: Imperative mood, 50 chars or less>

<Body: Explain what and why, not how. Wrap at 72 characters>

<List of changes>
- Change 1
- Change 2
- Change 3

<Optional sections>
Breaking Changes: <if any>
Fixes: #<issue-number>
Relates to: #<issue-number>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"
```

#### Step 3: Push Feature Branch
```bash
git push -u origin feature/<name>
```

#### Step 4: Create Pull Request
```bash
gh pr create --title "<PR Title>" --body "$(cat <<'EOF'
## Summary
<Brief overview of changes>

### Changes Made
- Change 1
- Change 2
- Change 3

### Files Modified
- File 1
- File 2

### Test Plan
- [ ] Manual testing completed
- [ ] All existing tests pass
- [ ] Documentation updated (if needed)

### Notes
<Any additional context>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)" --base main
```

#### Step 5: Update Todo List
Mark task as waiting for review:
```
- Waiting for CodeRabbit review on PR #X
```

### Important Rules

**NEVER:**
- ❌ Commit directly to `main`
- ❌ Force push to `main`
- ❌ Merge PRs yourself (only user can merge)
- ❌ Delete branches (only user can delete after merge)
- ❌ Skip CodeRabbit review
- ❌ Bypass hooks with `--no-verify`
- ❌ Commit without user approval

**ALWAYS:**
- ✅ Create feature branch first
- ✅ Show user changes before committing
- ✅ Wait for CodeRabbit review
- ✅ Implement CodeRabbit suggestions
- ✅ Let user merge and delete branches
- ✅ Use descriptive commit messages
- ✅ Include co-author attribution

### After Creating PR

1. **Wait for CodeRabbit review**
   - CodeRabbit will automatically review the PR
   - Review comments will appear on GitHub

2. **Implement CodeRabbit suggestions**
   - When CodeRabbit provides feedback, implement changes
   - Push additional commits to the same branch
   - CodeRabbit will re-review automatically

3. **User merges PR**
   - **ONLY the user can merge the PR**
   - **ONLY the user can delete the feature branch**
   - Do NOT merge or delete branches

### Example Flow

```
User: "ok lets commit the changes"

Claude:
1. git checkout -b feature/new-dashboard-component
2. git add -A && git status
3. [Shows what will be committed]
4. [User confirms or requests changes]
5. git commit -m "..."
6. git push -u origin feature/new-dashboard-component
7. gh pr create ...
8. "PR #X created: <URL>"
9. "Waiting for CodeRabbit review..."
```

### Post-Merge Cleanup

After user merges and deletes branch:
```bash
git checkout main
git pull origin main
# Feature branch already deleted by user on GitHub
git remote prune origin  # Clean up remote-tracking branches
```

---

## Current Project Status

**Main Branch**: `main`
**Current Version**: v1.5a (Native Hooks Support - Complete)
**Next Version**: v1.5b (Web Dashboard - In Progress)

**Active Feature Branches**:
- `feature/native-hooks-documentation` - PR #4 (Awaiting CodeRabbit review)
- `feature/web-dashboard` - Not yet PR'd (waiting for user approval)

**Workflow State**:
- ✅ v1.5a Implementation: Merged to main
- 🔄 v1.5a Documentation: PR #4 - Waiting for CodeRabbit
- ⏳ v1.5b Implementation: On feature branch, awaiting user review
