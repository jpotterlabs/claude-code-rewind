"""API routes for Claude Code Rewind dashboard."""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Depends, Request
from pydantic import BaseModel

from ...storage.database import DatabaseManager
from ...core.snapshot_engine import SnapshotEngine
from ...core.config import ConfigManager

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic models for API responses
class SnapshotResponse(BaseModel):
    """Snapshot metadata response."""
    id: str
    timestamp: str
    description: str
    tags: List[str]
    file_count: int
    total_size: int


class SnapshotDetailResponse(BaseModel):
    """Detailed snapshot response."""
    id: str
    timestamp: str
    description: str
    tags: List[str]
    files: List[Dict[str, Any]]
    total_size: int


class DiffResponse(BaseModel):
    """Diff response."""
    file_path: str
    changes: List[Dict[str, Any]]
    stats: Dict[str, int]


class SessionResponse(BaseModel):
    """Session information response."""
    session_id: str
    start_time: str
    end_time: Optional[str]
    snapshot_count: int
    total_changes: int


# Dependency to get project root from request
def get_project_root(request: Request) -> Path:
    """Get project root from request state."""
    return request.app.state.project_root


# Dependency to get database manager
def get_db_manager(project_root: Path = Depends(get_project_root)) -> DatabaseManager:
    """Get database manager for current project."""
    db_path = project_root / ".claude-rewind" / "metadata.db"
    return DatabaseManager(db_path)


# Dependency to get snapshot engine
def get_snapshot_engine(project_root: Path = Depends(get_project_root)) -> SnapshotEngine:
    """Get snapshot engine for current project."""
    config_manager = ConfigManager(project_root)
    config = config_manager.load_config()
    rewind_dir = project_root / ".claude-rewind"

    return SnapshotEngine(
        project_root,
        rewind_dir,
        config.performance,
        config.storage,
        config.git_integration,
    )


@router.get("/snapshots", response_model=List[SnapshotResponse])
async def list_snapshots(
    limit: int = 50,
    offset: int = 0,
    tags: Optional[str] = None,
    db: DatabaseManager = Depends(get_db_manager),
):
    """List snapshots with optional filtering.

    Args:
        limit: Maximum number of snapshots to return
        offset: Offset for pagination
        tags: Comma-separated tags to filter by
        db: Database manager

    Returns:
        List of snapshots
    """
    try:
        # Parse tags
        tag_list = tags.split(",") if tags else None

        # Get snapshots from database
        snapshots = db.list_snapshots(limit=limit, offset=offset)

        # Filter by tags if provided
        if tag_list:
            snapshots = [
                s for s in snapshots
                if any(tag in s.get("tags", []) for tag in tag_list)
            ]

        # Convert to response model
        return [
            SnapshotResponse(
                id=s["id"],
                timestamp=s["timestamp"],
                description=s.get("description", ""),
                tags=s.get("tags", []),
                file_count=s.get("file_count", 0),
                total_size=s.get("total_size", 0),
            )
            for s in snapshots
        ]

    except Exception as e:
        logger.exception(f"Failed to list snapshots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotDetailResponse)
async def get_snapshot(
    snapshot_id: str,
    engine: SnapshotEngine = Depends(get_snapshot_engine),
):
    """Get detailed snapshot information.

    Args:
        snapshot_id: Snapshot ID
        engine: Snapshot engine

    Returns:
        Detailed snapshot information
    """
    try:
        # Get snapshot metadata
        metadata = engine.get_snapshot_metadata(snapshot_id)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

        # Get file list
        files = []
        if hasattr(metadata, "files"):
            files = [
                {
                    "path": str(f.path),
                    "change_type": f.change_type.value if hasattr(f, "change_type") else "modified",
                    "size": f.size if hasattr(f, "size") else 0,
                }
                for f in metadata.files
            ]

        return SnapshotDetailResponse(
            id=metadata.id,
            timestamp=metadata.timestamp.isoformat(),
            description=metadata.description,
            tags=metadata.tags,
            files=files,
            total_size=sum(f.get("size", 0) for f in files),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get snapshot {snapshot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diff/{snapshot_id}/{file_path:path}", response_model=DiffResponse)
async def get_diff(
    snapshot_id: str,
    file_path: str,
    engine: SnapshotEngine = Depends(get_snapshot_engine),
):
    """Get diff for a specific file in a snapshot.

    Args:
        snapshot_id: Snapshot ID
        file_path: File path relative to project root
        engine: Snapshot engine

    Returns:
        Diff information
    """
    try:
        # Get snapshot
        metadata = engine.get_snapshot_metadata(snapshot_id)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

        # Load snapshot content
        snapshot = engine.load_snapshot(snapshot_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail=f"Snapshot content not found")

        # Find file in snapshot
        file_data = None
        for f in snapshot.files:
            if str(f.path) == file_path:
                file_data = f
                break

        if not file_data:
            raise HTTPException(status_code=404, detail=f"File {file_path} not in snapshot")

        # Generate diff (simplified for now)
        # TODO: Implement proper diff generation
        changes = [
            {
                "line_number": 1,
                "type": "modified",
                "content": "File content changed",
            }
        ]

        return DiffResponse(
            file_path=file_path,
            changes=changes,
            stats={
                "additions": 0,
                "deletions": 0,
                "modifications": 1,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get diff for {file_path} in {snapshot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions(
    limit: int = 10,
    db: DatabaseManager = Depends(get_db_manager),
):
    """List recent sessions.

    Args:
        limit: Maximum sessions to return
        db: Database manager

    Returns:
        List of sessions
    """
    try:
        # Get snapshots and group by session
        snapshots = db.list_snapshots(limit=1000)

        # Extract unique session IDs from tags
        sessions_data = {}
        for s in snapshots:
            tags = s.get("tags", [])
            session_tags = [t for t in tags if t.startswith("session:")]

            for tag in session_tags:
                session_id = tag.replace("session:", "")
                if session_id not in sessions_data:
                    sessions_data[session_id] = {
                        "session_id": session_id,
                        "start_time": s["timestamp"],
                        "end_time": None,
                        "snapshot_count": 0,
                        "total_changes": 0,
                    }

                sessions_data[session_id]["snapshot_count"] += 1
                sessions_data[session_id]["total_changes"] += s.get("file_count", 0)

                # Update end time
                if sessions_data[session_id]["end_time"] is None or \
                   s["timestamp"] > sessions_data[session_id]["end_time"]:
                    sessions_data[session_id]["end_time"] = s["timestamp"]

        # Convert to list and limit
        sessions = list(sessions_data.values())
        sessions.sort(key=lambda x: x["start_time"], reverse=True)
        sessions = sessions[:limit]

        return [
            SessionResponse(
                session_id=s["session_id"],
                start_time=s["start_time"],
                end_time=s["end_time"],
                snapshot_count=s["snapshot_count"],
                total_changes=s["total_changes"],
            )
            for s in sessions
        ]

    except Exception as e:
        logger.exception(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(db: DatabaseManager = Depends(get_db_manager)):
    """Get overall statistics.

    Args:
        db: Database manager

    Returns:
        Statistics dictionary
    """
    try:
        snapshots = db.list_snapshots(limit=10000)

        total_snapshots = len(snapshots)
        total_files = sum(s.get("file_count", 0) for s in snapshots)
        total_size = sum(s.get("total_size", 0) for s in snapshots)

        # Count by tag types
        tag_counts = {}
        for s in snapshots:
            for tag in s.get("tags", []):
                if tag.startswith("tool:"):
                    tool = tag.replace("tool:", "")
                    tag_counts[tool] = tag_counts.get(tool, 0) + 1

        return {
            "total_snapshots": total_snapshots,
            "total_files": total_files,
            "total_size": total_size,
            "tool_usage": tag_counts,
            "recent_activity": len([s for s in snapshots[:10]]),
        }

    except Exception as e:
        logger.exception(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket connection manager
class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept new connection."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """Remove connection."""
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Broadcast message to all connections."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to connection: {e}")


manager = ConnectionManager()


@router.post("/rollback/{snapshot_id}")
async def rollback_snapshot(
    snapshot_id: str,
    engine: SnapshotEngine = Depends(get_snapshot_engine),
):
    """Rollback project to a specific snapshot.

    Args:
        snapshot_id: Snapshot ID to rollback to
        engine: Snapshot engine

    Returns:
        Rollback result with files restored count
    """
    try:
        # Verify snapshot exists
        metadata = engine.get_snapshot_metadata(snapshot_id)
        if not metadata:
            raise HTTPException(status_code=404, detail=f"Snapshot {snapshot_id} not found")

        # Perform rollback
        # Note: This uses the existing rollback functionality
        from ...rollback.analyzer import RollbackAnalyzer

        analyzer = RollbackAnalyzer(engine.db_manager, engine.file_store, engine.project_root)
        files_to_restore = analyzer.analyze_rollback(snapshot_id)

        # Execute rollback
        files_restored = 0
        for file_path in files_to_restore:
            try:
                engine._restore_file(snapshot_id, file_path)
                files_restored += 1
            except Exception as e:
                logger.warning(f"Failed to restore {file_path}: {e}")

        return {
            "success": True,
            "snapshot_id": snapshot_id,
            "files_restored": files_restored,
            "message": f"Successfully rolled back to {snapshot_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to rollback to {snapshot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates.

    Clients can connect to receive live snapshot notifications.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Wait for messages from client (keepalive)
            data = await websocket.receive_text()

            # Echo back (for now)
            await websocket.send_json({"type": "pong", "timestamp": datetime.now().isoformat()})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.exception(f"WebSocket error: {e}")
        manager.disconnect(websocket)
