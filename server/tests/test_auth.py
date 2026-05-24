import pytest
from app.auth import verify_password, issue_session, validate_session

def test_verify_password_correct(env):
    # hash in conftest is bcrypt("test")
    assert verify_password("test") is True

def test_verify_password_wrong(env):
    assert verify_password("nope") is False

def test_issue_and_validate_roundtrip(env):
    token = issue_session()
    assert validate_session(token) is True

def test_validate_session_rejects_tampered(env):
    token = issue_session()
    bad = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    assert validate_session(bad) is False

def test_validate_session_rejects_empty(env):
    assert validate_session("") is False
    assert validate_session(None) is False
