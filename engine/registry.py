"""Institution packs: declarative identity, sources and capabilities, plus the connector registry."""

import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from connectors.alepe.connector import AlepeConnector
from connectors.base.http import SourceHttpClient
from connectors.base.protocol import Connector
from connectors.senate.connector import SenateConnector
from engine.db.models import Institution, SourceSystem
from engine.settings import get_settings

PACKS_DIR = Path(__file__).resolve().parent.parent / "institution-packs"
CONNECTORS: dict[str, type[Connector]] = {c.id: c for c in (SenateConnector, AlepeConnector)}


@lru_cache
def load_packs() -> dict[str, dict]:
    packs = {}
    for path in sorted(PACKS_DIR.glob("*/pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        packs[pack["institution"]["id"]] = pack
    return packs


def pack_for(institution_id: str) -> dict:
    return load_packs()[institution_id]


def bootstrap(session: Session) -> None:
    """Upsert institutions and source systems declared by the packs."""
    for pack in load_packs().values():
        inst = dict(pack["institution"], pack_id=pack["pack_id"], pack_version=pack["pack_version"])
        stmt = insert(Institution).values(**inst)
        session.execute(stmt.on_conflict_do_update(
            index_elements=[Institution.id],
            set_={k: stmt.excluded[k] for k in inst if k != "id"} | {"updated_at": stmt.excluded.updated_at},
        ))
        for src in pack["sources"]:
            row = {
                "id": src["id"], "institution_id": inst["id"], "name": src["name"], "base_url": src["base_url"],
                "documentation_url": src.get("documentation_url"), "allowed_hosts": src["allowed_hosts"],
                "connector": src["connector"],
                "config": src.get("config", {}) | {"max_requests_per_second": src.get("max_requests_per_second", 2)},
            }
            s = insert(SourceSystem).values(**row)
            session.execute(s.on_conflict_do_update(
                index_elements=[SourceSystem.id], set_={k: s.excluded[k] for k in row if k != "id"}
            ))
    session.commit()


def build_connector(source: SourceSystem, client: SourceHttpClient | None = None) -> Connector:
    cls = CONNECTORS[source.connector]
    config = dict(source.config, base_url=source.base_url)
    settings = get_settings()
    client = client or SourceHttpClient(
        source.allowed_hosts,
        max_requests_per_second=float(source.config.get("max_requests_per_second", 2)),
        timeout_s=settings.http_timeout_s,
        user_agent=settings.user_agent,
    )
    return cls(config, client)
