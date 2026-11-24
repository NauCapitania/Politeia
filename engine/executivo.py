"""Federal Executive read model: SIORG structure joined with cabinet terms, for the Executivo tab."""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from connectors.base.protocol import normalize_name
from engine.db.models import ExecutiveBody, IngestionRun, Mandate, Person, SourceSystem

INSTITUTION = "ins_br_executivo"
SENATE = "ins_br_senado"
PRESIDENCY_CODE = "26"
PRESIDENCY_ACRONYMS = {"CC", "CC/PR", "GSI", "GSI/PR", "SG", "SG/PR", "SRI", "SRI/PR", "SECOM", "SECOM/PR", "VPR"}


def kind_of(body: ExecutiveBody) -> str:
    if body.name.startswith("Ministério"):
        return "ministerio"
    if "Presidência da República" in body.name or (body.acronym or "").upper() in PRESIDENCY_ACRONYMS:
        return "presidencia"
    if body.legal_nature == "Administração Direta":
        return "orgao_ministerial"
    return "entidade"


def _key(text: str) -> str:
    return normalize_name(re.sub(r"\s*\((?:Brasil|Brazil)\)\s*$", "", text))


def match_body(title: str, label: str, bodies: list[ExecutiveBody]) -> ExecutiveBody | None:
    """Cabinet rows name ministries by their Wikipedia title; SIORG uses the full official name."""
    t, lab = _key(title), _key(label)
    by_name = {_key(b.name): b for b in bodies}
    if t in by_name:
        return by_name[t]
    starts = [b for b in bodies if _key(b.name).startswith(t) or (lab and _key(b.name).startswith(lab))]
    if len(starts) == 1:
        return starts[0]
    contains = [b for b in bodies if lab and lab in _key(b.name)]
    return contains[0] if len(contains) == 1 else None


def _term(m: Mandate, person: Person, senators: dict[str, str]) -> dict:
    a = m.attributes or {}
    return {"id": m.id, "person_id": person.id, "name": person.name, "profile_url": person.profile_url,
            "party": a.get("party"), "uf": a.get("uf"), "interim": m.participation == "interim",
            "start": m.start_date, "end": m.end_date, "end_note": a.get("end_note"),
            "current": m.status == "in_exercise", "epistemic_status": m.epistemic_status,
            "refs": a.get("refs", []), "senate_person_id": senators.get(normalize_name(person.name))}


def _runs(s: Session) -> list[dict]:
    out = []
    for src in s.scalars(select(SourceSystem).where(SourceSystem.institution_id == INSTITUTION)
                         .order_by(SourceSystem.id)):
        last = s.scalar(select(func.max(IngestionRun.finished_at)).where(
            IngestionRun.source_system_id == src.id, IngestionRun.status.in_(("succeeded", "partial"))))
        out.append({"id": src.id, "name": src.name, "url": src.documentation_url or src.base_url,
                    "last_success_at": last})
    return out


def executive_overview(s: Session) -> dict:
    bodies = s.scalars(select(ExecutiveBody).where(ExecutiveBody.institution_id == INSTITUTION,
                                                   ExecutiveBody.is_current.is_(True))).all()
    by_code = {b.siorg_code: b for b in bodies}
    presidency = by_code.get(PRESIDENCY_CODE)
    top = [b for b in bodies if b.parent_code == PRESIDENCY_CODE and b.siorg_code != PRESIDENCY_CODE]
    top_codes = {b.siorg_code for b in top}

    def anchor(b: ExecutiveBody) -> str | None:
        seen, cur = set(), b
        while cur and cur.parent_code and cur.siorg_code not in seen:
            seen.add(cur.siorg_code)
            if cur.parent_code in top_codes:
                return cur.parent_code
            cur = by_code.get(cur.parent_code)
        return None

    linked: dict[str, list[dict]] = {}
    for b in bodies:
        if b.siorg_code in top_codes or b.siorg_code == PRESIDENCY_CODE:
            continue
        a = anchor(b)
        if a:
            linked.setdefault(a, []).append({"code": b.siorg_code, "name": b.name, "acronym": b.acronym,
                                             "legal_nature": b.legal_nature, "site": b.site,
                                             "direct": b.parent_code == a})
    senators = {normalize_name(n): pid for pid, n in s.execute(
        select(Person.id, Person.name).join(Mandate, Mandate.person_id == Person.id)
        .where(Mandate.institution_id == SENATE).distinct())}
    terms = s.execute(select(Mandate, Person).join(Person, Person.id == Mandate.person_id).where(
        Mandate.institution_id == INSTITUTION, Mandate.role_type == "minister_of_state")
        .order_by(Mandate.start_date)).all()
    by_body: dict[str, list[dict]] = {}
    unmatched: dict[str, dict] = {}
    for m, person in terms:
        title = (m.attributes or {}).get("ministry_title") or m.represented_unit or ""
        body = match_body(title, m.represented_unit or "", top)
        row = _term(m, person, senators)
        if body:
            by_body.setdefault(body.siorg_code, []).append(row)
        else:
            entry = unmatched.setdefault(title, {"ministry": m.represented_unit, "title": title, "terms": []})
            entry["terms"].append(row)

    def holder(rows: list[dict]) -> dict | None:
        current = [r for r in rows if r["current"]]
        return max(current, key=lambda r: r["start"]) if current else None

    out = []
    for b in sorted(top, key=lambda b: (kind_of(b) != "presidencia", kind_of(b) != "ministerio", b.name)):
        rows = by_body.get(b.siorg_code, [])
        out.append({"code": b.siorg_code, "name": b.name, "acronym": b.acronym, "kind": kind_of(b),
                    "legal_nature": b.legal_nature, "competence": b.competence, "purpose": b.purpose,
                    "mission": b.mission, "legal_basis": b.legal_basis, "site": b.site,
                    "administrative_units": (b.attributes or {}).get("administrative_units", 0),
                    "archive_month": (b.attributes or {}).get("archive_month"),
                    "version_start": b.version_start,
                    "raw_record_id": str(b.raw_record_id) if b.raw_record_id else None,
                    "entities": sorted(linked.get(b.siorg_code, []), key=lambda e: e["name"]),
                    "holder": holder(rows), "terms": rows})
    return {
        "institution_id": INSTITUTION,
        "presidency": None if presidency is None else {
            "code": presidency.siorg_code, "name": presidency.name, "competence": presidency.competence,
            "legal_basis": presidency.legal_basis, "site": presidency.site},
        "counts": {"bodies": len(bodies), "top_level": len(top),
                   "ministries": sum(1 for b in top if kind_of(b) == "ministerio"),
                   "entities": sum(len(v) for v in linked.values()),
                   "ministers_in_office": sum(1 for b in out if b["holder"]),
                   "terms": len(terms)},
        "bodies": out,
        "unmatched": sorted(unmatched.values(), key=lambda u: u["ministry"] or ""),
        "sources": _runs(s),
    }
