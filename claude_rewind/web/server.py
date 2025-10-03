"""FastAPI server for web dashboard."""

import logging
from pathlib import Path
from typing import Optional
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .api.routes import router as api_router

logger = logging.getLogger(__name__)


class DashboardServer:
    """Web dashboard server for Claude Code Rewind."""

    def __init__(self, project_root: Path, host: str = "127.0.0.1", port: int = 8080):
        """Initialize dashboard server.

        Args:
            project_root: Project root directory
            host: Server host address
            port: Server port
        """
        self.project_root = project_root
        self.host = host
        self.port = port
        self.app = self._create_app()

    def _create_app(self) -> FastAPI:
        """Create FastAPI application."""
        app = FastAPI(
            title="Claude Code Rewind Dashboard",
            description="Visual timeline and diff viewer for Claude Code sessions",
            version="1.5.0",
        )

        # CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],  # TODO: Configure for production
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Include API routes
        app.include_router(api_router, prefix="/api")

        # Static files and templates
        web_dir = Path(__file__).parent
        static_dir = web_dir / "static"
        templates_dir = web_dir / "templates"

        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        if templates_dir.exists():
            templates = Jinja2Templates(directory=str(templates_dir))

            @app.get("/", response_class=HTMLResponse)
            async def dashboard_index(request):
                """Serve dashboard HTML."""
                return templates.TemplateResponse("index.html", {"request": request})

        # Health check
        @app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "project": str(self.project_root)}

        # Store project root in app state
        app.state.project_root = self.project_root

        return app

    def run(self, open_browser: bool = True):
        """Start the dashboard server.

        Args:
            open_browser: Whether to open browser automatically
        """
        logger.info(f"Starting dashboard server at http://{self.host}:{self.port}")

        if open_browser:
            # Open browser after short delay
            import webbrowser
            import threading

            def open_after_delay():
                import time
                time.sleep(1)
                webbrowser.open(f"http://{self.host}:{self.port}")

            threading.Thread(target=open_after_delay, daemon=True).start()

        # Run server
        uvicorn.run(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )

    async def run_async(self):
        """Run server asynchronously (for testing)."""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info",
        )
        server = uvicorn.Server(config)
        await server.serve()
