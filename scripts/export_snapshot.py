"""Export the public terminal data through the read-only v1 API routes."""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from itertools import batched
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from urllib.parse import quote, quote_plus
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from psycopg import OperationalError as DriverOperationalError
from sqlalchemy import create_engine, make_url
from sqlalchemy.exc import ArgumentError, DBAPIError, OperationalError
from sqlalchemy.orm import sessionmaker

from engine.api.app import app
from engine.api.camara import INSTITUTION as CAMARA
from engine.db.session import get_session
from engine.senado import INSTITUTION
from engine.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/terminal/public/data"
START = date(2023, 2, 1)
NEWS_TOPICS = ("impeachment_stf", "pgr", "stf", "caso_master", "presidencia_senado", "senado")
PUBLIC_SOURCES = {"src_br_senado_dadosabertos", "src_br_camara_dadosabertos"}
DEFAULT_WORKERS = 4
RETRY_DELAYS = (1, 2, 4)
PROPOSAL_BATCH = 100


class SnapshotError(Exception):
    pass


def snapshot_workers() -> int:
    try:
        workers = int(os.getenv("SNAPSHOT_WORKERS", str(DEFAULT_WORKERS)))
        if workers > 0:
            return workers
    except ValueError:
        pass
    raise SnapshotError("SNAPSHOT_WORKERS deve ser um inteiro positivo.")


@contextmanager
def snapshot_client(workers: int) -> Iterator[TestClient]:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True, pool_size=workers, max_overflow=0)
    factory = sessionmaker(engine, expire_on_commit=False)

    def session():
        with factory() as db:
            yield db

    previous_session = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = session
    try:
        with TestClient(app) as api:
            yield api
    finally:
        if previous_session is None:
            app.dependency_overrides.pop(get_session)
        else:
            app.dependency_overrides[get_session] = previous_session
        engine.dispose()


def redact_error(exc: Exception, database_url: str) -> str:
    detail = str(exc.orig if isinstance(exc, DBAPIError) else exc)
    detail = detail.replace(database_url, "[redigido]") if database_url else detail
    detail = re.sub(r"""(?i)\b(?:postgres(?:ql)?(?:\+[\w]+)?|[\w+.-]+(?=://[^\s/@]+@))://[^\s'"<>]+""",
                    "[redigido]", detail)
    detail = re.sub(r"""(?i)\bpassword\s*[:=]\s*(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;]+)""",
                    "password=[redigido]", detail)
    try:
        password = make_url(database_url).password
    except ArgumentError:
        password = None
    if password:
        for variant in sorted({password, quote(password, safe=""), quote_plus(password)}, key=len, reverse=True):
            detail = detail.replace(variant, "[redigido]")
    kind = type(exc).__name__
    return f"{kind}: {detail}" if detail else kind


def get_snapshot_data(api: TestClient, route: str, *, optional: bool = False, **params):
    path = f"/v1/{route}"
    for delay in (*RETRY_DELAYS, None):
        try:
            response = api.get(path, params=params)
        except (OperationalError, DriverOperationalError) as exc:
            if delay is None:
                detail = redact_error(exc, get_settings().database_url)
                raise SnapshotError(f"{path}: {detail}") from None
        else:
            if response.is_success:
                return response.json()
            if optional and response.status_code == 404:
                return None
            if response.status_code < 500 or delay is None:
                raise SnapshotError(f"{path}: HTTP {response.status_code}")
        sleep(delay)


def objects(value: object) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def export_snapshot(api: TestClient, output: Path, now: datetime, *, workers: int | None = None) -> None:
    workers = snapshot_workers() if workers is None else workers
    with ThreadPoolExecutor(max_workers=workers) as executor:
        _export_snapshot(api, output, now, executor, workers)


def _export_snapshot(api: TestClient, output: Path, now: datetime, executor: ThreadPoolExecutor, workers: int) -> None:
    today = now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
    people: set[str] = set()
    deputies: set[str] = set()
    sources: dict[str, set[str]] = defaultdict(set)

    def get(route: str, **params):
        return get_snapshot_data(api, route, **params)

    def write(path: str, value) -> None:
        file = output / f"{path}.json"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    def collect(data) -> None:
        for row in objects(data):
            person = row.get("person_id") or (row.get("id") if row.get("kind") == "person" else None)
            if isinstance(person, str) and person.startswith("per_"):
                people.add(person)
            if row.get("source_system_id") in PUBLIC_SOURCES and row.get("raw_record_id"):
                sources[row["raw_record_id"]].add(row.get("json_path") or "")

    def save(path: str, file: str | None = None, **params):
        data = get(path, **params)
        write(file or path, data)
        collect(data)
        return data

    def fetch_many[T](requests: Iterable[tuple[str, T, dict]]):
        def fetch(request):
            path, file, params = request
            return file, get(path, **params)

        for batch in batched(requests, workers):
            yield from executor.map(fetch, batch)

    def save_many(requests: Iterable[tuple[str, str, dict]]) -> None:
        for file, data in fetch_many(requests):
            write(file, data)
            collect(data)

    institutions = save("institutions")
    if not any(inst["id"] == INSTITUTION for inst in institutions):
        raise SnapshotError("O Senado não está cadastrado no banco.")
    for inst in institutions:
        institution_id = inst["id"]
        base = f"institutions/{institution_id}"
        capabilities = get(f"{base}/capabilities")
        for capability in capabilities:
            capability["issues"] = [
                {key: issue[key] for key in ("code", "count") if key in issue}
                for issue in capability["issues"]
            ]
        write(f"{base}/capabilities", capabilities)
        save(f"{base}/proposal-types")
        if institution_id == CAMARA:
            deputies.update(s["person_id"] for s in save(f"{base}/composition")["seats"] if s["person_id"])
        runs = get("ingestion/status", institution=institution_id)
        for run in runs["runs"]:
            # Keep status and issue counts; internal diagnostics can contain connection details.
            run["error"] = None
            for issue in run["issues"]:
                issue.pop("example", None)
        write(f"ingestion/{institution_id}", runs)

        proposals = []
        while True:
            page = get(f"{base}/proposals", limit=500, offset=len(proposals))
            proposals.extend(page["items"])
            if len(proposals) >= page["total"]:
                break
            if not page["items"]:
                raise SnapshotError("A lista de proposições mudou durante a exportação.")
        if len({proposal["id"] for proposal in proposals}) != len(proposals):
            raise SnapshotError("A lista de proposições mudou durante a exportação.")
        write(f"{base}/proposals", proposals)
        collect(proposals)
        detail_requests = (("proposals/details", ids, {"ids": ids})
                           for ids in batched((p["id"] for p in proposals), PROPOSAL_BATCH))
        for ids, details in fetch_many(detail_requests):
            for proposal_id in ids:
                if proposal_id not in details:
                    raise SnapshotError("A lista de proposições mudou durante a exportação.")
                detail = details[proposal_id]
                path = f"entities/{proposal_id}"
                for file, value in ((path, detail["entity"]), (f"{path}/relationships", detail["relationships"]),
                                    (f"{path}/timeline", detail["timeline"])):
                    write(file, value)
                    collect(value)

    changes = save("senado/mudancas")
    dates = {START, date(2025, 2, 1), today}
    for change in changes:
        day = date.fromisoformat(change["date"])
        dates.add(day)
        dates.add(day + timedelta(days=1))
    composition_dates = sorted(day.isoformat() for day in dates if START <= day <= today)
    save_many(("senado/composicao", f"senado/composicao/{day}", {"data": day}) for day in composition_dates)
    save("senado/composicao/2027")

    for path in ("presidencia/2025", "presidencia/2027"):
        save(path)
    save("dossies/stf-caso-master", optional=True)
    save("dossies/partidos", optional=True)
    committees = save("comissoes")
    votes = save("votacoes", limit=2000)
    details = (f"{route}/{row['id']}" for route, rows in (("comissoes", committees), ("votacoes", votes))
               for row in rows)
    save_many((path, path, {}) for path in details)
    save("noticias", limit=120)
    save_many(("noticias", f"noticias/{topic}", {"limit": 120, "tema": topic}) for topic in NEWS_TOPICS)

    if any(inst["id"] == CAMARA for inst in institutions):
        chamber_committees = save("camara/comissoes")
        chamber_votes = save("camara/votacoes", limit=2000)
        save("camara/trocas")
        save_many((path, path, {}) for path in (
            *(f"camara/comissoes/{row['id']}" for row in chamber_committees),
            *(f"camara/votacoes/{row['id']}" for row in chamber_votes if row.get("nominal"))))

    parties = set()
    exported_people = []
    for person, profile in fetch_many((f"senadores/{p}", p, {"optional": True}) for p in sorted(people)):
        if profile is None:
            continue
        exported_people.append(person)
        write(f"senadores/{person}", profile)

    def entity_requests(ids: Iterable[str]):
        for entity_id in ids:
            for suffix in ("", "/relationships", "/timeline"):
                path = f"entities/{entity_id}{suffix}"
                yield path, path, {}

    for path, data in fetch_many(entity_requests([*exported_people, *sorted(deputies - set(exported_people))])):
        write(path, data)
        collect(data)
        if path.endswith("/relationships"):
            parties.update(rel["target"] for rel in data if rel["kind"] == "current_party")
    save_many(entity_requests(sorted(parties)))

    records = defaultdict(dict)
    for raw_id, record in fetch_many((f"sources/{raw_id}", raw_id, {"path": path or None})
                                     for raw_id, paths in sorted(sources.items()) for path in sorted(paths)):
        record["response_headers"] = {}
        records[raw_id][record["ref"]["json_path"] or ""] = record
        if len(records[raw_id]) == len(sources[raw_id]):
            write(f"sources/{raw_id}", records.pop(raw_id))

    write("meta", {"generated_at": now.isoformat(), "composition_dates": composition_dates})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        workers = snapshot_workers()
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".politeia-snapshot-", dir=output.parent) as temp:
            staging = Path(temp) / "next"
            with snapshot_client(workers) as api:
                export_snapshot(api, staging, datetime.now(ZoneInfo("UTC")), workers=workers)
            previous = Path(temp) / "previous"
            if output.exists():
                output.rename(previous)
            try:
                staging.rename(output)
            except OSError:
                if previous.exists():
                    previous.rename(output)
                raise
    except Exception as exc:
        detail = redact_error(exc, get_settings().database_url)
        sys.exit(f"Não foi possível gerar o snapshot: {detail}")
    print(f"Snapshot salvo em {output}.")


if __name__ == "__main__":
    main()
