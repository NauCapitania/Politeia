"""Câmara dos Deputados endpoints: plenary votes, committees and party switches recorded by the Câmara."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.api.monitor import committee_detail, list_committees, list_votes, vote_detail
from engine.db.models import Party, PartyMembership, Person
from engine.db.session import get_session

INSTITUTION = "ins_br_camara"
router = APIRouter(prefix="/v1/camara")
DB = Annotated[Session, Depends(get_session)]


@router.get("/votacoes")
def votacoes(s: DB, limit: Annotated[int, Query(le=2000)] = 200, q: str | None = None, nominal: bool | None = None):
    return list_votes(s, INSTITUTION, limit=limit, q=q, nominal=nominal)


@router.get("/votacoes/{vote_id}")
def votacao(vote_id: str, s: DB):
    return vote_detail(s, vote_id, INSTITUTION)


@router.get("/comissoes")
def comissoes(s: DB):
    return list_committees(s, INSTITUTION)


@router.get("/comissoes/{committee_id}")
def comissao(committee_id: str, s: DB):
    return committee_detail(s, committee_id, INSTITUTION)


@router.get("/trocas")
def trocas(s: DB, desde: date = date(2023, 2, 1)):
    """Party switches: each start of a new party period in the Câmara's record after `desde`."""
    rows = s.execute(
        select(PartyMembership, Party.abbreviation, Person.name, Person.photo_url)
        .join(Party, Party.id == PartyMembership.party_id).join(Person, Person.id == PartyMembership.person_id)
        .where(PartyMembership.institution_id == INSTITUTION, PartyMembership.basis == "chamber_record")
        .order_by(PartyMembership.person_id, PartyMembership.valid_from.nulls_first())).all()
    out, previous = [], {}
    for pm, party, name, photo in rows:
        before = previous.get(pm.person_id)
        previous[pm.person_id] = party
        if before and before != party and pm.valid_from and pm.valid_from >= desde:
            out.append({"person_id": pm.person_id, "name": name, "photo_url": photo, "date": pm.valid_from,
                        "from": before, "to": party})
    return sorted(out, key=lambda r: r["date"], reverse=True)
