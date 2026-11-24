from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from scripts import export_snapshot as snapshot


def test_snapshot_configures_a_local_pool_without_overflow(monkeypatch):
    monkeypatch.delenv("SNAPSHOT_WORKERS", raising=False)
    assert snapshot.snapshot_workers() == 4
    monkeypatch.setenv("SNAPSHOT_WORKERS", "2")
    monkeypatch.setattr(snapshot, "get_settings", lambda: SimpleNamespace(database_url="postgresql+psycopg://localhost/db"))
    factory = Mock(wraps=create_engine)
    monkeypatch.setattr(snapshot, "create_engine", factory)
    with snapshot.snapshot_client(snapshot.snapshot_workers()):
        factory.assert_called_once_with("postgresql+psycopg://localhost/db", pool_pre_ping=True,
                                        pool_size=2, max_overflow=0)
    monkeypatch.setenv("SNAPSHOT_WORKERS", "0")
    with pytest.raises(snapshot.SnapshotError, match="SNAPSHOT_WORKERS"):
        snapshot.snapshot_workers()


def test_snapshot_retries_operational_errors_and_server_errors(monkeypatch):
    app = FastAPI()
    attempts = 0

    @app.get("/v1/institutions")
    def institutions():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OperationalError(None, None, Exception("connection lost"))
        if attempts == 2:
            raise HTTPException(503)
        return {"ok": True}

    sleep = Mock()
    monkeypatch.setattr(snapshot, "sleep", sleep)

    with TestClient(app) as api:
        assert snapshot.get_snapshot_data(api, "institutions") == {"ok": True}
    assert attempts == 3
    assert sleep.call_args_list == [call(1), call(2)]


def test_snapshot_reports_exhausted_retries_without_credentials(monkeypatch):
    dsn = "postgresql+psycopg://user:synthetic%40password@local.test/database"
    monkeypatch.setattr(snapshot, "get_settings", lambda: SimpleNamespace(database_url=dsn))
    sleep = Mock()
    monkeypatch.setattr(snapshot, "sleep", sleep)
    api = Mock()
    api.get.side_effect = OperationalError("SELECT not_for_logs", {"private": "not_for_logs"}, Exception(
        f"connection lost; {dsn}; alternate postgres://other:othersecret@localhost/db; "
        "password='a separate secret'; values synthetic@password and synthetic%40password"
    ))

    with pytest.raises(snapshot.SnapshotError) as error:
        snapshot.get_snapshot_data(api, "institutions")
    assert "/v1/institutions: OperationalError: connection lost" in str(error.value)
    secrets = (dsn, "othersecret", "a separate secret", "synthetic@password", "synthetic%40password", "not_for_logs")
    for secret in secrets:
        assert secret not in str(error.value)
    assert api.get.call_count == 4
    assert sleep.call_args_list == [call(1), call(2), call(4)]


def test_snapshot_does_not_retry_client_errors(monkeypatch):
    sleep = Mock()
    monkeypatch.setattr(snapshot, "sleep", sleep)
    api = Mock()
    api.get.return_value = Response(404)

    assert snapshot.get_snapshot_data(api, "dossies/unknown", optional=True) is None
    with pytest.raises(snapshot.SnapshotError, match="HTTP 404"):
        snapshot.get_snapshot_data(api, "dossies/unknown")
    assert api.get.call_count == 2
    sleep.assert_not_called()
