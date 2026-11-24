import json
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from connectors.base.http import FetchedResponse
from connectors.base.protocol import Batch, Issue, RawResponse
from connectors.senate.connector import SenateConnector
from engine.capabilities.compute import recompute_capabilities
from engine.db.models import IngestionRun, RawRecord, SourceSystem
from engine.ingestion.sync import process_batch
from engine.registry import build_connector

SOURCE_ID = "src_br_senado_dadosabertos"


def _from_run(session: Session, run_id: UUID) -> list[RawRecord]:
    latest = session.scalar(select(IngestionRun).where(
        IngestionRun.source_system_id == SOURCE_ID, IngestionRun.scope.contains(["proposals"]),
        IngestionRun.status.in_(("succeeded", "partial")), IngestionRun.is_source_fetch(),
    ).order_by(IngestionRun.started_at.desc(), IngestionRun.id.desc()).limit(1))
    if latest is None or latest.id != run_id:
        raise ValueError("expected the latest usable Senate proposals fetch; use --proposal-id for older records")
    records = list(session.scalars(select(RawRecord).where(
        RawRecord.source_system_id == SOURCE_ID, RawRecord.record_kind.in_(("proposal_list", "proposal_detail")),
        or_(RawRecord.first_run_id == run_id, RawRecord.last_run_id == run_id),
    ).order_by(RawRecord.record_kind, RawRecord.source_record_key, RawRecord.id)))
    if not records or len(records) != latest.stats.get("raw_records"):
        raise ValueError("the complete original batch is no longer identifiable; use --proposal-id")
    return records


def _for_proposals(session: Session, ids: list[int]) -> tuple[list[RawRecord], dict[str, int]]:
    records: dict[UUID, RawRecord] = {}
    lists: dict[str, UUID] = {}
    base = select(RawRecord).where(RawRecord.source_system_id == SOURCE_ID).order_by(
        RawRecord.last_seen_at.desc(), RawRecord.id.desc()).limit(1)
    for source_id in ids:
        listing = session.scalar(base.where(
            RawRecord.record_kind == "proposal_list", RawRecord.payload.contains([{"id": source_id}])))
        if listing is None:
            raise ValueError(f"no stored Senate proposal list entry for ID {source_id}")
        lists[str(source_id)] = listing.id
        records[listing.id] = listing
        detail = session.scalar(base.where(
            RawRecord.record_kind == "proposal_detail", RawRecord.source_record_key == str(source_id)))
        if detail is not None:
            records[detail.id] = detail
    indices = {raw_id: index for index, raw_id in enumerate(records)}
    return list(records.values()), {key: indices[raw_id] for key, raw_id in lists.items()}


def replay_proposals(factory: sessionmaker, *, run_id: UUID | None = None,
                     proposal_ids: list[int] | None = None) -> dict:
    if (run_id is None) == (not proposal_ids):
        raise ValueError("choose either a source run or one or more Senate proposal IDs")
    with factory() as session:
        source = session.get(SourceSystem, SOURCE_ID)
        if source is None:
            raise ValueError("the Senate source is not registered")
        connector = build_connector(source)
        if not isinstance(connector, SenateConnector):
            raise ValueError("the registered source does not use the Senate connector")
        selection = None
        stats = {"mode": "replay", "requests": 0}
        if run_id is not None:
            records = _from_run(session, run_id)
            stats["source_run_id"] = str(run_id)
        else:
            ids = list(dict.fromkeys(proposal_ids or []))
            records, selection = _for_proposals(session, ids)
            stats["source_proposal_ids"] = ids
        if any(r.response_format != "json" or r.payload is None for r in records):
            raise ValueError("stored proposal evidence must contain JSON")

        stats["raw_records"] = len(records)
        batch = Batch(scope="proposals")
        for record in records:
            response = FetchedResponse(record.url, record.http_status, json.dumps(record.payload).encode(),
                                       record.response_headers, record.retrieved_at, record.response_format)
            batch.add_raw(RawResponse(response, record.record_kind, record.source_record_key, record.payload))

        def normalize(value: Batch) -> Batch:
            connector.normalize_proposals(value, selection)
            for proposal in value.proposals:
                if proposal.attributes.get("detail_missing"):
                    value.issues.append(Issue("warning", "stored_proposal_detail_missing",
                                              "no stored detail for proposal", {"id": proposal.source_id},
                                              raw=proposal.ref.raw))
            return connector.validate(value)

        run = IngestionRun(institution_id=source.institution_id, source_system_id=source.id,
                           connector=connector.id, connector_version=connector.version, scope=["proposals"],
                           status="running", stats=stats)
        session.add(run)
        session.commit()
        result = process_batch(session, source, run, batch, list(r.id for r in records), stats, normalize, records)
        recompute_capabilities(session, source.institution_id)
        session.commit()
        return result
