# server/tests/conftest.py
import os
import pytest
from pathlib import Path

@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Isolated data dir per test."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    monkeypatch.setenv("BELOWICEBERG_DATA_DIR", str(tmp_path))
    return tmp_path

@pytest.fixture
def env(monkeypatch, tmp_data_dir):
    """Sane test env."""
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$KIXxPfnK4TBnXcGmZ7eOe.dxZBT9YR/qK1pT4yL.zJtBM3oWzqJ0a")  # bcrypt of "test"
    monkeypatch.setenv("SESSION_SECRET", "test-secret-do-not-use-in-prod")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    return tmp_data_dir
