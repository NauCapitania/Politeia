"""Persists connector batches: raw evidence first, then normalized records in a single transaction."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from connectors.base.http import SourceAccessError
from connectors.base.protocol import Batch, Identifier, Ref
from engine.capabilities.compute import recompute_capabilities
from engine.db.models import (
    EntityEvidence,
    ExternalIdentifier,
    IngestionRun,
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
    new_id,
)
from engine.registry import build_connector

log = logging.getLogger("politeia.sync")
PREFIX = {"person": "per", "party": "pty", "mandate": "man"}


def _now() -> datetime:
    return datetime.now(UTC)


def store_raw(session: Session, run: IngestionRun, source: SourceSystem, batch: Batch) -> list[uuid.UUID]:
    """Idempotent: an identical response (same URL and SHA-256) reuses the existing raw record."""
    ids = []
    for raw in batch.raw:
        r = raw.response
        payload, text = None, None
        if r.response_format == "json":
            payload = raw.json()
        else:
            text = r.text
        row = dict(
            id=uuid.uuid4(), first_run_id=run.id, last_run_id=run.id, institution_id=source.institution_id,
            source_system_id=source.id, record_kind=raw.record_kind, source_record_key=raw.source_record_key,
            url=r.url, http_status=r.status, response_format=r.response_format, content_sha256=r.sha256,
            payload=payload, payload_text=text, parser_version=f"{run.connector}@{run.connector_version}",
            response_headers=r.headers, retrieved_at=r.retrieved_at, last_seen_at=r.retrieved_at,
        )
        stmt = insert(RawRecord).values(**row)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_raw_records_source_system_id_url_content_sha256",
            set_={"last_seen_at": stmt.excluded.last_seen_at, "last_run_id": stmt.excluded.last_run_id},
        ).returning(RawRecord.id)
        ids.append(session.execute(stmt).scalar_one())
    return ids


class Persistor:
    def __init__(self, session: Session, run: IngestionRun, source: SourceSystem, raw_ids: list[uuid.UUID]):
        self.s = session
        self.run = run
        self.source = source
        self.raw_ids = raw_ids
        self.cache: dict[tuple[str, str, str], str] = {}
        self.now = _now()
        self.stats: dict[str, int] = {}

    def _count(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    def lookup(self, kind: str, ident: Identifier) -> str | None:
        key = (kind, ident.scheme, ident.value)
        if key not in self.cache:
            found = self.s.scalar(select(ExternalIdentifier.entity_id).where(
                ExternalIdentifier.entity_kind == kind, ExternalIdentifier.scheme == ident.scheme,
                ExternalIdentifier.value == ident.value))
            if found is None:
                return None
            self.cache[key] = found
        return self.cache[key]

    def resolve(self, kind: str, ident: Identifier) -> tuple[str, bool]:
        existing = self.lookup(kind, ident)
        if existing:
            return existing, False
        entity_id = new_id(PREFIX[kind])
        self.link(kind, entity_id, ident)
        self.cache[(kind, ident.scheme, ident.value)] = entity_id
        return entity_id, True

    def link(self, kind: str, entity_id: str, ident: Identifier) -> None:
        self.s.execute(insert(ExternalIdentifier).values(
            scheme=ident.scheme, value=ident.value, entity_kind=kind, entity_id=entity_id,
            source_system_id=self.source.id, quality=ident.quality,
        ).on_conflict_do_nothing())

    def evidence(self, kind: str, entity_id: str, ref: Ref) -> None:
        self.s.execute(insert(EntityEvidence).values(
            entity_kind=kind, entity_id=entity_id, raw_record_id=self.raw_ids[ref.raw], json_path=ref.path,
        ).on_conflict_do_nothing())

    def rel_evidence(self, kind: str, rel_id: str, ref: Ref) -> None:
        self.s.execute(insert(RelationshipEvidence).values(
            relationship_kind=kind, relationship_id=rel_id, raw_record_id=self.raw_ids[ref.raw], json_path=ref.path,
        ).on_conflict_do_nothing())

    # ---------------------------------------------------------------- members
    def persist_members(self, batch: Batch) -> None:
        inst = self.source.institution_id
        for p in batch.persons:
            pid, created = self.resolve("person", p.identifier)
            values = dict(name=p.name, full_name=p.full_name, gender=p.gender, photo_url=p.photo_url,
                          profile_url=p.profile_url, last_observed_at=self.now)
            if created:
                self.s.add(Person(id=pid, first_observed_at=self.now, **values))
                self.s.flush()
                self._count("persons_created")
            else:
                self.s.execute(update(Person).where(Person.id == pid).values(**values))
            for extra in p.extra_identifiers:
                self.link("person", pid, extra)
            self.evidence("person", pid, p.ref)

        for party in batch.parties:
            party_id, created = self.resolve("party", party.identifier)
            if created:
                self.s.add(Party(id=party_id, abbreviation=party.abbreviation, name=party.name,
                                 source_system_id=self.source.id))
                self.s.flush()
            elif party.name:
                self.s.execute(update(Party).where(Party.id == party_id).values(name=party.name))
            for extra in party.extra_identifiers:
                self.link("party", party_id, extra)
            self.evidence("party", party_id, party.ref)

        seen_mandates = []
        for m in batch.mandates:
            person_id = self.lookup("person", m.person)
            mid, created = self.resolve("mandate", m.identifier)
            values = dict(person_id=person_id, institution_id=inst, source_system_id=self.source.id,
                          role_type=m.role_type, represented_unit=m.represented_unit, participation=m.participation,
                          start_date=m.start_date, end_date=m.end_date, status=m.status,
                          epistemic_status=m.epistemic_status, attributes=m.attributes,
                          last_observed_at=self.now, last_seen_run_id=self.run.id)
            if created:
                self.s.add(Mandate(id=mid, first_observed_at=self.now, **values))
                self.s.flush()
            else:
                self.s.execute(update(Mandate).where(Mandate.id == mid).values(**values))
            seen_mandates.append(mid)
            self.rel_evidence("mandate", mid, m.ref)
        self._count("mandates", len(seen_mandates))

        if batch.complete_member_list:
            stale = self.s.execute(update(Mandate).where(
                Mandate.source_system_id == self.source.id, Mandate.status == "in_exercise",
                Mandate.id.not_in(seen_mandates)).values(status="not_observed"))
            self._count("mandates_no_longer_listed", stale.rowcount or 0)

        seen_current = []
        for pm in batch.memberships:
            person_id = self.lookup("person", pm.person)
            party_id = self.lookup("party", pm.party)
            if not person_id or not party_id:
                continue
            stmt = insert(PartyMembership).values(
                id=new_id("pmb"), person_id=person_id, party_id=party_id, institution_id=inst, basis=pm.basis,
                valid_from=pm.valid_from, valid_to=pm.valid_to, is_current=pm.is_current,
                epistemic_status=pm.epistemic_status, first_observed_at=self.now, last_observed_at=self.now,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_party_memberships_person_id_party_id_basis_valid_from",
                set_={"valid_to": stmt.excluded.valid_to, "is_current": stmt.excluded.is_current,
                      "last_observed_at": stmt.excluded.last_observed_at},
            ).returning(PartyMembership.id)
            pmb_id = self.s.execute(stmt).scalar_one()
            if pm.basis == "current_listing":
                seen_current.append(pmb_id)
            self.rel_evidence("party_membership", pmb_id, pm.ref)
        if batch.complete_member_list:
            self.s.execute(update(PartyMembership).where(
                PartyMembership.institution_id == inst, PartyMembership.basis == "current_listing",
                PartyMembership.is_current.is_(True), PartyMembership.id.not_in(seen_current),
            ).values(is_current=False))
        self._count("party_memberships", len(batch.memberships))

    # ---------------------------------------------------------------- proposals
    def persist_proposals(self, batch: Batch) -> None:
        inst = self.source.institution_id
        for p in batch.proposals:
            existing = self.s.scalar(select(Proposal.id).where(
                Proposal.source_system_id == self.source.id, Proposal.source_id == p.source_id))
            values = dict(institution_id=inst, source_system_id=self.source.id, source_id=p.source_id,
                          type_code=p.type_code, type_name=p.type_name, number=p.number, year=p.year,
                          identifier=p.identifier, title=p.title, ementa=p.ementa, introduced_on=p.introduced_on,
                          status=p.status, status_date=p.status_date, in_progress=p.in_progress,
                          official_url=p.official_url, attributes=p.attributes, last_observed_at=self.now)
            if existing:
                prop_id = existing
                self.s.execute(update(Proposal).where(Proposal.id == prop_id).values(**values))
            else:
                prop_id = new_id("prp")
                self.s.add(Proposal(id=prop_id, first_observed_at=self.now, **values))
                self.s.flush()
                self._count("proposals_created")
            self.evidence("proposal", prop_id, p.ref)
            for ref in p.extra_refs:
                self.evidence("proposal", prop_id, ref)

            ordinals = []
            for a in p.authors:
                person_id = self.lookup("person", a.person) if a.person else None
                resolution = a.resolution if person_id else "unresolved"
                attrs = dict(a.attributes)
                if a.person and not person_id:
                    attrs["unresolved_reason"] = ("no_member_with_this_name" if a.resolution == "name_match"
                                                  else "person_not_ingested")
                stmt = insert(ProposalAuthor).values(
                    id=new_id("pau"), proposal_id=prop_id, ordinal=a.ordinal, person_id=person_id,
                    author_name=a.name, author_kind=a.kind, resolution=resolution,
                    epistemic_status=a.epistemic_status, attributes=attrs)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_proposal_authors_proposal_id_ordinal",
                    set_={c: stmt.excluded[c] for c in ("person_id", "author_name", "author_kind", "resolution",
                                                        "epistemic_status", "attributes")},
                ).returning(ProposalAuthor.id)
                author_id = self.s.execute(stmt).scalar_one()
                ordinals.append(a.ordinal)
                self.rel_evidence("proposal_author", author_id, p.extra_refs[0] if p.extra_refs else p.ref)
                self._count("authors")
                if person_id:
                    self._count("authors_linked")
            if ordinals:
                self.s.query(ProposalAuthor).filter(
                    ProposalAuthor.proposal_id == prop_id, ProposalAuthor.ordinal.not_in(ordinals)
                ).delete(synchronize_session=False)

            for e in p.events:
                stmt = insert(LegislativeEvent).values(
                    id=new_id("evt"), institution_id=inst, proposal_id=prop_id, source_event_id=e.source_event_id,
                    event_type=e.event_type, event_date=e.event_date, description=e.description, body=e.body)
                self.s.execute(stmt.on_conflict_do_update(
                    constraint="uq_events_proposal_id_source_event_id",
                    set_={"event_date": stmt.excluded.event_date, "description": stmt.excluded.description,
                          "body": stmt.excluded.body}))
                self._count("events")
        self._count("proposals", len(batch.proposals))


def sync_source(factory: sessionmaker, source_id: str, scopes: list[str] | None = None, client=None) -> list[dict]:
    results = []
    with factory() as session:
        source = session.get(SourceSystem, source_id)
        connector = build_connector(source, client)
        for scope in scopes or connector.discover():
            results.append(_sync_scope(session, source, connector, scope))
        recompute_capabilities(session, source.institution_id)
        session.commit()
    return results


def _sync_scope(session: Session, source: SourceSystem, connector, scope: str) -> dict:
    run = IngestionRun(institution_id=source.institution_id, source_system_id=source.id, connector=connector.id,
                       connector_version=connector.version, scope=[scope], status="running", stats={})
    session.add(run)
    session.commit()
    try:
        batch = connector.fetch(scope)
    except SourceAccessError as exc:
        run.status, run.error, run.finished_at = "failed", str(exc), _now()
        session.commit()
        log.error("fetch failed", extra={"source": source.id, "scope": scope, "error": str(exc)})
        return {"run_id": str(run.id), "scope": scope, "status": run.status, "error": run.error}

    raw_ids = store_raw(session, run, source, batch)
    session.commit()  # raw evidence survives even if normalization fails

    try:
        connector.validate(connector.normalize(batch))
    except Exception as exc:  # noqa: BLE001 — unknown source shapes must not crash the run
        log.exception("normalization failed")
        batch.issues.append(_issue("error", "normalization_failed", repr(exc)))

    for issue in batch.issues:
        session.add(ValidationIssue(run_id=run.id, severity=issue.severity, code=issue.code, message=issue.message,
                                    context=issue.context,
                                    raw_record_id=raw_ids[issue.raw] if issue.raw is not None else None))
    stats = {"requests": connector.client.request_count, "raw_records": len(raw_ids),
             "deprecated_endpoints": dict(connector.client.deprecations)}
    if batch.has_errors:
        run.status, run.error = "failed", "validation errors; normalized data left unchanged"
        run.stats, run.finished_at = stats, _now()
        session.commit()
        return {"run_id": str(run.id), "scope": scope, "status": run.status, "error": run.error}

    persistor = Persistor(session, run, source, raw_ids)
    try:
        if scope == "members":
            persistor.persist_members(batch)
        else:
            persistor.persist_proposals(batch)
    except Exception as exc:
        session.rollback()
        run = session.get(IngestionRun, run.id)
        run.status, run.error, run.finished_at = "failed", f"persistence failed: {exc!r}", _now()
        session.commit()
        raise
    warnings = sum(1 for i in batch.issues if i.severity == "warning")
    run.status = "partial" if warnings else "succeeded"
    run.stats = stats | persistor.stats | {"warnings": warnings}
    run.finished_at = _now()
    session.commit()
    return {"run_id": str(run.id), "scope": scope, "status": run.status, "stats": run.stats}


def _issue(severity: str, code: str, message: str):
    from connectors.base.protocol import Issue

    return Issue(severity, code, message)


def last_run_time(session: Session, institution_id: str):
    return session.scalar(select(func.max(IngestionRun.finished_at)).where(
        IngestionRun.institution_id == institution_id, IngestionRun.status.in_(("succeeded", "partial"))))
