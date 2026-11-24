"""politeia CLI: `python -m engine.cli bootstrap | sync [--institution ID] [--scope members] | dossiers`."""

import argparse
import json
import logging
from uuid import UUID

from sqlalchemy import select

from engine.db.models import SourceSystem
from engine.db.session import session_factory
from engine.dossiers import load_dossiers
from engine.ingestion.replay import replay_proposals
from engine.ingestion.sync import sync_source
from engine.registry import CONNECTORS, bootstrap


def main() -> None:
    parser = argparse.ArgumentParser(prog="politeia")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap", help="register institution packs")
    sub.add_parser("dossiers", help="load curated, source-cited dossiers and relink news mentions")
    sync = sub.add_parser("sync", help="ingest from official sources")
    sync.add_argument("--institution", action="append", help="institution id (default: all)")
    sync.add_argument("--scope", action="append", help="composition | members | votes | speeches | proposals | news")
    replay = sub.add_parser("replay-proposals", help="normalize stored Senate proposal evidence without refetching")
    selection = replay.add_mutually_exclusive_group(required=True)
    selection.add_argument("--from-run", type=UUID, help="latest usable proposals fetch run ID")
    selection.add_argument("--proposal-id", type=int, action="append", help="Senate proposal ID; repeatable")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    factory = session_factory()
    if args.cmd == "replay-proposals":
        try:
            result = replay_proposals(factory, run_id=args.from_run, proposal_ids=args.proposal_id)
        except ValueError as exc:
            replay.error(str(exc))
        print(json.dumps(result, ensure_ascii=False, default=str))
        if result["status"] == "failed":
            raise SystemExit(1)
        return

    with factory() as s:
        bootstrap(s)
        if args.cmd == "bootstrap":
            return
        if args.cmd == "dossiers":
            from engine.media import relink_all

            stats = load_dossiers(s)
            stats["news_mentions"] = relink_all(s)
            s.commit()
            print(json.dumps(stats, ensure_ascii=False))
            return
        q = select(SourceSystem.id).where(SourceSystem.connector.in_(list(CONNECTORS)))
        if args.institution:
            q = q.where(SourceSystem.institution_id.in_(args.institution))
        source_ids = list(s.scalars(q))
    scopes = args.scope
    for sid in source_ids:
        ordered = scopes or None  # connector order: persons before the records that reference them
        for result in sync_source(factory, sid, ordered):
            print(json.dumps({"source": sid} | result, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
