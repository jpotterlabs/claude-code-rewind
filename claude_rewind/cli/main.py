"""Main CLI entry point for Claude Rewind Tool."""

import click
import sys
from pathlib import Path
from typing import Optional
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
    click.echo("  • Start using Claude Code - snapshots will be created automatically")
    click.echo("  • Use 'claude-rewind timeline' to view your action history")


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
    
    if dry_run:
        click.echo(f"Dry run: Would clean up snapshots older than {cleanup_after_days} days")
        click.echo(f"Dry run: Would keep maximum of {max_snapshots} snapshots")
        click.echo("Note: Actual cleanup logic will be implemented in storage tasks")
    else:
        if not force:
            if not click.confirm(f"Clean up snapshots older than {cleanup_after_days} days?"):
                click.echo("Cleanup cancelled.")
                return
        
        click.echo("Cleanup functionality will be fully implemented in storage tasks")
        if verbose:
            click.echo(f"Configuration: max_snapshots={max_snapshots}, cleanup_after_days={cleanup_after_days}")


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
    
    # If no options provided, show interactive timeline
    if not any([filter_action, filter_date, search, bookmarked_only]):
        timeline_manager.show_interactive_timeline()
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
                snapshots = self.db_manager.get_snapshots(limit=1000)  # Get all to find by ID
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
            snapshots = db_manager.get_snapshots(limit=10)
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


if __name__ == '__main__':
    cli()