import httpx

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


def test_normalize_name_is_accent_and_case_insensitive():
    assert normalize_name("  João  PAULO ") == normalize_name("joao paulo") == "joao paulo"
