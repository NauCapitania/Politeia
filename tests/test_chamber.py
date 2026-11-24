"""Câmara dos Deputados: recorded official responses -> connector -> Postgres -> v1 API."""

import os
import subprocess
import sys
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from connectors.chamber.connector import PERSON, ChamberConnector, legislature_end
from engine.db import models as M
from engine.db.session import get_session
from engine.ingestion.sync import sync_source
from engine.registry import bootstrap, load_packs
from tests.conftest import TEST_DB, chamber_sources, make_client

SOURCE = "src_br_camara_dadosabertos"
HOSTS = ("dadosabertos.camara.leg.br",)
FIXED_TODAY = date(2025, 11, 30)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("connectors.chamber.connector.today", lambda: FIXED_TODAY)


def connector(overrides=None):
    handler, calls = chamber_sources(overrides)
    src = load_packs()["ins_br_camara"]["sources"][0]
    cfg = dict(src["config"], base_url=src["base_url"], votes_window_days=20)
    return ChamberConnector(cfg, make_client(handler, hosts=HOSTS)), calls


def test_pack_is_registered_with_official_seat_count():
    pack = load_packs()["ins_br_camara"]
    assert pack["institution"]["seat_count"] == 513
    assert pack["sources"][0]["allowed_hosts"] == list(HOSTS)
    assert legislature_end(57) == date(2027, 1, 31)


def test_members_use_official_ids_and_record_party_switches():
    c, calls = connector()
    b = c.run("members")
    assert not b.has_errors and b.complete_member_list
    names = {p.identifier.value: p for p in b.persons}
    assert names["204379"].name == "Acácio Favacho" and names["204379"].gender == "male"
    assert names["204379"].profile_url == "https://www.camara.leg.br/deputados/204379"
    m = next(m for m in b.mandates if m.person.value == "204379")
    assert m.identifier.value == "57:204379" and m.represented_unit == "AP" and m.role_type == "deputy"
    assert m.start_date == date(2023, 2, 1) and m.end_date == date(2027, 1, 31)
    history = [(x.party.value, x.valid_from, x.valid_to) for x in b.memberships
               if x.person.value == "204379" and x.basis == "chamber_record"]
    assert history[:2] == [("PROS", date(2019, 2, 1), date(2022, 4, 11)), ("MDB", date(2022, 4, 11), None)]
    assert any(x.basis == "current_listing" and x.party.value == "MDB" for x in b.memberships)
    assert any(u.endswith("/deputados/204379/historico") for u in calls)


def test_schema_change_is_an_error_not_silent_data():
    c, _ = connector({r"/api/v2/deputados$": httpx.Response(200, json={"erro": "x"})})
    b = c.run("members")
    assert b.has_errors and not b.persons and not b.complete_member_list


def test_proposals_authors_and_events():
    c, _ = connector()
    b = c.run("proposals")
    p = next(p for p in b.proposals if p.source_id == "2576168")
    assert p.identifier == "PEC 38/2025" and p.type_name == "Proposta de Emenda à Constituição"
    assert p.official_url == "https://www.camara.leg.br/propostas-legislativas/2576168"
    assert p.status and p.in_progress is True
    assert p.authors and all(a.person.scheme == PERSON for a in p.authors if a.person)
    assert p.events and all(e.source_event_id.startswith("2576168:") for e in p.events)


def test_votes_keep_symbolic_and_nominal_ballots():
    c, _ = connector()
    b = c.run("votes")
    ev = {e.source_id: e for e in b.vote_events}
    nominal, symbolic = ev["2524984-37"], ev["2500526-52"]
    assert nominal.attributes["nominal"] and {v.vote_label for v in nominal.votes} == {"Sim", "Não"}
    assert nominal.totals["totalVotosSim"] == 1 and nominal.totals["totalVotosNao"] == 1
    assert not symbolic.votes and symbolic.result == "aprovado" and symbolic.matter_code == "2500526"


def test_committees_mark_chair_and_substitutes():
    c, _ = connector()
    b = c.run("committees")
    ccjc = next(x for x in b.committees if x.source_code == "2003")
    assert ccjc.scheme == "camara.orgao" and ccjc.abbreviation == "CCJC"
    roles = {m.name: (m.seat_kind, m.role) for m in ccjc.members}
    assert roles["Leur Lomanto Júnior"] == ("titular", "PRESIDENTE")
    assert roles["Rodrigo de Castro"] == ("titular", "VICE-PRESIDENTE")
    assert roles["Luiz Carlos Busato"] == ("suplente", None)


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
    mp = pytest.MonkeyPatch()
    mp.setattr("connectors.chamber.connector.today", lambda: FIXED_TODAY)
    for _ in range(2):  # second run proves idempotency
        handler, _ = chamber_sources()
        sync_source(f, SOURCE, ["members", "proposals", "votes", "committees"],
                    client=make_client(handler, hosts=HOSTS))
    mp.undo()
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


def test_pipeline_persists_chamber_through_generic_models(factory):
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(M.Mandate).filter_by(institution_id="ins_br_camara")) == 2
        assert s.scalar(select(func.count()).select_from(M.Committee).filter_by(institution_id="ins_br_camara")) == 1
        votes = s.scalars(select(M.VoteEvent).filter_by(institution_id="ins_br_camara")).all()
        assert len(votes) == 2


def test_chamber_api_routes(api):
    comp = api.get("/v1/institutions/ins_br_camara/composition").json()
    assert comp["seat_count"] == 513 and comp["observed_members"] == 2
    votes = api.get("/v1/camara/votacoes").json()
    nominal = next(v for v in votes if v["nominal"])
    detail = api.get(f"/v1/camara/votacoes/{nominal['id']}").json()
    assert {v["label"] for v in detail["votes"]} == {"Sim", "Não"}
    assert api.get("/v1/camara/votacoes", params={"nominal": "true"}).json() == [nominal]
    committees = api.get("/v1/camara/comissoes").json()
    assert committees[0]["abbreviation"] == "CCJC" and committees[0]["chair"] == "Leur Lomanto Júnior"
    assert api.get(f"/v1/camara/comissoes/{committees[0]['id']}").json()["members"]
    trocas = api.get("/v1/camara/trocas", params={"desde": "2019-01-01"}).json()
    assert {"name": "Acácio Favacho", "from": "PROS", "to": "MDB", "date": "2022-04-11"}.items() <= trocas[0].items()
    senate_votes = api.get("/v1/votacoes").json()
    assert all(v["id"] not in {x["id"] for x in votes} for v in senate_votes)
