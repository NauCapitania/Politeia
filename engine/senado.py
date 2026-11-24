"""Senate-specific read models: who held each seat on a date, party on a date, change events."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from connectors.base.protocol import normalize_name
from engine.db.models import (
    DossierItem,
    ExternalIdentifier,
    Mandate,
    MandateExercise,
    Party,
    PartyMembership,
    Person,
)

INSTITUTION = "ins_br_senado"
PERSON_SCHEME = "senado.parlamentar"


def person_codes(s: Session, ids: list[str] | None = None) -> dict[str, str]:
    q = select(ExternalIdentifier.entity_id, ExternalIdentifier.value).where(
        ExternalIdentifier.entity_kind == "person", ExternalIdentifier.scheme == PERSON_SCHEME)
    if ids is not None:
        q = q.where(ExternalIdentifier.entity_id.in_(ids))
    return dict(s.execute(q).all())


def parties_on(s: Session, person_ids: list[str], on: date) -> dict[str, str]:
    """Party abbreviation per person on a date. Dated affiliation history decides; roster observations are used only
    for people without any affiliation history, bounded by when the roster last listed them."""
    rows = s.execute(select(PartyMembership.person_id, Party.abbreviation, PartyMembership.basis,
                            PartyMembership.valid_from, PartyMembership.valid_to, PartyMembership.is_current,
                            PartyMembership.last_observed_at)
                     .join(Party, Party.id == PartyMembership.party_id)
                     .where(PartyMembership.person_id.in_(person_ids))).all()
    with_history = {r.person_id for r in rows if r.basis == "affiliation_history"}
    best: dict[str, tuple] = {}
    for pid, abbr, basis, vf, vt, current, seen in rows:
        if basis != "affiliation_history":
            if pid in with_history:
                continue
            if vt is None and not current and seen is not None:
                vt = seen.date() + timedelta(days=1)
        if (vf and vf > on) or (vt and vt <= on):
            continue
        rank = vf or date.min
        if pid not in best or rank > best[pid][0]:
            best[pid] = (rank, abbr)
    return {pid: abbr for pid, (_, abbr) in best.items()}


def seats_on(s: Session, on: date) -> list[dict]:
    """Who sat in each seat on `on`. Seat = (titular code, first legislature); latest exercise start wins."""
    rows = s.execute(select(MandateExercise, Mandate, Person).join(Mandate, Mandate.id == MandateExercise.mandate_id)
                     .join(Person, Person.id == MandateExercise.person_id).where(
        MandateExercise.institution_id == INSTITUTION, MandateExercise.start_date <= on,
        or_(MandateExercise.end_date.is_(None), MandateExercise.end_date >= on))).all()
    codes = person_codes(s, [p.id for _, _, p in rows])
    by_seat: dict[tuple, tuple] = {}
    for ex, m, p in rows:
        attrs = m.attributes or {}
        legs = attrs.get("legislatures") or [None]
        seat = (str(attrs.get("holder_code") or codes.get(p.id)), str(legs[0]))
        rank = (ex.start_date, ex.end_date is None or ex.end_date > on)
        if seat not in by_seat or rank > by_seat[seat][0]:
            by_seat[seat] = (rank, ex, m, p)
    parties = parties_on(s, [p.id for _, _, _, p in by_seat.values()], on)
    out = []
    for (holder, leg), (_, ex, m, p) in by_seat.items():
        out.append({"person_id": p.id, "code": codes.get(p.id), "name": p.name, "photo_url": p.photo_url,
                    "uf": m.represented_unit, "party": parties.get(p.id), "participation":
                    "titular" if m.participation == "holder" else "suplente", "holder_code": holder,
                    "legislature": leg, "exercise_start": ex.start_date, "exercise_end": ex.end_date,
                    "mandate_end": m.end_date})
    return sorted(out, key=lambda r: (r["party"] or "~", r["name"]))


def change_events(s: Session, since: date) -> list[dict]:
    """Exercise starts/ends and party switches since a date, for the time slider."""
    events = []
    rows = s.execute(select(MandateExercise, Person.name, Mandate.represented_unit)
                     .join(Person, Person.id == MandateExercise.person_id)
                     .join(Mandate, Mandate.id == MandateExercise.mandate_id)
                     .where(MandateExercise.institution_id == INSTITUTION)).all()
    for ex, name, uf in rows:
        if ex.start_date and ex.start_date >= since:
            events.append({"date": ex.start_date, "kind": "exercicio_inicio", "person_id": ex.person_id,
                           "name": name, "uf": uf, "detail": "Assume o exercício do mandato"})
        if ex.end_date and ex.end_date >= since:
            events.append({"date": ex.end_date, "kind": "exercicio_fim", "person_id": ex.person_id, "name": name,
                           "uf": uf, "detail": ex.end_cause or "Deixa o exercício"})
    senators = {pid for pid in s.scalars(select(Mandate.person_id).where(Mandate.institution_id == INSTITUTION))}
    names = dict(s.execute(select(Person.id, Person.name).where(Person.id.in_(senators))).all())
    hist = defaultdict(list)
    q = (select(PartyMembership.person_id, Party.abbreviation, PartyMembership.valid_from, PartyMembership.valid_to)
         .join(Party, Party.id == PartyMembership.party_id)
         .where(PartyMembership.person_id.in_(senators), PartyMembership.basis == "affiliation_history"))
    for pid, abbr, vf, vt in s.execute(q).all():
        hist[pid].append((vf, vt, abbr))
    for pid, spans in hist.items():
        spans.sort(key=lambda x: x[0] or date.min)
        for prev, cur in zip(spans, spans[1:], strict=False):
            if cur[0] and cur[0] >= since and prev[2] != cur[2]:
                events.append({"date": cur[0], "kind": "troca_partido", "person_id": pid, "name": names.get(pid),
                               "detail": f"{prev[2]} → {cur[2]}", "from": prev[2], "to": cur[2]})
    return sorted(events, key=lambda e: e["date"])


def seats_2027(s: Session) -> dict:
    """The Senate from 1 Feb 2027: the 27 seats whose mandates run to 2031 plus the 54 elected in October 2026.
    Continuing seats show today's occupant and party; elected seats come from the sourced 2027 dossier."""
    # Read the outgoing legislature (never past 31 Jan 2027) so mandates ingested after the posse are not doubled.
    today = min(date.today(), date(2027, 1, 31))
    continuing = [r | {"group": "continua"} for r in seats_on(s, today)
                  if r["mandate_end"] and date(2031, 1, 1) <= r["mandate_end"] < date(2035, 1, 1)]
    elected = s.scalars(select(DossierItem).where(DossierItem.dossier == "presidencia-2027",
                                                  DossierItem.kind == "elected_2026")).all()
    current = {normalize_name(r["name"]): r for r in seats_on(s, today)}
    known = {normalize_name(n): (pid, photo) for pid, n, photo in s.execute(
        select(Person.id, Person.name, Person.photo_url).join(Mandate, Mandate.person_id == Person.id)
        .where(Mandate.institution_id == INSTITUTION)).all()}
    out = list(continuing)
    for item in elected:
        p = item.payload
        key = normalize_name(p["name"])
        pid, photo = known.get(key, (None, None))
        now = current.get(key)
        out.append({"person_id": pid, "name": p["name"], "photo_url": photo, "uf": p.get("uf"),
                    "party": p.get("party"), "group": "reeleito" if now else "eleito_2026",
                    "note": p.get("note"), "sources": item.sources, "mandate_end": date(2035, 1, 31)})
    parties: dict[str, int] = {}
    for r in out:
        parties[r["party"] or "S/Partido"] = parties.get(r["party"] or "S/Partido", 0) + 1
    return {"date": date(2027, 2, 1), "seat_count": 81, "observed": len(out),
            "continuing": len(continuing), "elected": len(elected),
            "reelected": sum(1 for r in out if r["group"] == "reeleito"),
            "parties": dict(sorted(parties.items(), key=lambda x: -x[1])),
            "note": "Projeção: cadeiras que seguem até 2031 com o partido de hoje; eleitos de 2026 com o partido "
                    "informado pelas fontes da eleição. Trocas de partido até a posse não estão refletidas.",
            "seats": sorted(out, key=lambda r: (r["party"] or "~", r["name"]))}
