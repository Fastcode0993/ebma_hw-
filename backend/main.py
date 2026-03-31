"""
FastAPI Application for Walking Assistant Robot Control System.

This is the main entry point for the backend server.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .core.config import settings
from .routers import robot, logs

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Server: {settings.HOST}:{settings.PORT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down server...")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Web-based control and monitoring system for indoor semi-autonomous walking assistant robot",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(robot.router)
app.include_router(logs.router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "websocket": "ws://localhost:8000/robot/ws/control",
            "set_destination": "POST /robot/api/destination",
            "get_status": "GET /robot/api/status",
            "get_logs": "GET /logs",
            "emergency_stop": "POST /robot/api/emergency_stop"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": "2026-03-31T10:00:00Z"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )