from fastapi import FastAPI
from app.routes import admin, notes

def create_app() -> FastAPI:
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    app.include_router(notes.router)
    return app

app = create_app()  # for `uvicorn app.main:app`
