"""Export the public terminal data through the read-only v1 API routes."""

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from engine.api.app import app
from engine.senado import INSTITUTION

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps/terminal/public/data"
START = date(2023, 2, 1)
NEWS_TOPICS = ("impeachment_stf", "pgr", "stf", "caso_master", "presidencia_senado", "senado")
SENATE_SOURCE = "src_br_senado_dadosabertos"


class SnapshotError(Exception):
    pass


def objects(value: object) -> Iterator[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def export_snapshot(api: TestClient, output: Path, now: datetime) -> None:
    today = now.astimezone(ZoneInfo("America/Sao_Paulo")).date()
    people: set[str] = set()
    sources: dict[str, set[str]] = defaultdict(set)

    def get(route: str, *, optional: bool = False, **params):
        response = api.get(f"/v1/{route}", params=params)
        if optional and response.status_code == 404:
            return None
        if not response.is_success:
            raise SnapshotError(f"/v1/{route}: HTTP {response.status_code}")
        return response.json()

    def write(path: str, value) -> None:
        file = output / f"{path}.json"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")

    def collect(data) -> None:
        for row in objects(data):
            person = row.get("person_id") or (row.get("id") if row.get("kind") == "person" else None)
            if isinstance(person, str) and person.startswith("per_"):
                people.add(person)
            if row.get("source_system_id") == SENATE_SOURCE and row.get("raw_record_id"):
                sources[row["raw_record_id"]].add(row.get("json_path") or "")

    def save(path: str, file: str | None = None, **params):
        data = get(path, **params)
        write(file or path, data)
        collect(data)
        return data

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
        for proposal in proposals:
            path = f"entities/{proposal['id']}"
            save(path)
            save(f"{path}/relationships")
            save(f"{path}/timeline")

    changes = save("senado/mudancas")
    dates = {START, date(2025, 2, 1), today}
    for change in changes:
        day = date.fromisoformat(change["date"])
        dates.add(day)
        dates.add(day + timedelta(days=1))
    composition_dates = sorted(day.isoformat() for day in dates if START <= day <= today)
    for day in composition_dates:
        save("senado/composicao", f"senado/composicao/{day}", data=day)
    save("senado/composicao/2027")

    for path in ("presidencia/2025", "presidencia/2027", "dossies/stf-caso-master"):
        save(path)
    for committee in save("comissoes"):
        save(f"comissoes/{committee['id']}")
    for vote in save("votacoes", limit=2000):
        save(f"votacoes/{vote['id']}")
    save("noticias", limit=120)
    for topic in NEWS_TOPICS:
        save("noticias", f"noticias/{topic}", limit=120, tema=topic)

    parties = set()
    for person in sorted(people):
        profile = get(f"senadores/{person}", optional=True)
        if profile is None:
            continue
        write(f"senadores/{person}", profile)
        path = f"entities/{person}"
        save(path)
        for relationship in save(f"{path}/relationships"):
            if relationship["kind"] == "current_party":
                parties.add(relationship["target"])
        save(f"{path}/timeline")
    for party in sorted(parties):
        path = f"entities/{party}"
        save(path)
        save(f"{path}/relationships")
        save(f"{path}/timeline")

    for raw_id, paths in sorted(sources.items()):
        records = {}
        for path in sorted(paths):
            record = get(f"sources/{raw_id}", path=path or None)
            record["response_headers"] = {}
            records[path] = record
        write(f"sources/{raw_id}", records)

    write("meta", {"generated_at": now.isoformat(), "composition_dates": composition_dates})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".politeia-snapshot-", dir=output.parent) as temp:
            staging = Path(temp) / "next"
            with TestClient(app, raise_server_exceptions=False) as api:
                export_snapshot(api, staging, datetime.now(ZoneInfo("UTC")))
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
        # Do not print underlying exceptions or API bodies: they may include credentials.
        detail = str(exc) if isinstance(exc, SnapshotError) else type(exc).__name__
        sys.exit(f"Não foi possível gerar o snapshot: {detail}")
    print(f"Snapshot salvo em {output}.")


if __name__ == "__main__":
    main()
