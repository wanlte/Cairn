from fastapi import FastAPI

from apps.api.main import create_app


def test_create_app_returns_fastapi():
    app = create_app()
    assert isinstance(app, FastAPI)
    assert app.title == "Cairn API"
