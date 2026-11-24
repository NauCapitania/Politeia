import itertools
import json
from datetime import date

import httpx
import pytest

from connectors.news.connector import NewsConnector
from engine.analysis.secret_ballot import posterior_marginals
from engine.dossiers import DossierError, read_dossiers
from engine.registry import pack_for
from tests.conftest import make_client


def brute_force(priors, totals):
    cands = list(totals)
    acc = [dict.fromkeys(cands, 0.0) for _ in priors]
    z = 0.0
    for combo in itertools.product(cands, repeat=len(priors)):
        if any(combo.count(c) != n for c, n in totals.items()):
            continue
        w = 1.0
        for p, c in zip(priors, combo, strict=True):
            w *= p[c]
        z += w
        for i, c in enumerate(combo):
            acc[i][c] += w
    return [{c: v / z for c, v in a.items()} for a in acc]


def test_secret_ballot_posterior_matches_brute_force_and_totals():
    priors = [{"A": 0.9, "B": 0.05, "C": 0.05}, {"A": 0.6, "B": 0.3, "C": 0.1}, {"A": 0.2, "B": 0.1, "C": 0.7},
              {"A": 0.5, "B": 0.25, "C": 0.25}, {"A": 0.95, "B": 0.04, "C": 0.01}, {"A": 0.3, "B": 0.6, "C": 0.1}]
    totals = {"A": 3, "B": 2, "C": 1}
    got = posterior_marginals(priors, totals)
    want = brute_force(priors, totals)
    for g, w in zip(got, want, strict=True):
        for c in totals:
            assert g[c] == pytest.approx(w[c], abs=1e-9)
    for c, n in totals.items():
        assert sum(g[c] for g in got) == pytest.approx(n)


def test_secret_ballot_rejects_totals_that_do_not_match_voters():
    with pytest.raises(ValueError):
        posterior_marginals([{"A": 1.0, "B": 0.0}], {"A": 1, "B": 1})


RSS = """<?xml version="1.0" encoding="ISO-8859-1"?><rss><channel>
<item><title>PGR analisa relatórios do caso Master sobre ministros do STF</title><link>https://ex.com/a</link>
<description>&lt;p&gt;Texto &lt;b&gt;curto&lt;/b&gt; sobre o Banco Master.&lt;/p&gt;</description>
<pubDate>Mon, 23 Nov 2026 18:00:00 -0300</pubDate></item>
<item><title>Duplicado</title><link>https://ex.com/a</link></item>
<item><title>Sem link</title></item>
</channel></rss>""".encode("latin-1")


@pytest.mark.parametrize("status", [404, 403])
def test_news_rss_keeps_headline_link_excerpt_and_topics_only(status):
    def handler(req: httpx.Request):
        if req.url.host == "down.example":
            return httpx.Response(status)
        return httpx.Response(200, content=RSS, headers={"content-type": "application/rss+xml"})

    cfg = {"feeds": [{"id": "f1", "url": "https://feed.example/rss", "outlet": "Exemplo"},
                     {"id": "f2", "url": "https://down.example/rss", "outlet": "Fora"}]}
    c = NewsConnector(cfg, make_client(handler, hosts=("feed.example", "down.example")))
    b = c.run("news")
    assert [n.url for n in b.news] == ["https://ex.com/a"]
    n = b.news[0]
    assert n.outlet == "Exemplo" and n.published_at.date() == date(2026, 11, 23)
    assert n.excerpt == "Texto curto sobre o Banco Master."
    assert {"caso_master", "stf", "pgr"} <= set(n.topics)
    assert any(i.code == "feed_unavailable" for i in b.issues) and not b.has_errors
    assert [(i.severity, i.message) for i in b.issues] == [("warning", f"HTTP {status}")]


def test_cartacapital_politics_uses_public_google_news_rss():
    rss_source = next(s for s in pack_for("ins_br_senado")["sources"] if s["connector"] == "news-rss")
    feed = next(f for f in rss_source["config"]["feeds"] if f["id"] == "cartacapital_politica")
    payload = b"""<rss><channel><item>
        <title>Noticia de politica - CartaCapital</title>
        <link>https://news.google.com/rss/articles/abc</link>
        <description>
        &lt;a href="https://news.google.com/rss/articles/abc" target="_blank"&gt;Noticia de politica&lt;/a&gt;
        &amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;CartaCapital&lt;/font&gt;</description>
        <source url="https://www.cartacapital.com.br">CartaCapital</source>
    </item></channel></rss>"""

    def handler(req: httpx.Request):
        assert (req.url.host, req.url.path) == ("news.google.com", "/rss/search")
        assert req.url.params["q"] == "site:cartacapital.com.br/politica/"
        return httpx.Response(200, content=payload, headers={"content-type": "application/rss+xml"})

    client = make_client(handler, hosts=tuple(rss_source["allowed_hosts"]))
    batch = NewsConnector({"feeds": [feed]}, client).run("news")
    assert not batch.issues
    [news] = batch.news
    assert (news.feed, news.outlet, news.title) == ("cartacapital_politica", "CartaCapital", "Noticia de politica")
    assert news.excerpt is None


def test_metropoles_rss_uses_politics_section_and_ignores_unrelated_items():
    rss_source = next(s for s in pack_for("ins_br_senado")["sources"] if s["connector"] == "news-rss")
    feed = next(f for f in rss_source["config"]["feeds"] if f["id"] == "metropoles")
    payload = """<rss><channel>
        <item><title>Real Madrid deve igualar salário de Bellingham ao de Vini Jr. em renovação</title>
          <link>https://www.metropoles.com/esportes/futebol/real-madrid-bellingham</link>
          <category>Política</category></item>
        <item><title>Lula é citado em reportagem sobre reality show</title>
          <link>https://www.metropoles.com/entretenimento/televisao/reality-show</link></item>
        <item><title>Erika Hilton recebe ameaça de morte</title>
          <link>https://www.metropoles.com/brasil/politica-brasil/erika-hilton</link></item>
        <item><title>Eleições 2026: brasileiros reclamam de filas</title>
          <link>https://www.metropoles.com/brasil/filas-para-votar</link></item>
        <item><title>Câmara escura: aprenda a tirar fotos</title>
          <link>https://www.metropoles.com/brasil/dicas-de-fotos?secao=politica</link></item>
        <item><title>Corinthians: MPSP pede afastamento de presidente e intervenção judicial</title>
          <link>https://www.metropoles.com/sao-paulo/afastamento-do-presidente-do-corinthians</link>
          <description>MPSP diz que o clube foi capturado por um grupo político.</description></item>
        <item><title>Notícia de última hora</title>
          <link>https://www.metropoles.com/brasil/ultima-hora</link><category>Política</category></item>
    </channel></rss>""".encode()

    def handler(req: httpx.Request):
        assert req.url.path == "/brasil/politica-brasil/feed"
        return httpx.Response(200, content=payload)

    client = make_client(handler, hosts=tuple(rss_source["allowed_hosts"]))
    batch = NewsConnector({"feeds": [feed]}, client).run("news")
    assert len(batch.raw) == 1
    assert [n.title for n in batch.news] == [
        "Erika Hilton recebe ameaça de morte",
        "Eleições 2026: brasileiros reclamam de filas",
        "Notícia de última hora",
    ]
    assert batch.news[-1].topics == ["politica"]


def test_curated_dossiers_are_sourced_and_keep_messias_out_of_the_court():
    dossiers = {d["dossier"]: d for d in read_dossiers()}
    assert {"stf-caso-master", "presidencia-2025", "presidencia-2027"} <= set(dossiers)
    stf = dossiers["stf-caso-master"]["items"]
    ministers = [i for i in stf if i["kind"] == "minister"]
    assert len(ministers) == 10 and sum(i["kind"] == "vacancy" for i in stf) == 1
    assert not any("Messias" in i["payload"]["name"] for i in ministers)
    sent = {i["payload"]["name"] for i in ministers if i["payload"]["master_report"]["status"] == "sent_to_pgr"}
    assert sent == {"Alexandre de Moraes", "Nunes Marques", "Dias Toffoli", "André Mendonça"}
    result = next(i for i in dossiers["presidencia-2025"]["items"] if i["kind"] == "contest")["payload"]["result"]
    assert sorted(r["votes"] for r in result) == [4, 4, 73]


def test_dossier_without_sources_is_rejected(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"dossier": "x", "as_of": "2026-11-23", "items": [
        {"id": "a", "kind": "k", "payload": {}, "sources": []}]}))
    with pytest.raises(DossierError):
        read_dossiers(tmp_path)
