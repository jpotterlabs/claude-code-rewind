"""Timeline management and display functionality for Claude Rewind Tool."""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import re
import fnmatch

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.layout import Layout
from rich.live import Live
from rich.align import Align
from rich import box
from rich.columns import Columns

from .interfaces import ITimelineManager
from .models import SnapshotMetadata, TimelineFilters, SnapshotId
from ..storage.database import DatabaseManager


logger = logging.getLogger(__name__)


class TimelineManager(ITimelineManager):
    """Manages timeline display and navigation functionality."""
    
    def __init__(self, db_manager: DatabaseManager, console: Optional[Console] = None):
        """Initialize timeline manager.
        
        Args:
            db_manager: Database manager for snapshot operations
            console: Rich console for output (creates new if None)
        """
        self.db_manager = db_manager
        self.console = console or Console()
        self._bookmarks: Dict[SnapshotId, str] = {}
        self._load_bookmarks()
    
    def _load_bookmarks(self) -> None:
        """Load bookmarks from database storage."""
        try:
            bookmarks = self.db_manager.list_bookmarks()
            self._bookmarks = {
                snapshot_id: name 
                for snapshot_id, name, _, _ in bookmarks
            }
            logger.debug(f"Loaded {len(self._bookmarks)} bookmarks")
        except Exception as e:
            logger.error(f"Error loading bookmarks: {e}")
            self._bookmarks = {}
    
    def _save_bookmarks(self) -> None:
        """Save bookmarks to persistent storage."""
        # Bookmarks are saved immediately when added/removed
        # This method is kept for compatibility
        pass
    
    def show_interactive_timeline(self) -> None:
        """Display interactive timeline interface."""
        try:
            snapshots = self.db_manager.list_snapshots()
            
            if not snapshots:
                self.console.print("[yellow]No snapshots found.[/yellow]")
                self.console.print("Run some Claude Code actions to create snapshots.")
                return
            
            self._display_timeline_interface(snapshots)
            
        except Exception as e:
            logger.error(f"Error displaying timeline: {e}")
            self.console.print(f"[red]Error displaying timeline: {e}[/red]")
    
    def _display_timeline_interface(self, snapshots: List[SnapshotMetadata]) -> None:
        """Display the main timeline interface with navigation."""
        current_page = 0
        page_size = 10
        filters = TimelineFilters()
        search_query = ""
        
        while True:
            # Apply filters and search
            filtered_snapshots = self._apply_filters_and_search(snapshots, filters, search_query)
            
            # Calculate pagination
            total_pages = (len(filtered_snapshots) + page_size - 1) // page_size
            start_idx = current_page * page_size
            end_idx = min(start_idx + page_size, len(filtered_snapshots))
            page_snapshots = filtered_snapshots[start_idx:end_idx]
            
            # Clear screen and display timeline
            self.console.clear()
            self._display_timeline_header(len(filtered_snapshots), current_page + 1, total_pages)
            
            if search_query:
                self.console.print(f"[dim]Search: {search_query}[/dim]")
            
            if filters.date_range or filters.action_types or filters.file_patterns or filters.bookmarked_only:
                self._display_active_filters(filters)
            
            if page_snapshots:
                self._display_snapshot_table(page_snapshots, start_idx)
            else:
                self.console.print("[yellow]No snapshots match current filters.[/yellow]")
            
            self._display_navigation_help()
            
            # Get user input
            try:
                command = Prompt.ask(
                    "[bold blue]Command[/bold blue]",
                    choices=["n", "p", "f", "s", "b", "d", "r", "q", "h"],
                    default="q",
                    show_choices=False
                ).lower()
                
                if command == "q":
                    break
                elif command == "n" and current_page < total_pages - 1:
                    current_page += 1
                elif command == "p" and current_page > 0:
                    current_page -= 1
                elif command == "f":
                    filters = self._configure_filters()
                    current_page = 0
                elif command == "s":
                    search_query = self._get_search_query()
                    current_page = 0
                elif command == "b":
                    self._manage_bookmarks(page_snapshots)
                elif command == "d":
                    self._show_snapshot_details(page_snapshots)
                elif command == "r":
                    filters = TimelineFilters()
                    search_query = ""
                    current_page = 0
                elif command == "h":
                    self._show_help()
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")
    
    def _display_timeline_header(self, total_snapshots: int, current_page: int, total_pages: int) -> None:
        """Display timeline header with summary information."""
        title = f"Claude Rewind Timeline - {total_snapshots} snapshots"
        if total_pages > 1:
            title += f" (Page {current_page}/{total_pages})"
        
        header = Panel(
            Align.center(Text(title, style="bold cyan")),
            box=box.ROUNDED,
            style="blue"
        )
        self.console.print(header)
    
    def _display_active_filters(self, filters: TimelineFilters) -> None:
        """Display currently active filters."""
        filter_parts = []
        
        if filters.date_range:
            start, end = filters.date_range
            filter_parts.append(f"Date: {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
        
        if filters.action_types:
            filter_parts.append(f"Actions: {', '.join(filters.action_types)}")
        
        if filters.file_patterns:
            filter_parts.append(f"Files: {', '.join(filters.file_patterns)}")
        
        if filters.bookmarked_only:
            filter_parts.append("Bookmarked only")
        
        if filter_parts:
            filter_text = " | ".join(filter_parts)
            self.console.print(f"[dim]Active filters: {filter_text}[/dim]")
    
    def _display_snapshot_table(self, snapshots: List[SnapshotMetadata], start_idx: int) -> None:
        """Display snapshots in a formatted table."""
        table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        table.add_column("#", style="dim", width=3)
        table.add_column("ID", style="cyan", width=12)
        table.add_column("Timestamp", style="green", width=19)
        table.add_column("Action", style="yellow", width=15)
        table.add_column("Files", style="blue", width=6)
        table.add_column("Size", style="magenta", width=8)
        table.add_column("Bookmark", style="red", width=10)
        table.add_column("Description", style="white")
        
        for i, snapshot in enumerate(snapshots):
            row_num = start_idx + i + 1
            
            # Format timestamp
            timestamp_str = snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            
            # Format size
            size_str = self._format_size(snapshot.total_size)
            
            # Get bookmark name
            bookmark = self._bookmarks.get(snapshot.id, "")
            
            # Truncate description
            description = snapshot.prompt_context[:50] + "..." if len(snapshot.prompt_context) > 50 else snapshot.prompt_context
            
            table.add_row(
                str(row_num),
                snapshot.id[:10] + "...",
                timestamp_str,
                snapshot.action_type,
                str(len(snapshot.files_affected)),
                size_str,
                bookmark,
                description
            )
        
        self.console.print(table)
    
    def _display_navigation_help(self) -> None:
        """Display navigation help at bottom of screen."""
        help_text = (
            "[bold]Commands:[/bold] "
            "[cyan]n[/cyan]ext | [cyan]p[/cyan]rev | [cyan]f[/cyan]ilter | [cyan]s[/cyan]earch | "
            "[cyan]b[/cyan]ookmark | [cyan]d[/cyan]etails | [cyan]r[/cyan]eset | [cyan]h[/cyan]elp | [cyan]q[/cyan]uit"
        )
        self.console.print(Panel(help_text, box=box.SIMPLE))
    
    def _apply_filters_and_search(self, snapshots: List[SnapshotMetadata], 
                                 filters: TimelineFilters, search_query: str) -> List[SnapshotMetadata]:
        """Apply filters and search to snapshot list."""
        filtered = snapshots[:]
        
        # Apply date range filter
        if filters.date_range:
            start_date, end_date = filters.date_range
            filtered = [s for s in filtered if start_date <= s.timestamp <= end_date]
        
        # Apply action type filter
        if filters.action_types:
            filtered = [s for s in filtered if s.action_type in filters.action_types]
        
        # Apply file pattern filter
        if filters.file_patterns:
            filtered = [
                s for s in filtered 
                if any(
                    any(fnmatch.fnmatch(str(f), pattern) for pattern in filters.file_patterns)
                    for f in s.files_affected
                )
            ]
        
        # Apply bookmark filter
        if filters.bookmarked_only:
            filtered = [s for s in filtered if s.id in self._bookmarks]
        
        # Apply search query
        if search_query:
            query_lower = search_query.lower()
            filtered = [
                s for s in filtered
                if (query_lower in s.prompt_context.lower() or
                    query_lower in s.action_type.lower() or
                    query_lower in s.id.lower())
            ]
        
        return filtered
    
    def _configure_filters(self) -> TimelineFilters:
        """Interactive filter configuration."""
        self.console.print("\n[bold]Configure Filters[/bold]")
        
        filters = TimelineFilters()
        
        # Date range filter
        if Confirm.ask("Filter by date range?"):
            try:
                start_str = Prompt.ask("Start date (YYYY-MM-DD)")
                end_str = Prompt.ask("End date (YYYY-MM-DD)")
                
                start_date = datetime.strptime(start_str, "%Y-%m-%d")
                end_date = datetime.strptime(end_str, "%Y-%m-%d")
                
                if start_date <= end_date:
                    filters.date_range = (start_date, end_date)
                else:
                    self.console.print("[red]Invalid date range[/red]")
            except ValueError:
                self.console.print("[red]Invalid date format[/red]")
        
        # Action type filter
        if Confirm.ask("Filter by action types?"):
            action_types_str = Prompt.ask("Action types (comma-separated)")
            filters.action_types = [t.strip() for t in action_types_str.split(",") if t.strip()]
        
        # File pattern filter
        if Confirm.ask("Filter by file patterns?"):
            patterns_str = Prompt.ask("File patterns (comma-separated, supports wildcards)")
            filters.file_patterns = [p.strip() for p in patterns_str.split(",") if p.strip()]
        
        # Bookmarked only filter
        filters.bookmarked_only = Confirm.ask("Show only bookmarked snapshots?")
        
        return filters
    
    def _get_search_query(self) -> str:
        """Get search query from user."""
        return Prompt.ask("Search query (searches ID, action type, and description)", default="")
    
    def _manage_bookmarks(self, snapshots: List[SnapshotMetadata]) -> None:
        """Manage bookmarks for displayed snapshots."""
        if not snapshots:
            self.console.print("[yellow]No snapshots to bookmark[/yellow]")
            return
        
        self.console.print("\n[bold]Bookmark Management[/bold]")
        
        # Show current bookmarks
        bookmarked_snapshots = [s for s in snapshots if s.id in self._bookmarks]
        if bookmarked_snapshots:
            self.console.print("\nCurrent bookmarks:")
            for snapshot in bookmarked_snapshots:
                bookmark_name = self._bookmarks[snapshot.id]
                self.console.print(f"  {snapshot.id[:10]}... - {bookmark_name}")
        
        action = Prompt.ask(
            "Action",
            choices=["add", "remove", "list", "cancel"],
            default="cancel"
        )
        
        if action == "add":
            self._add_bookmark(snapshots)
        elif action == "remove":
            self._remove_bookmark(snapshots)
        elif action == "list":
            self._list_all_bookmarks()
    
    def _add_bookmark(self, snapshots: List[SnapshotMetadata]) -> None:
        """Add bookmark to a snapshot."""
        try:
            snapshot_num = int(Prompt.ask("Snapshot number to bookmark")) - 1
            if 0 <= snapshot_num < len(snapshots):
                snapshot = snapshots[snapshot_num]
                bookmark_name = Prompt.ask("Bookmark name")
                
                if bookmark_name:
                    # Ask for optional description
                    description = Prompt.ask("Bookmark description (optional)", default="")
                    description = description if description.strip() else None
                    
                    success = self.bookmark_snapshot(snapshot.id, bookmark_name, description)
                    if success:
                        self.console.print(f"[green]Added bookmark '{bookmark_name}' to snapshot {snapshot.id[:10]}...[/green]")
                    else:
                        self.console.print("[red]Failed to add bookmark[/red]")
                else:
                    self.console.print("[red]Bookmark name cannot be empty[/red]")
            else:
                self.console.print("[red]Invalid snapshot number[/red]")
        except ValueError:
            self.console.print("[red]Invalid snapshot number[/red]")
    
    def _remove_bookmark(self, snapshots: List[SnapshotMetadata]) -> None:
        """Remove bookmark from a snapshot."""
        bookmarked_snapshots = [s for s in snapshots if s.id in self._bookmarks]
        
        if not bookmarked_snapshots:
            self.console.print("[yellow]No bookmarked snapshots in current view[/yellow]")
            return
        
        try:
            snapshot_num = int(Prompt.ask("Snapshot number to remove bookmark from")) - 1
            if 0 <= snapshot_num < len(snapshots):
                snapshot = snapshots[snapshot_num]
                if snapshot.id in self._bookmarks:
                    bookmark_name = self._bookmarks.pop(snapshot.id)
                    self._save_bookmarks()
                    self.console.print(f"[green]Removed bookmark '{bookmark_name}' from snapshot {snapshot.id[:10]}...[/green]")
                else:
                    self.console.print("[yellow]Snapshot is not bookmarked[/yellow]")
            else:
                self.console.print("[red]Invalid snapshot number[/red]")
        except ValueError:
            self.console.print("[red]Invalid snapshot number[/red]")
    
    def _list_all_bookmarks(self) -> None:
        """List all bookmarks."""
        if not self._bookmarks:
            self.console.print("[yellow]No bookmarks found[/yellow]")
            return
        
        self.console.print("\n[bold]All Bookmarks:[/bold]")
        for snapshot_id, bookmark_name in self._bookmarks.items():
            self.console.print(f"  {snapshot_id[:10]}... - {bookmark_name}")
    
    def _show_snapshot_details(self, snapshots: List[SnapshotMetadata]) -> None:
        """Show detailed information for a selected snapshot."""
        if not snapshots:
            self.console.print("[yellow]No snapshots to show details for[/yellow]")
            return
        
        try:
            snapshot_num = int(Prompt.ask("Snapshot number for details")) - 1
            if 0 <= snapshot_num < len(snapshots):
                snapshot = snapshots[snapshot_num]
                self._display_snapshot_details(snapshot)
                Prompt.ask("Press Enter to continue")
            else:
                self.console.print("[red]Invalid snapshot number[/red]")
        except ValueError:
            self.console.print("[red]Invalid snapshot number[/red]")
    
    def _display_snapshot_details(self, snapshot: SnapshotMetadata) -> None:
        """Display detailed information for a snapshot."""
        self.console.print(f"\n[bold]Snapshot Details: {snapshot.id}[/bold]")
        
        details_table = Table(show_header=False, box=box.SIMPLE)
        details_table.add_column("Field", style="cyan", width=20)
        details_table.add_column("Value", style="white")
        
        details_table.add_row("ID", snapshot.id)
        details_table.add_row("Timestamp", snapshot.timestamp.strftime("%Y-%m-%d %H:%M:%S"))
        details_table.add_row("Action Type", snapshot.action_type)
        details_table.add_row("Files Affected", str(len(snapshot.files_affected)))
        details_table.add_row("Total Size", self._format_size(snapshot.total_size))
        details_table.add_row("Compression Ratio", f"{snapshot.compression_ratio:.2f}")
        
        if snapshot.parent_snapshot:
            details_table.add_row("Parent Snapshot", snapshot.parent_snapshot)
        
        bookmark = self._bookmarks.get(snapshot.id)
        if bookmark:
            details_table.add_row("Bookmark", bookmark)
        
        self.console.print(details_table)
        
        # Show prompt context
        if snapshot.prompt_context:
            self.console.print(f"\n[bold]Prompt Context:[/bold]")
            self.console.print(Panel(snapshot.prompt_context, box=box.SIMPLE))
        
        # Show affected files
        if snapshot.files_affected:
            self.console.print(f"\n[bold]Affected Files:[/bold]")
            for file_path in snapshot.files_affected[:10]:  # Show first 10 files
                self.console.print(f"  • {file_path}")
            
            if len(snapshot.files_affected) > 10:
                remaining = len(snapshot.files_affected) - 10
                self.console.print(f"  ... and {remaining} more files")
    
    def _show_help(self) -> None:
        """Show detailed help information."""
        help_content = """
[bold]Claude Rewind Timeline Help[/bold]

[cyan]Navigation Commands:[/cyan]
  n - Next page
  p - Previous page
  q - Quit timeline

[cyan]Filtering & Search:[/cyan]
  f - Configure filters (date range, action types, file patterns)
  s - Search snapshots by content
  r - Reset all filters and search

[cyan]Bookmark Management:[/cyan]
  b - Manage bookmarks (add, remove, list)

[cyan]Information:[/cyan]
  d - Show detailed information for a snapshot
  h - Show this help

[cyan]Filters:[/cyan]
  • Date Range: Filter snapshots by creation date
  • Action Types: Filter by Claude action types (edit_file, create_file, etc.)
  • File Patterns: Filter by affected file patterns (supports wildcards like *.py)
  • Bookmarked Only: Show only bookmarked snapshots

[cyan]Search:[/cyan]
  Search looks through snapshot IDs, action types, and prompt descriptions.
  Search is case-insensitive and matches partial text.
        """
        
        self.console.print(Panel(help_content.strip(), title="Help", box=box.ROUNDED))
        Prompt.ask("Press Enter to continue")
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f}KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f}MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"
    
    def filter_snapshots(self, filters: TimelineFilters) -> List[SnapshotMetadata]:
        """Filter snapshots based on criteria.
        
        Args:
            filters: Filter criteria to apply
            
        Returns:
            List of filtered snapshot metadata
        """
        try:
            all_snapshots = self.db_manager.list_snapshots()
            return self._apply_filters_and_search(all_snapshots, filters, "")
        except Exception as e:
            logger.error(f"Error filtering snapshots: {e}")
            return []
    
    def bookmark_snapshot(self, snapshot_id: SnapshotId, name: str, description: Optional[str] = None) -> bool:
        """Add a bookmark to a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            name: Bookmark name
            description: Optional bookmark description
            
        Returns:
            True if bookmark was added successfully
        """
        try:
            # Verify snapshot exists
            snapshot = self.db_manager.get_snapshot(snapshot_id)
            if not snapshot:
                logger.error(f"Snapshot not found: {snapshot_id}")
                return False
            
            # Save to database
            success = self.db_manager.add_bookmark(snapshot_id, name, description)
            if success:
                self._bookmarks[snapshot_id] = name
                logger.info(f"Added bookmark '{name}' to snapshot {snapshot_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error adding bookmark: {e}")
            return False
    
    def remove_bookmark(self, snapshot_id: SnapshotId) -> bool:
        """Remove bookmark from a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            True if bookmark was removed successfully
        """
        try:
            success = self.db_manager.remove_bookmark(snapshot_id)
            if success and snapshot_id in self._bookmarks:
                del self._bookmarks[snapshot_id]
                logger.info(f"Removed bookmark from snapshot {snapshot_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error removing bookmark: {e}")
            return False
    
    def get_bookmark_info(self, snapshot_id: SnapshotId) -> Optional[Tuple[str, Optional[str]]]:
        """Get bookmark information for a snapshot.
        
        Args:
            snapshot_id: Snapshot identifier
            
        Returns:
            Tuple of (name, description) if bookmark exists, None otherwise
        """
        try:
            return self.db_manager.get_bookmark(snapshot_id)
        except Exception as e:
            logger.error(f"Error getting bookmark info: {e}")
            return None
    
    def list_all_bookmarks(self) -> List[Tuple[SnapshotId, str, Optional[str], datetime]]:
        """List all bookmarks with their metadata.
        
        Returns:
            List of tuples: (snapshot_id, name, description, created_at)
        """
        try:
            return self.db_manager.list_bookmarks()
        except Exception as e:
            logger.error(f"Error listing bookmarks: {e}")
            return []
    
    def search_snapshots(self, query: str) -> List[SnapshotMetadata]:
        """Search snapshots by content or metadata.
        
        Args:
            query: Search query string
            
        Returns:
            List of matching snapshot metadata
        """
        try:
            if not query.strip():
                return self.db_manager.list_snapshots()
            
            # Use enhanced database search that includes bookmarks
            return self.db_manager.search_snapshots_by_metadata(query.strip())
        except Exception as e:
            logger.error(f"Error searching snapshots: {e}")
            return []
    
    def search_snapshots_advanced(self, query: str, include_files: bool = False, 
                                 include_bookmarks: bool = True) -> List[SnapshotMetadata]:
        """Advanced search with additional options.
        
        Args:
            query: Search query string
            include_files: Whether to search in affected file names
            include_bookmarks: Whether to search in bookmark names/descriptions
            
        Returns:
            List of matching snapshot metadata
        """
        try:
            if not query.strip():
                return self.db_manager.list_snapshots()
            
            if include_bookmarks:
                # Use database search that includes bookmarks
                results = self.db_manager.search_snapshots_by_metadata(query.strip())
            else:
                # Use basic search without bookmarks
                all_snapshots = self.db_manager.list_snapshots()
                results = self._apply_filters_and_search(all_snapshots, TimelineFilters(), query)
            
            # Additional file name search if requested
            if include_files:
                query_lower = query.lower()
                file_matches = []
                
                for snapshot in self.db_manager.list_snapshots():
                    if any(query_lower in str(f).lower() for f in snapshot.files_affected):
                        if snapshot not in results:
                            file_matches.append(snapshot)
                
                results.extend(file_matches)
                # Sort by timestamp descending
                results.sort(key=lambda s: s.timestamp, reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"Error in advanced search: {e}")
            return []