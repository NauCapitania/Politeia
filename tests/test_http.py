import httpx
import pytest

from connectors.base.http import SourceAccessError
from tests.conftest import make_client

URL = "https://legis.senado.leg.br/dadosabertos/senador/lista/atual"


def test_senate_proxy_only_relays_official_hosts_and_keeps_original_evidence():
    calls = []

    def handler(req):
        calls.append(req)
        if req.url.host != "relay.example":
            return httpx.Response(200, text="direct")
        if req.url.params["url"].endswith("/lista"):
            return httpx.Response(302, headers={"location": "./atual?format=json"})
        return httpx.Response(200, json={"official": True})

    with make_client(handler, hosts=("legis.senado.leg.br", "www12.senado.leg.br", "news.google.com"),
                     senado_proxy_url="https://relay.example/senate", senado_proxy_secret="test-only") as client:
        official = client.get("https://legis.senado.leg.br/dadosabertos/lista")
        client.get("https://www12.senado.leg.br/noticias/rss", accept="application/rss+xml")
        client.get("https://news.google.com/rss")
    assert official.url == "https://legis.senado.leg.br/dadosabertos/atual?format=json"
    assert official.response_format == "json" and official.content == b'{"official":true}'
    assert all(r.headers["authorization"] == "Bearer test-only" for r in calls[:3])
    assert calls[2].headers["accept"] == "application/rss+xml"
    assert calls[3].url.host == "news.google.com" and "authorization" not in calls[3].headers


def test_senate_proxy_rechecks_source_allowlist_on_redirect():
    client = make_client(
        lambda _: httpx.Response(302, headers={"location": "https://other.example/"}),
        senado_proxy_url="https://relay.example/", senado_proxy_secret="test-only",
    )
    with pytest.raises(SourceAccessError, match="host not allowed for this source"):
        client.get("https://legis.senado.leg.br/dadosabertos/lista")
    assert client.request_count == 1


@pytest.mark.parametrize("url, secret", [
    ("https://relay.example/", None),
    (None, "test-only"),
    ("http://relay.example/", "test-only"),
    ("https://user:pw@relay.example/", "test-only"),
])
def test_senate_proxy_rejects_incomplete_or_insecure_configuration(url, secret):
    with pytest.raises(ValueError, match="SENADO_PROXY_URL"):
        make_client(lambda _: httpx.Response(200), senado_proxy_url=url, senado_proxy_secret=secret)

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
