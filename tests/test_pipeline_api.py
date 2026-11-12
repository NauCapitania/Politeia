"""End-to-end: recorded official responses -> ingestion -> Postgres -> common v1 API."""

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from engine.db import models as M
from engine.db.session import get_session
from engine.ingestion.sync import sync_source
from engine.registry import bootstrap
from tests.conftest import TEST_DB, make_client, official_sources

SOURCES = {"ins_br_senado": "src_br_senado_dadosabertos", "ins_pe_alepe": "src_pe_alepe_dadosabertos"}


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


def test_institutions_are_separated(factory):
    assert count(factory, M.Mandate, institution_id="ins_br_senado") == 3
    assert count(factory, M.Mandate, institution_id="ins_pe_alepe") == 5
    with factory() as s:
        shared = s.execute(text("""select count(*) from core.mandates a join core.mandates b
            on a.person_id = b.person_id and a.institution_id <> b.institution_id""")).scalar()
    assert shared == 0


def test_raw_evidence_preserved_with_hash(factory):
    with factory() as s:
        rows = s.execute(select(M.RawRecord.content_sha256, M.RawRecord.payload, M.RawRecord.payload_text)).all()
    assert rows and all(len(h) == 64 and (p is not None or t) for h, p, t in rows)


def test_common_contract_for_both_institutions(api):
    insts = api.get("/v1/institutions").json()
    assert {i["id"] for i in insts} == set(SOURCES)
    shapes = []
    for iid in SOURCES:
        m = api.get(f"/v1/institutions/{iid}/members").json()
        p = api.get(f"/v1/institutions/{iid}/proposals").json()
        assert m["total"] > 0 and p["total"] > 0
        shapes.append((set(m["items"][0]), set(p["items"][0])))
    assert shapes[0] == shapes[1]


def test_composition_uses_seat_count_and_flags_unverified(api):
    sen = api.get("/v1/institutions/ins_br_senado/composition").json()
    assert sen["seat_count"] == 81 and len(sen["seats"]) == 81 and sen["observed_members"] == 3
    assert sum(s["state"] == "occupied" for s in sen["seats"]) == 3
    pe = api.get("/v1/institutions/ins_pe_alepe/composition").json()
    assert pe["seat_count"] is None and len(pe["seats"]) == 5 and pe["discrepancy"]
    assert sum(g["count"] for g in pe["groups"]) == pe["observed_members"]


def test_capabilities_reflect_real_ingestion(api):
    sen = {c["capability"]: c for c in api.get("/v1/institutions/ins_br_senado/capabilities").json()}
    pe = {c["capability"]: c for c in api.get("/v1/institutions/ins_pe_alepe/capabilities").json()}
    # The members run carried affiliation warnings, so the run (and capability) is honestly partial.
    assert sen["members"]["status"] in {"available", "partial"} and sen["members"]["record_count"] == 3
    # Two of the three recorded senators have no affiliation response: history is partial, not available.
    assert sen["party_history"]["status"] == "partial"
    assert pe["party_history"]["status"] == "unavailable_in_source"
    assert pe["proposal_events"]["status"] == "unavailable_in_source"
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
    props = api.get("/v1/institutions/ins_pe_alepe/proposals", params={"limit": 50}).json()["items"]
    authors = [a for p in props for a in p["authors"]]
    assert all(a["person_id"] is None for a in authors if a["kind"] != "member")
    linked = [a for a in authors if a["person_id"]]
    assert linked and all(a["resolution"] == "name_match" for a in linked)


def test_filters_pagination_graph_and_errors(api):
    page = api.get("/v1/institutions/ins_pe_alepe/proposals", params={"limit": 2, "offset": 1}).json()
    assert len(page["items"]) <= 2 and page["offset"] == 1
    assert api.get("/v1/institutions/ins_pe_alepe/proposals", params={"q": "zzzz-inexistente"}).json()["total"] == 0
    g = api.get("/v1/institutions/ins_br_senado/graph").json()
    assert g["focus"] == "ins_br_senado" and all(e["kind"] and e["explanation"] for e in g["edges"])
    assert api.get("/v1/institutions/nope").status_code == 404
    assert api.get("/v1/entities/per_missing").status_code == 404
    assert api.get("/v1/institutions/ins_pe_alepe/members", params={"limit": 9999}).status_code == 422
    status = api.get("/v1/ingestion/status", params={"institution": "ins_pe_alepe"}).json()
    assert status["runs"] and all(r["status"] in {"succeeded", "partial"} for r in status["runs"])
