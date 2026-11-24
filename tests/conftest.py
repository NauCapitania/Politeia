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
    """Recorded responses from the official Senado endpoints, keyed by path."""
    routes = {
        r"/dadosabertos/senador/lista/atual$": ("senate/senadores_atual.json", "application/json"),
        r"/dadosabertos/senador/5672/filiacoes$": ("senate/filiacoes_5672.json", "application/json"),
        r"/dadosabertos/processo$": ("senate/processos_lista.json", "application/json"),
        r"/dadosabertos/processo/9101538$": ("senate/processo_8360649.json", "application/json"),
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


def make_client(handler, hosts=("legis.senado.leg.br",), **kw) -> SourceHttpClient:
    return SourceHttpClient(list(hosts), max_requests_per_second=1000, transport=httpx.MockTransport(handler),
                            sleep=lambda s: None, **kw)


@pytest.fixture
def load_json():
    return lambda rel: json.loads(fixture_bytes(rel))


def chamber_sources(overrides: dict | None = None):
    """Recorded responses from the official Câmara endpoints, keyed by path."""
    routes = {
        r"/api/v2/deputados$": "deputados.json",
        r"/api/v2/deputados/(\d+)$": "deputado_{}.json",
        r"/api/v2/deputados/(\d+)/historico$": "historico_{}.json",
        r"/api/v2/proposicoes$": "proposicoes.json",
        r"/api/v2/proposicoes/(\d+)$": "proposicao_{}.json",
        r"/api/v2/proposicoes/(\d+)/autores$": "autores_{}.json",
        r"/api/v2/proposicoes/(\d+)/tramitacoes$": "tramitacoes_{}.json",
        r"/api/v2/votacoes$": "votacoes.json",
        r"/api/v2/votacoes/([\d-]+)/votos$": "votos_{}.json",
        r"/api/v2/orgaos$": "orgaos.json",
        r"/api/v2/orgaos/(\d+)$": "orgao_{}.json",
        r"/api/v2/orgaos/(\d+)/membros$": "membros_{}.json",
    }
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        for pattern, target in (overrides or {}).items():
            if re.search(pattern, request.url.path):
                return target(request) if callable(target) else target
        for pattern, name in routes.items():
            m = re.search(pattern, request.url.path)
            if m:
                file = FIX / "chamber" / name.format(*m.groups())
                if file.exists():
                    return httpx.Response(200, content=file.read_bytes(), headers={"content-type": "application/json"})
                return httpx.Response(200, json={"dados": [], "links": []})
        return httpx.Response(404, json={"erro": "not found"})

    return handler, calls
