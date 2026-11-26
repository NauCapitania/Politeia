"""Ontology projection: curated map + ingested tables + dossiers -> state/process/behavior tables and API."""

import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from engine.db import models as M
from engine.db.session import get_session
from engine.dossiers import load_dossiers
from engine.ingestion.sync import sync_source
from engine.ontology.load import ONTOLOGY_FILE, OntologyError, load_ontology, read_ontology
from engine.registry import bootstrap
from tests.conftest import TEST_DB, make_client, official_sources

SOURCE_TABLES = (M.Person, M.Mandate, M.PartyMembership, M.Committee, M.CommitteeMembership, M.DossierItem,
                 M.Claim, M.NewsItem, M.NewsMention, M.RawRecord)


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
    handler, _ = official_sources()
    sync_source(f, "src_br_senado_dadosabertos", ["members"], client=make_client(handler))
    with f() as s:
        load_dossiers(s)
        s.add(M.NewsItem(id="nws_pgr", source_system_id="src_noticias_rss", feed="g1_politica", outlet="g1",
                         url="https://g1.globo.com/politica/pgr-relatorios", title="PGR analisa relatórios da PF",
                         topics=["pgr", "caso_master"]))
        s.commit()
        s.info["stats"] = load_ontology(s)
        s.commit()
    yield f
    engine.dispose()


def count(f, model, **where):
    with f() as s:
        return s.scalar(select(func.count()).select_from(model).filter_by(**where))


@pytest.fixture(scope="module")
def api(factory):
    from engine.api.app import app

    def session():
        with factory() as s:
            yield s

    app.dependency_overrides[get_session] = session
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_rebuild_is_idempotent_and_leaves_source_tables_alone(factory):
    with factory() as s:
        first = load_ontology(s)
        s.commit()
    before = {m: count(factory, m) for m in SOURCE_TABLES}
    with factory() as s:
        second = load_ontology(s)
        s.commit()
    assert first == second
    assert {m: count(factory, m) for m in SOURCE_TABLES} == before


def test_every_competence_office_and_holding_has_a_source(factory):
    with factory() as s:
        for model, table in ((M.Competence, "state.competences"), (M.Office, "state.offices"),
                             (M.Body, "state.bodies"), (M.OfficeHolding, "core.office_holdings"),
                             (M.Proceeding, "process.proceedings")):
            ids = set(s.scalars(select(model.id)))
            cited = set(s.scalars(select(M.FactSource.row_id).where(M.FactSource.table_name == table)))
            assert ids and ids <= cited, table
        assert all(c.legal_basis_id for c in s.scalars(select(M.Competence)))


def test_current_holders_come_from_mandates_and_dossiers(factory):
    with factory() as s:
        senators = s.scalar(select(func.count()).select_from(M.Mandate).where(
            M.Mandate.institution_id == "ins_br_senado", M.Mandate.status == "in_exercise"))
        held = dict(s.execute(select(M.OfficeHolding.office_id, func.count())
                               .group_by(M.OfficeHolding.office_id)).all())
        stf = s.scalars(select(M.OfficeHolding).where(M.OfficeHolding.office_id == "off_ministro_stf")).all()
        office = s.get(M.Office, "off_ministro_stf")
    assert held["off_senador"] == senators
    assert len(stf) == 10 and office.seats == 11
    assert all(h.nominated_by for h in stf)
    assert held["off_pres_republica"] == held["off_pres_stf"] == held["off_pgr"] == 1


def test_master_and_2027_are_proceedings_on_the_map(factory):
    with factory() as s:
        pgr = s.get(M.Proceeding, "prc_master_relatorios_pf")
        deadline = s.get(M.Deadline, "ddl_prc_master_relatorios_pf")
        cited = s.scalars(select(M.Participant).where(M.Participant.proceeding_id == pgr.id,
                                                      M.Participant.role.like("citado_%"))).all()
        race = s.get(M.Proceeding, "prc_presidencia_senado_2027")
        estimates = s.scalars(select(M.Estimate)).all()
        links = s.scalars(select(M.NewsLink).where(M.NewsLink.news_item_id == "nws_pgr")).all()
    assert pgr.competence_id == "cmp_pgr_denuncia_ministro_stf" and deadline.basis == "politeia_estimate"
    assert cited and all(p.epistemic_status == "press_report" for p in cited)
    assert race.competence_id == "cmp_senadores_elegem_presidente"
    assert estimates and {e.label for e in estimates} == {"inferência"}
    with factory() as s:
        month_only = s.scalars(select(M.Step).where(M.Step.date_label == "2026-01")).all()
        actors = s.scalars(select(M.Participant).where(M.Participant.role == "ator_processual")).all()
    assert month_only and all(st.happened_on is None for st in month_only)
    assert next(a for a in actors if a.label == "Presidente do STF").epistemic_status == "press_report"
    assert {(n.target_kind, n.target_id) for n in links} == {("analysis", "ana_caso_master"),
                                                             ("proceeding", "prc_master_relatorios_pf")}


def test_api_exposes_the_map(api):
    d = api.get("/v1/ontologia").json()
    assert {p["id"] for p in d["powers"] if p["constitutional"]} == {
        "pow_legislativo", "pow_executivo", "pow_judiciario",
    }
    assert next(p for p in d["powers"] if p["id"] == "grp_funcoes_justica")["constitutional"] is False
    assert not any(p["id"] == "pow_controle" for p in d["powers"])
    by_id = {b["id"]: b for b in d["bodies"]}
    assert by_id["bod_tcu"]["power_id"] == "pow_legislativo"
    assert by_id["bod_tcu"]["parent_id"] is None
    assert all(by_id[b]["power_id"] == "pow_executivo" for b in ("bod_pf", "bod_cgu", "bod_agu"))
    assert all(by_id[b]["power_id"] == "grp_funcoes_justica" for b in ("bod_pgr", "bod_dpu"))
    judiciary = {b["id"] for b in d["bodies"] if b["power_id"] == "pow_judiciario"}
    assert {"bod_stf", "bod_stj", "bod_tse", "bod_tst", "bod_stm", "bod_cnj"} <= judiciary
    assert all(b["legal_basis_id"] for b in d["bodies"] if b["id"] in judiciary)
    # No invented holders or administrative subordination of other courts to the STF.
    assert all(b["parent_id"] is None for b in d["bodies"] if b["id"] in judiciary)
    assert next(b for b in d["bodies"] if b["id"] == "bod_stj")["holders"] == 0
    stf = next(o for o in d["offices"] if o["id"] == "off_ministro_stf")
    assert stf["holders"] == 10 and stf["vacancies"] == 1
    assert next(b for b in d["bodies"] if b["id"] == "bod_stf")["holders"] == 10
    flow = sorted((c["flow_order"], c["verb"]) for c in d["competences"] if c["flow"] == "nomeacao_ministro_stf")
    assert [verb for _, verb in flow][-1] == "Nomear"
    assert all(h["office_id"] != "off_membro_comissao" for h in d["holdings"])
    master = next(p for p in d["proceedings"] if p["id"] == "prc_master_relatorios_pf")
    assert master["deadlines"][0]["due_on"] == "2026-12-08" and master["news"][0]["url"].endswith("pgr-relatorios")
    assert all(st["sources"] for st in master["steps"] if st["status"] == "done")
    race = next(a for a in d["analyses"] if a["id"] == "ana_presidencia_2027")
    assert all(e["sources"] for e in race["estimates"])
    links = api.get("/v1/ontologia/ligacoes/ins_br_senado").json()
    assert links["kind"] == "vote_agreement" and isinstance(links["links"], list)
    assert api.get("/v1/ontologia/ligacoes/ins_nao_existe").status_code == 404


def test_curated_file_rejects_competence_without_legal_basis(tmp_path):
    doc = json.loads(ONTOLOGY_FILE.read_text(encoding="utf-8"))
    doc["competences"][0]["legal_basis"] = "lei_inexistente"
    bad = tmp_path / "uniao.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(OntologyError, match="legal_basis"):
        read_ontology(bad)
    assert read_ontology()["competences"]
