"""Public API contracts. Internal ORM models are never returned directly."""

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")
EntityKind = Literal["institution", "person", "party", "mandate", "proposal"]


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class SourceRef(BaseModel):
    raw_record_id: str
    source_system_id: str
    record_kind: str
    url: str
    retrieved_at: datetime
    json_path: str | None = None
    content_sha256: str


class SourceSystemOut(BaseModel):
    id: str
    name: str
    base_url: str
    documentation_url: str | None


class Capability(BaseModel):
    capability: str
    status: str
    record_count: int | None
    coverage: dict[str, Any]
    last_success_at: datetime | None
    note: str | None
    issues: list[dict[str, Any]]


class Institution(BaseModel):
    id: str
    slug: str
    official_name: str
    short_name: str
    institution_type: str
    jurisdiction: str
    geographic_scope: str
    country: str
    website: str
    seat_count: int | None
    seat_count_status: str
    seat_count_source: str | None
    terminology: dict[str, str]
    observed_member_count: int
    last_ingested_at: datetime | None
    sources: list[SourceSystemOut]
    pack_id: str
    pack_version: str


class Identifier(BaseModel):
    scheme: str
    value: str
    quality: str


class PartyRef(BaseModel):
    id: str
    abbreviation: str
    name: str | None


class Member(BaseModel):
    person_id: str
    mandate_id: str
    name: str
    full_name: str | None
    gender: str | None
    photo_url: str | None
    profile_url: str | None
    role_type: str
    represented_unit: str | None
    participation: str | None
    start_date: date | None
    end_date: date | None
    party: PartyRef | None
    identifiers: list[Identifier]
    epistemic_status: str
    attributes: dict[str, Any]
    authored_proposals: int


class CompositionGroup(BaseModel):
    party: PartyRef | None
    count: int


class Seat(BaseModel):
    index: int
    person_id: str | None
    mandate_id: str | None
    name: str | None
    party_abbreviation: str | None
    party_id: str | None
    represented_unit: str | None
    participation: str | None
    state: Literal["occupied", "unobserved"]


class Composition(BaseModel):
    institution_id: str
    seat_count: int | None
    seat_count_status: str
    observed_members: int
    seats: list[Seat]
    groups: list[CompositionGroup]
    discrepancy: str | None
    capability: Capability | None


class Author(BaseModel):
    ordinal: int
    name: str
    kind: str
    person_id: str | None
    resolution: str
    epistemic_status: str
    party: str | None = None
    note: str | None = None


class ProposalSummary(BaseModel):
    id: str
    institution_id: str
    identifier: str
    type_code: str
    type_name: str
    number: str
    year: int
    ementa: str | None
    introduced_on: date | None
    date_semantics: str
    status: str | None
    status_date: date | None
    in_progress: bool | None
    official_url: str | None
    authors: list[Author]


class Event(BaseModel):
    id: str
    event_type: str
    event_date: datetime | None
    description: str | None
    body: str | None


class Entity(BaseModel):
    id: str
    kind: EntityKind
    label: str
    institution_id: str | None
    attributes: dict[str, Any]
    identifiers: list[Identifier]
    sources: list[SourceRef]


class Relationship(BaseModel):
    id: str
    kind: str
    source: str
    target: str
    label: str
    explanation: str
    valid_from: date | None = None
    valid_to: date | None = None
    is_current: bool | None = None
    epistemic_status: str
    sources: list[SourceRef] = Field(default_factory=list)


class TimelineItem(BaseModel):
    date: date | datetime
    kind: str
    label: str
    related_id: str | None = None
    epistemic_status: str


class GraphNode(BaseModel):
    id: str
    kind: str
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class Graph(BaseModel):
    focus: str
    nodes: list[GraphNode]
    edges: list[Relationship]
    truncated: bool


class SourceRecord(BaseModel):
    ref: SourceRef
    http_status: int
    response_format: str
    parser_version: str
    first_run_id: str
    last_run_id: str
    last_seen_at: datetime
    response_headers: dict[str, str]
    excerpt: Any = None


class IngestionRun(BaseModel):
    id: str
    institution_id: str
    source_system_id: str
    connector: str
    connector_version: str
    scope: list[str]
    status: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict[str, Any]
    error: str | None
    issues: list[dict[str, Any]]


class IngestionStatus(BaseModel):
    runs: list[IngestionRun]
