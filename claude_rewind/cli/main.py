"""Main CLI entry point for Claude Rewind Tool."""

import click
from pathlib import Path
from typing import Optional

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
    
    if config:
        config_data = config_manager.load_config(Path(config))
    else:
        config_data = config_manager.load_config()
    
    # Store in context for subcommands
    ctx.obj['config'] = config_data
    ctx.obj['config_manager'] = config_manager
    ctx.obj['project_root'] = project_path
    ctx.obj['verbose'] = verbose


@cli.command()
@click.pass_context
def init(ctx: click.Context):
    """Initialize Claude Rewind in the current project."""
    project_root = ctx.obj['project_root']
    config_manager = ctx.obj['config_manager']
    
    click.echo(f"Initializing Claude Rewind in {project_root}")
    
    # Create .claude-rewind directory
    rewind_dir = project_root / ".claude-rewind"
    rewind_dir.mkdir(exist_ok=True)
    
    # Create default configuration
    if config_manager.create_default_config_file():
        click.echo(f"✓ Created configuration file: {config_manager.get_config_path()}")
    else:
        click.echo("✗ Failed to create configuration file", err=True)
        return
    
    # Create snapshots directory
    snapshots_dir = rewind_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)
    click.echo(f"✓ Created snapshots directory: {snapshots_dir}")
    
    click.echo("Claude Rewind initialized successfully!")


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
@click.pass_context
def cleanup(ctx: click.Context):
    """Clean up old snapshots based on configuration."""
    click.echo("Cleanup functionality will be implemented in task 2.1")


if __name__ == '__main__':
    cli()