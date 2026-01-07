"""Main FastAPI application entry point."""

from fastapi import FastAPI

from app.config import settings
from app.database import engine, Base
from app.routers import experiments, events

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="A simplified A/B testing experimentation API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Include routers
app.include_router(experiments.router)
app.include_router(events.router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
