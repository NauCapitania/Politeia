"""Ontologia endpoints: the current map of the União (powers, bodies, offices, competences, holders) and the
live processes and analyses built on it, for the home screen."""

from collections import Counter, defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.db import models as M
from engine.db.session import get_session

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_session)]
NEWS_PER_TARGET = 8
# Plain committee seats are counted in bodies[].holders; the list per committee is in /v1/comissoes/{id}.
COMMITTEE_MEMBER = "off_membro_comissao"
# SIORG competence texts run to pages; the full text stays in the database and in /v1/executivo.
DESCRIPTION_LIMIT = 280


def _row(obj, *exclude: str) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns if c.key not in exclude}


def _short(value: str | None, limit: int = DESCRIPTION_LIMIT) -> str | None:
    if not value or len(value) <= limit:
        return value
    return value[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "…"


def _sources(s: Session, table: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for f in s.scalars(select(M.FactSource).where(M.FactSource.table_name == table).order_by(M.FactSource.id)):
        src = {k: v for k, v in (("kind", f.source_kind), ("url", f.url), ("outlet", f.outlet),
                                 ("date", f.published_on), ("raw_record_id", f.raw_record_id)) if v is not None}
        if src not in out[f.row_id]:
            out[f.row_id].append(src)
    return out


def _news(s: Session, kind: str) -> dict[str, list[dict]]:
    ranked = (select(M.NewsLink.target_id, M.NewsItem.title, M.NewsItem.url, M.NewsItem.outlet,
                     M.NewsItem.published_at,
                     func.row_number().over(partition_by=M.NewsLink.target_id,
                                            order_by=M.NewsItem.published_at.desc().nulls_last()).label("n"))
              .join(M.NewsItem, M.NewsItem.id == M.NewsLink.news_item_id)
              .where(M.NewsLink.target_kind == kind).subquery())
    out: dict[str, list[dict]] = defaultdict(list)
    for row in s.execute(select(ranked).where(ranked.c.n <= NEWS_PER_TARGET).order_by(ranked.c.target_id, ranked.c.n)):
        out[row.target_id].append({"title": row.title, "url": row.url, "outlet": row.outlet,
                                   "published_at": row.published_at})
    return out


def ontology_overview(s: Session) -> dict:
    persons = dict(s.execute(select(M.Person.id, M.Person.name)
                             .where(M.Person.id.in_(select(M.OfficeHolding.person_id)))).all())
    party = dict(s.execute(select(M.Affiliation.person_id, M.Organization.abbreviation)
                           .join(M.Organization)).all())
    holdings = s.scalars(select(M.OfficeHolding).order_by(M.OfficeHolding.office_id, M.OfficeHolding.id)).all()
    held = Counter((h.office_id, h.body_id) for h in holdings if h.seat_kind != "suplente")
    held_office = Counter(h.office_id for h in holdings if h.seat_kind != "suplente")
    offices = []
    for o in s.scalars(select(M.Office).order_by(M.Office.id)):
        row = _row(o) | {"holders": held_office[o.id]}
        if o.seats is not None:
            row["vacancies"] = max(o.seats - held_office[o.id], 0)
        offices.append(row)
    members = Counter(body for body, _ in {(h.body_id, h.person_id) for h in holdings if h.body_id}
                      if body)
    bodies = [_row(b) | {"description": _short(b.description), "holders": members[b.id]}
              for b in s.scalars(select(M.Body).order_by(M.Body.id))]
    affiliated = Counter(org for org in party.values())
    organizations = [_row(o, "party_id") | {"current_members": affiliated[o.abbreviation]}
                     for o in s.scalars(select(M.Organization).order_by(M.Organization.id))]
    proceedings = []
    participants = defaultdict(list)
    participant_sources = _sources(s, "process.participants")
    for p in s.scalars(select(M.Participant).order_by(M.Participant.id)):
        participants[p.proceeding_id].append(_row(p, "proceeding_id") | {"sources": participant_sources[p.id]})
    steps = defaultdict(list)
    step_sources = _sources(s, "process.steps")
    for st in s.scalars(select(M.Step).order_by(M.Step.proceeding_id, M.Step.ordinal)):
        steps[st.proceeding_id].append(_row(st, "proceeding_id") | {"sources": step_sources[st.id]})
    deadlines = defaultdict(list)
    for d in s.scalars(select(M.Deadline).order_by(M.Deadline.due_on)):
        deadlines[d.proceeding_id].append(_row(d, "proceeding_id"))
    news = _news(s, "proceeding")
    proc_sources = _sources(s, "process.proceedings")
    for p in s.scalars(select(M.Proceeding).order_by(M.Proceeding.id)):
        proceedings.append(_row(p) | {"participants": participants[p.id], "steps": steps[p.id],
                                      "deadlines": deadlines[p.id], "news": news[p.id],
                                      "sources": proc_sources[p.id]})
    entities = defaultdict(list)
    for e in s.scalars(select(M.AnalysisEntity).order_by(M.AnalysisEntity.entity_kind, M.AnalysisEntity.entity_id)):
        entities[e.analysis_id].append(_row(e, "analysis_id"))
    estimates = defaultdict(list)
    estimate_sources = _sources(s, "analysis.estimates")
    for e in s.scalars(select(M.Estimate).order_by(M.Estimate.id)):
        estimates[e.analysis_id].append(_row(e, "analysis_id") | {"sources": estimate_sources[e.id]})
    analysis_news = _news(s, "analysis")
    analyses = [_row(a) | {"entities": entities[a.id], "estimates": estimates[a.id], "news": analysis_news[a.id]}
                for a in s.scalars(select(M.Analysis).order_by(M.Analysis.id))]
    holding_sources = _sources(s, "core.office_holdings")
    return {
        "federative_units": [_row(x) for x in s.scalars(select(M.FederativeUnit).order_by(M.FederativeUnit.id))],
        "powers": [_row(x) for x in s.scalars(select(M.Power).order_by(M.Power.ordinal))],
        "legislatures": [_row(x) for x in s.scalars(select(M.Legislature).order_by(M.Legislature.number))],
        "legal_bases": [_row(x) for x in s.scalars(select(M.LegalBasis).order_by(M.LegalBasis.id))],
        "bodies": bodies,
        "offices": offices,
        "competences": [_row(x) for x in s.scalars(select(M.Competence).order_by(M.Competence.id))],
        "organizations": organizations,
        "holdings": [
            _row(h, "mandate_id", "committee_membership_id") | {
                "person_name": persons.get(h.person_id), "party": party.get(h.person_id),
                "sources": holding_sources[h.id]}
            for h in holdings if h.office_id != COMMITTEE_MEMBER],
        "seats_by_body": [{"office_id": o, "body_id": b, "holders": n} for (o, b), n in sorted(held.items(),
                                                                                             key=str)],
        "proceedings": proceedings,
        "analyses": analyses,
    }


@router.get("/ontologia")
def ontologia(s: DB):
    return ontology_overview(s)


@router.get("/ontologia/ligacoes/{institution_id}")
def ligacoes(institution_id: str, s: DB, top: Annotated[int, Query(ge=1, le=20)] = 5):
    """Each member's strongest vote-agreement links (open roll calls only), for the behavior layer."""
    links = s.scalars(select(M.ObservedLink).where(M.ObservedLink.institution_id == institution_id)).all()
    if not links and s.get(M.Institution, institution_id) is None:
        raise HTTPException(404, "instituição não encontrada")
    by_person: dict[str, list] = defaultdict(list)
    for link in links:
        for a, b in ((link.person_a_id, link.person_b_id), (link.person_b_id, link.person_a_id)):
            by_person[a].append((link.weight, link.shared, b))
    pairs = set()
    for person, items in by_person.items():
        for weight, shared, other in sorted(items, key=lambda x: (-x[0], -x[1], x[2]))[:top]:
            pairs.add((min(person, other), max(person, other), weight, shared))
    return {
        "institution_id": institution_id,
        "kind": "vote_agreement",
        "note": "Concordância em votações nominais abertas (Sim, Não, Abstenção, Obstrução). Votos secretos não "
                "entram. É comportamento observado, não filiação nem alinhamento declarado.",
        "links": [{"a": a, "b": b, "weight": w, "shared": n} for a, b, w, n in sorted(pairs)],
    }
