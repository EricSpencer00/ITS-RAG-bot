# Re-export the FastAPI app from main module
from app.main import app

__all__ = ["app"]
