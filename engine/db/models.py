"""Relational model of the Politeia Engine.

Schemas:
- registry: institutions, source systems, capability state
- ingestion: runs, raw source records, validation issues
- core: persons, identifiers, mandates, parties, memberships, committees
- legislative: proposals, authorship, rapporteurs, events
- evidence: links from derived facts to the raw records that support them
- media: news items from public feeds and the entities they mention
- analysis: curated dossiers and claims (declarations, press reports, analyses) with sources
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

SCHEMAS = ("registry", "ingestion", "core", "legislative", "evidence", "media", "analysis")


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# --------------------------------------------------------------------------- registry


class Institution(Base):
    __tablename__ = "institutions"
    __table_args__ = {"schema": "registry"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    pack_id: Mapped[str] = mapped_column(String(64))
    pack_version: Mapped[str] = mapped_column(String(32))
    official_name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str] = mapped_column(Text)
    institution_type: Mapped[str] = mapped_column(String(64))
    jurisdiction: Mapped[str] = mapped_column(Text)
    geographic_scope: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(String(2))
    website: Mapped[str] = mapped_column(Text)
    seat_count: Mapped[int | None] = mapped_column(Integer)
    seat_count_status: Mapped[str] = mapped_column(String(16))
    seat_count_source: Mapped[str | None] = mapped_column(Text)
    terminology: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class SourceSystem(Base):
    __tablename__ = "source_systems"
    __table_args__ = {"schema": "registry"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text)
    documentation_url: Mapped[str | None] = mapped_column(Text)
    allowed_hosts: Mapped[list] = mapped_column(JSONB, default=list)
    connector: Mapped[str] = mapped_column(String(64))
    config: Mapped[dict] = mapped_column(JSONB, default=dict)


class CapabilityState(Base):
    """Derived from ingestion state; recomputed after every sync."""

    __tablename__ = "capability_states"
    __table_args__ = {"schema": "registry"}

    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"), primary_key=True)
    capability: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32))
    source_system_id: Mapped[str | None] = mapped_column(ForeignKey("registry.source_systems.id"))
    record_count: Mapped[int | None] = mapped_column(Integer)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage: Mapped[dict] = mapped_column(JSONB, default=dict)
    issues: Mapped[list] = mapped_column(JSONB, default=list)
    note: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = _now()


# --------------------------------------------------------------------------- ingestion


class IngestionRun(Base):
    __tablename__ = "runs"
    __table_args__ = {"schema": "ingestion"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"), index=True)
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"))
    connector: Mapped[str] = mapped_column(String(64))
    connector_version: Mapped[str] = mapped_column(String(32))
    scope: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16))  # running | succeeded | partial | failed
    started_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    @classmethod
    def is_source_fetch(cls):
        return cls.stats["mode"].as_string().is_distinct_from("replay")


class RawRecord(Base):
    """Original evidence. Never deleted by normalization."""

    __tablename__ = "raw_records"
    __table_args__ = (
        UniqueConstraint("source_system_id", "url", "content_sha256"),
        Index("ix_raw_records_source_key", "source_system_id", "record_kind", "source_record_key"),
        {"schema": "ingestion"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion.runs.id"))
    last_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion.runs.id"))
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"))
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"))
    record_kind: Mapped[str] = mapped_column(String(64))
    source_record_key: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    http_status: Mapped[int] = mapped_column(Integer)
    response_format: Mapped[str] = mapped_column(String(16))
    content_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict | list | None] = mapped_column(JSONB)
    payload_text: Mapped[str | None] = mapped_column(Text)
    parser_version: Mapped[str] = mapped_column(String(32))
    response_headers: Mapped[dict] = mapped_column(JSONB, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    __table_args__ = {"schema": "ingestion"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion.runs.id", ondelete="CASCADE"), index=True)
    severity: Mapped[str] = mapped_column(String(16))  # info | warning | error
    code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion.raw_records.id"))
    created_at: Mapped[datetime] = _now()


# --------------------------------------------------------------------------- core


class Person(Base):
    __tablename__ = "persons"
    __table_args__ = {"schema": "core"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    full_name: Mapped[str | None] = mapped_column(Text)
    alternative_names: Mapped[list] = mapped_column(JSONB, default=list)
    gender: Mapped[str | None] = mapped_column(String(32))
    photo_url: Mapped[str | None] = mapped_column(Text)
    profile_url: Mapped[str | None] = mapped_column(Text)
    first_observed_at: Mapped[datetime] = _now()
    last_observed_at: Mapped[datetime] = _now()


class ExternalIdentifier(Base):
    __tablename__ = "external_identifiers"
    __table_args__ = (
        UniqueConstraint("scheme", "value", "entity_kind"),
        Index("ix_external_identifiers_entity", "entity_kind", "entity_id"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scheme: Mapped[str] = mapped_column(String(96))
    value: Mapped[str] = mapped_column(Text)
    entity_kind: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"))
    quality: Mapped[str] = mapped_column(String(16))  # official | name-derived
    first_observed_at: Mapped[datetime] = _now()


class Party(Base):
    __tablename__ = "parties"
    __table_args__ = {"schema": "core"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    abbreviation: Mapped[str] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"), index=True)
    first_observed_at: Mapped[datetime] = _now()


class Mandate(Base):
    __tablename__ = "mandates"
    __table_args__ = (
        Index("ix_mandates_institution_status", "institution_id", "status"),
        Index("ix_mandates_validity", "institution_id", "start_date", "end_date"),
        {"schema": "core"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("core.persons.id"), index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"))
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"))
    role_type: Mapped[str] = mapped_column(String(64))
    represented_unit: Mapped[str | None] = mapped_column(Text)
    participation: Mapped[str | None] = mapped_column(String(32))  # holder | substitute_in_exercise
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32))  # in_exercise | not_observed
    epistemic_status: Mapped[str] = mapped_column(String(16))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_observed_at: Mapped[datetime] = _now()
    last_observed_at: Mapped[datetime] = _now()
    last_seen_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion.runs.id"))


class PartyMembership(Base):
    __tablename__ = "party_memberships"
    __table_args__ = (
        UniqueConstraint("person_id", "party_id", "basis", "valid_from", postgresql_nulls_not_distinct=True),
        Index("ix_party_memberships_validity", "person_id", "valid_from", "valid_to"),
        {"schema": "core"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("core.persons.id"), index=True)
    party_id: Mapped[str] = mapped_column(ForeignKey("core.parties.id"), index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"))
    basis: Mapped[str] = mapped_column(String(32))  # affiliation_history | current_listing
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean)
    epistemic_status: Mapped[str] = mapped_column(String(16))
    first_observed_at: Mapped[datetime] = _now()
    last_observed_at: Mapped[datetime] = _now()


class Committee(Base):
    __tablename__ = "committees"
    __table_args__ = (UniqueConstraint("institution_id", "source_code"), {"schema": "core"})

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    abbreviation: Mapped[str | None] = mapped_column(Text)
    committee_type: Mapped[str | None] = mapped_column(Text)
    source_code: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion.raw_records.id"))
    first_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommitteeMembership(Base):
    __tablename__ = "committee_memberships"
    __table_args__ = (
        Index("uq_committee_memberships_current", "committee_id", "person_id", "seat_kind", unique=True,
              postgresql_where=text("is_current")),
        {"schema": "core"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    committee_id: Mapped[str] = mapped_column(ForeignKey("core.committees.id"), index=True)
    mandate_id: Mapped[str | None] = mapped_column(ForeignKey("core.mandates.id"))
    person_id: Mapped[str] = mapped_column(ForeignKey("core.persons.id"), index=True)
    role: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    seat_kind: Mapped[str] = mapped_column(Text, default="titular", server_default="titular")  # titular | suplente
    party_abbreviation: Mapped[str | None] = mapped_column(Text)
    represented_unit: Mapped[str | None] = mapped_column(Text)
    bloc: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion.raw_records.id"))


# --------------------------------------------------------------------------- legislative


class Proposal(Base):
    __tablename__ = "proposals"
    __table_args__ = (
        UniqueConstraint("source_system_id", "source_id"),
        Index("ix_proposals_type_number_year", "institution_id", "type_code", "number", "year"),
        Index("ix_proposals_introduced", "institution_id", "introduced_on"),
        {"schema": "legislative"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"))
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"))
    source_id: Mapped[str] = mapped_column(Text)
    type_code: Mapped[str] = mapped_column(Text)
    type_name: Mapped[str] = mapped_column(Text)
    number: Mapped[str] = mapped_column(Text)
    year: Mapped[int] = mapped_column(Integer)
    identifier: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    ementa: Mapped[str | None] = mapped_column(Text)
    introduced_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str | None] = mapped_column(Text)
    status_date: Mapped[date | None] = mapped_column(Date)
    in_progress: Mapped[bool | None] = mapped_column(Boolean)
    official_url: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_observed_at: Mapped[datetime] = _now()
    last_observed_at: Mapped[datetime] = _now()


class ProposalAuthor(Base):
    __tablename__ = "proposal_authors"
    __table_args__ = (UniqueConstraint("proposal_id", "ordinal"), {"schema": "legislative"})

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("legislative.proposals.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    person_id: Mapped[str | None] = mapped_column(ForeignKey("core.persons.id"), index=True)
    author_name: Mapped[str] = mapped_column(Text)
    author_kind: Mapped[str] = mapped_column(String(32))  # member | external | committee | executive | other
    resolution: Mapped[str] = mapped_column(String(16))  # official_id | name_match | unresolved
    epistemic_status: Mapped[str] = mapped_column(String(16))
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)


class ProposalRapporteur(Base):
    __tablename__ = "proposal_rapporteurs"
    __table_args__ = {"schema": "legislative"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("legislative.proposals.id", ondelete="CASCADE"))
    person_id: Mapped[str | None] = mapped_column(ForeignKey("core.persons.id"))
    committee_id: Mapped[str | None] = mapped_column(ForeignKey("core.committees.id"))
    designated_on: Mapped[date | None] = mapped_column(Date)


class LegislativeEvent(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("proposal_id", "source_event_id"),
        Index("ix_events_proposal_date", "proposal_id", "event_date"),
        {"schema": "legislative"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"))
    proposal_id: Mapped[str] = mapped_column(ForeignKey("legislative.proposals.id", ondelete="CASCADE"))
    source_event_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- evidence


class EntityEvidence(Base):
    __tablename__ = "entity_evidence"
    __table_args__ = (
        UniqueConstraint("entity_kind", "entity_id", "raw_record_id", "json_path"),
        Index("ix_entity_evidence_entity", "entity_kind", "entity_id"),
        {"schema": "evidence"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_kind: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64))
    raw_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion.raw_records.id"), index=True)
    json_path: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = _now()


class RelationshipEvidence(Base):
    __tablename__ = "relationship_evidence"
    __table_args__ = (
        UniqueConstraint("relationship_kind", "relationship_id", "raw_record_id", "json_path"),
        Index("ix_relationship_evidence_rel", "relationship_kind", "relationship_id"),
        {"schema": "evidence"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    relationship_kind: Mapped[str] = mapped_column(String(32))
    relationship_id: Mapped[str] = mapped_column(String(64))
    raw_record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ingestion.raw_records.id"), index=True)
    json_path: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = _now()


# --------------------------------------------------------------------------- exercises, votes, speeches


class MandateExercise(Base):
    """A period in which a person actually held the seat (titular or suplente in exercise)."""

    __tablename__ = "mandate_exercises"
    __table_args__ = (
        UniqueConstraint("person_id", "source_exercise_id"),
        Index("ix_mandate_exercises_validity", "institution_id", "start_date", "end_date"),
        {"schema": "core"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"))
    person_id: Mapped[str] = mapped_column(ForeignKey("core.persons.id"), index=True)
    mandate_id: Mapped[str] = mapped_column(ForeignKey("core.mandates.id", ondelete="CASCADE"), index=True)
    source_exercise_id: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    end_cause_code: Mapped[str | None] = mapped_column(Text)
    end_cause: Mapped[str | None] = mapped_column(Text)


class VoteEvent(Base):
    __tablename__ = "vote_events"
    __table_args__ = (
        UniqueConstraint("source_system_id", "source_id"),
        Index("ix_vote_events_held_on", "institution_id", "held_on"),
        {"schema": "legislative"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("registry.institutions.id"))
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"))
    source_id: Mapped[str] = mapped_column(Text)
    session_code: Mapped[str | None] = mapped_column(Text)
    held_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(Text)
    matter: Mapped[str | None] = mapped_column(Text)
    matter_code: Mapped[str | None] = mapped_column(Text)
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("legislative.proposals.id"), index=True)
    secret: Mapped[bool] = mapped_column(Boolean)
    result: Mapped[str | None] = mapped_column(Text)
    totals: Mapped[dict] = mapped_column(JSONB, default=dict)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion.raw_records.id"), index=True)


class IndividualVote(Base):
    __tablename__ = "individual_votes"
    __table_args__ = {"schema": "legislative"}

    vote_event_id: Mapped[str] = mapped_column(
        ForeignKey("legislative.vote_events.id", ondelete="CASCADE"), primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("core.persons.id"), primary_key=True, index=True)
    party_abbreviation: Mapped[str | None] = mapped_column(Text)
    represented_unit: Mapped[str | None] = mapped_column(Text)
    vote_code: Mapped[str | None] = mapped_column(Text)
    vote_label: Mapped[str | None] = mapped_column(Text)


class Speech(Base):
    __tablename__ = "speeches"
    __table_args__ = (
        UniqueConstraint("source_system_id", "source_id"),
        Index("ix_speeches_person_date", "person_id", "delivered_on"),
        {"schema": "legislative"},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"))
    source_id: Mapped[str] = mapped_column(Text)
    person_id: Mapped[str] = mapped_column(ForeignKey("core.persons.id"))
    delivered_on: Mapped[date | None] = mapped_column(Date)
    kind: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    indexing: Mapped[str | None] = mapped_column(Text)
    session: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    text_url: Mapped[str | None] = mapped_column(Text)
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion.raw_records.id"), index=True)


# --------------------------------------------------------------------------- media


class NewsItem(Base):
    """Headline-level record of a public feed item. Full article text is never stored."""

    __tablename__ = "news_items"
    __table_args__ = (Index("ix_news_items_published", "published_at"), {"schema": "media"})

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system_id: Mapped[str] = mapped_column(ForeignKey("registry.source_systems.id"), index=True)
    feed: Mapped[str] = mapped_column(Text)
    outlet: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    topics: Mapped[list] = mapped_column(JSONB, default=list)
    raw_record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ingestion.raw_records.id"), index=True)
    first_observed_at: Mapped[datetime] = _now()


class NewsMention(Base):
    __tablename__ = "news_mentions"
    __table_args__ = (Index("ix_news_mentions_entity", "entity_kind", "entity_id"), {"schema": "media"})

    news_item_id: Mapped[str] = mapped_column(ForeignKey("media.news_items.id", ondelete="CASCADE"),
                                              primary_key=True)
    entity_kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    entity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    matched_text: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(String(32))  # exact_name | alias
    confidence: Mapped[str] = mapped_column(String(16))  # high | medium | low


# --------------------------------------------------------------------------- analysis


class DossierItem(Base):
    """Curated, source-cited knowledge (contests, ministers, case timeline, procedure) loaded from dossiers/."""

    __tablename__ = "dossier_items"
    __table_args__ = (Index("ix_dossier_items_dossier_kind", "dossier", "kind"), {"schema": "analysis"})

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    dossier: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSONB)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    as_of: Mapped[date | None] = mapped_column(Date)
    content_sha256: Mapped[str] = mapped_column(String(64))
    loaded_at: Mapped[datetime] = _now()


class Claim(Base):
    """A sourced statement about a subject: official fact, declaration, press report or analysis."""

    __tablename__ = "claims"
    __table_args__ = (
        Index("ix_claims_topic_subject", "topic", "subject_id"),
        {"schema": "analysis"},
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    dossier: Mapped[str] = mapped_column(String(64))
    topic: Mapped[str] = mapped_column(String(64))
    subject_kind: Mapped[str] = mapped_column(String(32))
    subject_id: Mapped[str | None] = mapped_column(String(64))
    subject_label: Mapped[str] = mapped_column(Text)
    position: Mapped[str | None] = mapped_column(Text)
    statement: Mapped[str] = mapped_column(Text)
    claim_type: Mapped[str] = mapped_column(String(32))  # official | declaration | press_report | analysis
    confidence: Mapped[str] = mapped_column(String(16))
    review_status: Mapped[str] = mapped_column(String(16))  # curated | auto | disputed
    stated_on: Mapped[date | None] = mapped_column(Date)
    sources: Mapped[list] = mapped_column(JSONB, default=list)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)
