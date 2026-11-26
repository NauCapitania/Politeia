"""End-to-end: recorded official responses -> ingestion -> Postgres -> common v1 API."""

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from connectors.base.protocol import Batch
from connectors.news.connector import NewsConnector
from connectors.senate.connector import SenateConnector
from engine.capabilities.compute import recompute_capabilities
from engine.db import models as M
from engine.db.session import get_session
from engine.dossiers import load_dossiers
from engine.ingestion.replay import replay_proposals
from engine.ingestion.sync import Persistor, store_raw, sync_source
from engine.registry import bootstrap, build_connector
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


def test_registered_institutions(api):
    insts = api.get("/v1/institutions").json()
    assert {i["id"] for i in insts} == set(SOURCES) | {"ins_br_executivo", "ins_br_camara"}
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
    assert set(json.loads((tmp_path / "ontologia.json").read_text(encoding="utf-8"))) >= {"powers", "competences"}
    assert (tmp_path / "ontologia/ligacoes/ins_br_senado.json").is_file()


def test_snapshot_exports_frontend_data_and_public_source_excerpts(api, factory, tmp_path, monkeypatch):
    from engine.api import queries

    get_capabilities = queries.capabilities

    def capabilities_with_private_diagnostics(session, institution_id):
        capabilities = get_capabilities(session, institution_id)
        if not capabilities:
            return capabilities
        capabilities[0].issues = [
            {"code": "last_run_failed", "message": "internal connection details"},
            {"code": "missing_affiliation", "count": 2},
        ]
        return capabilities

    monkeypatch.setattr(queries, "capabilities", capabilities_with_private_diagnostics)
    with factory() as session:
        load_dossiers(session)
        source = session.get(M.SourceSystem, "src_noticias_rss")
        feed = next(f for f in source.config["feeds"] if f["id"] == "metropoles")
        with make_client(lambda _: httpx.Response(200, text="""<rss><channel>
            <item><link>https://www.metropoles.com/brasil/ultima-hora</link><category>Política</category></item>
            <item><link>https://www.metropoles.com/brasil/sao-paulo</link><category>Brasil</category></item>
            <item><link>https://www.metropoles.com/brasil/patrocinio</link><category>Esportes</category></item>
        </channel></rss>"""), hosts=("www.metropoles.com",)) as client:
            connector = NewsConnector({"feeds": [feed]}, client)
            batch = connector.fetch("news")
        run = M.IngestionRun(institution_id=source.institution_id, source_system_id=source.id,
                             connector=connector.id, connector_version=connector.version,
                             scope=["news"], status="succeeded")
        session.add(run)
        session.flush()
        [raw_id] = store_raw(session, run, source, batch)
        session.add_all(M.NewsItem(id=id_, source_system_id="src_noticias_rss", feed="metropoles",
                                   outlet="Metrópoles", url=f"https://www.metropoles.com/{path}",
                                   title=title, published_at=datetime(2026, 11, day, tzinfo=UTC), topics=topics,
                                   raw_record_id=raw_id)
                        for id_, path, title, day, topics in (
                            ("nws_esporte", "esportes/futebol/real-madrid",
                             "Real Madrid deve igualar salário de Bellingham ao de Vini Jr. em renovação", 24, []),
                            ("nws_tv", "entretenimento/televisao/reality-show",
                             "Série sobre o Senado ganha nova temporada", 23, ["senado", "politica"]),
                            ("nws_justica", "poder-justica/caso-ninho-do-urubu",
                             "MP do Rio tenta reverter absolvição de réus do caso Ninho do Urubu", 23, []),
                            ("nws_senado", "brasil/relatorio", "Senado discute novo relatório", 22, ["senado"]),
                            ("nws_secao", "brasil/politica-brasil/erika-hilton",
                             "Erika Hilton recebe ameaça de morte", 21, []),
                            ("nws_categoria", "brasil/ultima-hora", "Notícia de última hora", 20, []),
                            ("nws_brasil", "brasil/sao-paulo", "Notícia de São Paulo", 19, []),
                            ("nws_patrocinio", "brasil/patrocinio",
                             "Time renova patrocínio com o BRB", 24, ["caso_master"]),
                        ))
        session.add(M.NewsItem(id="nws_master", source_system_id=source.id, feed="gnews_caso_master",
                               outlet="Exemplo", url="https://news.google.com/rss/articles/abc",
                               title="Justiça mantém prisão de Vorcaro",
                               published_at=datetime(2026, 11, 18, tzinfo=UTC), topics=["caso_master"]))
        person_id = session.scalar(select(M.Mandate.person_id).where(M.Mandate.institution_id == "ins_br_senado"))
        session.flush()
        session.add(M.NewsMention(news_item_id="nws_senado", entity_kind="person", entity_id=person_id,
                                  matched_text="Senador de teste", method="exact_name", confidence="high"))
        session.commit()
    now = datetime(2026, 11, 24, 1, 30, tzinfo=ZoneInfo("UTC"))
    export_snapshot(api, tmp_path, now)

    def read(path):
        return json.loads((tmp_path / f"{path}.json").read_text(encoding="utf-8"))

    assert [n["id"] for n in api.get("/v1/noticias", params={"limit": 1}).json()] == ["nws_senado"]
    assert [n["id"] for n in read("noticias")] == ["nws_senado", "nws_secao", "nws_categoria", "nws_master"]
    assert [n["id"] for n in read("noticias/senado")] == ["nws_senado"]
    assert read("noticias/senado")[0]["mentions"][0]["id"] == person_id
    assert "news" not in read(f"senadores/{person_id}")
    assert "news" not in api.get(f"/v1/senadores/{person_id}").json()
    assert [n["id"] for n in read("noticias/caso_master")] == ["nws_master"]
    with factory() as session:
        assert session.get(M.NewsItem, "nws_esporte") is not None

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
    parties = read("dossies/partidos")
    assert parties == api.get("/v1/dossies/partidos").json()
    assert {"party", "event", "funding", "comparison", "analysis", "site"} <= parties["items"].keys()


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


def test_official_proposal_author_is_linked_without_a_current_mandate(factory, api):
    proposal_id = 9116010
    proposal = {"id": proposal_id, "identificacao": "PL 5522/2026"}
    detail = {"autoriaIniciativa": [
        {"siglaTipo": "SENADOR", "codigoParlamentar": 6359, "autor": "Lourdinha Pereira"},
        {"siglaTipo": "SENADOR", "autor": "Outro autor"},
    ]}
    handler, _ = official_sources({
        r"/dadosabertos/processo$": lambda r: httpx.Response(
            200, json=[proposal] if r.url.params["sigla"] == "PL" else []),
        rf"/dadosabertos/processo/{proposal_id}$": httpx.Response(200, json=detail),
    })
    [run] = sync_source(factory, SOURCES["ins_br_senado"], ["proposals"], client=make_client(handler))
    assert run["status"] == "succeeded" and run["stats"]["authors_linked"] == 1

    base = "/v1/institutions/ins_br_senado"
    [item] = api.get(f"{base}/proposals", params={"q": proposal["identificacao"]}).json()["items"]
    official, unidentified = item["authors"]
    assert official["resolution"] == "official_id"
    assert unidentified["person_id"] is None and unidentified["resolution"] == "unresolved"
    person_id = official["person_id"]
    person = api.get(f"/v1/entities/{person_id}").json()
    assert any(str(proposal_id) in source["url"] for source in person["sources"])
    assert count(factory, M.Mandate, person_id=person_id) == 0


def test_total_scope_outage_updates_coverage_before_next_scope(factory, api):
    base = "/v1/institutions/ins_br_senado"
    original, _ = official_sources()

    def handler(request):
        if request.url.path.endswith("/votacao"):
            return httpx.Response(503)
        if request.url.path.endswith("/senador/lista/atual"):
            caps = {c["capability"]: c for c in api.get(f"{base}/capabilities").json()}
            assert caps["votes"]["status"] == "ingestion_failed"
            assert caps["votes"]["last_success_at"] is None
        return original(request)

    failed, members = sync_source(factory, SOURCES["ins_br_senado"], ["votes", "members"], client=make_client(handler))
    assert failed["status"] == "failed"
    assert failed["error"] == "no source responses; normalized data left unchanged"
    assert members["status"] == "partial"
    runs = api.get("/v1/ingestion/status", params={"institution": "ins_br_senado"}).json()["runs"]
    run = next(r for r in runs if r["id"] == failed["run_id"])
    assert run["stats"]["raw_records"] == 0 and run["stats"]["warnings"] > 0
    assert run["issues"][0]["code"] == "votes_unavailable"


def test_replay_proposals_reuses_original_evidence_without_claiming_a_fresh_fetch(factory, api, monkeypatch):
    source_id = SOURCES["ins_br_senado"]
    seen = datetime(2026, 1, 5, 12, tzinfo=UTC)
    finished = datetime.now(UTC)
    proposals = [
        {"id": 9111975, "identificacao": "PL 5522/2026"},
        {"id": 9125400, "identificacao": "PL 3220/2019 (Substitutivo-CD)"},
    ]
    handler, _ = official_sources({
        r"/dadosabertos/processo$": lambda req: httpx.Response(
            200, json=proposals if req.url.params["sigla"] == "PL" else []),
        r"/dadosabertos/processo/(9111975|9125400)$": httpx.Response(200, json={"autoriaIniciativa": [
            {"siglaTipo": "SENADOR", "codigoParlamentar": 6459, "autor": "Autora fora do exercício"},
        ]}),
    })
    with factory() as s:
        source = s.get(M.SourceSystem, source_id)
        connector = build_connector(source, make_client(handler))
        batch = connector.fetch("proposals")
        for raw in batch.raw:
            raw.response = replace(raw.response, retrieved_at=seen)
        run = M.IngestionRun(institution_id=source.institution_id, source_system_id=source.id, connector=connector.id,
                             connector_version=connector.version, scope=["proposals"], status="partial",
                             started_at=finished, finished_at=finished, stats={"raw_records": len(batch.raw)})
        s.add(run)
        s.flush()
        raw_ids = store_raw(s, run, source, batch)
        s.commit()
        run_id = run.id
        raws = s.scalars(select(M.RawRecord).where(M.RawRecord.id.in_(raw_ids))).all()
        raw_history = {r.id: (r.first_run_id, r.last_run_id, r.retrieved_at, r.last_seen_at, r.content_sha256)
                       for r in raws}
        recompute_capabilities(s, source.institution_id)
        s.commit()
    before = api.get("/v1/institutions/ins_br_senado").json()["last_ingested_at"]

    def forbidden(*args):
        pytest.fail("offline replay contacted the source")

    monkeypatch.setattr(SenateConnector, "fetch", forbidden)
    targeted = replay_proposals(factory, proposal_ids=[9125400])
    assert targeted["status"] == "succeeded" and targeted["stats"]["proposals"] == 1
    assert count(factory, M.Proposal, source_id="9111975") == 0
    replay = replay_proposals(factory, run_id=run_id)
    assert replay["status"] == "succeeded"
    assert replay["stats"]["mode"] == "replay"
    assert replay["stats"]["source_run_id"] == str(run_id) and replay["stats"]["requests"] == 0
    assert replay["stats"]["proposals"] == 2 and count(factory, M.Proposal, source_id="9125400") == 1

    with factory() as s:
        proposal = s.scalar(select(M.Proposal).where(M.Proposal.source_id == "9125400"))
        assert proposal.first_observed_at == proposal.last_observed_at == seen
        assert proposal.identifier == proposals[1]["identificacao"]
        author = s.scalar(select(M.ProposalAuthor).where(M.ProposalAuthor.proposal_id == proposal.id))
        assert author.resolution == "official_id"
        person = s.get(M.Person, author.person_id)
        assert person.first_observed_at == person.last_observed_at == seen
        evidence = s.scalar(select(M.EntityEvidence).where(
            M.EntityEvidence.entity_id == proposal.id, M.EntityEvidence.json_path == "$[1]"))
        assert evidence.raw_record_id in raw_ids
        raws = s.scalars(select(M.RawRecord).where(M.RawRecord.id.in_(raw_ids))).all()
        assert {r.id: (r.first_run_id, r.last_run_id, r.retrieved_at, r.last_seen_at, r.content_sha256)
                for r in raws} == raw_history
        assert s.get(M.IngestionRun, UUID(replay["run_id"])).stats["mode"] == "replay"
        assert s.get(M.CapabilityState, ("ins_br_senado", "proposals")).last_success_at == finished

    status = api.get("/v1/ingestion/status", params={"institution": "ins_br_senado"}).json()
    assert status["runs"][0]["stats"]["mode"] == "replay"
    assert api.get("/v1/institutions/ins_br_senado").json()["last_ingested_at"] == before

    with factory() as s:
        proposal = s.scalar(select(M.Proposal).where(M.Proposal.source_id == "9125400"))
        author = s.scalar(select(M.ProposalAuthor).where(M.ProposalAuthor.proposal_id == proposal.id))
        person_id = author.person_id
        prop_id, author_id = proposal.id, author.id
        proposal.status = "Old normalization of the same observation"
        proposal.last_observed_at = finished
        s.commit()

    same_run = replay_proposals(factory, run_id=run_id)
    assert same_run["status"] == "succeeded"
    assert same_run["stats"].get("proposals_replay_skipped_newer", 0) == 0
    with factory() as s:
        assert (s.get(M.Proposal, prop_id).status, s.get(M.Proposal, prop_id).last_observed_at) == (None, finished)

    persist = Persistor.persist_proposals
    with factory() as s:
        for proposal in s.scalars(select(M.Proposal).where(M.Proposal.source_id.in_(["9111975", "9125400"]))):
            proposal.status = "Before interrupted replay"
        s.commit()

    def fail_on_second_proposal(persistor, batch, evidence):
        assert len(batch.proposals) == 1
        persist(persistor, batch, evidence)
        if batch.proposals[0].source_id == "9125400":
            raise RuntimeError("test replay persistence failure")

    with monkeypatch.context() as patch:
        patch.setattr(Persistor, "persist_proposals", fail_on_second_proposal)
        with pytest.raises(RuntimeError, match="test replay persistence failure"):
            replay_proposals(factory, run_id=run_id)
    with factory() as s:
        assert dict(s.execute(select(M.Proposal.source_id, M.Proposal.status).where(
            M.Proposal.source_id.in_(["9111975", "9125400"]))).all()) == {
                "9111975": None, "9125400": "Before interrupted replay",
            }
        failed = s.scalar(select(M.IngestionRun).where(M.IngestionRun.status == "failed",
                          M.IngestionRun.stats["mode"].as_string() == "replay"))
        assert failed.stats["proposals"] == 1 and failed.finished_at is not None

    def after_live_update(persistor, batch, evidence):
        with factory() as s:
            proposal = s.get(M.Proposal, prop_id)
            older = batch.raw[batch.proposals[0].ref.raw]
            changed = [item | {"situacaoAtual": "Newer live status"} for item in older.json()]
            response = replace(older.response, retrieved_at=finished, content=json.dumps(changed).encode())
            newer_batch = Batch(scope="proposals", raw=[replace(older, response=response, parsed=changed)])
            source = s.get(M.SourceSystem, source_id)
            newer_run = M.IngestionRun(institution_id=source.institution_id, source_system_id=source_id,
                                       connector=source.connector, connector_version="test", scope=["proposals"],
                                       status="succeeded", finished_at=finished)
            s.add(newer_run)
            s.flush()
            [newer_id] = store_raw(s, newer_run, source, newer_batch)
            s.add(M.EntityEvidence(entity_kind="proposal", entity_id=prop_id, raw_record_id=newer_id,
                                   json_path="$[1]"))
            proposal.status = "Newer live status"
            proposal.last_observed_at = finished
            author = s.get(M.ProposalAuthor, author_id)
            author.person_id = None
            author.resolution = "unresolved"
            author.attributes = author.attributes | {"unresolved_reason": "person_not_ingested"}
            s.commit()
        persist(persistor, batch, evidence)

    monkeypatch.setattr(Persistor, "persist_proposals", after_live_update)
    retry = replay_proposals(factory, proposal_ids=[9125400])
    assert retry["stats"]["proposals_replay_skipped_newer"] == retry["stats"]["authors_linked"] == 1
    with factory() as s:
        proposal = s.get(M.Proposal, prop_id)
        author = s.get(M.ProposalAuthor, author_id)
        assert (proposal.status, proposal.last_observed_at) == ("Newer live status", finished)
        assert (author.person_id, author.resolution) == (person_id, "official_id")
