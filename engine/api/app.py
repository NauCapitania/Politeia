"""Politeia Engine API (v1)."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from engine.api import queries as Q
from engine.api import schemas as S
from engine.db.models import Institution
from engine.db.session import get_session
from engine.settings import get_settings

app = FastAPI(title="Politeia Engine API", version="0.1.0",
              description="Institution-agnostic access to normalized legislative data with provenance.")
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(","), allow_methods=["GET"],
                   allow_headers=["*"])

DB = Annotated[Session, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]
Text = Annotated[str | None, Query(max_length=200)]


def _inst(s: Session, institution_id: str) -> Institution:
    inst = s.get(Institution, institution_id) or s.scalar(select(Institution).where(Institution.slug == institution_id))
    if not inst:
        raise HTTPException(404, "institution not found")
    return inst


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/institutions", response_model=list[S.Institution])
def list_institutions(s: DB):
    return [Q.institution(s, i) for i in s.scalars(select(Institution).order_by(Institution.official_name.desc()))]


@app.get("/v1/institutions/{institution_id}", response_model=S.Institution)
def get_institution(institution_id: str, s: DB):
    return Q.institution(s, _inst(s, institution_id))


@app.get("/v1/institutions/{institution_id}/capabilities", response_model=list[S.Capability])
def get_capabilities(institution_id: str, s: DB):
    return Q.capabilities(s, _inst(s, institution_id).id)


@app.get("/v1/institutions/{institution_id}/composition", response_model=S.Composition)
def get_composition(institution_id: str, s: DB):
    return Q.composition(s, _inst(s, institution_id))


@app.get("/v1/institutions/{institution_id}/members", response_model=S.Page[S.Member])
def get_members(institution_id: str, s: DB, q: Text = None, party: Text = None, unit: Text = None,
                limit: Limit = 100, offset: Offset = 0):
    return Q.members(s, _inst(s, institution_id).id, q=q, party=party, unit=unit, limit=limit, offset=offset)


@app.get("/v1/institutions/{institution_id}/proposals", response_model=S.Page[S.ProposalSummary])
def get_proposals(institution_id: str, s: DB, q: Text = None, type_code: Text = None, author: Text = None,
                  limit: Limit = 50, offset: Offset = 0):
    return Q.proposals(s, _inst(s, institution_id).id, q=q, type_code=type_code, author=author, limit=limit,
                       offset=offset)


@app.get("/v1/institutions/{institution_id}/proposal-types")
def get_proposal_types(institution_id: str, s: DB) -> list[dict]:
    return Q.proposal_types(s, _inst(s, institution_id).id)


@app.get("/v1/institutions/{institution_id}/graph", response_model=S.Graph)
def get_graph(institution_id: str, s: DB, focus: Text = None, limit: Annotated[int, Query(ge=1, le=200)] = 60):
    return Q.graph(s, _inst(s, institution_id), focus, limit)


@app.get("/v1/entities/{entity_id}", response_model=S.Entity)
def get_entity(entity_id: str, s: DB):
    ent = Q.entity(s, entity_id)
    if not ent:
        raise HTTPException(404, "entity not found")
    return ent


@app.get("/v1/entities/{entity_id}/relationships", response_model=list[S.Relationship])
def get_relationships(entity_id: str, s: DB):
    if not Q.entity_kind(entity_id):
        raise HTTPException(404, "entity not found")
    return Q.relationships(s, entity_id)


@app.get("/v1/entities/{entity_id}/timeline", response_model=list[S.TimelineItem])
def get_timeline(entity_id: str, s: DB):
    if not Q.entity_kind(entity_id):
        raise HTTPException(404, "entity not found")
    return Q.timeline(s, entity_id)


@app.get("/v1/sources/{raw_record_id}", response_model=S.SourceRecord)
def get_source(raw_record_id: str, s: DB, path: Text = None):
    rec = Q.source_record(s, raw_record_id, path)
    if not rec:
        raise HTTPException(404, "source record not found")
    return rec


@app.get("/v1/ingestion/status", response_model=S.IngestionStatus)
def get_ingestion_status(s: DB, institution: Text = None, limit: Limit = 50):
    return Q.ingestion_status(s, institution, limit)
