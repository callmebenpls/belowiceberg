from fastapi import FastAPI
from app.routes import admin, notes, query

def create_app() -> FastAPI:
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    app.include_router(query.router)
    return app

app = create_app()  # for `uvicorn app.main:app`
