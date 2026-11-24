"""politeia CLI: `python -m engine.cli bootstrap | sync [--institution ID] [--scope members]`."""

import argparse
import json
import logging

from sqlalchemy import select

from engine.db.models import SourceSystem
from engine.db.session import session_factory
from engine.ingestion.sync import sync_source
from engine.registry import CONNECTORS, bootstrap


def main() -> None:
    parser = argparse.ArgumentParser(prog="politeia")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("bootstrap", help="register institution packs")
    sync = sub.add_parser("sync", help="ingest from official sources")
    sync.add_argument("--institution", action="append", help="institution id (default: all)")
    sync.add_argument("--scope", action="append", help="composition | members | votes | speeches | proposals | news")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    factory = session_factory()
    with factory() as s:
        bootstrap(s)
        if args.cmd == "bootstrap":
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
