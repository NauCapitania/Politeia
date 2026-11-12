"""Read model: assembles API contracts from the relational store."""

import re
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from engine.api import schemas as S
from engine.db.models import (
    CapabilityState,
    EntityEvidence,
    ExternalIdentifier,
    IngestionRun,
    Institution,
    LegislativeEvent,
    Mandate,
    Party,
    PartyMembership,
    Person,
    Proposal,
    ProposalAuthor,
    RawRecord,
    RelationshipEvidence,
    SourceSystem,
    ValidationIssue,
)

KIND_BY_PREFIX = {"ins": "institution", "per": "person", "pty": "party", "man": "mandate", "prp": "proposal"}
PARTICIPATION_LABEL = {"holder": "titular", "substitute_in_exercise": "suplente em exercício"}


def entity_kind(entity_id: str) -> str | None:
    return KIND_BY_PREFIX.get(entity_id.split("_", 1)[0])


# ------------------------------------------------------------------------- provenance


def _source_refs(s: Session, model, kind_col, id_col, kind: str, ids: list[str]) -> dict[str, list[S.SourceRef]]:
    if not ids:
        return {}
    rows = s.execute(
        select(id_col, model.json_path, RawRecord).join(RawRecord, RawRecord.id == model.raw_record_id)
        .where(kind_col == kind, id_col.in_(ids))
    ).all()
    out: dict[str, list[S.SourceRef]] = defaultdict(list)
    for eid, path, raw in rows:
        out[eid].append(_ref(raw, path))
    return out


def _ref(raw: RawRecord, path: str | None = None) -> S.SourceRef:
    return S.SourceRef(raw_record_id=str(raw.id), source_system_id=raw.source_system_id, record_kind=raw.record_kind,
                       url=raw.url, retrieved_at=raw.retrieved_at, json_path=path, content_sha256=raw.content_sha256)


def entity_sources(s: Session, kind: str, ids: list[str]) -> dict[str, list[S.SourceRef]]:
    return _source_refs(s, EntityEvidence, EntityEvidence.entity_kind, EntityEvidence.entity_id, kind, ids)


def relationship_sources(s: Session, kind: str, ids: list[str]) -> dict[str, list[S.SourceRef]]:
    return _source_refs(s, RelationshipEvidence, RelationshipEvidence.relationship_kind,
                        RelationshipEvidence.relationship_id, kind, ids)


def identifiers(s: Session, kind: str, ids: list[str]) -> dict[str, list[S.Identifier]]:
    out: dict[str, list[S.Identifier]] = defaultdict(list)
    if ids:
        for e in s.scalars(select(ExternalIdentifier).where(ExternalIdentifier.entity_kind == kind,
                                                            ExternalIdentifier.entity_id.in_(ids))):
            out[e.entity_id].append(S.Identifier(scheme=e.scheme, value=e.value, quality=e.quality))
    return out


# ------------------------------------------------------------------------- institutions


def capabilities(s: Session, inst_id: str) -> list[S.Capability]:
    rows = s.scalars(select(CapabilityState).where(CapabilityState.institution_id == inst_id)
                     .order_by(CapabilityState.capability))
    return [S.Capability(capability=c.capability, status=c.status, record_count=c.record_count, coverage=c.coverage,
                         last_success_at=c.last_success_at, note=c.note, issues=c.issues) for c in rows]


def institution(s: Session, inst: Institution) -> S.Institution:
    count = s.scalar(select(func.count()).where(Mandate.institution_id == inst.id, Mandate.status == "in_exercise"))
    last = s.scalar(select(func.max(IngestionRun.finished_at)).where(
        IngestionRun.institution_id == inst.id, IngestionRun.status.in_(("succeeded", "partial"))))
    sources = s.scalars(select(SourceSystem).where(SourceSystem.institution_id == inst.id))
    return S.Institution(
        id=inst.id, slug=inst.slug, official_name=inst.official_name, short_name=inst.short_name,
        institution_type=inst.institution_type, jurisdiction=inst.jurisdiction, geographic_scope=inst.geographic_scope,
        country=inst.country, website=inst.website, seat_count=inst.seat_count,
        seat_count_status=inst.seat_count_status, seat_count_source=inst.seat_count_source,
        terminology=inst.terminology, observed_member_count=count or 0, last_ingested_at=last,
        pack_id=inst.pack_id, pack_version=inst.pack_version,
        sources=[S.SourceSystemOut(id=x.id, name=x.name, base_url=x.base_url, documentation_url=x.documentation_url)
                 for x in sources],
    )


def _current_parties(s: Session, inst_id: str, person_ids: list[str]) -> dict[str, S.PartyRef]:
    rows = s.execute(select(PartyMembership.person_id, Party).join(Party, Party.id == PartyMembership.party_id).where(
        PartyMembership.institution_id == inst_id, PartyMembership.basis == "current_listing",
        PartyMembership.is_current.is_(True), PartyMembership.person_id.in_(person_ids))).all()
    return {pid: S.PartyRef(id=p.id, abbreviation=p.abbreviation, name=p.name) for pid, p in rows}


def members(s: Session, inst_id: str, *, q: str | None, party: str | None, unit: str | None,
            limit: int, offset: int) -> S.Page[S.Member]:
    stmt = (select(Mandate, Person).join(Person, Person.id == Mandate.person_id)
            .where(Mandate.institution_id == inst_id, Mandate.status == "in_exercise"))
    if q:
        stmt = stmt.where(or_(Person.name.ilike(f"%{q}%"), Person.full_name.ilike(f"%{q}%")))
    if unit:
        stmt = stmt.where(Mandate.represented_unit == unit)
    if party:
        stmt = stmt.where(Mandate.person_id.in_(select(PartyMembership.person_id).where(
            PartyMembership.party_id == party, PartyMembership.is_current.is_(True),
            PartyMembership.basis == "current_listing")))
    total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = s.execute(stmt.order_by(Person.name).limit(limit).offset(offset)).all()
    pids = [p.id for _, p in rows]
    parties = _current_parties(s, inst_id, pids)
    idents = identifiers(s, "person", pids)
    authored = dict(s.execute(select(ProposalAuthor.person_id, func.count()).where(
        ProposalAuthor.person_id.in_(pids)).group_by(ProposalAuthor.person_id)).all())
    items = [S.Member(
        person_id=p.id, mandate_id=m.id, name=p.name, full_name=p.full_name, gender=p.gender, photo_url=p.photo_url,
        profile_url=p.profile_url, role_type=m.role_type, represented_unit=m.represented_unit,
        participation=m.participation, start_date=m.start_date, end_date=m.end_date, party=parties.get(p.id),
        identifiers=idents.get(p.id, []), epistemic_status=m.epistemic_status, attributes=m.attributes,
        authored_proposals=authored.get(p.id, 0)) for m, p in rows]
    return S.Page(items=items, total=total, limit=limit, offset=offset)


def composition(s: Session, inst: Institution) -> S.Composition:
    page = members(s, inst.id, q=None, party=None, unit=None, limit=10_000, offset=0)
    groups: dict[str | None, list[S.Member]] = defaultdict(list)
    for m in page.items:
        groups[m.party.id if m.party else None].append(m)
    ordered = sorted(groups.values(), key=lambda g: (-len(g), g[0].party.abbreviation if g[0].party else "~"))
    seats: list[S.Seat] = []
    for group in ordered:
        for m in sorted(group, key=lambda x: (x.represented_unit or "", x.name)):
            seats.append(S.Seat(index=len(seats), person_id=m.person_id, mandate_id=m.mandate_id, name=m.name,
                                party_abbreviation=m.party.abbreviation if m.party else None,
                                party_id=m.party.id if m.party else None, represented_unit=m.represented_unit,
                                participation=m.participation, state="occupied"))
    discrepancy = None
    if inst.seat_count is not None:
        for i in range(len(seats), inst.seat_count):
            seats.append(S.Seat(index=i, person_id=None, mandate_id=None, name=None, party_abbreviation=None,
                                party_id=None, represented_unit=None, participation=None, state="unobserved"))
        if page.total != inst.seat_count:
            discrepancy = f"{page.total} members observed in source for {inst.seat_count} official seats"
    else:
        discrepancy = "Official seat count not verified; composition shows observed members only"
    cap = next((c for c in capabilities(s, inst.id) if c.capability == "party_composition"), None)
    return S.Composition(
        institution_id=inst.id, seat_count=inst.seat_count, seat_count_status=inst.seat_count_status,
        observed_members=page.total, seats=seats, discrepancy=discrepancy, capability=cap,
        groups=[S.CompositionGroup(party=g[0].party, count=len(g)) for g in ordered])


# ------------------------------------------------------------------------- proposals


def _authors(s: Session, prop_ids: list[str]) -> dict[str, list[S.Author]]:
    out: dict[str, list[S.Author]] = defaultdict(list)
    if prop_ids:
        for a in s.scalars(select(ProposalAuthor).where(ProposalAuthor.proposal_id.in_(prop_ids))
                           .order_by(ProposalAuthor.ordinal)):
            note = None
            reason = (a.attributes or {}).get("unresolved_reason")
            if reason == "person_not_ingested":
                note = "Official identifier present, person not among ingested current members"
            elif reason == "no_member_with_this_name":
                note = "No current member with exactly this name"
            elif a.resolution == "name_match":
                note = "Linked by exact normalized-name match (source has no member identifier)"
            out[a.proposal_id].append(S.Author(
                ordinal=a.ordinal, name=a.author_name, kind=a.author_kind, person_id=a.person_id,
                resolution=a.resolution, epistemic_status=a.epistemic_status,
                party=(a.attributes or {}).get("party"), note=note))
    return out


def _proposal(p: Proposal, authors: list[S.Author]) -> S.ProposalSummary:
    return S.ProposalSummary(
        id=p.id, institution_id=p.institution_id, identifier=p.identifier, type_code=p.type_code,
        type_name=p.type_name, number=p.number, year=p.year, ementa=p.ementa, introduced_on=p.introduced_on,
        date_semantics=(p.attributes or {}).get("date_semantics", "presentation"), status=p.status,
        status_date=p.status_date, in_progress=p.in_progress, official_url=p.official_url, authors=authors)


def proposals(s: Session, inst_id: str, *, q: str | None, type_code: str | None, author: str | None,
              limit: int, offset: int) -> S.Page[S.ProposalSummary]:
    stmt = select(Proposal).where(Proposal.institution_id == inst_id)
    if q:
        stmt = stmt.where(or_(Proposal.ementa.ilike(f"%{q}%"), Proposal.identifier.ilike(f"%{q}%")))
    if type_code:
        stmt = stmt.where(Proposal.type_code == type_code)
    if author:
        stmt = stmt.where(Proposal.id.in_(select(ProposalAuthor.proposal_id).where(ProposalAuthor.person_id == author)))
    total = s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(s.scalars(stmt.order_by(Proposal.introduced_on.desc().nulls_last(), Proposal.number.desc())
                          .limit(limit).offset(offset)))
    authors = _authors(s, [p.id for p in rows])
    return S.Page(items=[_proposal(p, authors.get(p.id, [])) for p in rows], total=total, limit=limit, offset=offset)


def proposal_types(s: Session, inst_id: str) -> list[dict[str, Any]]:
    rows = s.execute(select(Proposal.type_code, Proposal.type_name, func.count()).where(
        Proposal.institution_id == inst_id).group_by(Proposal.type_code, Proposal.type_name)
        .order_by(func.count().desc())).all()
    return [{"type_code": c, "type_name": n, "count": k} for c, n, k in rows]


# ------------------------------------------------------------------------- entities & relationships


def entity(s: Session, entity_id: str) -> S.Entity | None:
    kind = entity_kind(entity_id)
    if kind == "institution":
        inst = s.get(Institution, entity_id)
        if not inst:
            return None
        return S.Entity(id=inst.id, kind="institution", label=inst.official_name, institution_id=inst.id,
                        attributes={"short_name": inst.short_name, "website": inst.website}, identifiers=[],
                        sources=[])
    if kind == "person":
        p = s.get(Person, entity_id)
        if not p:
            return None
        m = s.scalar(select(Mandate).where(Mandate.person_id == p.id).order_by(Mandate.last_observed_at.desc()))
        attrs = {"full_name": p.full_name, "gender": p.gender, "photo_url": p.photo_url, "profile_url": p.profile_url,
                 "first_observed_at": p.first_observed_at, "last_observed_at": p.last_observed_at}
        return S.Entity(id=p.id, kind="person", label=p.name, institution_id=m.institution_id if m else None,
                        attributes=attrs, identifiers=identifiers(s, "person", [p.id]).get(p.id, []),
                        sources=entity_sources(s, "person", [p.id]).get(p.id, []))
    if kind == "party":
        p = s.get(Party, entity_id)
        if not p:
            return None
        src = s.get(SourceSystem, p.source_system_id)
        return S.Entity(id=p.id, kind="party", label=p.abbreviation, institution_id=src.institution_id,
                        attributes={"name": p.name, "scope_note": "Party identity is scoped to its source system"},
                        identifiers=identifiers(s, "party", [p.id]).get(p.id, []),
                        sources=entity_sources(s, "party", [p.id]).get(p.id, [])[:5])
    if kind == "mandate":
        m = s.get(Mandate, entity_id)
        if not m:
            return None
        attrs = {"person_id": m.person_id, "role_type": m.role_type, "represented_unit": m.represented_unit,
                 "participation": m.participation, "start_date": m.start_date, "end_date": m.end_date,
                 "status": m.status, **m.attributes}
        return S.Entity(id=m.id, kind="mandate", label=f"{m.role_type} · {m.represented_unit or ''}".strip(" ·"),
                        institution_id=m.institution_id, attributes=attrs,
                        identifiers=identifiers(s, "mandate", [m.id]).get(m.id, []),
                        sources=relationship_sources(s, "mandate", [m.id]).get(m.id, []))
    if kind == "proposal":
        p = s.get(Proposal, entity_id)
        if not p:
            return None
        summary = _proposal(p, _authors(s, [p.id]).get(p.id, []))
        events = s.scalars(select(LegislativeEvent).where(LegislativeEvent.proposal_id == p.id)
                           .order_by(LegislativeEvent.event_date.desc().nulls_last()))
        attrs = summary.model_dump(mode="json") | {"source_attributes": p.attributes, "events": [
            S.Event(id=e.id, event_type=e.event_type, event_date=e.event_date, description=e.description,
                    body=e.body).model_dump(mode="json") for e in events]}
        return S.Entity(id=p.id, kind="proposal", label=p.identifier, institution_id=p.institution_id,
                        attributes=attrs, identifiers=[S.Identifier(scheme=f"{p.source_system_id}:id",
                                                                    value=p.source_id, quality="official")],
                        sources=entity_sources(s, "proposal", [p.id]).get(p.id, []))
    return None


def relationships(s: Session, entity_id: str, limit: int = 200) -> list[S.Relationship]:
    kind = entity_kind(entity_id)
    rels: list[S.Relationship] = []
    if kind == "person":
        for m in s.scalars(select(Mandate).where(Mandate.person_id == entity_id)):
            inst = s.get(Institution, m.institution_id)
            part = PARTICIPATION_LABEL.get(m.participation or "", "")
            rels.append(S.Relationship(
                id=m.id, kind="holds_mandate", source=entity_id, target=m.institution_id,
                label=f"{inst.terminology.get('member', m.role_type)} {part}".strip(),
                explanation=f"Listed as current member by {inst.short_name} ({m.represented_unit or 'unit n/a'})"
                if m.status == "in_exercise" else "No longer listed as current member",
                valid_from=m.start_date, valid_to=m.end_date, is_current=m.status == "in_exercise",
                epistemic_status=m.epistemic_status))
        for pm, party in s.execute(select(PartyMembership, Party).join(Party, Party.id == PartyMembership.party_id)
                                   .where(PartyMembership.person_id == entity_id)):
            history = pm.basis == "affiliation_history"
            rels.append(S.Relationship(
                id=pm.id, kind="party_affiliation" if history else "current_party", source=entity_id, target=party.id,
                label=party.abbreviation,
                explanation="Party affiliation record from the source's affiliation history" if history
                else "Party shown in the institution's current member listing",
                valid_from=pm.valid_from, valid_to=pm.valid_to, is_current=pm.is_current,
                epistemic_status=pm.epistemic_status))
        for a, p in s.execute(select(ProposalAuthor, Proposal).join(Proposal, Proposal.id == ProposalAuthor.proposal_id)
                              .where(ProposalAuthor.person_id == entity_id)
                              .order_by(Proposal.introduced_on.desc().nulls_last()).limit(limit)):
            rels.append(S.Relationship(
                id=a.id, kind="authored", source=entity_id, target=p.id, label=p.identifier,
                explanation="Author by official parliamentary identifier" if a.resolution == "official_id"
                else "Author name matched to member name (no identifier in source)",
                valid_from=p.introduced_on, epistemic_status=a.epistemic_status))
    elif kind == "party":
        for pm, person in s.execute(select(PartyMembership, Person).join(Person, Person.id == PartyMembership.person_id)
                                    .where(PartyMembership.party_id == entity_id, PartyMembership.is_current.is_(True),
                                           PartyMembership.basis == "current_listing").limit(limit)):
            rels.append(S.Relationship(id=pm.id, kind="current_party", source=person.id, target=entity_id,
                                       label=person.name, explanation="Current member listed with this party",
                                       is_current=True, epistemic_status=pm.epistemic_status))
    elif kind == "proposal":
        prop = s.get(Proposal, entity_id)
        for a in s.scalars(select(ProposalAuthor).where(ProposalAuthor.proposal_id == entity_id)):
            if a.person_id:
                rels.append(S.Relationship(id=a.id, kind="authored", source=a.person_id, target=entity_id,
                                           label=a.author_name, explanation=f"Author ({a.resolution})",
                                           valid_from=prop.introduced_on, epistemic_status=a.epistemic_status))
        if prop:
            rels.append(S.Relationship(id=f"{entity_id}:inst", kind="submitted_to", source=entity_id,
                                       target=prop.institution_id, label="submitted to",
                                       explanation="Proposal registered by this institution's source system",
                                       epistemic_status="verified"))
    for kind_name in ("mandate", "party_membership", "proposal_author"):
        ids = [r.id for r in rels]
        refs = relationship_sources(s, kind_name, ids)
        for r in rels:
            if r.id in refs:
                r.sources = refs[r.id][:3]
    return rels


def timeline(s: Session, entity_id: str) -> list[S.TimelineItem]:
    items: list[S.TimelineItem] = []
    for r in relationships(s, entity_id):
        if r.valid_from:
            verb = {"holds_mandate": "Mandate starts", "party_affiliation": "Joins party", "authored": "Presents",
                    "current_party": "Party"}.get(r.kind, r.kind)
            items.append(S.TimelineItem(date=r.valid_from, kind=r.kind, label=f"{verb}: {r.label}",
                                        related_id=r.target if r.source == entity_id else r.source,
                                        epistemic_status=r.epistemic_status))
        if r.valid_to and r.kind == "party_affiliation":
            items.append(S.TimelineItem(date=r.valid_to, kind="party_disaffiliation", label=f"Leaves party: {r.label}",
                                        related_id=r.target, epistemic_status=r.epistemic_status))
    if entity_kind(entity_id) == "proposal":
        for e in s.scalars(select(LegislativeEvent).where(LegislativeEvent.proposal_id == entity_id)):
            if e.event_date:
                items.append(S.TimelineItem(date=e.event_date, kind=e.event_type,
                                            label=f"{e.body + ' · ' if e.body else ''}{e.description or ''}",
                                            epistemic_status="verified"))
    return sorted(items, key=lambda i: str(i.date), reverse=True)


def graph(s: Session, inst: Institution, focus: str | None, limit: int = 60) -> S.Graph:
    nodes: dict[str, S.GraphNode] = {}
    edges: list[S.Relationship] = []
    truncated = False

    def node(nid: str, kind: str, label: str, **attrs) -> None:
        nodes.setdefault(nid, S.GraphNode(id=nid, kind=kind, label=label, attributes=attrs))

    node(inst.id, "institution", inst.short_name)
    if not focus or focus == inst.id:
        comp = composition(s, inst)
        for g in comp.groups:
            if g.party:
                node(g.party.id, "party", g.party.abbreviation, members=g.count, name=g.party.name)
                edges.append(S.Relationship(
                    id=f"{inst.id}:{g.party.id}", kind="represented_in", source=g.party.id, target=inst.id,
                    label=f"{g.count} seats",
                    explanation=f"{g.count} current members listed with {g.party.abbreviation}",
                    is_current=True, epistemic_status="derived"))
        return S.Graph(focus=inst.id, nodes=list(nodes.values()), edges=edges, truncated=False)

    ent = entity(s, focus)
    if not ent:
        return S.Graph(focus=focus, nodes=list(nodes.values()), edges=[], truncated=False)
    node(ent.id, ent.kind, ent.label)
    rels = relationships(s, focus, limit=limit)
    if len(rels) >= limit:
        truncated = True
    for r in rels:
        for nid in (r.source, r.target):
            if nid in nodes:
                continue
            e = entity(s, nid) if entity_kind(nid) != "proposal" else None
            if entity_kind(nid) == "proposal":
                p = s.get(Proposal, nid)
                node(nid, "proposal", p.identifier, ementa=p.ementa, introduced_on=str(p.introduced_on or ""))
            elif e:
                node(nid, e.kind, e.label)
        edges.append(r)
    return S.Graph(focus=focus, nodes=list(nodes.values()), edges=edges, truncated=truncated)


# ------------------------------------------------------------------------- sources & ingestion

PATH_TOKEN = re.compile(r"\.([^.\[]+)|\[(\d+)\]")


def resolve_path(payload: Any, path: str | None) -> Any:
    if not path or not path.startswith("$") or payload is None:
        return None
    cur = payload
    for key, idx in PATH_TOKEN.findall(path[1:]):
        try:
            cur = cur[int(idx)] if idx else cur[key]
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    return cur


def source_record(s: Session, raw_id: str, path: str | None) -> S.SourceRecord | None:
    try:
        raw = s.get(RawRecord, uuid.UUID(raw_id))
    except ValueError:
        return None
    if not raw:
        return None
    excerpt = resolve_path(raw.payload, path) if path else None
    if excerpt is None and raw.payload_text and path and path.startswith("/projetos/projeto["):
        n = int(re.findall(r"\d+", path)[0])
        parts = re.findall(r"<projeto .*?</projeto>", raw.payload_text, re.S)
        excerpt = parts[n - 1] if 0 < n <= len(parts) else None
    return S.SourceRecord(ref=_ref(raw, path), http_status=raw.http_status, response_format=raw.response_format,
                          parser_version=raw.parser_version, first_run_id=str(raw.first_run_id),
                          last_run_id=str(raw.last_run_id), last_seen_at=raw.last_seen_at,
                          response_headers=raw.response_headers, excerpt=excerpt)


def ingestion_status(s: Session, inst_id: str | None, limit: int) -> S.IngestionStatus:
    stmt = select(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit)
    if inst_id:
        stmt = stmt.where(IngestionRun.institution_id == inst_id)
    runs = list(s.scalars(stmt))
    issues: dict[str, list[dict]] = defaultdict(list)
    if runs:
        rows = s.execute(select(ValidationIssue.run_id, ValidationIssue.severity, ValidationIssue.code,
                                func.count(), func.min(ValidationIssue.message))
                         .where(ValidationIssue.run_id.in_([r.id for r in runs]))
                         .group_by(ValidationIssue.run_id, ValidationIssue.severity, ValidationIssue.code)).all()
        for run_id, sev, code, n, msg in rows:
            issues[str(run_id)].append({"severity": sev, "code": code, "count": n, "example": msg})
    return S.IngestionStatus(runs=[S.IngestionRun(
        id=str(r.id), institution_id=r.institution_id, source_system_id=r.source_system_id, connector=r.connector,
        connector_version=r.connector_version, scope=r.scope, status=r.status, started_at=r.started_at,
        finished_at=r.finished_at, stats=r.stats, error=r.error, issues=issues.get(str(r.id), [])) for r in runs])
