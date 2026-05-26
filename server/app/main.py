from fastapi import FastAPI
from app.db import migrate
from app.routes import admin, notes, query
from app.routes import auth as auth_routes
from app.routes import user_notes as user_notes_routes
from app.routes import progress as progress_routes
from app.routes import admin_books as admin_books_routes
from app.routes import admin_jobs as admin_jobs_routes


def create_app() -> FastAPI:
    migrate()
    from app import books as bk
    bk.reset_stale_jobs()
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    app.include_router(query.router)
    app.include_router(auth_routes.router)
    app.include_router(user_notes_routes.router)
    app.include_router(progress_routes.router)
    app.include_router(admin_books_routes.router)
    app.include_router(admin_jobs_routes.router)
    return app

try:
    app = create_app()
except Exception:
    app = None  # env not set (e.g. during test collection); use create_app() instead
