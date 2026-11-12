"""Capability state is derived from what was actually ingested, never assumed from the pack alone.

Statuses: available | partial | empty | stale | ingestion_failed | not_ingested | unavailable_in_source
"""

from datetime import UTC, datetime

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from engine.db.models import (
    CapabilityState,
    IngestionRun,
    LegislativeEvent,
    Mandate,
    PartyMembership,
    Proposal,
    ProposalAuthor,
    ValidationIssue,
)
from engine.registry import pack_for


def _counts(s: Session, inst: str, capability: str) -> tuple[int, dict]:
    current = and_(Mandate.institution_id == inst, Mandate.status == "in_exercise")
    if capability in ("members", "mandates"):
        n = s.scalar(select(func.count()).where(current)) or 0
        dated = s.scalar(select(func.count()).where(current, Mandate.start_date.is_not(None))) or 0
        return n, {"with_dates": dated} if capability == "mandates" else {}
    if capability == "party_composition":
        n = s.scalar(select(func.count(func.distinct(PartyMembership.person_id))).where(
            PartyMembership.institution_id == inst, PartyMembership.basis == "current_listing",
            PartyMembership.is_current.is_(True))) or 0
        members = s.scalar(select(func.count()).where(current)) or 0
        return n, {"members_with_party": n, "members": members}
    if capability == "party_history":
        n = s.scalar(select(func.count()).where(PartyMembership.institution_id == inst,
                                                PartyMembership.basis == "affiliation_history")) or 0
        persons = s.scalar(select(func.count(func.distinct(PartyMembership.person_id))).where(
            PartyMembership.institution_id == inst, PartyMembership.basis == "affiliation_history")) or 0
        return n, {"persons_covered": persons}
    if capability == "proposals":
        n, lo, hi, with_status = s.execute(select(
            func.count(), func.min(Proposal.introduced_on), func.max(Proposal.introduced_on),
            func.count(Proposal.status)).where(Proposal.institution_id == inst)).one()
        return n or 0, {"introduced_from": lo.isoformat() if lo else None,
                        "introduced_to": hi.isoformat() if hi else None, "with_status": with_status}
    if capability == "proposal_authors":
        rows = dict(s.execute(select(ProposalAuthor.resolution, func.count()).join(
            Proposal, Proposal.id == ProposalAuthor.proposal_id).where(Proposal.institution_id == inst)
            .group_by(ProposalAuthor.resolution)).all())
        member_unresolved = s.scalar(select(func.count()).select_from(ProposalAuthor).join(
            Proposal, Proposal.id == ProposalAuthor.proposal_id).where(
            Proposal.institution_id == inst, ProposalAuthor.author_kind == "member",
            ProposalAuthor.person_id.is_(None))) or 0
        return sum(rows.values()), {"by_resolution": rows, "member_authors_unresolved": member_unresolved}
    if capability == "proposal_events":
        n = s.scalar(select(func.count()).where(LegislativeEvent.institution_id == inst)) or 0
        return n, {}
    return 0, {}


def recompute_capabilities(s: Session, inst: str) -> None:
    pack = pack_for(inst)
    source_id = pack["sources"][0]["id"]
    for capability, spec in pack["capabilities"].items():
        row = {"institution_id": inst, "capability": capability, "source_system_id": source_id,
               "note": spec.get("note"), "updated_at": datetime.now(UTC), "issues": [], "coverage": {},
               "record_count": None, "last_success_at": None}
        if "declared" in spec:
            row["status"] = spec["declared"]
        else:
            scope = spec["scope"]
            runs = s.scalars(select(IngestionRun).where(
                IngestionRun.institution_id == inst, IngestionRun.scope.contains([scope]),
                IngestionRun.status != "running").order_by(IngestionRun.started_at.desc())).all()
            ok = next((r for r in runs if r.status in ("succeeded", "partial")), None)
            count, coverage = _counts(s, inst, capability)
            row.update(record_count=count, coverage=coverage, last_success_at=ok.finished_at if ok else None)
            if not runs:
                row["status"] = "not_ingested"
            elif ok is None:
                row["status"] = "ingestion_failed"
                row["issues"] = [{"code": "last_run_failed", "message": runs[0].error}]
            elif runs[0] is not ok:
                row["status"] = "stale"
                row["issues"] = [{"code": "last_run_failed", "message": runs[0].error}]
            elif count == 0:
                row["status"] = "empty"
            else:
                warnings = s.execute(select(ValidationIssue.code, func.count()).where(
                    ValidationIssue.run_id == ok.id, ValidationIssue.severity == "warning")
                    .group_by(ValidationIssue.code)).all()
                row["issues"] = [{"code": c, "count": n} for c, n in warnings]
                incomplete = (
                    (capability == "party_composition" and coverage["members_with_party"] < coverage["members"])
                    or (capability == "proposal_authors" and coverage["member_authors_unresolved"] > 0)
                    or (capability == "mandates" and coverage.get("with_dates", 0) < count)
                )
                row["status"] = "partial" if incomplete or (warnings and ok.status == "partial") else "available"
        stmt = insert(CapabilityState).values(**row)
        s.execute(stmt.on_conflict_do_update(
            index_elements=[CapabilityState.institution_id, CapabilityState.capability],
            set_={k: stmt.excluded[k] for k in row if k not in ("institution_id", "capability")}))
