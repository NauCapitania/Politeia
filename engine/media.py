"""News persistence and conservative entity linking (exact full-name matches only)."""

import re
import uuid

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from connectors.base.protocol import Batch, normalize_name
from engine.db.models import DossierItem, Mandate, NewsItem, NewsMention, Person, SourceSystem, new_id


def _patterns(s: Session) -> list[tuple[str, str, re.Pattern, str]]:
    """(entity_kind, entity_id, pattern, confidence) for senators and curated actors (e.g. STF ministers)."""
    out = []
    people = s.execute(select(Person.id, Person.name).join(Mandate, Mandate.person_id == Person.id).distinct())
    for pid, name in people:
        if name and len(name.split()) >= 2:
            out.append(("person", pid, re.compile(rf"\b{re.escape(normalize_name(name))}\b"), "high"))
    for item in s.scalars(select(DossierItem).where(DossierItem.kind == "minister")):
        for alias in item.payload.get("aliases", []):
            out.append(("minister", item.id, re.compile(rf"\b{re.escape(normalize_name(alias))}\b"),
                        "high" if len(alias.split()) >= 2 else "medium"))
    return out


def link_mentions(s: Session, items: list[tuple[str, str]]) -> int:
    patterns = _patterns(s)
    rows = []
    for news_id, text in items:
        key = normalize_name(text)
        found = {}
        for kind, eid, pat, conf in patterns:
            m = pat.search(key)
            if m and (kind, eid) not in found:
                found[(kind, eid)] = dict(news_item_id=news_id, entity_kind=kind, entity_id=eid,
                                          matched_text=m.group(0), method="exact_name", confidence=conf)
        rows += found.values()
    ids = [i for i, _ in items]
    for i in range(0, len(ids), 500):
        s.execute(delete(NewsMention).where(NewsMention.news_item_id.in_(ids[i:i + 500])))
    for i in range(0, len(rows), 500):
        s.execute(insert(NewsMention).values(rows[i:i + 500]).on_conflict_do_nothing())
    return len(rows)


def persist_news(s: Session, source: SourceSystem, raw_ids: list[uuid.UUID], batch: Batch) -> int:
    linked = []
    for n in batch.news:
        values = dict(source_system_id=source.id, feed=n.feed, outlet=n.outlet, url=n.url, title=n.title,
                      excerpt=n.excerpt, published_at=n.published_at, topics=n.topics,
                      raw_record_id=raw_ids[n.ref.raw])
        stmt = insert(NewsItem).values(id=new_id("nws"), **values)
        nid = s.execute(stmt.on_conflict_do_update(
            index_elements=[NewsItem.url], set_={k: stmt.excluded[k] for k in values if k != "url"},
        ).returning(NewsItem.id)).scalar_one()
        linked.append((nid, f"{n.title} {n.excerpt or ''}"))
    link_mentions(s, linked)
    return len(batch.news)


def relink_all(s: Session) -> int:
    items = [(i, f"{t} {e or ''}") for i, t, e in s.execute(select(NewsItem.id, NewsItem.title, NewsItem.excerpt))]
    return link_mentions(s, items)
