import httpx
import pytest

from connectors.base.http import SourceAccessError
from tests.conftest import make_client

URL = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual"


def test_retries_on_transient_errors_then_succeeds():
    seq = iter([httpx.Response(503), httpx.Response(429, headers={"retry-after": "2"}), httpx.Response(200, json={})])
    slept: list[float] = []
    client = make_client(lambda r: next(seq))
    client.sleep = slept.append
    resp = client.get(URL)
    assert resp.status == 200 and client.request_count == 3
    assert 2.0 in slept  # Retry-After honoured


def test_gives_up_after_bounded_attempts():
    client = make_client(lambda r: httpx.Response(500), max_attempts=3)
    with pytest.raises(SourceAccessError) as exc:
        client.get(URL)
    assert exc.value.status == 500 and client.request_count == 3


def test_client_errors_are_not_retried():
    client = make_client(lambda r: httpx.Response(404))
    with pytest.raises(SourceAccessError):
        client.get(URL)
    assert client.request_count == 1


def test_rejects_hosts_outside_allow_list_and_plain_http():
    client = make_client(lambda r: httpx.Response(200))
    with pytest.raises(SourceAccessError):
        client.get("https://example.com/x")
    with pytest.raises(SourceAccessError):
        client.get("http://legis.senado.leg.br/dadosabertos/x")


def test_redirect_to_foreign_host_is_refused():
    client = make_client(lambda r: httpx.Response(301, headers={"location": "https://evil.example/"}))
    with pytest.raises(SourceAccessError):
        client.get(URL)


def test_response_metadata_hash_and_deprecation():
    headers = {"content-type": "application/json", "deprecation": "true", "sunset": "2027-01-01"}
    client = make_client(lambda r: httpx.Response(200, content=b'{"a":1}', headers=headers))
    a, b = client.get(URL), client.get(URL)
    assert a.sha256 == b.sha256 and len(a.sha256) == 64
    assert a.response_format == "json" and a.headers["sunset"] == "2027-01-01"
    assert client.deprecations
