"""End-to-end: recorded official responses -> ingestion -> Postgres -> common v1 API."""

import json
import os
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from engine.db import models as M
from engine.db.session import get_session
from engine.dossiers import load_dossiers
from engine.ingestion.sync import sync_source
from engine.registry import bootstrap
from scripts.export_snapshot import export_snapshot
from tests.conftest import TEST_DB, make_client, official_sources

SOURCES = {"ins_br_senado": "src_br_senado_dadosabertos"}


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
        s.commit()
    for src in SOURCES.values():
        handler, _ = official_sources()
        for scope in ("members", "proposals"):
            sync_source(f, src, [scope], client=make_client(handler))
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


def count(f, model, **where):
    with f() as s:
        return s.scalar(select(func.count()).select_from(model).filter_by(**where))


def test_resync_is_idempotent(factory):
    before = {m: count(factory, m) for m in (M.Person, M.Mandate, M.Proposal, M.RawRecord, M.ProposalAuthor)}
    for src in SOURCES.values():
        handler, _ = official_sources()
        sync_source(factory, src, ["members", "proposals"], client=make_client(handler))
    after = {m: count(factory, m) for m in before}
    assert before == after


def test_senate_mandates_persisted(factory):
    assert count(factory, M.Mandate, institution_id="ins_br_senado") == 3


def test_raw_evidence_preserved_with_hash(factory):
    with factory() as s:
        rows = s.execute(select(M.RawRecord.content_sha256, M.RawRecord.payload, M.RawRecord.payload_text)).all()
    assert rows and all(len(h) == 64 and (p is not None or t) for h, p, t in rows)


def test_institutions_include_every_pack(api):
    insts = api.get("/v1/institutions").json()
    assert {i["id"] for i in insts} == {*SOURCES, "ins_br_camara"}
    m = api.get("/v1/institutions/ins_br_senado/members").json()
    p = api.get("/v1/institutions/ins_br_senado/proposals").json()
    assert m["total"] > 0 and p["total"] > 0


def test_composition_uses_seat_count_and_flags_unverified(api):
    sen = api.get("/v1/institutions/ins_br_senado/composition").json()
    assert sen["seat_count"] == 81 and len(sen["seats"]) == 81 and sen["observed_members"] == 3
    assert sum(s["state"] == "occupied" for s in sen["seats"]) == 3
    assert sum(g["count"] for g in sen["groups"]) == sen["observed_members"]


def test_capabilities_reflect_real_ingestion(api):
    sen = {c["capability"]: c for c in api.get("/v1/institutions/ins_br_senado/capabilities").json()}
    # The members run carried affiliation warnings, so the run (and capability) is honestly partial.
    assert sen["members"]["status"] in {"available", "partial"} and sen["members"]["record_count"] == 3
    # Two of the three recorded senators have no affiliation response: history is partial, not available.
    assert sen["party_history"]["status"] == "partial"
    assert sen["committees"]["status"] == "not_ingested"


def test_entity_relationships_timeline_and_provenance(api):
    m = api.get("/v1/institutions/ins_br_senado/members", params={"q": ""}).json()["items"]
    person = next(x for x in m if any(i["value"] == "5672" for i in x["identifiers"]))
    ent = api.get(f"/v1/entities/{person['person_id']}").json()
    assert ent["kind"] == "person" and ent["sources"]
    rels = api.get(f"/v1/entities/{person['person_id']}/relationships").json()
    kinds = {r["kind"] for r in rels}
    assert {"holds_mandate", "current_party", "party_affiliation"} <= kinds
    assert all(r["sources"] or r["epistemic_status"] == "derived" for r in rels)
    assert api.get(f"/v1/entities/{person['person_id']}/timeline").json()
    src = ent["sources"][0]
    rec = api.get(f"/v1/sources/{src['raw_record_id']}", params={"path": src["json_path"]}).json()
    assert rec["ref"]["url"].startswith("https://legis.senado.leg.br/") and rec["excerpt"] is not None


def test_proposal_authors_link_to_people_only_with_evidence(api):
    props = api.get("/v1/institutions/ins_br_senado/proposals", params={"limit": 50}).json()["items"]
    authors = [a for p in props for a in p["authors"]]
    assert all(a["person_id"] is None for a in authors if a["kind"] != "member")


def test_snapshot_exports_without_stf_dossier(api, tmp_path):
    assert api.get("/v1/dossies/stf-caso-master").status_code == 404
    export_snapshot(api, tmp_path, datetime(2026, 11, 24, tzinfo=ZoneInfo("UTC")))

    assert json.loads((tmp_path / "dossies/stf-caso-master.json").read_text(encoding="utf-8")) is None
    assert (tmp_path / "meta.json").is_file()


def test_snapshot_exports_frontend_data_and_public_source_excerpts(api, factory, tmp_path, monkeypatch):
    from engine.api import queries

    get_capabilities = queries.capabilities

    def capabilities_with_private_diagnostics(session, institution_id):
        capabilities = get_capabilities(session, institution_id)
        if institution_id != "ins_br_senado":
            return capabilities
        capabilities[0].issues = [
            {"code": "last_run_failed", "message": "internal connection details"},
            {"code": "missing_affiliation", "count": 2},
        ]
        return capabilities

    monkeypatch.setattr(queries, "capabilities", capabilities_with_private_diagnostics)
    with factory() as session:
        load_dossiers(session)
        session.commit()
    now = datetime(2026, 11, 24, 1, 30, tzinfo=ZoneInfo("UTC"))
    export_snapshot(api, tmp_path, now)

    def read(path):
        return json.loads((tmp_path / f"{path}.json").read_text(encoding="utf-8"))

    meta = read("meta")
    assert meta["generated_at"] == now.isoformat()
    assert meta["composition_dates"][-1] == "2026-11-23"
    for day in (*meta["composition_dates"], "2027"):
        assert "seats" in read(f"senado/composicao/{day}")

    proposals = read("institutions/ins_br_senado/proposals")
    assert proposals == api.get("/v1/institutions/ins_br_senado/proposals").json()["items"]
    for row in proposals:
        path = f"entities/{row['id']}"
        for suffix in ("", "/relationships", "/timeline"):
            assert read(path + suffix) == api.get(f"/v1/{path}{suffix}").json()
    proposal = read(f"entities/{proposals[0]['id']}")
    assert proposal["sources"]
    for source in proposal["sources"]:
        path = source["json_path"] or ""
        record = read(f"sources/{source['raw_record_id']}")[path]
        public_record = api.get(f"/v1/sources/{source['raw_record_id']}", params={"path": path}).json()
        assert record["excerpt"] == public_record["excerpt"]
        assert record["response_headers"] == {}
    runs = read("ingestion/ins_br_senado")["runs"]
    assert any(run["status"] == "partial" for run in runs)
    assert all(run["error"] is None and all("example" not in issue for issue in run["issues"]) for run in runs)
    capabilities = read("institutions/ins_br_senado/capabilities")
    assert capabilities[0]["issues"] == [{"code": "last_run_failed"}, {"code": "missing_affiliation", "count": 2}]
    assert read("dossies/stf-caso-master")["dossier"] == "stf-caso-master"


def test_filters_pagination_graph_and_errors(api):
    page = api.get("/v1/institutions/ins_br_senado/proposals", params={"limit": 2, "offset": 1}).json()
    assert len(page["items"]) <= 2 and page["offset"] == 1
    assert api.get("/v1/institutions/ins_br_senado/proposals", params={"q": "zzzz-inexistente"}).json()["total"] == 0
    g = api.get("/v1/institutions/ins_br_senado/graph").json()
    assert g["focus"] == "ins_br_senado" and all(e["kind"] and e["explanation"] for e in g["edges"])
    assert api.get("/v1/institutions/nope").status_code == 404
    assert api.get("/v1/entities/per_missing").status_code == 404
    assert api.get("/v1/institutions/ins_br_senado/members", params={"limit": 9999}).status_code == 422
    status = api.get("/v1/ingestion/status", params={"institution": "ins_br_senado"}).json()
    assert status["runs"] and all(r["status"] in {"succeeded", "partial"} for r in status["runs"])


def test_qualified_proposal_keeps_its_identifier_and_parent_type(factory, api):
    substitute = {
        "id": 9115907, "identificacao": "PL 5631/2026 (Substitutivo-CD)", "tipoDocumento": "Emenda",
        "codigoMateria": 176019, "dataApresentacao": "2026-10-20",
    }

    def proposal_list(request):
        return httpx.Response(200, json=[substitute] if request.url.params["sigla"] == "PL" else [])

    handler, _ = official_sources({
        r"/dadosabertos/processo$": proposal_list,
        r"/dadosabertos/processo/9115907$": httpx.Response(200, json={}),
    })
    [run] = sync_source(factory, SOURCES["ins_br_senado"], ["proposals"], client=make_client(handler))
    assert run["status"] == "succeeded" and run["stats"]["warnings"] == 0

    base = "/v1/institutions/ins_br_senado"
    [proposal] = api.get(f"{base}/proposals", params={"q": "(Substitutivo-CD)", "type_code": "PL"}).json()["items"]
    assert proposal["identifier"] == substitute["identificacao"]
    assert (proposal["type_code"], proposal["type_name"], proposal["number"], proposal["year"]) == (
        "PL", "Emenda", "5631", 2026,
    )
    [pl] = [t for t in api.get(f"{base}/proposal-types").json() if t["type_code"] == "PL"]
    page = api.get(f"{base}/proposals", params={"type_code": "PL"}).json()
    assert pl["type_name"] == "Projeto de Lei Ordinária" and pl["count"] == page["total"] == 4
