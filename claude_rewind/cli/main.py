"""Main CLI entry point for Claude Rewind Tool."""

import click
import sys
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

from ..core.config import ConfigManager


@click.group()
@click.option('--config', '-c', type=click.Path(exists=True), 
              help='Path to configuration file')
@click.option('--project-root', '-p', type=click.Path(exists=True), 
              help='Project root directory')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx: click.Context, config: Optional[str], project_root: Optional[str], verbose: bool):
    """Claude Rewind Tool - Time-travel debugging for Claude Code actions."""
    # Ensure context object exists
    ctx.ensure_object(dict)
    
    # Set up configuration
    project_path = Path(project_root) if project_root else Path.cwd()
    config_manager = ConfigManager(project_path)
    
    try:
        if config:
            config_data = config_manager.load_config(Path(config))
        else:
            config_data = config_manager.load_config()
        
        # Validate configuration
        validation_errors = config_manager.validate_config(config_data)
        if validation_errors:
            click.echo("Configuration validation errors:", err=True)
            for error in validation_errors:
                click.echo(f"  - {error}", err=True)
            if not ctx.resilient_parsing:
                sys.exit(1)
    except Exception as e:
        if verbose:
            click.echo(f"Error loading configuration: {e}", err=True)
        config_data = config_manager.get_default_config()
    
    # Store in context for subcommands
    ctx.obj['config'] = config_data
    ctx.obj['config_manager'] = config_manager
    ctx.obj['project_root'] = project_path
    ctx.obj['verbose'] = verbose


@cli.command()
@click.option('--force', is_flag=True, help='Force initialization even if already initialized')
@click.option('--skip-git-check', is_flag=True, help='Skip git repository detection and .gitignore setup')
@click.pass_context
def init(ctx: click.Context, force: bool, skip_git_check: bool):
    """Initialize Claude Rewind in the current project."""
    from ..storage.database import DatabaseManager
    import git
    
    project_root = ctx.obj['project_root']
    config_manager = ctx.obj['config_manager']
    verbose = ctx.obj['verbose']
    
    click.echo(f"Initializing Claude Rewind in {project_root}")
    
    # Check if already initialized
    rewind_dir = project_root / ".claude-rewind"
    if rewind_dir.exists() and not force:
        click.echo("Claude Rewind is already initialized in this project.")
        click.echo("Use --force to reinitialize.")
        return
    
    # Create .claude-rewind directory
    rewind_dir.mkdir(exist_ok=True)
    if verbose:
        click.echo(f"✓ Created directory: {rewind_dir}")
    
    # Create default configuration
    if config_manager.create_default_config_file():
        click.echo(f"✓ Created configuration file: {config_manager.get_config_path()}")
    else:
        click.echo("✗ Failed to create configuration file", err=True)
        return
    
    # Create snapshots directory
    snapshots_dir = rewind_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)
    if verbose:
        click.echo(f"✓ Created snapshots directory: {snapshots_dir}")
    
    # Initialize database
    try:
        db_path = rewind_dir / "metadata.db"
        db_manager = DatabaseManager(db_path)
        click.echo(f"✓ Initialized database: {db_path}")
        if verbose:
            click.echo("  - Created snapshots table")
            click.echo("  - Created file_changes table")
            click.echo("  - Created indexes for performance")
    except Exception as e:
        click.echo(f"✗ Failed to initialize database: {e}", err=True)
        return
    
    # Git integration setup
    if not skip_git_check:
        try:
            # Check if we're in a git repository
            repo = git.Repo(project_root, search_parent_directories=True)
            git_root = Path(repo.working_dir)
            
            if verbose:
                click.echo(f"✓ Detected git repository at: {git_root}")
            
            # Check if .gitignore exists and add .claude-rewind if needed
            gitignore_path = git_root / ".gitignore"
            gitignore_entry = ".claude-rewind/"
            
            if gitignore_path.exists():
                gitignore_content = gitignore_path.read_text()
                if gitignore_entry not in gitignore_content:
                    with open(gitignore_path, 'a') as f:
                        f.write(f"\n# Claude Rewind Tool\n{gitignore_entry}\n")
                    click.echo("✓ Added .claude-rewind/ to .gitignore")
                else:
                    if verbose:
                        click.echo("✓ .claude-rewind/ already in .gitignore")
            else:
                # Create .gitignore with .claude-rewind entry
                with open(gitignore_path, 'w') as f:
                    f.write(f"# Claude Rewind Tool\n{gitignore_entry}\n")
                click.echo("✓ Created .gitignore with .claude-rewind/ entry")
                
        except git.InvalidGitRepositoryError:
            if verbose:
                click.echo("ℹ No git repository detected - skipping git integration")
        except Exception as e:
            click.echo(f"⚠ Git integration warning: {e}")
            if verbose:
                click.echo("  Continuing without git integration...")
    
    # Create initial status file
    status_file = rewind_dir / "status.json"
    import json
    status_data = {
        "initialized_at": datetime.now().isoformat(),
        "version": "0.1.0",
        "project_root": str(project_root),
        "git_integration": not skip_git_check
    }
    
    try:
        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)
        if verbose:
            click.echo(f"✓ Created status file: {status_file}")
    except Exception as e:
        click.echo(f"⚠ Warning: Could not create status file: {e}")
    
    click.echo("\n🎉 Claude Rewind initialized successfully!")
    click.echo("\nNext steps:")
    click.echo("  • Run 'claude-rewind status' to verify the setup")
    click.echo("  • Run 'claude-rewind monitor' to start intelligent Claude Code monitoring")
    click.echo("  • Use 'claude-rewind timeline' to view your action history")
    click.echo("  • Use 'claude-rewind diff <snapshot-id>' to see what changed")


@cli.command()
@click.option('--mode', type=click.Choice(['claude', 'filesystem', 'hybrid']), default='claude',
              help='Monitoring mode: claude (Claude Code integration), filesystem (file watching), or hybrid (both)')
@click.option('--sensitivity', type=click.Choice(['low', 'medium', 'high']), default='medium',
              help='Detection sensitivity for Claude actions')
@click.option('--no-backup', is_flag=True, help='Skip creating backup snapshots on start')
@click.pass_context
def monitor(ctx: click.Context, mode: str, sensitivity: str, no_backup: bool):
    """Start automatic monitoring and snapshot creation for Claude Code actions.

    This is the sophisticated monitoring system that replaces the simple 'watch' command.
    It can detect Claude Code actions intelligently rather than just watching for file changes.
    """
    from ..core.snapshot_engine import SnapshotEngine
    from ..hooks.claude_hook_manager import ClaudeHookManager
    from ..hooks.claude_interceptor import ClaudeCodeInterceptor
    from ..core.models import ActionContext
    from ..core.config import PerformanceConfig
    import time

    project_root = ctx.obj['project_root']
    config = ctx.obj['config']
    verbose = ctx.obj['verbose']

    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Claude Rewind not initialized in this project.", err=True)
        click.echo("Run 'claude-rewind init' first.")
        sys.exit(1)

    # Initialize components
    config_manager = ConfigManager(project_root)
    config = config_manager.load_config()
    performance_config = config.performance
    storage_config = config.storage
    git_config = config.git_integration
    snapshot_engine = SnapshotEngine(project_root, rewind_dir, performance_config, storage_config, git_config)

    click.echo(f"🎯 Starting Claude Code monitoring in {mode} mode...")
    click.echo(f"📍 Project: {project_root}")
    click.echo(f"🔧 Sensitivity: {sensitivity}")

    try:
        if mode in ['claude', 'hybrid']:
            # Initialize Claude Code integration
            claude_manager = ClaudeHookManager(project_root, snapshot_engine, config)
            claude_interceptor = ClaudeCodeInterceptor(project_root, config)

            # Create backup snapshot if requested
            if not no_backup:
                click.echo("📸 Creating backup snapshot before monitoring...")
                backup_context = ActionContext(
                    action_type="backup",
                    timestamp=datetime.now(),
                    prompt_context="Pre-monitoring backup snapshot",
                    affected_files=[],
                    tool_name="claude_rewind_monitor",
                    session_id=None
                )
                try:
                    backup_id = snapshot_engine.create_snapshot(backup_context)
                    click.echo(f"✅ Backup snapshot created: {backup_id}")
                except Exception as e:
                    click.echo(f"⚠️  Warning: Failed to create backup: {e}")

            # Start Claude monitoring
            if claude_manager.start_monitoring():
                click.echo("🔍 Claude Code integration monitoring started")
            else:
                click.echo("❌ Failed to start Claude monitoring", err=True)
                if mode == 'claude':
                    sys.exit(1)

        if mode in ['filesystem', 'hybrid']:
            # Fallback to filesystem watching for broader coverage
            click.echo("👁️  Adding filesystem monitoring as fallback...")

        # Set sensitivity levels
        sensitivity_configs = {
            'low': {'check_interval': 2.0, 'confidence_threshold': 0.8},
            'medium': {'check_interval': 1.0, 'confidence_threshold': 0.7},
            'high': {'check_interval': 0.5, 'confidence_threshold': 0.6}
        }

        sens_config = sensitivity_configs[sensitivity]

        click.echo("🚀 Monitoring active! Press Ctrl+C to stop.")
        click.echo("=" * 50)

        # Main monitoring loop
        snapshots_created = 0
        actions_detected = 0
        start_time = datetime.now()

        while True:
            try:
                if mode in ['claude', 'hybrid']:
                    # Check for Claude actions using the interceptor
                    detected_actions = claude_interceptor.detect_claude_actions()

                    for action in detected_actions:
                        if action.estimated_confidence >= sens_config['confidence_threshold']:
                            actions_detected += 1

                            # Convert to ActionContext
                            action_context = ActionContext(
                                action_type=action.tool_name,
                                timestamp=action.timestamp,
                                prompt_context=f"Claude {action.tool_name}: {action.detection_method}",
                                affected_files=action.file_paths,
                                tool_name="claude_code",
                                session_id=claude_manager._current_session_id if 'claude_manager' in locals() else None
                            )

                            if verbose:
                                click.echo(f"🎯 Detected: {action.tool_name} on {action.file_paths} "
                                         f"(confidence: {action.estimated_confidence:.2f})")

                # Display periodic status
                if verbose and actions_detected > 0 and actions_detected % 5 == 0:
                    runtime = datetime.now() - start_time
                    click.echo(f"📊 Status: {actions_detected} actions detected, "
                             f"{snapshots_created} snapshots created, "
                             f"runtime: {runtime.total_seconds():.0f}s")

                # Sleep based on sensitivity
                time.sleep(sens_config['check_interval'])

            except Exception as e:
                click.echo(f"❌ Error in monitoring loop: {e}", err=True)
                if verbose:
                    import traceback
                    traceback.print_exc()
                time.sleep(2.0)  # Longer sleep on error

    except KeyboardInterrupt:
        click.echo("\n🛑 Stopping monitoring...")

        if mode in ['claude', 'hybrid'] and 'claude_manager' in locals():
            if claude_manager.stop_monitoring():
                click.echo("✅ Claude monitoring stopped")

            # Show session statistics
            stats = claude_manager.get_session_stats()
            click.echo(f"📊 Session Summary:")
            click.echo(f"   • Actions detected: {stats.get('action_count', 0)}")
            click.echo(f"   • Session duration: {stats.get('session_duration_seconds', 0):.1f}s")
            click.echo(f"   • Total snapshots: {snapshots_created}")

        click.echo("👋 Monitoring stopped.")

    except Exception as e:
        click.echo(f"💥 Fatal error in monitoring: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.pass_context
def watch(ctx: click.Context):
    """Legacy file watching command (deprecated).

    This command has been replaced by 'claude-rewind monitor' which provides
    intelligent Claude Code integration instead of simple file watching.
    """
    click.echo("⚠️  The 'watch' command is deprecated and will be removed in a future version.")
    click.echo("")
    click.echo("🎯 The new 'monitor' command provides intelligent Claude Code integration:")
    click.echo("   • Detects actual Claude actions (not just any file change)")
    click.echo("   • Creates context-rich snapshots with metadata")
    click.echo("   • Tracks Claude Code sessions")
    click.echo("   • Multiple detection modes and sensitivity levels")
    click.echo("")
    click.echo("💡 Migration guide:")
    click.echo("   Old: claude-rewind watch")
    click.echo("   New: claude-rewind monitor")
    click.echo("")

    if click.confirm("Would you like to start the new monitor command now?"):
        ctx.invoke(monitor)
    else:
        click.echo("")
        click.echo("📚 Learn more:")
        click.echo("   claude-rewind monitor --help")
        click.echo("   claude-rewind session --help")


@cli.command()
@click.option('--action', type=click.Choice(['start', 'stop', 'status', 'stats']), default='status',
              help='Action to perform on Claude Code session')
@click.option('--show-recent', type=int, default=5, help='Number of recent actions to show')
@click.pass_context
def session(ctx: click.Context, action: str, show_recent: int):
    """Manage Claude Code monitoring sessions."""
    from ..hooks.claude_hook_manager import ClaudeHookManager
    from ..core.snapshot_engine import SnapshotEngine
    from ..core.config import PerformanceConfig

    project_root = ctx.obj['project_root']
    config = ctx.obj['config']
    verbose = ctx.obj['verbose']

    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Claude Rewind not initialized in this project.", err=True)
        click.echo("Run 'claude-rewind init' first.")
        sys.exit(1)

    # Initialize components
    config_manager = ConfigManager(project_root)
    config = config_manager.load_config()
    performance_config = config.performance
    storage_config = config.storage
    git_config = config.git_integration
    snapshot_engine = SnapshotEngine(project_root, rewind_dir, performance_config, storage_config, git_config)
    claude_manager = ClaudeHookManager(project_root, snapshot_engine, config)

    if action == 'start':
        click.echo("🚀 Starting Claude Code monitoring session...")
        if claude_manager.start_monitoring():
            click.echo("✅ Monitoring session started successfully")
            stats = claude_manager.get_session_stats()
            click.echo(f"📋 Session ID: {stats.get('session_id', 'Unknown')}")
        else:
            click.echo("❌ Failed to start monitoring session", err=True)
            sys.exit(1)

    elif action == 'stop':
        if claude_manager.stop_monitoring():
            click.echo("🛑 Monitoring session stopped")
            stats = claude_manager.get_session_stats()
            if stats.get('action_count', 0) > 0:
                click.echo(f"📊 Final stats: {stats['action_count']} actions detected")
        else:
            click.echo("⚠️  No active session to stop")

    elif action == 'stats':
        stats = claude_manager.get_session_stats()
        click.echo("📊 Claude Code Session Statistics")
        click.echo("=" * 40)

        if stats.get('session_id'):
            click.echo(f"Session ID: {stats['session_id']}")
            click.echo(f"Started: {stats.get('session_start_time', 'Unknown')}")
            click.echo(f"Duration: {stats.get('session_duration_seconds', 0):.1f}s")
            click.echo(f"Actions detected: {stats.get('action_count', 0)}")
            click.echo(f"Recent actions: {stats.get('recent_actions_count', 0)}")
            click.echo(f"Monitoring active: {'Yes' if stats.get('is_monitoring') else 'No'}")
            click.echo(f"Hook count: {stats.get('pre_hooks_count', 0)} pre, {stats.get('post_hooks_count', 0)} post")

            if show_recent > 0:
                recent_actions = claude_manager.get_recent_actions(show_recent)
                if recent_actions:
                    click.echo(f"\n📝 Recent Actions (last {len(recent_actions)}):")
                    for i, action in enumerate(recent_actions, 1):
                        time_str = action.timestamp.strftime("%H:%M:%S")
                        click.echo(f"  {i}. [{time_str}] {action.action_type} - {len(action.affected_files)} files")
        else:
            click.echo("No active session")

    else:  # status
        stats = claude_manager.get_session_stats()

        if stats.get('is_monitoring'):
            click.echo("🟢 Monitoring Status: ACTIVE")
            click.echo(f"   Session: {stats.get('session_id', 'Unknown')}")
            click.echo(f"   Actions: {stats.get('action_count', 0)}")
            click.echo(f"   Duration: {stats.get('session_duration_seconds', 0):.1f}s")
        else:
            click.echo("🔴 Monitoring Status: INACTIVE")
            click.echo("   Use 'claude-rewind monitor' to start monitoring")


@cli.command()
@click.pass_context
def status(ctx: click.Context):
    """Show current status of Claude Rewind."""
    project_root = ctx.obj['project_root']
    config = ctx.obj['config']
    
    click.echo(f"Claude Rewind Status for {project_root}")
    click.echo("=" * 50)
    
    # Check if initialized
    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Status: Not initialized")
        click.echo("Run 'claude-rewind init' to initialize")
        return
    
    click.echo("Status: Initialized")
    click.echo(f"Configuration: {rewind_dir / 'config.yml'}")
    
    # Show basic config info
    storage_config = config.get('storage', {})
    click.echo(f"Max snapshots: {storage_config.get('max_snapshots', 'N/A')}")
    click.echo(f"Compression: {'Enabled' if storage_config.get('compression_enabled') else 'Disabled'}")


@cli.command()
@click.option('--dry-run', is_flag=True, help='Show what would be cleaned up without actually doing it')
@click.option('--force', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def cleanup(ctx: click.Context, dry_run: bool, force: bool):
    """Clean up old snapshots based on configuration."""
    project_root = ctx.obj['project_root']
    config = ctx.obj['config']
    verbose = ctx.obj['verbose']
    
    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Claude Rewind not initialized in this project.", err=True)
        click.echo("Run 'claude-rewind init' first.")
        sys.exit(1)
    
    snapshots_dir = rewind_dir / "snapshots"
    if not snapshots_dir.exists():
        click.echo("No snapshots directory found.")
        return
    
    # Get cleanup configuration
    storage_config = config.get('storage', {})
    max_snapshots = storage_config.get('max_snapshots', 100)
    cleanup_after_days = storage_config.get('cleanup_after_days', 30)
    
    try:
        # Initialize storage components
        from ..storage.database import DatabaseManager
        from ..storage.file_store import FileStore
        from datetime import datetime, timedelta

        db_manager = DatabaseManager(rewind_dir / "metadata.db")
        file_store = FileStore(rewind_dir)

        # Get current snapshots
        all_snapshots = db_manager.list_snapshots()
        if not all_snapshots:
            click.echo("No snapshots found to clean up.")
            return

        # Calculate cleanup targets
        cutoff_date = datetime.now() - timedelta(days=cleanup_after_days)
        old_snapshots = [s for s in all_snapshots if s.timestamp < cutoff_date]
        excess_snapshots = []

        # Check if we exceed max_snapshots limit
        if len(all_snapshots) > max_snapshots:
            # Sort by timestamp (newest first) and take excess
            sorted_snapshots = sorted(all_snapshots, key=lambda x: x.timestamp, reverse=True)
            excess_snapshots = sorted_snapshots[max_snapshots:]

        # Combine cleanup targets
        snapshots_to_delete = list(set(old_snapshots + excess_snapshots))

        if not snapshots_to_delete:
            click.echo("✅ No cleanup needed.")
            click.echo(f"   Total snapshots: {len(all_snapshots)}")
            click.echo(f"   Oldest snapshot: {min(all_snapshots, key=lambda x: x.timestamp).timestamp.strftime('%Y-%m-%d %H:%M')}")
            return

        # Show what will be cleaned
        click.echo(f"Cleanup Analysis:")
        click.echo(f"  Total snapshots: {len(all_snapshots)}")
        click.echo(f"  Snapshots older than {cleanup_after_days} days: {len(old_snapshots)}")
        click.echo(f"  Snapshots exceeding limit of {max_snapshots}: {len(excess_snapshots)}")
        click.echo(f"  Total to delete: {len(snapshots_to_delete)}")

        if dry_run:
            click.echo("\n[DRY RUN] Would delete the following snapshots:")
            for snapshot in sorted(snapshots_to_delete, key=lambda x: x.timestamp):
                age_days = (datetime.now() - snapshot.timestamp).days
                click.echo(f"  • {snapshot.id} ({snapshot.timestamp.strftime('%Y-%m-%d %H:%M')}) - {age_days} days old")
            click.echo(f"\nDisk space that would be freed: Calculating...")

            # Calculate approximate disk usage
            total_size = 0
            for snapshot in snapshots_to_delete:
                try:
                    snapshot_data = file_store.get_snapshot_manifest(snapshot.id)
                    total_size += snapshot_data.get('total_size', 0)
                except:
                    pass  # Skip if can't calculate

            if total_size > 0:
                size_mb = total_size / (1024 * 1024)
                click.echo(f"Estimated disk space to be freed: {size_mb:.1f} MB")

            return

        # Confirm deletion
        if not force:
            if not click.confirm(f"\nDelete {len(snapshots_to_delete)} snapshots?"):
                click.echo("Cleanup cancelled.")
                return

        # Execute cleanup
        click.echo("\nExecuting cleanup...")
        deleted_count = 0
        failed_count = 0

        for snapshot in snapshots_to_delete:
            try:
                # Delete from file store
                file_store.delete_snapshot(snapshot.id)
                # Delete from database
                db_manager.delete_snapshot(snapshot.id)
                deleted_count += 1

                if verbose:
                    age_days = (datetime.now() - snapshot.timestamp).days
                    click.echo(f"  ✓ Deleted {snapshot.id} ({age_days} days old)")

            except Exception as e:
                failed_count += 1
                if verbose:
                    click.echo(f"  ✗ Failed to delete {snapshot.id}: {e}")

        # Report results
        click.echo(f"\n✅ Cleanup completed!")
        click.echo(f"   Snapshots deleted: {deleted_count}")
        if failed_count > 0:
            click.echo(f"   Failed deletions: {failed_count}")
        click.echo(f"   Remaining snapshots: {len(all_snapshots) - deleted_count}")

    except Exception as e:
        click.echo(f"Error during cleanup: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.pass_context
def config(ctx: click.Context):
    """Show current configuration."""
    config_data = ctx.obj['config']
    config_manager = ctx.obj['config_manager']
    
    click.echo(f"Configuration file: {config_manager.get_config_path()}")
    click.echo("Current configuration:")
    click.echo("=" * 50)
    
    # Display storage config
    storage = config_data.get('storage', {})
    click.echo("Storage:")
    click.echo(f"  Max snapshots: {storage.get('max_snapshots', 'N/A')}")
    click.echo(f"  Compression: {'Enabled' if storage.get('compression_enabled') else 'Disabled'}")
    click.echo(f"  Cleanup after: {storage.get('cleanup_after_days', 'N/A')} days")
    click.echo(f"  Max disk usage: {storage.get('max_disk_usage_mb', 'N/A')} MB")
    
    # Display display config
    display = config_data.get('display', {})
    click.echo("\nDisplay:")
    click.echo(f"  Theme: {display.get('theme', 'N/A')}")
    click.echo(f"  Diff algorithm: {display.get('diff_algorithm', 'N/A')}")
    click.echo(f"  Show line numbers: {display.get('show_line_numbers', 'N/A')}")
    click.echo(f"  Context lines: {display.get('context_lines', 'N/A')}")
    
    # Display git integration
    git_config = config_data.get('git_integration', {})
    click.echo("\nGit Integration:")
    click.echo(f"  Respect .gitignore: {git_config.get('respect_gitignore', 'N/A')}")
    click.echo(f"  Auto commit rollbacks: {git_config.get('auto_commit_rollbacks', 'N/A')}")


@cli.command()
@click.option('--validate-only', is_flag=True, help='Only validate configuration without showing details')
@click.pass_context
def validate(ctx: click.Context, validate_only: bool):
    """Validate the current configuration."""
    config_data = ctx.obj['config']
    config_manager = ctx.obj['config_manager']
    
    validation_errors = config_manager.validate_config(config_data)
    
    if validation_errors:
        click.echo("Configuration validation failed:", err=True)
        for error in validation_errors:
            click.echo(f"  ✗ {error}", err=True)
        sys.exit(1)
    else:
        click.echo("✓ Configuration is valid")
        if not validate_only:
            click.echo(f"Configuration file: {config_manager.get_config_path()}")
            click.echo("All configuration values are within acceptable ranges.")


@cli.command()
@click.option('--filter-action', type=str, help='Filter by action type')
@click.option('--filter-date', type=str, help='Filter by date (YYYY-MM-DD)')
@click.option('--search', type=str, help='Search snapshots by content')
@click.option('--bookmarked-only', is_flag=True, help='Show only bookmarked snapshots')
@click.option('--limit', type=int, default=50, help='Maximum number of snapshots to show')
@click.pass_context
def timeline(ctx: click.Context, filter_action: Optional[str], filter_date: Optional[str], 
            search: Optional[str], bookmarked_only: bool, limit: int):
    """Display interactive timeline of Claude Code actions."""
    from ..storage.database import DatabaseManager
    from ..core.timeline import TimelineManager
    from ..core.models import TimelineFilters
    from datetime import datetime
    
    project_root = ctx.obj['project_root']
    verbose = ctx.obj['verbose']
    
    # Check if initialized
    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Claude Rewind not initialized in this project.", err=True)
        click.echo("Run 'claude-rewind init' first.")
        sys.exit(1)
    
    # Initialize database manager
    try:
        db_path = rewind_dir / "metadata.db"
        db_manager = DatabaseManager(db_path)
    except Exception as e:
        click.echo(f"Error accessing database: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)
    
    # Initialize timeline manager
    timeline_manager = TimelineManager(db_manager)
    
    # If no options provided, show timeline
    if not any([filter_action, filter_date, search, bookmarked_only]):
        # Check if running in interactive terminal
        import sys
        if sys.stdout.isatty() and sys.stdin.isatty():
            timeline_manager.show_interactive_timeline()
        else:
            # Non-interactive mode - show simple timeline listing
            click.echo("Timeline (non-interactive mode):")
            snapshots = db_manager.list_snapshots(limit=20)  # Show last 20
            if not snapshots:
                click.echo("No snapshots found.")
                return

            for i, snapshot in enumerate(snapshots, 1):
                timestamp_str = snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                click.echo(f"  {i:2d}. {snapshot.id} | {timestamp_str} | {snapshot.action_type}")

            if len(snapshots) == 20:
                click.echo("  ... (showing last 20 snapshots)")
            click.echo(f"\nTotal: {len(db_manager.list_snapshots())} snapshots")
        return
    
    # Apply command-line filters
    filters = TimelineFilters()
    
    if filter_action:
        filters.action_types = [filter_action]
    
    if filter_date:
        try:
            date_obj = datetime.strptime(filter_date, "%Y-%m-%d")
            # Filter for the entire day
            end_date = date_obj.replace(hour=23, minute=59, second=59)
            filters.date_range = (date_obj, end_date)
        except ValueError:
            click.echo(f"Invalid date format: {filter_date}. Use YYYY-MM-DD.", err=True)
            sys.exit(1)
    
    filters.bookmarked_only = bookmarked_only
    
    # Get and display filtered snapshots
    try:
        if search:
            snapshots = timeline_manager.search_snapshots(search)
        else:
            snapshots = timeline_manager.filter_snapshots(filters)
        
        # Apply limit
        if limit > 0:
            snapshots = snapshots[:limit]
        
        if not snapshots:
            click.echo("No snapshots found matching the criteria.")
            return
        
        # Display results in a simple table format
        click.echo(f"Found {len(snapshots)} snapshots:")
        click.echo("-" * 80)
        
        for i, snapshot in enumerate(snapshots, 1):
            timestamp_str = snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            files_count = len(snapshot.files_affected)
            description = snapshot.prompt_context[:60] + "..." if len(snapshot.prompt_context) > 60 else snapshot.prompt_context
            
            click.echo(f"{i:3d}. {snapshot.id[:10]}... | {timestamp_str} | {snapshot.action_type:15s} | {files_count:2d} files | {description}")
        
        click.echo("-" * 80)
        click.echo(f"Total: {len(snapshots)} snapshots")
        
        if len(snapshots) == limit and limit > 0:
            click.echo(f"(Limited to {limit} results. Use --limit to show more)")
    
    except Exception as e:
        click.echo(f"Error retrieving snapshots: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument('snapshot_id', required=False)
@click.option('--file', '-f', type=str, help='Show diff for specific file only')
@click.option('--format', '-F', type=click.Choice(['unified', 'side-by-side', 'patch']), 
              default='unified', help='Diff output format')
@click.option('--before', type=str, help='Compare with specific snapshot (for file diffs)')
@click.option('--after', type=str, help='Compare with specific snapshot (for file diffs)')
@click.option('--context', '-C', type=int, default=3, help='Number of context lines')
@click.option('--no-color', is_flag=True, help='Disable syntax highlighting and colors')
@click.option('--export', type=click.Path(), help='Export diff to file')
@click.option('--interactive', '-i', is_flag=True, help='Interactive diff viewer')
@click.pass_context
def diff(ctx: click.Context, snapshot_id: Optional[str], file: Optional[str], 
         format: str, before: Optional[str], after: Optional[str], 
         context: int, no_color: bool, export: Optional[str], interactive: bool):
    """Show diff for snapshot or between snapshots."""
    from ..core.diff_viewer import DiffViewer
    from ..core.models import DiffFormat
    from ..storage.database import DatabaseManager
    from ..storage.file_store import FileStore
    from pathlib import Path
    
    project_root = ctx.obj['project_root']
    verbose = ctx.obj['verbose']
    
    # Check if project is initialized
    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Claude Rewind is not initialized in this project.", err=True)
        click.echo("Run 'claude-rewind init' first.")
        sys.exit(1)
    
    try:
        # Initialize storage components
        db_manager = DatabaseManager(rewind_dir / "metadata.db")
        file_store = FileStore(rewind_dir)
        
        # Create storage manager wrapper
        class StorageManagerWrapper:
            def __init__(self, db_manager, file_store):
                self.db_manager = db_manager
                self.file_store = file_store
            
            def load_snapshot(self, snapshot_id):
                # Get snapshot metadata from database
                snapshots = self.db_manager.list_snapshots(limit=1000)  # Get all to find by ID
                snapshot_metadata = None
                for s in snapshots:
                    if s.id == snapshot_id:
                        snapshot_metadata = s
                        break
                
                if not snapshot_metadata:
                    return None
                
                # Get file states from file store
                try:
                    manifest = self.file_store.get_snapshot_manifest(snapshot_id)
                    file_states = {}
                    
                    for file_path_str, file_info in manifest['files'].items():
                        from ..core.models import FileState
                        from datetime import datetime
                        
                        file_path = Path(file_path_str)
                        file_state = FileState(
                            path=file_path,
                            content_hash=file_info.get('content_hash', ''),
                            size=file_info.get('size', 0),
                            modified_time=datetime.fromisoformat(file_info.get('modified_time', datetime.now().isoformat())),
                            permissions=file_info.get('permissions', 0o644),
                            exists=file_info.get('exists', True)
                        )
                        file_states[file_path] = file_state
                    
                    from ..core.models import Snapshot
                    return Snapshot(
                        id=snapshot_id,
                        timestamp=snapshot_metadata.timestamp,
                        metadata=snapshot_metadata,
                        file_states=file_states
                    )
                except Exception as e:
                    if verbose:
                        click.echo(f"Error loading snapshot files: {e}", err=True)
                    return None
            
            def load_file_content(self, content_hash):
                try:
                    return self.file_store.retrieve_content(content_hash)
                except Exception:
                    return None
        
        storage_manager = StorageManagerWrapper(db_manager, file_store)
        
        # Create diff viewer
        diff_viewer = DiffViewer(
            storage_manager=storage_manager,
            context_lines=context,
            enable_colors=not no_color
        )
        
        # Convert format string to enum
        format_map = {
            'unified': DiffFormat.UNIFIED,
            'side-by-side': DiffFormat.SIDE_BY_SIDE,
            'patch': DiffFormat.PATCH
        }
        diff_format = format_map[format]
        
        # Handle different diff scenarios
        if file and before and after:
            # File diff between two snapshots
            diff_output = diff_viewer.show_file_diff(
                Path(file), before, after, diff_format
            )
        elif file and snapshot_id:
            # File diff between snapshot and current
            diff_output = diff_viewer.show_file_diff(
                Path(file), snapshot_id, "current", diff_format
            )
        elif snapshot_id:
            # Snapshot diff against current state
            if interactive:
                # Launch interactive diff viewer
                _show_interactive_diff(diff_viewer, snapshot_id, no_color)
                return
            else:
                diff_output = diff_viewer.show_snapshot_diff(snapshot_id, diff_format)
        else:
            # No snapshot specified - show help or recent snapshots
            click.echo("No snapshot specified. Recent snapshots:")
            snapshots = db_manager.list_snapshots(limit=10)
            if not snapshots:
                click.echo("No snapshots found.")
                return
            
            for i, snapshot in enumerate(snapshots, 1):
                timestamp_str = snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                click.echo(f"{i:2d}. {snapshot.id} | {timestamp_str} | {snapshot.action_type}")
            
            click.echo("\nUse: claude-rewind diff <snapshot-id>")
            return
        
        # Output or export diff
        if export:
            # Export to file (disable colors for clean output)
            export_diff = diff_viewer.export_diff(snapshot_id, diff_format)
            Path(export).write_text(export_diff)
            click.echo(f"Diff exported to: {export}")
        else:
            # Display to terminal
            click.echo(diff_output)
    
    except Exception as e:
        click.echo(f"Error generating diff: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument('snapshot_id')
@click.option('--files', '-f', multiple=True, help='Specific files to rollback (can be used multiple times)')
@click.option('--preserve-changes', is_flag=True, default=True, 
              help='Preserve manual changes made after Claude actions')
@click.option('--no-backup', is_flag=True, help='Skip creating backup before rollback')
@click.option('--dry-run', is_flag=True, help='Show what would be done without making changes')
@click.option('--force', is_flag=True, help='Skip confirmation prompts')
@click.pass_context
def rollback(ctx: click.Context, snapshot_id: str, files: Tuple[str], 
            preserve_changes: bool, no_backup: bool, dry_run: bool, force: bool):
    """Rollback project state to a specific snapshot."""
    from ..core.rollback_engine import RollbackEngine
    from ..core.models import RollbackOptions
    from ..storage.database import DatabaseManager
    from ..storage.file_store import FileStore
    from pathlib import Path
    
    project_root = ctx.obj['project_root']
    verbose = ctx.obj['verbose']
    
    # Check if project is initialized
    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Claude Rewind is not initialized in this project.", err=True)
        click.echo("Run 'claude-rewind init' first.")
        sys.exit(1)
    
    try:
        # Initialize storage components
        db_manager = DatabaseManager(rewind_dir / "metadata.db")
        file_store = FileStore(rewind_dir)
        
        # Create storage manager wrapper
        class StorageManagerWrapper:
            def __init__(self, db_manager, file_store):
                self.db_manager = db_manager
                self.file_store = file_store
            
            def load_snapshot(self, snapshot_id):
                # Get snapshot metadata from database
                snapshot_metadata = self.db_manager.get_snapshot(snapshot_id)
                if not snapshot_metadata:
                    return None
                
                # Get file states from file store
                try:
                    manifest = self.file_store.get_snapshot_manifest(snapshot_id)
                    file_states = {}
                    
                    for file_path_str, file_info in manifest['files'].items():
                        from ..core.models import FileState
                        from datetime import datetime
                        
                        file_path = Path(file_path_str)
                        file_state = FileState(
                            path=file_path,
                            content_hash=file_info.get('content_hash', ''),
                            size=file_info.get('size', 0),
                            modified_time=datetime.fromisoformat(file_info.get('modified_time', datetime.now().isoformat())),
                            permissions=file_info.get('permissions', 0o644),
                            exists=file_info.get('exists', True)
                        )
                        file_states[file_path] = file_state
                    
                    from ..core.models import Snapshot
                    return Snapshot(
                        id=snapshot_id,
                        timestamp=snapshot_metadata.timestamp,
                        metadata=snapshot_metadata,
                        file_states=file_states
                    )
                except Exception as e:
                    if verbose:
                        click.echo(f"Error loading snapshot files: {e}", err=True)
                    return None
            
            def load_file_content(self, content_hash):
                try:
                    return self.file_store.retrieve_content(content_hash)
                except Exception:
                    return None
        
        storage_manager = StorageManagerWrapper(db_manager, file_store)
        
        # Create rollback engine
        rollback_engine = RollbackEngine(storage_manager, project_root)
        
        # Prepare rollback options
        selective_files = [Path(f) for f in files] if files else None
        options = RollbackOptions(
            selective_files=selective_files,
            preserve_manual_changes=preserve_changes,
            create_backup=not no_backup,
            dry_run=dry_run
        )
        
        # Show preview first
        click.echo(f"Analyzing rollback to snapshot: {snapshot_id}")
        preview = rollback_engine.preview_rollback(snapshot_id, options)
        
        # Display preview
        click.echo("\nRollback Preview:")
        click.echo("=" * 50)
        
        if preview.files_to_restore:
            click.echo(f"Files to restore ({len(preview.files_to_restore)}):")
            for file_path in preview.files_to_restore[:10]:  # Show first 10
                click.echo(f"  ✓ {file_path}")
            if len(preview.files_to_restore) > 10:
                click.echo(f"  ... and {len(preview.files_to_restore) - 10} more files")
        
        if preview.files_to_delete:
            click.echo(f"\nFiles to delete ({len(preview.files_to_delete)}):")
            for file_path in preview.files_to_delete[:10]:  # Show first 10
                click.echo(f"  ✗ {file_path}")
            if len(preview.files_to_delete) > 10:
                click.echo(f"  ... and {len(preview.files_to_delete) - 10} more files")
        
        if preview.conflicts:
            click.echo(f"\nConflicts detected ({len(preview.conflicts)}):")
            for conflict in preview.conflicts[:5]:  # Show first 5
                click.echo(f"  ⚠ {conflict.file_path}: {conflict.description}")
            if len(preview.conflicts) > 5:
                click.echo(f"  ... and {len(preview.conflicts) - 5} more conflicts")
        
        click.echo(f"\nTotal estimated changes: {preview.estimated_changes}")
        
        if dry_run:
            click.echo("\n[DRY RUN] No actual changes would be made.")
            return
        
        # Confirm rollback
        if not force:
            if preview.conflicts and preserve_changes:
                click.echo("\n⚠ Conflicts detected. Manual changes will be preserved where possible.")
            
            if not click.confirm(f"\nProceed with rollback to {snapshot_id}?"):
                click.echo("Rollback cancelled.")
                return
        
        # Execute rollback
        click.echo("\nExecuting rollback...")
        result = rollback_engine.execute_rollback(snapshot_id, options)
        
        # Display results
        if result.success:
            click.echo("✅ Rollback completed successfully!")
            click.echo(f"   Files restored: {len(result.files_restored)}")
            click.echo(f"   Files deleted: {len(result.files_deleted)}")
            if result.conflicts_resolved:
                click.echo(f"   Conflicts resolved: {len(result.conflicts_resolved)}")
        else:
            click.echo("❌ Rollback completed with errors:", err=True)
            for error in result.errors:
                click.echo(f"   • {error}", err=True)
        
        if verbose and (result.files_restored or result.files_deleted):
            click.echo("\nDetailed changes:")
            for file_path in result.files_restored:
                click.echo(f"  ✓ Restored: {file_path}")
            for file_path in result.files_deleted:
                click.echo(f"  ✗ Deleted: {file_path}")
    
    except Exception as e:
        click.echo(f"Error during rollback: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@cli.command()
@click.argument('snapshot_id')
@click.option('--files', '-f', multiple=True, help='Specific files to preview (can be used multiple times)')
@click.option('--preserve-changes', is_flag=True, default=True,
              help='Consider preserving manual changes in preview')
@click.option('--detailed', '-d', is_flag=True, help='Show detailed file-by-file preview')
@click.pass_context
def preview(ctx: click.Context, snapshot_id: str, files: Tuple[str], 
           preserve_changes: bool, detailed: bool):
    """Preview what a rollback operation would do."""
    from ..core.rollback_engine import RollbackEngine
    from ..core.models import RollbackOptions
    from ..storage.database import DatabaseManager
    from ..storage.file_store import FileStore
    from pathlib import Path
    
    project_root = ctx.obj['project_root']
    verbose = ctx.obj['verbose']
    
    # Check if project is initialized
    rewind_dir = project_root / ".claude-rewind"
    if not rewind_dir.exists():
        click.echo("Claude Rewind is not initialized in this project.", err=True)
        click.echo("Run 'claude-rewind init' first.")
        sys.exit(1)
    
    try:
        # Initialize storage components
        db_manager = DatabaseManager(rewind_dir / "metadata.db")
        file_store = FileStore(rewind_dir)
        
        # Create storage manager wrapper (same as rollback command)
        class StorageManagerWrapper:
            def __init__(self, db_manager, file_store):
                self.db_manager = db_manager
                self.file_store = file_store
            
            def load_snapshot(self, snapshot_id):
                snapshot_metadata = self.db_manager.get_snapshot(snapshot_id)
                if not snapshot_metadata:
                    return None
                
                try:
                    manifest = self.file_store.get_snapshot_manifest(snapshot_id)
                    file_states = {}
                    
                    for file_path_str, file_info in manifest['files'].items():
                        from ..core.models import FileState
                        from datetime import datetime
                        
                        file_path = Path(file_path_str)
                        file_state = FileState(
                            path=file_path,
                            content_hash=file_info.get('content_hash', ''),
                            size=file_info.get('size', 0),
                            modified_time=datetime.fromisoformat(file_info.get('modified_time', datetime.now().isoformat())),
                            permissions=file_info.get('permissions', 0o644),
                            exists=file_info.get('exists', True)
                        )
                        file_states[file_path] = file_state
                    
                    from ..core.models import Snapshot
                    return Snapshot(
                        id=snapshot_id,
                        timestamp=snapshot_metadata.timestamp,
                        metadata=snapshot_metadata,
                        file_states=file_states
                    )
                except Exception as e:
                    if verbose:
                        click.echo(f"Error loading snapshot files: {e}", err=True)
                    return None
            
            def load_file_content(self, content_hash):
                try:
                    return self.file_store.retrieve_content(content_hash)
                except Exception:
                    return None
        
        storage_manager = StorageManagerWrapper(db_manager, file_store)
        
        # Create rollback engine
        rollback_engine = RollbackEngine(storage_manager, project_root)
        
        # Prepare rollback options
        selective_files = [Path(f) for f in files] if files else None
        options = RollbackOptions(
            selective_files=selective_files,
            preserve_manual_changes=preserve_changes,
            create_backup=False,  # No backup needed for preview
            dry_run=True  # Always dry run for preview
        )
        
        # Get snapshot info
        snapshot_metadata = db_manager.get_snapshot(snapshot_id)
        if not snapshot_metadata:
            click.echo(f"Snapshot not found: {snapshot_id}", err=True)
            sys.exit(1)
        
        # Show snapshot info
        click.echo(f"Rollback Preview for Snapshot: {snapshot_id}")
        click.echo("=" * 60)
        click.echo(f"Timestamp: {snapshot_metadata.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        click.echo(f"Action: {snapshot_metadata.action_type}")
        click.echo(f"Description: {snapshot_metadata.prompt_context[:100]}...")
        click.echo()
        
        # Generate preview
        click.echo("Analyzing changes...")
        preview = rollback_engine.preview_rollback(snapshot_id, options)
        
        # Display summary
        click.echo("Summary:")
        click.echo("-" * 30)
        click.echo(f"Files to restore: {len(preview.files_to_restore)}")
        click.echo(f"Files to delete: {len(preview.files_to_delete)}")
        click.echo(f"Conflicts: {len(preview.conflicts)}")
        click.echo(f"Total changes: {preview.estimated_changes}")
        
        if not detailed:
            # Show brief overview
            if preview.files_to_restore:
                click.echo(f"\nFiles to restore (showing first 5 of {len(preview.files_to_restore)}):")
                for file_path in preview.files_to_restore[:5]:
                    click.echo(f"  ✓ {file_path}")
                if len(preview.files_to_restore) > 5:
                    click.echo(f"  ... and {len(preview.files_to_restore) - 5} more")
            
            if preview.files_to_delete:
                click.echo(f"\nFiles to delete (showing first 5 of {len(preview.files_to_delete)}):")
                for file_path in preview.files_to_delete[:5]:
                    click.echo(f"  ✗ {file_path}")
                if len(preview.files_to_delete) > 5:
                    click.echo(f"  ... and {len(preview.files_to_delete) - 5} more")
            
            if preview.conflicts:
                click.echo(f"\nConflicts (showing first 3 of {len(preview.conflicts)}):")
                for conflict in preview.conflicts[:3]:
                    click.echo(f"  ⚠ {conflict.file_path}: {conflict.description}")
                if len(preview.conflicts) > 3:
                    click.echo(f"  ... and {len(preview.conflicts) - 3} more")
        else:
            # Show detailed view
            if preview.files_to_restore:
                click.echo(f"\nFiles to restore ({len(preview.files_to_restore)}):")
                for file_path in preview.files_to_restore:
                    click.echo(f"  ✓ {file_path}")
            
            if preview.files_to_delete:
                click.echo(f"\nFiles to delete ({len(preview.files_to_delete)}):")
                for file_path in preview.files_to_delete:
                    click.echo(f"  ✗ {file_path}")
            
            if preview.conflicts:
                click.echo(f"\nConflicts ({len(preview.conflicts)}):")
                for conflict in preview.conflicts:
                    click.echo(f"  ⚠ {conflict.file_path}")
                    click.echo(f"    Type: {conflict.conflict_type}")
                    click.echo(f"    Description: {conflict.description}")
        
        # Show next steps
        click.echo("\nNext steps:")
        if files:
            click.echo(f"  claude-rewind rollback {snapshot_id} --files " + " --files ".join(files))
        else:
            click.echo(f"  claude-rewind rollback {snapshot_id}")
        
        if preview.conflicts and preserve_changes:
            click.echo("  (Conflicts will be resolved automatically with --preserve-changes)")
    
    except Exception as e:
        click.echo(f"Error generating preview: {e}", err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _show_interactive_diff(diff_viewer, snapshot_id: str, no_color: bool):
    """Show interactive diff viewer using Rich."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text
        from rich.layout import Layout
        from rich.live import Live
        from rich.table import Table
        import keyboard
        import threading
        import time
    except ImportError:
        click.echo("Interactive mode requires 'rich' and 'keyboard' packages.", err=True)
        click.echo("Install with: pip install rich keyboard")
        sys.exit(1)
    
    console = Console()
    
    # Get file changes for the snapshot
    try:
        file_changes = diff_viewer.get_file_changes(snapshot_id)
        if not file_changes:
            console.print("[yellow]No changes found in this snapshot.[/yellow]")
            return
    except Exception as e:
        console.print(f"[red]Error loading snapshot: {e}[/red]")
        return
    
    # Interactive state
    current_file_index = 0
    scroll_position = 0
    show_help = False
    
    def create_layout():
        """Create the Rich layout for interactive diff viewer."""
        layout = Layout()
        
        # Split into header, main content, and footer
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        
        # Header with snapshot info
        header_text = f"Snapshot: {snapshot_id} | File {current_file_index + 1}/{len(file_changes)}"
        if len(file_changes) > 0:
            current_file = file_changes[current_file_index]
            header_text += f" | {current_file.path} ({current_file.change_type.value})"
        
        layout["header"].update(Panel(header_text, style="bold blue"))
        
        # Main content area
        if show_help:
            help_text = """
[bold]Interactive Diff Viewer - Keyboard Shortcuts[/bold]

[cyan]Navigation:[/cyan]
  ↑/k     - Previous file
  ↓/j     - Next file
  ←/h     - Scroll up
  →/l     - Scroll down
  Home    - First file
  End     - Last file

[cyan]Actions:[/cyan]
  Enter   - Show full diff for current file
  Space   - Toggle between unified/side-by-side view
  e       - Export current file diff
  
[cyan]Other:[/cyan]
  ?       - Toggle this help
  q/Esc   - Quit

Press any key to continue...
            """
            layout["main"].update(Panel(help_text, title="Help"))
        else:
            # Show diff for current file
            if len(file_changes) > 0:
                current_file = file_changes[current_file_index]
                try:
                    # Get diff for current file
                    diff_text = diff_viewer.show_file_diff(
                        current_file.path, snapshot_id, "current"
                    )
                    
                    # Split into lines and apply scrolling
                    diff_lines = diff_text.split('\n')
                    visible_lines = diff_lines[scroll_position:scroll_position + 20]  # Show 20 lines
                    
                    content = '\n'.join(visible_lines)
                    if scroll_position > 0:
                        content = f"... (scrolled {scroll_position} lines)\n" + content
                    if len(diff_lines) > scroll_position + 20:
                        content += f"\n... ({len(diff_lines) - scroll_position - 20} more lines)"
                    
                    layout["main"].update(Panel(content, title=f"Diff: {current_file.path}"))
                except Exception as e:
                    layout["main"].update(Panel(f"Error loading diff: {e}", style="red"))
            else:
                layout["main"].update(Panel("No files to display", style="yellow"))
        
        # Footer with controls
        footer_text = "↑↓: Navigate files | ←→: Scroll | Enter: Full diff | Space: Toggle view | ?: Help | q: Quit"
        layout["footer"].update(Panel(footer_text, style="dim"))
        
        return layout
    
    # Keyboard event handler
    def on_key_event(event):
        nonlocal current_file_index, scroll_position, show_help
        
        if event.event_type == keyboard.KEY_DOWN:
            key = event.name
            
            if key in ['q', 'esc']:
                return False  # Exit
            elif key == '?':
                show_help = not show_help
            elif key in ['up', 'k'] and not show_help:
                current_file_index = max(0, current_file_index - 1)
                scroll_position = 0
            elif key in ['down', 'j'] and not show_help:
                current_file_index = min(len(file_changes) - 1, current_file_index + 1)
                scroll_position = 0
            elif key in ['left', 'h'] and not show_help:
                scroll_position = max(0, scroll_position - 5)
            elif key in ['right', 'l'] and not show_help:
                scroll_position += 5
            elif key == 'home' and not show_help:
                current_file_index = 0
                scroll_position = 0
            elif key == 'end' and not show_help:
                current_file_index = len(file_changes) - 1
                scroll_position = 0
            elif key == 'enter' and not show_help and len(file_changes) > 0:
                # Show full diff in pager
                current_file = file_changes[current_file_index]
                full_diff = diff_viewer.show_file_diff(
                    current_file.path, snapshot_id, "current"
                )
                console.print(f"\n[bold]Full diff for {current_file.path}:[/bold]")
                console.print(full_diff)
                console.input("\nPress Enter to continue...")
            elif show_help:
                show_help = False  # Any key exits help
        
        return True  # Continue
    
    # Start keyboard listener in separate thread
    keyboard_active = True
    
    def keyboard_listener():
        while keyboard_active:
            try:
                event = keyboard.read_event()
                if not on_key_event(event):
                    break
            except:
                break
    
    keyboard_thread = threading.Thread(target=keyboard_listener, daemon=True)
    keyboard_thread.start()
    
    # Main display loop
    try:
        with Live(create_layout(), refresh_per_second=10, screen=True) as live:
            while keyboard_active:
                live.update(create_layout())
                time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        keyboard_active = False
        console.print("\n[dim]Exiting interactive diff viewer...[/dim]")


@cli.command('hook-handler')
@click.argument('event_type')
@click.argument('event_data', type=click.STRING, default='{}')
@click.pass_context
def hook_handler(ctx: click.Context, event_type: str, event_data: str):
    """Handle native hook event (called by Claude Code).

    This command is invoked by Claude Code when hooks fire.
    Not meant to be called directly by users.

    Args:
        event_type: Event type (e.g., "PostToolUse")
        event_data: JSON string with event data
    """
    from ..native_hooks.handlers import handle_hook_event

    project_root = ctx.obj['project_root']

    try:
        exit_code = handle_hook_event(event_type, event_data, project_root)
        sys.exit(exit_code)
    except Exception as e:
        click.echo(f"Hook handler failed: {e}", err=True)
        sys.exit(1)


@cli.group('hooks')
@click.pass_context
def hooks(ctx: click.Context):
    """Manage native hooks integration."""
    pass


@hooks.command('init')
@click.option('--force', is_flag=True, help='Overwrite existing hooks')
@click.pass_context
def hooks_init(ctx: click.Context, force: bool):
    """Initialize native hooks in .claude/settings.json.

    This configures Claude Code 2.0 to call claude-rewind when events fire.

    Example:
        $ claude-rewind hooks init
        ✓ Configured .claude/settings.json with hooks
        ✓ PostToolUse → automatic snapshots
        ✓ SubagentStop → subagent tracking
        ✓ SessionStart/End → lifecycle management
    """
    from ..native_hooks.registration import (
        register_native_hooks,
        is_hooks_registered,
        get_claude_settings_path
    )

    project_root = ctx.obj['project_root']

    try:
        # Check if already registered
        if is_hooks_registered(project_root) and not force:
            click.echo("✓ Native hooks are already registered.")
            click.echo("\nUse --force to overwrite existing hooks.")
            return

        # Register hooks
        click.echo("Configuring native hooks...")
        register_native_hooks(project_root)

        # Success message
        settings_path = get_claude_settings_path(project_root)
        click.echo(f"\n✓ Configured {settings_path}")
        click.echo("\nRegistered hooks:")
        click.echo("  ✓ SessionStart/End → lifecycle management")
        click.echo("  ✓ PostToolUse → automatic snapshots")
        click.echo("  ✓ SubagentStart/Stop → subagent tracking")
        click.echo("  ✓ Error → auto-suggest rollback")
        click.echo("\n🎉 Claude Code Rewind is now event-driven!")
        click.echo("\nNext: Restart Claude Code for hooks to take effect.")

    except Exception as e:
        click.echo(f"Failed to register hooks: {e}", err=True)
        sys.exit(1)


@hooks.command('status')
@click.pass_context
def hooks_status(ctx: click.Context):
    """Show status of registered hooks.

    Example:
        $ claude-rewind hooks status
        Status: Registered
        Hooks: 7 active
        ...
    """
    from ..native_hooks.registration import (
        is_hooks_registered,
        get_registered_hooks,
        get_claude_settings_path
    )

    project_root = ctx.obj['project_root']

    try:
        settings_path = get_claude_settings_path(project_root)

        if not settings_path.exists():
            click.echo("Status: Not configured")
            click.echo(f"File: {settings_path} (not found)")
            click.echo("\nRun 'claude-rewind hooks init' to configure.")
            return

        if not is_hooks_registered(project_root):
            click.echo("Status: Not registered")
            click.echo(f"File: {settings_path}")
            click.echo("\nRun 'claude-rewind hooks init' to register.")
            return

        # Get registered hooks
        registered_hooks = get_registered_hooks(project_root)

        click.echo("Status: ✓ Registered")
        click.echo(f"File: {settings_path}")
        click.echo(f"\nActive hooks: {len(registered_hooks)}")

        for hook_name, hook_config in registered_hooks.items():
            description = hook_config.get('description', 'No description')
            click.echo(f"  ✓ {hook_name}")
            click.echo(f"    {description}")

    except Exception as e:
        click.echo(f"Failed to check hooks status: {e}", err=True)
        sys.exit(1)


@hooks.command('disable')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def hooks_disable(ctx: click.Context, confirm: bool):
    """Disable native hooks (remove from .claude/settings.json).

    Example:
        $ claude-rewind hooks disable
    """
    from ..native_hooks.registration import unregister_hooks, is_hooks_registered

    project_root = ctx.obj['project_root']

    try:
        if not is_hooks_registered(project_root):
            click.echo("✓ Native hooks are not registered.")
            return

        if not confirm:
            if not click.confirm("Remove native hooks from .claude/settings.json?"):
                click.echo("Cancelled.")
                return

        unregister_hooks(project_root)

        click.echo("✓ Removed native hooks from .claude/settings.json")
        click.echo("\nNote: Polling-based monitoring is still available via:")
        click.echo("  claude-rewind monitor")

    except Exception as e:
        click.echo(f"Failed to disable hooks: {e}", err=True)
        sys.exit(1)


@hooks.command('test')
@click.pass_context
def hooks_test(ctx: click.Context):
    """Test native hooks configuration.

    Validates that hooks are registered correctly and can be invoked.

    Example:
        $ claude-rewind hooks test
    """
    from ..native_hooks.registration import get_registered_hooks, is_hooks_registered
    from ..native_hooks.events import HookEventType

    project_root = ctx.obj['project_root']

    try:
        if not is_hooks_registered(project_root):
            click.echo("✗ Native hooks are not registered.")
            click.echo("\nRun 'claude-rewind hooks init' first.")
            sys.exit(1)

        registered_hooks = get_registered_hooks(project_root)

        click.echo("Testing native hooks configuration...\n")

        # Check that all expected hooks are registered
        expected_hooks = [
            HookEventType.SESSION_START,
            HookEventType.POST_TOOL_USE,
            HookEventType.SUBAGENT_STOP,
            HookEventType.ERROR
        ]

        all_registered = True
        for hook_type in expected_hooks:
            hook_name = hook_type.value
            if hook_name in registered_hooks:
                click.echo(f"  ✓ {hook_name} registered")
            else:
                click.echo(f"  ✗ {hook_name} missing")
                all_registered = False

        if all_registered:
            click.echo("\n✅ All hooks are registered correctly!")
            click.echo("\nHooks will be activated when you restart Claude Code.")
        else:
            click.echo("\n⚠️  Some hooks are missing.")
            click.echo("\nRun 'claude-rewind hooks init --force' to fix.")
            sys.exit(1)

    except Exception as e:
        click.echo(f"Test failed: {e}", err=True)
        sys.exit(1)


@cli.command('dashboard')
@click.option('--host', default='127.0.0.1', help='Server host address')
@click.option('--port', default=8080, help='Server port')
@click.option('--no-browser', is_flag=True, help='Do not open browser automatically')
@click.pass_context
def dashboard(ctx: click.Context, host: str, port: int, no_browser: bool):
    """Start the web dashboard server.

    Opens an interactive web dashboard showing:
    - Visual timeline of all snapshots
    - Real-time snapshot monitoring
    - Detailed diff viewer
    - Session statistics

    Examples:
        claude-rewind dashboard
        claude-rewind dashboard --port 9000
        claude-rewind dashboard --no-browser
    """
    from ..web.server import DashboardServer

    project_root = ctx.obj['project_root']

    # Check if project is initialized
    rewind_dir = project_root / '.claude-rewind'
    if not rewind_dir.exists():
        click.echo("Error: Project not initialized.", err=True)
        click.echo("Run 'claude-rewind init' first.", err=True)
        sys.exit(1)

    click.echo("🌐 Starting Claude Code Rewind Dashboard...")
    click.echo(f"✓ Server running at http://{host}:{port}")
    click.echo(f"✓ Project: {project_root}")

    if not no_browser:
        click.echo("✓ Opening browser...")

    click.echo("\nPress Ctrl+C to stop the server\n")

    try:
        server = DashboardServer(project_root, host=host, port=port)
        server.run(open_browser=not no_browser)
    except KeyboardInterrupt:
        click.echo("\n\n✓ Dashboard server stopped")
    except Exception as e:
        click.echo(f"\nError starting dashboard: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()