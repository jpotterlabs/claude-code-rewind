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


if __name__ == '__main__':
    cli()