"""Executivo endpoints: federal Executive structure (SIORG) and cabinet terms."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from engine.db.session import get_session
from engine.executivo import executive_overview

router = APIRouter(prefix="/v1")
DB = Annotated[Session, Depends(get_session)]


@router.get("/executivo")
def executivo(s: DB):
    return executive_overview(s)
