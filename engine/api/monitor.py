"""Senate-monitor endpoints: composition by date, senator profile, votes, news, dossiers and presidency analyses."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from engine.analysis.presidencia import _claim, analysis_2025, analysis_2027
from engine.db.models import (
    Claim,
    DossierItem,
    IndividualVote,
    Mandate,
    MandateExercise,
    NewsItem,
    NewsMention,
    Party,
    PartyMembership,
    Person,
    Speech,
    VoteEvent,
)
from engine.db.session import get_session
from engine.senado import INSTITUTION, change_events, person_codes, seats_on

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_session)]


def _news(rows) -> list[dict]:
    return [{"id": n.id, "title": n.title, "url": n.url, "outlet": n.outlet, "excerpt": n.excerpt,
             "published_at": n.published_at, "topics": n.topics} for n in rows]


@router.get("/senado/composicao")
def composicao(s: DB, data: date | None = None):
    on = data or date.today()
    seats = seats_on(s, on)
    return {"date": on, "seat_count": 81, "observed": len(seats), "seats": seats,
            "note": None if len(seats) == 81 else "A reconstrução por exercícios não fechou 81 cadeiras nesta data."}


@router.get("/senado/mudancas")
def mudancas(s: DB, desde: date = date(2023, 2, 1)):
    return change_events(s, desde)


@router.get("/senadores/{person_id}")
def senador(person_id: str, s: DB):
    p = s.get(Person, person_id)
    if p is None:
        raise HTTPException(404, "senador não encontrado")
    code = person_codes(s, [person_id]).get(person_id)
    mandates = s.scalars(select(Mandate).where(Mandate.person_id == person_id, Mandate.institution_id == INSTITUTION)
                         .order_by(Mandate.start_date.desc())).all()
    exercises = s.scalars(select(MandateExercise).where(MandateExercise.person_id == person_id)
                          .order_by(MandateExercise.start_date.desc())).all()
    parties = s.execute(select(Party.abbreviation, Party.name, PartyMembership.valid_from, PartyMembership.valid_to,
                               PartyMembership.basis).join(Party, Party.id == PartyMembership.party_id)
                        .where(PartyMembership.person_id == person_id)
                        .order_by(PartyMembership.valid_from.desc().nulls_last())).all()
    votes = s.execute(select(VoteEvent, IndividualVote)
                      .join(IndividualVote, IndividualVote.vote_event_id == VoteEvent.id)
                      .where(IndividualVote.person_id == person_id)
                      .order_by(VoteEvent.held_on.desc()).limit(60)).all()
    vote_counts = dict(s.execute(select(IndividualVote.vote_code, func.count()).where(
        IndividualVote.person_id == person_id).group_by(IndividualVote.vote_code)).all())
    speeches = s.scalars(select(Speech).where(Speech.person_id == person_id)
                         .order_by(Speech.delivered_on.desc()).limit(30)).all()
    news = s.scalars(select(NewsItem).join(NewsMention, NewsMention.news_item_id == NewsItem.id).where(
        NewsMention.entity_kind == "person", NewsMention.entity_id == person_id)
        .order_by(NewsItem.published_at.desc().nulls_last()).limit(30)).all()
    claims = s.scalars(select(Claim).where(Claim.subject_id == person_id)).all()
    return {
        "id": p.id, "code": code, "name": p.name, "full_name": p.full_name, "gender": p.gender,
        "photo_url": p.photo_url, "profile_url": p.profile_url,
        "links": {"perfil_oficial": p.profile_url,
                  "redes_sociais": None if not code else
                  f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{code}"},
        "social_note": "Sem API gratuita para leitura automática de redes; o perfil oficial do Senado lista as redes.",
        "mandates": [{"id": m.id, "uf": m.represented_unit, "participation": m.participation, "start": m.start_date,
                      "end": m.end_date, "status": m.status,
                      "source_participation": (m.attributes or {}).get("source_participation"),
                      "holder": (m.attributes or {}).get("holder")} for m in mandates],
        "exercises": [{"start": e.start_date, "end": e.end_date, "end_cause": e.end_cause} for e in exercises],
        "parties": [{"party": a, "name": n, "from": f, "to": t, "basis": b} for a, n, f, t, b in parties],
        "vote_summary": vote_counts,
        "votes": [{"id": e.id, "date": e.held_on, "description": e.description, "matter": e.matter,
                   "secret": e.secret, "result": e.result, "vote": v.vote_code, "vote_label": v.vote_label,
                   "party_at_vote": v.party_abbreviation} for e, v in votes],
        "speeches": [{"id": x.id, "date": x.delivered_on, "kind": x.kind, "summary": x.summary, "url": x.url}
                     for x in speeches],
        "news": _news(news), "claims": [_claim(c) for c in claims],
    }


@router.get("/votacoes")
def votacoes(s: DB, limit: Annotated[int, Query(le=200)] = 50, secreta: bool | None = None,
             q: str | None = None):
    stmt = select(VoteEvent).where(VoteEvent.institution_id == INSTITUTION)
    if secreta is not None:
        stmt = stmt.where(VoteEvent.secret.is_(secreta))
    if q:
        stmt = stmt.where(VoteEvent.description.ilike(f"%{q}%") | VoteEvent.matter.ilike(f"%{q}%"))
    rows = s.scalars(stmt.order_by(VoteEvent.held_on.desc(), VoteEvent.source_id.desc()).limit(limit)).all()
    return [{"id": e.id, "date": e.held_on, "description": e.description, "matter": e.matter, "secret": e.secret,
             "result": e.result, "totals": e.totals} for e in rows]


@router.get("/votacoes/{vote_id}")
def votacao(vote_id: str, s: DB):
    e = s.get(VoteEvent, vote_id)
    if e is None:
        raise HTTPException(404, "votação não encontrada")
    votes = s.execute(select(IndividualVote, Person.name).join(Person, Person.id == IndividualVote.person_id)
                      .where(IndividualVote.vote_event_id == vote_id).order_by(Person.name)).all()
    return {"id": e.id, "date": e.held_on, "description": e.description, "matter": e.matter, "secret": e.secret,
            "result": e.result, "totals": e.totals, "raw_record_id": str(e.raw_record_id) if e.raw_record_id else None,
            "votes": [{"person_id": v.person_id, "name": n, "party": v.party_abbreviation, "uf": v.represented_unit,
                       "vote": v.vote_code, "label": v.vote_label} for v, n in votes]}


@router.get("/noticias")
def noticias(s: DB, tema: str | None = None, entidade: str | None = None,
             limit: Annotated[int, Query(le=200)] = 60):
    stmt = select(NewsItem)
    if tema:
        stmt = stmt.where(NewsItem.topics.contains([tema]))
    if entidade:
        stmt = stmt.join(NewsMention, NewsMention.news_item_id == NewsItem.id).where(NewsMention.entity_id == entidade)
    rows = s.scalars(stmt.order_by(NewsItem.published_at.desc().nulls_last()).limit(limit)).all()
    mentions: dict[str, list] = {}
    if rows:
        for m in s.scalars(select(NewsMention).where(NewsMention.news_item_id.in_([r.id for r in rows]))):
            mentions.setdefault(m.news_item_id, []).append({"kind": m.entity_kind, "id": m.entity_id,
                                                            "text": m.matched_text, "confidence": m.confidence})
    return [n | {"mentions": mentions.get(n["id"], [])} for n in _news(rows)]


@router.get("/dossies/{dossier}")
def dossie(dossier: str, s: DB):
    items = s.scalars(select(DossierItem).where(DossierItem.dossier == dossier).order_by(DossierItem.id)).all()
    if not items:
        raise HTTPException(404, "dossiê não encontrado")
    out: dict[str, list] = {}
    for i in items:
        out.setdefault(i.kind, []).append({"id": i.id, **i.payload, "sources": i.sources})
    claims = s.scalars(select(Claim).where(Claim.dossier == dossier)).all()
    return {"dossier": dossier, "as_of": items[0].as_of, "items": out, "claims": [_claim(c) for c in claims]}


@router.get("/presidencia/2025")
def presidencia_2025(s: DB):
    return analysis_2025(s)


@router.get("/presidencia/2027")
def presidencia_2027(s: DB):
    return analysis_2027(s)
