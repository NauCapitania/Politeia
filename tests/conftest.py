import json
import os
import re
from pathlib import Path

import httpx
import pytest

from connectors.base.http import SourceHttpClient

FIX = Path(__file__).parent / "fixtures"
TEST_DB = os.environ.get("POLITEIA_TEST_DATABASE_URL",
                         "postgresql+psycopg://politeia:politeia@localhost:5432/politeia_test")


def fixture_bytes(rel: str) -> bytes:
    return (FIX / rel).read_bytes()


def official_sources(overrides: dict | None = None):
    """Recorded responses from the official Senado and ALEPE endpoints, keyed by path."""
    routes = {
        r"/dadosabertos/senador/lista/atual$": ("senate/senadores_atual.json", "application/json"),
        r"/dadosabertos/senador/5672/filiacoes$": ("senate/filiacoes_5672.json", "application/json"),
        r"/dadosabertos/processo$": ("senate/processos_lista.json", "application/json"),
        r"/dadosabertos/processo/9101538$": ("senate/processo_8360649.json", "application/json"),
        r"/api/v1/parlamentares/$": ("alepe/parlamentares.json", "application/json"),
        r"/api/v1/proposicoes/projetos/$": ("alepe/projetos_2026.xml", "application/xml"),
    }
    routes.update(overrides or {})
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        for pattern, target in routes.items():
            if re.search(pattern, request.url.path):
                if isinstance(target, httpx.Response):
                    return target
                if callable(target):
                    return target(request)
                name, ctype = target
                return httpx.Response(200, content=fixture_bytes(name), headers={"content-type": ctype})
        return httpx.Response(404, json={"erro": "not found"})

    return handler, calls


def make_client(handler, hosts=("legis.senado.leg.br", "dadosabertos.alepe.pe.gov.br"), **kw) -> SourceHttpClient:
    return SourceHttpClient(list(hosts), max_requests_per_second=1000, transport=httpx.MockTransport(handler),
                            sleep=lambda s: None, **kw)


@pytest.fixture
def load_json():
    return lambda rel: json.loads(fixture_bytes(rel))
