import json

import pytest

from engine.dossiers import DossierError, read_dossiers


def test_party_dossier_has_latest_funding_and_covers_multiple_event_types():
    doc = next(doc for doc in read_dossiers() if doc["dossier"] == "partidos")
    funds = {(item["payload"]["fund"], item["payload"]["year"]): item["payload"]
             for item in doc["items"] if item["kind"] == "funding"}
    assert {y for fund, y in funds if fund == "fefc"} == {2018, 2020, 2022, 2024, 2026}
    assert len(funds["fefc", 2026]["allocations"]) == 30
    assert len(funds["partidario", 2025]["allocations"]) == 19
    assert funds["partidario", 2026]["partial"]
    assert {"fundacao", "registro", "extincao", "fusao", "incorporacao", "renomeacao", "federacao"} <= {
        item["payload"]["type"] for item in doc["items"] if item["kind"] == "event"
    }


@pytest.mark.parametrize(("change", "error"), [
    ({"sources": []}, "has no sources"),
    ({"sources": [{"url": "javascript:alert(1)", "kind": "official", "outlet": "TSE"}]}, "invalid source URL"),
    ({"type": "coligacao"}, "invalid event type"),
    ({"to": ["desconhecido"]}, "unknown party id"),
])
def test_party_dossier_rejects_invalid_payloads(tmp_path, change, error):
    doc = next(doc for doc in read_dossiers() if doc["dossier"] == "partidos")
    first_event = next(item for item in doc["items"] if item["kind"] == "event")
    (first_event if "sources" in change else first_event["payload"]).update(change)
    (tmp_path / "partidos.json").write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DossierError, match=error):
        read_dossiers(tmp_path)
