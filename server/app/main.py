from fastapi import FastAPI
from app.db import migrate
from app.routes import admin, notes, query
from app.routes import auth as auth_routes

def create_app() -> FastAPI:
    migrate()
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)        # legacy, removed in Task 19
    app.include_router(notes.router)
    app.include_router(query.router)
    app.include_router(auth_routes.router)
    return app

try:
    app = create_app()
except Exception:
    app = None  # env not set (e.g. during test collection); use create_app() instead
