"""Curated, source-cited dossiers (dossiers/*.json) loaded into analysis.dossier_items and analysis.claims.

Curated knowledge complements automated ingestion where no structured official source exists (secret ballots,
press counts, case timelines). Every item and claim must carry sources; loading fails otherwise.
"""

import hashlib
import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from connectors.base.protocol import normalize_name, parse_date
from engine.db.models import Claim, DossierItem, Mandate, Person
from engine.party_dossier import validate_party_dossier

DOSSIERS_DIR = Path(__file__).resolve().parent.parent / "dossiers"
CLAIM_TYPES = {"official", "declaration", "press_report", "analysis"}


class DossierError(ValueError):
    pass


def read_dossiers(directory: Path = DOSSIERS_DIR) -> list[dict]:
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]
    for doc in docs:
        for item in doc.get("items", []) + doc.get("claims", []):
            if not item.get("sources"):
                raise DossierError(f"{doc['dossier']}/{item['id']} has no sources")
        for c in doc.get("claims", []):
            if c["claim_type"] not in CLAIM_TYPES:
                raise DossierError(f"{c['id']}: unknown claim_type {c['claim_type']}")
        if doc["dossier"] == "partidos":
            try:
                validate_party_dossier(doc)
            except (ValueError, KeyError, TypeError) as exc:
                raise DossierError(f"partidos: {exc}") from exc
    return docs


def senator_index(s: Session) -> dict[str, str]:
    rows = s.execute(select(Person.id, Person.name, Person.full_name)
                     .join(Mandate, Mandate.person_id == Person.id).distinct())
    index: dict[str, str] = {}
    for pid, name, full in rows:
        for n in (name, full):
            if n:
                index.setdefault(normalize_name(n), pid)
    return index


def load_dossiers(s: Session, directory: Path = DOSSIERS_DIR) -> dict[str, int]:
    people = senator_index(s)
    stats = {}
    for doc in read_dossiers(directory):
        dossier = doc["dossier"]
        as_of = parse_date(doc.get("as_of"))
        ids = []
        for item in doc.get("items", []):
            payload = item["payload"]
            if "name" in payload and item["kind"] in ("candidate", "elected_2026"):
                payload = payload | {"person_id": people.get(normalize_name(payload["name"]))}
            sha = hashlib.sha256(json.dumps([payload, item["sources"]], sort_keys=True).encode()).hexdigest()
            row = dict(id=item["id"], dossier=dossier, kind=item["kind"], payload=payload, sources=item["sources"],
                       as_of=as_of, content_sha256=sha)
            stmt = insert(DossierItem).values(**row)
            s.execute(stmt.on_conflict_do_update(index_elements=[DossierItem.id],
                                                 set_={k: stmt.excluded[k] for k in row if k != "id"}))
            ids.append(item["id"])
        s.execute(delete(DossierItem).where(DossierItem.dossier == dossier, DossierItem.id.not_in(ids)))
        claim_ids = []
        for c in doc.get("claims", []):
            subject_id = c.get("subject_id") or people.get(normalize_name(c["subject_label"]))
            row = dict(id=c["id"], dossier=dossier, topic=c["topic"], subject_kind=c.get("subject_kind", "person"),
                       subject_id=subject_id, subject_label=c["subject_label"], position=c.get("position"),
                       statement=c["statement"], claim_type=c["claim_type"], confidence=c["confidence"],
                       review_status=c.get("review_status", "curated"), stated_on=parse_date(c.get("stated_on") or
                                                                                            c["sources"][0].get("date")),
                       sources=c["sources"], attributes=c.get("attributes", {}))
            stmt = insert(Claim).values(**row)
            s.execute(stmt.on_conflict_do_update(index_elements=[Claim.id],
                                                 set_={k: stmt.excluded[k] for k in row if k != "id"}))
            claim_ids.append(c["id"])
        s.execute(delete(Claim).where(Claim.dossier == dossier, Claim.id.not_in(claim_ids)))
        stats[dossier] = len(ids) + len(claim_ids)
    return stats
