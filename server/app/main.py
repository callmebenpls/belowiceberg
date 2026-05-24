from fastapi import FastAPI
from app.routes import admin

def create_app() -> FastAPI:
    app = FastAPI(title="belowiceberg")
    app.include_router(admin.router)
    return app

app = create_app()  # for `uvicorn app.main:app`
