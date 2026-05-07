"""
FastAPI application factory for the SAFER REST API.

Run with:
    uvicorn safer_api.app:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI

from safer_api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="SAFER Risk Assessment API",
        description=(
            "REST interface for the SAFER (Software Analysis Framework for Evaluating Risk) "
            "model. Reference: arXiv:2408.02876v2."
        ),
        version="1.0.0",
    )
    app.include_router(router)
    return app


app = create_app()
