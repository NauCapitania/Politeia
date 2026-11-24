"""Poder Executivo: SIORG archive + cabinet list -> Postgres -> /v1/executivo."""

import csv
import io
import json
import os
import subprocess
import sys
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from connectors.executive.cabinet import CabinetConnector, parse_cabinet, pt_date
from connectors.executive.siorg import SiorgConnector
from engine.db import models as M
from engine.db.session import get_session
from engine.ingestion.sync import sync_source
from engine.registry import bootstrap
from tests.conftest import TEST_DB, fixture_bytes, make_client

URI = "https://estruturaorganizacional.dados.gov.br/id"
HOSTS = ("repositorio.dados.gov.br", "pt.wikipedia.org")
COLUMNS = ["codigoUnidade", "codigoUnidadePai", "codigoOrgaoEntidade", "codigoTipoUnidade", "nome", "sigla",
           "codigoEsfera", "codigoPoder", "codigoNaturezaJuridica", "versaoConsulta", "dataInicialVersaoConsulta",
           "competencia", "finalidade", "missao", "descricaoAtoNormativo", "areaAtuacao", "site", "uf"]


def unit(code, parent, kind, name, acronym, poder="1", nature="3", owner=None, competence=""):
    return {"codigoUnidade": f"{URI}/unidade-organizacional/{code}",
            "codigoUnidadePai": f"{URI}/unidade-organizacional/{parent}" if parent else "",
            "codigoOrgaoEntidade": f"{URI}/unidade-organizacional/{owner or code}",
            "codigoTipoUnidade": f"{URI}/tipo-unidade/{kind}", "nome": name, "sigla": acronym,
            "codigoEsfera": f"{URI}/esfera/1", "codigoPoder": f"{URI}/poder/{poder}",
            "codigoNaturezaJuridica": f"{URI}/natureza-juridica/{nature}", "versaoConsulta": "1.0",
            "dataInicialVersaoConsulta": "2023-01-01", "competencia": competence, "finalidade": "", "missao": "",
            "descricaoAtoNormativo": "Decreto nº 11.907, de 30 de janeiro de 2024", "areaAtuacao": "", "site": "",
            "uf": ""}


BASE_ROWS = [
    unit("26", "", "orgao", "Presidência da República", "PR", competence="Sancionar e vetar projetos de lei."),
    unit("308793", "26", "orgao", "Ministério da Agricultura e Pecuária", "MAPA", competence="Política agrícola."),
    unit("264359", "26", "orgao", "Ministério das Comunicações", "MCOM"),
    unit("42673", "26", "orgao", "Secretaria de Relações Institucionais da Presidência da República", "SRI/PR"),
    unit("1408", "26", "orgao", "Vice-Presidência da República", "VPR"),
    unit("900", "308793", "entidade", "Companhia Nacional de Abastecimento", "CONAB", nature="1"),
    unit("901", "900", "entidade", "Subsidiária da Conab", "SUBC", nature="6"),
    unit("5001", "308793", "unidade-administrativa", "Secretaria-Executiva", "SE", owner="308793"),
    unit("5002", "308793", "unidade-administrativa", "Gabinete do Ministro", "GM", owner="308793"),
    unit("77", "", "orgao", "Câmara dos Deputados", "CD", poder="2"),
]


def archive(rows) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("estrutura-organizacional-completa-siorg.csv", out.getvalue().encode("utf-8-sig"))
    return buf.getvalue()


def handler_for(rows, wikitext: bytes | None = None):
    zipped = archive(rows)
    listing = ('<a href="estrutura-organizacional-completa-2026-06.zip">a</a>'
               '<a href="estrutura-organizacional-completa-2026-07.zip">b</a>')

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "pt.wikipedia.org":
            return httpx.Response(200, content=wikitext or fixture_bytes("executive/gabinete.json"),
                                  headers={"content-type": "application/json"})
        if request.url.path.endswith("2026-07.zip"):
            return httpx.Response(200, content=zipped, headers={"content-type": "application/zip"})
        if request.url.path.endswith("/estrutura-organizacional-completa/"):
            return httpx.Response(200, text=listing, headers={"content-type": "text/html"})
        return httpx.Response(404)

    return handler


def test_pt_dates():
    assert pt_date("1.º de janeiro de 2023").isoformat() == "2023-01-01"
    assert pt_date("07 de janeiro de 2025").isoformat() == "2025-01-07"
    assert pt_date("{{N/A|''Em exercício''}}") is None


def test_cabinet_parser_keeps_rowspans_interims_refs_and_only_first_table():
    terms, problems = parse_cabinet(json.loads(fixture_bytes("executive/gabinete.json"))["parse"]["wikitext"])
    assert not problems
    assert {t["ministry"] for t in terms} == {
        "Agricultura e Pecuária", "Comunicações", "Secretaria de Relações Institucionais",
        "Secretaria Extraordinária da Presidência da República para Apoio à Reconstrução do Rio Grande do Sul"}
    agro = [t for t in terms if t["ministry"] == "Agricultura e Pecuária"]
    assert [(t["name"], t["party"], t["uf"]) for t in agro] == [("Carlos Fávaro", "PSD", "MT"),
                                                                 ("André de Paula", "PSD", "PE")]
    assert agro[0]["end"].isoformat() == "2026-03-31" and agro[1]["end"] is None
    sonia = next(t for t in terms if t["name"].startswith("Sônia"))
    assert sonia["interim"] and sonia["party"] is None and sonia["person_title"] is None
    assert agro[1]["refs"][0]["url"].startswith("https://g1.globo.com/")


def test_siorg_connector_keeps_federal_executive_bodies_and_archive_hash():
    conn = SiorgConnector({}, make_client(handler_for(BASE_ROWS), hosts=HOSTS))
    batch = conn.run("structure")
    assert not batch.has_errors
    assert {b.code for b in batch.executive_bodies} == {"26", "308793", "264359", "42673", "1408", "900", "901"}
    raw = batch.raw[0].response
    assert raw.headers["x-archive-month"] == "2026-07"
    assert raw.headers["x-archive-sha256"]
    assert raw.url.endswith("2026-07.zip#orgaos-e-entidades-do-poder-executivo-federal")
    mapa = next(b for b in batch.executive_bodies if b.code == "308793")
    assert mapa.attributes["administrative_units"] == 2 and mapa.legal_nature == "Administração Direta"
    assert next(b for b in batch.executive_bodies if b.code == "900").legal_nature == "Empresa Pública"


def test_cabinet_connector_marks_terms_as_extracted():
    conn = CabinetConnector({}, make_client(handler_for(BASE_ROWS), hosts=HOSTS))
    batch = conn.run("members")
    assert not batch.has_errors and batch.complete_member_list
    current = [m for m in batch.mandates if m.status == "in_exercise"]
    assert {m.represented_unit for m in current} == {"Agricultura e Pecuária", "Comunicações",
                                                     "Secretaria de Relações Institucionais"}
    assert all(m.epistemic_status == "extracted" for m in batch.mandates)


@pytest.fixture(scope="module")
def factory():
    engine = create_engine(TEST_DB)
    try:
        engine.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"test database unavailable: {exc}")
    env = dict(os.environ, POLITEIA_DATABASE_URL=TEST_DB)
    for cmd in ("downgrade", "upgrade"):
        subprocess.run([sys.executable, "-m", "alembic", cmd, "base" if cmd == "downgrade" else "head"],
                       check=True, env=env, capture_output=True)
    f = sessionmaker(engine, expire_on_commit=False)
    with f() as s:
        bootstrap(s)
    handler = handler_for(BASE_ROWS)
    sync_source(f, "src_br_siorg", ["structure"], client=make_client(handler, hosts=HOSTS))
    sync_source(f, "src_ptwiki_gabinete", ["members"], client=make_client(handler, hosts=HOSTS))
    yield f
    engine.dispose()


@pytest.fixture(scope="module")
def api(factory):
    from engine.api.app import app

    def session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_executivo_joins_structure_and_cabinet(api):
    d = api.get("/v1/executivo").json()
    assert d["presidency"]["competence"] == "Sancionar e vetar projetos de lei."
    bodies = {b["code"]: b for b in d["bodies"]}
    assert set(bodies) == {"308793", "264359", "42673", "1408"}
    assert bodies["42673"]["kind"] == "presidencia" and bodies["308793"]["kind"] == "ministerio"
    assert bodies["308793"]["holder"]["name"] == "André de Paula"
    assert [t["name"] for t in bodies["308793"]["terms"]] == ["Carlos Fávaro", "André de Paula"]
    assert {e["code"] for e in bodies["308793"]["entities"]} == {"900", "901"}
    assert bodies["42673"]["holder"]["name"] == "José Nobre Guimarães"
    assert bodies["1408"]["holder"] is None
    assert [u["ministry"] for u in d["unmatched"]] == [
        "Secretaria Extraordinária da Presidência da República para Apoio à Reconstrução do Rio Grande do Sul"]
    assert d["counts"]["ministers_in_office"] == 3
    caps = {c["capability"]: c["status"] for c in api.get("/v1/institutions/ins_br_executivo/capabilities").json()}
    assert caps["executive_structure"] == "available"


def test_resync_keeps_removed_bodies_and_terms_as_history(factory, api):
    rows = [r for r in BASE_ROWS if not r["codigoUnidade"].endswith("/264359")]
    wiki = json.loads(fixture_bytes("executive/gabinete.json"))
    text = wiki["parse"]["wikitext"]
    start = text.find("|rowspan=\"3\" | [[Ministério das Comunicações")
    if start < 0:
        start = text.find("[[Ministério das Comunicações")
    end = text.find("[[Enchentes", start)
    wiki["parse"]["wikitext"] = text[:text.rfind("\n|-", 0, start)] + text[text.rfind("\n|-", 0, end):]
    handler = handler_for(rows, json.dumps(wiki).encode())
    sync_source(factory, "src_br_siorg", ["structure"], client=make_client(handler, hosts=HOSTS))
    sync_source(factory, "src_ptwiki_gabinete", ["members"], client=make_client(handler, hosts=HOSTS))
    with factory() as s:
        mcom = s.scalar(select(M.ExecutiveBody).where(M.ExecutiveBody.siorg_code == "264359"))
        assert mcom is not None and mcom.is_current is False
        frederico = s.scalar(select(M.Mandate).where(M.Mandate.represented_unit == "Comunicações",
                                                     M.Mandate.end_date.is_(None)))
        assert frederico.status == "not_observed"
        ended = s.scalars(select(M.Mandate).where(M.Mandate.represented_unit == "Comunicações")).all()
        assert ended and all(m.status == "not_observed" for m in ended)
    d = api.get("/v1/executivo").json()
    assert "264359" not in {b["code"] for b in d["bodies"]}
    names = {t["name"] for b in d["bodies"] for t in b["terms"]}
    names |= {t["name"] for u in d["unmatched"] for t in u["terms"]}
    assert "Juscelino Filho" not in names and "Carlos Fávaro" in names


INLINE = "\n".join([
    '{| class="wikitable"',
    "! Ministério !! Foto !! Ministro !! Partido !! Início !! Fim !! Ref.",
    "|-",
    '| rowspan="2" | [[Ministério da Pesca e Aquicultura|Pesca e Aquicultura]] || [[Ficheiro:X.jpg|50px]] '
    "|| [[André de Paula]] || [[PSD]]/PE || 1.º de janeiro de 2023 || 31 de março de 2026 "
    '|| <ref name="pesca">{{citar web |url=https://g1.globo.com/pesca |titulo=Posse |website=G1}}</ref>',
    "|-",
    "| [[Ficheiro:Y.jpg|50px]] || [[Fulano de Tal]] || Sem partido || 1.º de abril de 2026 "
    "|| {{N/A|''Em exercício''}} || <ref name=\"pesca\" />",
    "|}",
])


def test_inline_cells_and_reused_named_refs():
    terms, problems = parse_cabinet(INLINE)
    assert not problems
    assert [(t["name"], t["party"], t["ministry"]) for t in terms] == [
        ("André de Paula", "PSD", "Pesca e Aquicultura"), ("Fulano de Tal", None, "Pesca e Aquicultura")]
    assert terms[1]["refs"] == [{"url": "https://g1.globo.com/pesca", "title": "Posse", "date": None, "outlet": "G1"}]


def wiki_handler(text: str):
    body = json.dumps({"parse": {"title": "x", "revid": 1, "wikitext": text}}).encode()
    return make_client(handler_for(BASE_ROWS, body), hosts=HOSTS)


def test_partial_parse_is_not_a_complete_listing_and_ids_ignore_start_date():
    second = INLINE.index("| [[Ficheiro:Y.jpg")
    broken = INLINE[:second] + "| só uma célula\n|}"
    batch = CabinetConnector({}, wiki_handler(broken)).run("members")
    assert not batch.complete_member_list
    assert any(i.code == "cabinet_row_skipped" for i in batch.issues)
    ids = [m.identifier.value for m in CabinetConnector({}, wiki_handler(INLINE)).run("members").mandates]
    moved = INLINE.replace("1.º de abril de 2026", "2 de abril de 2026")
    assert ids == [m.identifier.value for m in CabinetConnector({}, wiki_handler(moved)).run("members").mandates]


def test_cabinet_source_excerpt_is_the_cited_row(factory):
    from engine.api.queries import source_record

    with factory() as s:
        mandate = s.scalar(select(M.Mandate).where(M.Mandate.institution_id == "ins_br_executivo")
                           .order_by(M.Mandate.start_date))
        ev = s.scalar(select(M.RelationshipEvidence).where(M.RelationshipEvidence.relationship_id == mandate.id))
        rec = source_record(s, str(ev.raw_record_id), ev.json_path)
    assert ev.json_path.startswith("$.parse.wikitext#row")
    assert mandate.represented_unit in rec.excerpt or "Ministério" in rec.excerpt


def test_news_does_not_link_cabinet_only_people(factory):
    from engine.media import _patterns

    with factory() as s:
        names = {p.pattern for kind, _, p, _ in _patterns(s) if kind == "person"}
    assert not any("andre de paula" in n for n in names)
