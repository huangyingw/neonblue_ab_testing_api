"""Main FastAPI application entry point."""

import os
import secrets

from fastapi import FastAPI

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.routers import experiments, events, feature_flags, api_tokens
from app.auth import hash_token
from app.models import ApiToken

# Create database tables
Base.metadata.create_all(bind=engine)


def _bootstrap_token():
    """Create initial token if none exists."""
    db = SessionLocal()
    try:
        token_count = db.query(ApiToken).count()
        if token_count == 0:
            # Check for bootstrap token from environment
            bootstrap_token = os.environ.get("BOOTSTRAP_TOKEN")
            if not bootstrap_token:
                bootstrap_token = secrets.token_urlsafe(32)
                print(f"\n{'='*60}")
                print("INITIAL API TOKEN CREATED")
                print(f"{'='*60}")
                print(f"Token: {bootstrap_token}")
                print("Store this token securely - it will not be shown again!")
                print(f"{'='*60}\n")

            token_hash = hash_token(bootstrap_token)
            db_token = ApiToken(
                name="Bootstrap Token",
                token_hash=token_hash,
            )
            db.add(db_token)
            db.commit()
    finally:
        db.close()


_bootstrap_token()

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
app.include_router(feature_flags.router)
app.include_router(api_tokens.router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
