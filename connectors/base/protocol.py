"""Connector contract shared by every institution pack.

A connector knows one source system. It fetches raw responses and normalizes them into
source-neutral records; the engine (engine.ingestion.sync) persists them with provenance.
"""

import json
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from connectors.base.http import FetchedResponse, SourceHttpClient

EPISTEMIC = ("verified", "extracted", "conflicting", "unknown", "derived")


@dataclass
class RawResponse:
    """A fetched response plus what it represents in the source."""

    response: FetchedResponse
    record_kind: str
    source_record_key: str | None = None
    parsed: Any = None

    def json(self) -> Any:
        if self.parsed is None:
            self.parsed = json.loads(self.response.content)
        return self.parsed


@dataclass(frozen=True)
class Ref:
    """Points to the raw response (by index in the fetch result) and the path inside it."""

    raw: int
    path: str


@dataclass(frozen=True)
class Identifier:
    scheme: str
    value: str
    quality: str = "official"  # official | name-derived


@dataclass
class PersonRecord:
    identifier: Identifier
    name: str
    ref: Ref
    full_name: str | None = None
    gender: str | None = None
    photo_url: str | None = None
    profile_url: str | None = None
    extra_identifiers: list[Identifier] = field(default_factory=list)


@dataclass
class PartyRecord:
    identifier: Identifier
    abbreviation: str
    ref: Ref
    name: str | None = None
    extra_identifiers: list[Identifier] = field(default_factory=list)


@dataclass
class MandateRecord:
    identifier: Identifier
    person: Identifier
    role_type: str
    ref: Ref
    represented_unit: str | None = None
    participation: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    status: str = "in_exercise"
    epistemic_status: str = "verified"
    attributes: dict = field(default_factory=dict)


@dataclass
class PartyMembershipRecord:
    person: Identifier
    party: Identifier
    basis: str
    is_current: bool
    ref: Ref
    valid_from: date | None = None
    valid_to: date | None = None
    epistemic_status: str = "verified"


@dataclass
class AuthorRecord:
    ordinal: int
    name: str
    kind: str  # member | external | committee | executive | other
    person: Identifier | None
    resolution: str  # official_id | name_match | unresolved
    epistemic_status: str
    attributes: dict = field(default_factory=dict)


@dataclass
class EventRecord:
    source_event_id: str
    event_type: str
    event_date: datetime | None
    description: str | None
    body: str | None = None


@dataclass
class ProposalRecord:
    source_id: str
    type_code: str
    type_name: str
    number: str
    year: int
    ref: Ref
    ementa: str | None = None
    title: str | None = None
    introduced_on: date | None = None
    status: str | None = None
    status_date: date | None = None
    in_progress: bool | None = None
    official_url: str | None = None
    authors: list[AuthorRecord] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)
    extra_refs: list[Ref] = field(default_factory=list)

    @property
    def identifier(self) -> str:
        return f"{self.type_code} {self.number}/{self.year}"


@dataclass
class ExerciseRecord:
    """A period in which `person` actually sat in the seat of `mandate`."""

    person: Identifier
    mandate: Identifier
    source_exercise_id: str
    ref: Ref
    start_date: date | None = None
    end_date: date | None = None
    end_cause_code: str | None = None
    end_cause: str | None = None


@dataclass
class IndividualVoteRecord:
    person: Identifier
    name: str
    party: str | None
    unit: str | None
    vote_code: str | None
    vote_label: str | None


@dataclass
class VoteEventRecord:
    source_id: str
    ref: Ref
    held_on: date | None
    description: str | None
    secret: bool
    result: str | None
    session_code: str | None = None
    matter: str | None = None
    matter_code: str | None = None
    totals: dict = field(default_factory=dict)
    votes: list[IndividualVoteRecord] = field(default_factory=list)
    attributes: dict = field(default_factory=dict)


@dataclass
class SpeechRecord:
    source_id: str
    person: Identifier
    ref: Ref
    delivered_on: date | None
    kind: str | None = None
    summary: str | None = None
    indexing: str | None = None
    session: str | None = None
    url: str | None = None
    text_url: str | None = None


@dataclass
class NewsRecord:
    url: str
    title: str
    outlet: str
    feed: str
    ref: Ref
    excerpt: str | None = None
    published_at: datetime | None = None
    topics: list[str] = field(default_factory=list)


@dataclass
class Issue:
    severity: str  # info | warning | error
    code: str
    message: str
    context: dict = field(default_factory=dict)
    raw: int | None = None


@dataclass
class Batch:
    scope: str
    raw: list[RawResponse] = field(default_factory=list)
    persons: list[PersonRecord] = field(default_factory=list)
    parties: list[PartyRecord] = field(default_factory=list)
    mandates: list[MandateRecord] = field(default_factory=list)
    memberships: list[PartyMembershipRecord] = field(default_factory=list)
    proposals: list[ProposalRecord] = field(default_factory=list)
    exercises: list[ExerciseRecord] = field(default_factory=list)
    vote_events: list[VoteEventRecord] = field(default_factory=list)
    speeches: list[SpeechRecord] = field(default_factory=list)
    news: list[NewsRecord] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    complete_member_list: bool = False

    def add_raw(self, raw: RawResponse) -> int:
        self.raw.append(raw)
        return len(self.raw) - 1

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


class Connector(ABC):
    id: str
    version: str
    scopes: tuple[str, ...]

    def __init__(self, source_config: dict, client: SourceHttpClient):
        self.config = source_config
        self.client = client

    def discover(self) -> list[str]:
        """Scopes this connector can sync."""
        return list(self.scopes)

    @abstractmethod
    def fetch(self, scope: str) -> Batch: ...

    @abstractmethod
    def normalize(self, batch: Batch) -> Batch: ...

    def validate(self, batch: Batch) -> Batch:
        seen: set[tuple[str, str]] = set()
        for p in batch.persons:
            key = (p.identifier.scheme, p.identifier.value)
            if key in seen:
                batch.issues.append(Issue("error", "duplicate_person", f"duplicate person identifier {key}"))
            seen.add(key)
            if not p.name.strip():
                batch.issues.append(Issue("error", "missing_name", "person without name", {"id": key[1]}))
        seen_prop: set[str] = set()
        for pr in batch.proposals:
            if pr.source_id in seen_prop:
                batch.issues.append(Issue("warning", "duplicate_proposal", f"duplicate proposal {pr.source_id}"))
            seen_prop.add(pr.source_id)
        return batch

    def run(self, scope: str) -> Batch:
        return self.validate(self.normalize(self.fetch(scope)))


def normalize_name(name: str) -> str:
    """Accent/case-insensitive key; used only for name-derived identifiers, never as a primary key."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().casefold()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


def as_list(value: Any) -> list:
    """Source APIs serialize single-item lists as objects; normalize to list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]
