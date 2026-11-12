import httpx

from connectors.alepe.connector import AlepeConnector
from connectors.base.protocol import normalize_name
from engine.registry import load_packs
from tests.conftest import make_client, official_sources


def _connector(cls, pack: str, overrides=None):
    handler, calls = official_sources(overrides)
    src = load_packs()[pack]["sources"][0]
    return cls(dict(src["config"], base_url=src["base_url"]), make_client(handler)), calls


def senate(overrides=None):
    from connectors.senate.connector import SenateConnector
    return _connector(SenateConnector, "ins_br_senado", overrides)


def test_senate_members_keep_official_ids_mandates_and_party_history():
    c, _ = senate()
    b = c.run("members")
    assert not b.has_errors and b.complete_member_list
    assert {p.identifier.scheme for p in b.persons} == {"senado.parlamentar"}
    assert {p.identifier.value for p in b.persons} == {"5672", "5982", "6358"}
    assert all(m.start_date and m.represented_unit for m in b.mandates)
    assert {m.participation for m in b.mandates} >= {"holder", "substitute_in_exercise"}
    history = [m for m in b.memberships if m.person.value == "5672" and m.basis == "affiliation_history"]
    assert history and any(m.valid_to for m in history)
    current = [m for m in b.memberships if m.is_current and m.basis == "current_listing"]
    assert len(current) == 3


def test_senate_failed_affiliation_request_is_a_warning_not_a_crash():
    c, _ = senate()
    b = c.run("members")
    assert any(i.code == "affiliations_unavailable" and i.severity == "warning" for i in b.issues)
    assert len(b.persons) == 3


def test_senate_proposal_parsing_authors_and_events():
    c, _ = senate()
    b = c.run("proposals")
    assert b.proposals, b.issues
    p = b.proposals[0]
    assert p.type_code and p.number and p.year and p.official_url.startswith("https://www25.senado.leg.br/")
    assert any(a.resolution == "official_id" and a.person.scheme == "senado.parlamentar" for a in p.authors)
    assert p.events and all(e.source_event_id for e in p.events)


def test_senate_schema_change_is_reported_not_guessed():
    c, _ = senate({r"/dadosabertos/senador/lista/atual$": httpx.Response(200, json={"Unexpected": {}})})
    b = c.run("members")
    assert b.has_errors and not b.persons and not b.complete_member_list


def test_alepe_members_use_explicit_name_derived_identity():
    c, _ = _connector(AlepeConnector, "ins_pe_alepe")
    b = c.run("members")
    assert len(b.persons) == 5 and b.complete_member_list
    assert all(p.identifier.quality == "name-derived" for p in b.persons)
    assert all(m.start_date is None and m.attributes.get("dates_available") is False for m in b.mandates)
    assert all(m.basis == "current_listing" for m in b.memberships)


def test_alepe_proposals_from_xml_with_unresolved_external_authors():
    c, _ = _connector(AlepeConnector, "ins_pe_alepe")
    b = c.run("proposals")
    assert len(b.proposals) == 5
    assert {p.type_code for p in b.proposals} <= {"PLO", "PLC", "PR", "PEC", "LDO", "LOA", "PPA"}
    authors = [a for p in b.proposals for a in p.authors]
    ext = [a for a in authors if a.kind != "member"]
    assert ext and all(a.person is None and a.resolution == "unresolved" for a in ext)
    members = [a for a in authors if a.kind == "member"]
    assert all(a.resolution == "name_match" and a.epistemic_status == "extracted" for a in members)
    assert not any(p.events for p in b.proposals)  # source publishes no procedural history


def test_alepe_malformed_xml_and_missing_fields():
    bad = httpx.Response(200, content=b"<projetos><projeto", headers={"content-type": "application/xml"})
    c, _ = _connector(AlepeConnector, "ins_pe_alepe", {r"/api/v1/proposicoes/projetos/$": bad})
    assert c.run("proposals").has_errors
    partial = httpx.Response(200, content=b'<projetos><projeto numero="1" ano="2026"/></projetos>',
                             headers={"content-type": "application/xml"})
    c, _ = _connector(AlepeConnector, "ins_pe_alepe", {r"/api/v1/proposicoes/projetos/$": partial})
    b = c.run("proposals")
    assert not b.proposals and any(i.code == "missing_field" for i in b.issues)


def test_duplicate_members_are_validation_errors():
    dup = httpx.Response(200, json=[{"nomeParlamentar": "Ana Silva", "partido": "PT"},
                                    {"nomeParlamentar": "ANA  SILVA", "partido": "PT"}])
    c, _ = _connector(AlepeConnector, "ins_pe_alepe", {r"/api/v1/parlamentares/$": dup})
    b = c.run("members")
    assert any(i.code == "duplicate_person" for i in b.issues) and b.has_errors


def test_normalize_name_is_accent_and_case_insensitive():
    assert normalize_name("  João  PAULO ") == normalize_name("joao paulo") == "joao paulo"
