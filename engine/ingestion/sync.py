"""Persists raw evidence before normalized records."""

import logging
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from connectors.base.http import SourceAccessError
from connectors.base.protocol import AuthorRecord, Batch, Identifier, Ref
from engine.capabilities.compute import recompute_capabilities
from engine.db.models import (
    Committee,
    CommitteeMembership,
    EntityEvidence,
    ExecutiveBody,
    ExternalIdentifier,
    IndividualVote,
    IngestionRun,
    LegislativeEvent,
    Mandate,
    MandateExercise,
    Party,
    PartyMembership,
    Person,
    Proposal,
    ProposalAuthor,
    RawRecord,
    RelationshipEvidence,
    SourceSystem,
    Speech,
    ValidationIssue,
    VoteEvent,
    new_id,
)
from engine.registry import build_connector

log = logging.getLogger("politeia.sync")
PREFIX = {"person": "per", "party": "pty", "mandate": "man", "committee": "com"}


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
                values["attributes"] = Mandate.attributes.op("||")(m.attributes)  # scopes enrich, never erase
                self.s.execute(update(Mandate).where(Mandate.id == mid).values(**values))
            seen_mandates.append(mid)
            self.rel_evidence("mandate", mid, m.ref)
        self._count("mandates", len(seen_mandates))

        if batch.complete_member_list:
            listed = (Mandate.status != "not_observed" if batch.complete_term_history
                      else Mandate.status == "in_exercise")
            stale = self.s.execute(update(Mandate).where(
                Mandate.source_system_id == self.source.id, listed,
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

    # ---------------------------------------------------------------- composition, votes, speeches
    def ensure_person(self, ident: Identifier, name: str, evidence: RawRecord | None = None) -> str:
        pid, created = self.resolve("person", ident)
        if created:
            self.s.add(Person(id=pid, name=name, first_observed_at=evidence.retrieved_at if evidence else self.now,
                              last_observed_at=evidence.last_seen_at if evidence else self.now))
            self.s.flush()
            self._count("persons_created")
        return pid

    def persist_composition(self, batch: Batch) -> None:
        self.persist_members(batch)
        inst = self.source.institution_id
        rows = []
        for e in batch.exercises:
            person_id = self.lookup("person", e.person)
            mandate_id = self.lookup("mandate", e.mandate)
            if not person_id or not mandate_id:
                continue
            rows.append(dict(institution_id=inst, person_id=person_id, mandate_id=mandate_id,
                             source_exercise_id=e.source_exercise_id, start_date=e.start_date, end_date=e.end_date,
                             end_cause_code=e.end_cause_code, end_cause=e.end_cause))
        for i in range(0, len(rows), 500):
            stmt = insert(MandateExercise).values(rows[i:i + 500])
            self.s.execute(stmt.on_conflict_do_update(
                constraint="uq_mandate_exercises_person_id_source_exercise_id",
                set_={k: stmt.excluded[k] for k in ("mandate_id", "start_date", "end_date", "end_cause_code",
                                                    "end_cause")}))
        self._count("exercises", len(rows))

    def persist_votes(self, batch: Batch) -> None:
        inst = self.source.institution_id
        n_votes = 0
        for ev in batch.vote_events:
            existing = self.s.scalar(select(VoteEvent.id).where(
                VoteEvent.source_system_id == self.source.id, VoteEvent.source_id == ev.source_id))
            vid = existing or new_id("vot")
            proposal_id = None
            if ev.matter_code:
                proposal_id = self.s.scalar(select(Proposal.id).where(
                    Proposal.institution_id == inst, or_(
                        Proposal.attributes["codigo_materia"].astext == ev.matter_code,
                        and_(Proposal.source_system_id == self.source.id, Proposal.source_id == ev.matter_code))))
            values = dict(institution_id=inst, source_system_id=self.source.id, source_id=ev.source_id,
                          session_code=ev.session_code, held_on=ev.held_on, description=ev.description,
                          matter=ev.matter, matter_code=ev.matter_code, proposal_id=proposal_id, secret=ev.secret,
                          result=ev.result, totals=ev.totals, attributes=ev.attributes,
                          raw_record_id=self.raw_ids[ev.ref.raw])
            stmt = insert(VoteEvent).values(id=vid, **values)
            self.s.execute(stmt.on_conflict_do_update(index_elements=[VoteEvent.id], set_=values))
            rows = {}
            for v in ev.votes:
                pid = self.ensure_person(v.person, v.name)
                rows[pid] = dict(vote_event_id=vid, person_id=pid, party_abbreviation=v.party,
                                 represented_unit=v.unit, vote_code=v.vote_code, vote_label=v.vote_label)
            if ev.secret:  # a secret ballot keeps only what the source still lists (participation), never stale choices
                self.s.execute(delete(IndividualVote).where(
                    IndividualVote.vote_event_id == vid, IndividualVote.person_id.not_in(list(rows))))
            if rows:
                stmt = insert(IndividualVote).values(list(rows.values()))
                self.s.execute(stmt.on_conflict_do_update(
                    index_elements=[IndividualVote.vote_event_id, IndividualVote.person_id],
                    set_={k: stmt.excluded[k] for k in ("party_abbreviation", "represented_unit", "vote_code",
                                                        "vote_label")}))
            n_votes += len(rows)
        self._count("vote_events", len(batch.vote_events))
        self._count("individual_votes", n_votes)

    def persist_speeches(self, batch: Batch) -> None:
        rows = []
        for sp in batch.speeches:
            pid = self.lookup("person", sp.person)
            if not pid:
                self._count("speeches_unknown_person")
                continue
            existing = self.s.scalar(select(Speech.id).where(
                Speech.source_system_id == self.source.id, Speech.source_id == sp.source_id))
            rows.append(dict(id=existing or new_id("spc"), source_system_id=self.source.id, source_id=sp.source_id,
                             person_id=pid, delivered_on=sp.delivered_on, kind=sp.kind, summary=sp.summary,
                             indexing=sp.indexing, session=sp.session, url=sp.url, text_url=sp.text_url,
                             raw_record_id=self.raw_ids[sp.ref.raw]))
        for i in range(0, len(rows), 500):
            stmt = insert(Speech).values(rows[i:i + 500])
            self.s.execute(stmt.on_conflict_do_update(
                constraint="uq_speeches_source_system_id_source_id",
                set_={k: stmt.excluded[k] for k in ("person_id", "delivered_on", "kind", "summary", "indexing",
                                                    "session", "url", "text_url", "raw_record_id")}))
        self._count("speeches", len(rows))

    def persist_committees(self, batch: Batch) -> None:
        """Upsert committees and their current seats; seats no longer listed are closed, not deleted."""
        inst, today = self.source.institution_id, self.now.date()
        n_members = 0
        for c in batch.committees:
            cid, created = self.resolve("committee", Identifier(c.scheme, c.source_code))
            values = dict(institution_id=inst, name=c.name, abbreviation=c.abbreviation,
                          committee_type=c.committee_type, source_code=c.source_code, attributes=c.attributes,
                          raw_record_id=self.raw_ids[c.ref.raw], last_observed_at=self.now)
            stmt = insert(Committee).values(id=cid, first_observed_at=self.now, **values)
            self.s.execute(stmt.on_conflict_do_update(index_elements=[Committee.id], set_=values))
            self.evidence("committee", cid, c.ref)
            self._count("committees_created" if created else "committees_updated")
            rows = {}
            for m in c.members:
                pid = self.ensure_person(m.person, m.name)
                rows[(pid, m.seat_kind)] = dict(
                    id=new_id("cms"), committee_id=cid, person_id=pid, seat_kind=m.seat_kind, role=m.role,
                    party_abbreviation=m.party, represented_unit=m.unit, bloc=m.bloc, is_current=True,
                    valid_from=today, last_observed_at=self.now, raw_record_id=self.raw_ids[m.ref.raw])
            if rows:
                stmt = insert(CommitteeMembership).values(list(rows.values()))
                # Only an open period is extended; a senator returning after leaving starts a new row.
                self.s.execute(stmt.on_conflict_do_update(
                    index_elements=["committee_id", "person_id", "seat_kind"],
                    index_where=text("is_current"),
                    set_={k: stmt.excluded[k] for k in ("role", "party_abbreviation", "represented_unit", "bloc",
                                                        "last_observed_at", "raw_record_id")}))
            self.s.execute(update(CommitteeMembership).where(
                CommitteeMembership.committee_id == cid, CommitteeMembership.is_current.is_(True),
                CommitteeMembership.last_observed_at < self.now).values(is_current=False, valid_to=today))
            n_members += len(rows)
        self._count("committee_members", n_members)
        if not any(i.code in ("committee_list_unavailable", "committee_unavailable") for i in batch.issues):
            # Complete listing: committees absent from it are no longer active (e.g. a CPI that ended).
            gone = select(Committee.id).where(Committee.institution_id == inst, or_(
                Committee.last_observed_at.is_(None), Committee.last_observed_at < self.now))
            self.s.execute(update(CommitteeMembership).where(
                CommitteeMembership.committee_id.in_(gone), CommitteeMembership.is_current.is_(True))
                .values(is_current=False, valid_to=today))
            self.s.execute(update(Committee).where(Committee.id.in_(gone)).values(
                attributes=Committee.attributes.op("||")(func.jsonb_build_object("active", False))))

    def persist_news(self, batch: Batch) -> None:
        from engine.media import persist_news

        self._count("news", persist_news(self.s, self.source, self.raw_ids, batch))

    # ---------------------------------------------------------------- proposals
    def _has_newer_proposal_evidence(self, proposal_id: str, replayed: list[RawRecord]) -> bool:
        newer = [and_(RawRecord.record_kind == raw.record_kind, RawRecord.id != raw.id,
                      RawRecord.last_seen_at > raw.last_seen_at) for raw in replayed]
        return self.s.scalar(select(EntityEvidence.id).join(RawRecord, RawRecord.id == EntityEvidence.raw_record_id)
                             .where(EntityEvidence.entity_kind == "proposal", EntityEvidence.entity_id == proposal_id,
                                    or_(*newer)).limit(1)) is not None

    def _link_missing_replayed_authors(self, proposal_id: str, authors: list[AuthorRecord],
                                      detail: RawRecord, detail_ref: Ref) -> None:
        for author in authors:
            if not author.person or author.kind != "member" or author.resolution != "official_id" or author.name == "?":
                continue
            saved = self.s.scalar(select(ProposalAuthor).join(RelationshipEvidence, and_(
                RelationshipEvidence.relationship_kind == "proposal_author",
                RelationshipEvidence.relationship_id == ProposalAuthor.id,
                RelationshipEvidence.raw_record_id == detail.id,
            )).where(
                ProposalAuthor.proposal_id == proposal_id, ProposalAuthor.ordinal == author.ordinal,
                ProposalAuthor.person_id.is_(None), ProposalAuthor.author_name == author.name,
                ProposalAuthor.author_kind == author.kind,
                ProposalAuthor.attributes["source_code"].as_string() == author.person.value,
            ))
            if saved is None:
                continue
            created = self.lookup("person", author.person) is None
            saved.person_id = self.ensure_person(author.person, author.name, detail)
            if created:
                self.evidence("person", saved.person_id, detail_ref)
            saved.resolution = author.resolution
            saved.attributes = {key: value for key, value in saved.attributes.items() if key != "unresolved_reason"}
            self._count("authors_linked")

    def persist_proposals(self, batch: Batch, evidence: list[RawRecord] | None = None) -> None:
        inst = self.source.institution_id
        for p in batch.proposals:
            list_record = evidence[p.ref.raw] if evidence is not None else None
            detail_ref = p.extra_refs[0] if p.extra_refs else p.ref
            query = select(Proposal.id).where(
                Proposal.source_system_id == self.source.id, Proposal.source_id == p.source_id)
            if evidence is not None:
                query = query.with_for_update()
            existing = self.s.scalar(query)
            if existing and evidence is not None:
                replayed = [evidence[ref.raw] for ref in (p.ref, *p.extra_refs)]
                if self._has_newer_proposal_evidence(existing, replayed):
                    if p.extra_refs:
                        self._link_missing_replayed_authors(existing, p.authors, evidence[detail_ref.raw], detail_ref)
                    self._count("proposals_replay_skipped_newer")
                    continue
            values = dict(institution_id=inst, source_system_id=self.source.id, source_id=p.source_id,
                          type_code=p.type_code, type_name=p.type_name, number=p.number, year=p.year,
                          identifier=p.identifier, title=p.title, ementa=p.ementa, introduced_on=p.introduced_on,
                          status=p.status, status_date=p.status_date, in_progress=p.in_progress,
                          official_url=p.official_url, attributes=p.attributes, last_observed_at=self.now)
            if existing:
                prop_id = existing
                if p.attributes.get("detail_missing"):  # list-only row: keep details saved by earlier runs
                    values = {k: v for k, v in values.items() if v is not None and k != "attributes"}
                if list_record:
                    values.pop("last_observed_at")
                self.s.execute(update(Proposal).where(Proposal.id == prop_id).values(**values))
            else:
                prop_id = new_id("prp")
                if list_record:
                    values["last_observed_at"] = list_record.last_seen_at
                self.s.add(Proposal(id=prop_id, first_observed_at=list_record.retrieved_at if list_record else self.now,
                                    **values))
                self.s.flush()
                self._count("proposals_created")
            self.evidence("proposal", prop_id, p.ref)
            for ref in p.extra_refs:
                self.evidence("proposal", prop_id, ref)

            ordinals = []
            for a in p.authors:
                person_id = self.lookup("person", a.person) if a.person else None
                if (not person_id and a.person and a.kind == "member"
                        and a.resolution == "official_id" and a.name != "?"):
                    person_id = self.ensure_person(a.person, a.name, evidence[detail_ref.raw] if evidence else None)
                    self.evidence("person", person_id, detail_ref)
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
                self.rel_evidence("proposal_author", author_id, detail_ref)
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

    # ---------------------------------------------------------------- executive structure
    def persist_executive_structure(self, batch: Batch) -> None:
        """Upsert SIORG organs/entities; those missing from a complete listing stay, flagged not current."""
        inst = self.source.institution_id
        existing = dict(self.s.execute(select(ExecutiveBody.siorg_code, ExecutiveBody.id)
                                       .where(ExecutiveBody.institution_id == inst)).all())
        seen = []
        for b in batch.executive_bodies:
            values = dict(source_system_id=self.source.id, parent_code=b.parent_code, unit_type=b.unit_type,
                          name=b.name, acronym=b.acronym, legal_nature=b.legal_nature, competence=b.competence,
                          purpose=b.purpose, mission=b.mission, legal_basis=b.legal_basis, site=b.site,
                          version=b.version, version_start=b.version_start, is_current=True,
                          attributes=b.attributes, raw_record_id=self.raw_ids[b.ref.raw], last_observed_at=self.now,
                          last_seen_run_id=self.run.id)
            body_id = existing.get(b.code)
            if body_id:
                self.s.execute(update(ExecutiveBody).where(ExecutiveBody.id == body_id).values(**values))
                self._count("executive_bodies_updated")
            else:
                body_id = new_id("exb")
                self.s.add(ExecutiveBody(id=body_id, institution_id=inst, siorg_code=b.code,
                                         first_observed_at=self.now, **values))
                self.s.flush()
                self._count("executive_bodies_created")
            seen.append(body_id)
            self.evidence("executive_body", body_id, b.ref)
        if seen:
            gone = self.s.execute(update(ExecutiveBody).where(
                ExecutiveBody.institution_id == inst, ExecutiveBody.is_current.is_(True),
                ExecutiveBody.id.not_in(seen)).values(is_current=False))
            self._count("executive_bodies_no_longer_listed", gone.rowcount or 0)


def sync_source(factory: sessionmaker, source_id: str, scopes: list[str] | None = None, client=None) -> list[dict]:
    results = []
    with factory() as session:
        source = session.get(SourceSystem, source_id)
        connector = build_connector(source, client)
        wanted = connector.discover() if scopes is None else [sc for sc in scopes if sc in connector.scopes]
        for scope in wanted:
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
    stats = {"requests": connector.client.request_count, "raw_records": len(raw_ids),
             "deprecated_endpoints": dict(connector.client.deprecations)}
    return process_batch(session, source, run, batch, raw_ids, stats,
                         lambda value: connector.validate(connector.normalize(value)))


def process_batch(session: Session, source: SourceSystem, run: IngestionRun, batch: Batch,
                  raw_ids: list[uuid.UUID], stats: dict, normalize: Callable[[Batch], Batch],
                  evidence: list[RawRecord] | None = None) -> dict:
    scope = batch.scope
    try:
        normalize(batch)
    except Exception as exc:  # noqa: BLE001 — unknown source shapes must not crash the run
        log.exception("normalization failed")
        batch.issues.append(_issue("error", "normalization_failed", repr(exc)))

    for issue in batch.issues:
        session.add(ValidationIssue(run_id=run.id, severity=issue.severity, code=issue.code, message=issue.message,
                                    context=issue.context,
                                    raw_record_id=raw_ids[issue.raw] if issue.raw is not None else None))
    warnings = sum(1 for i in batch.issues if i.severity == "warning")
    if batch.has_errors or (warnings and not raw_ids):
        reason = "validation errors" if batch.has_errors else "no source responses"
        run.status, run.error = "failed", f"{reason}; normalized data left unchanged"
        run.stats, run.finished_at = stats | {"warnings": warnings}, _now()
        session.commit()
        return {"run_id": str(run.id), "scope": scope, "status": run.status, "error": run.error}

    persistor = Persistor(session, run, source, raw_ids)
    try:
        if scope == "proposals":
            if evidence is None:
                persistor.persist_proposals(batch)
            else:
                for proposal in batch.proposals:
                    persistor.persist_proposals(replace(batch, proposals=[proposal]), evidence)
                    run.stats = stats | persistor.stats | {"warnings": warnings}
                    session.commit()
        else:
            {"members": persistor.persist_members, "composition": persistor.persist_composition,
             "votes": persistor.persist_votes, "speeches": persistor.persist_speeches, "news": persistor.persist_news,
             "committees": persistor.persist_committees,
             "structure": persistor.persist_executive_structure}[scope](batch)
    except Exception as exc:
        session.rollback()
        run = session.get(IngestionRun, run.id)
        run.status, run.error, run.finished_at = "failed", f"persistence failed: {exc!r}", _now()
        session.commit()
        raise
    warnings += 1 if persistor.stats.get("speeches_unknown_person") else 0
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
        IngestionRun.institution_id == institution_id, IngestionRun.status.in_(("succeeded", "partial")),
        IngestionRun.is_source_fetch()))
