"""SIORG monthly open-data archives: organs and entities of the federal Executive, with official competences.

The live SIORG API is often unreachable, so the connector reads the official monthly archive published at
repositorio.dados.gov.br. The raw record keeps the federal-Executive rows of the archive CSV verbatim, plus the
archive's URL and SHA-256 so the extract can be checked against the original file.
"""

import csv
import io
import re
import zipfile
from datetime import UTC, datetime

from connectors.base.http import FetchedResponse
from connectors.base.protocol import Batch, Connector, ExecutiveBodyRecord, Issue, RawResponse, Ref, parse_date

ARCHIVE_DIR = "https://repositorio.dados.gov.br/seges/siorg/estrutura-organizacional-completa/"
ARCHIVE_RE = re.compile(r"estrutura-organizacional-completa-(\d{4}-\d{2})\.zip")
CSV_NAME = "estrutura-organizacional-completa-siorg.csv"
FEDERAL, EXECUTIVE = "1", "1"
BODY_TYPES = ("orgao", "entidade")
LEGAL_NATURE = {
    "1": "Empresa Pública",
    "2": "Fundação Pública",
    "3": "Administração Direta",
    "4": "Autarquia",
    "6": "Sociedade de Economia Mista",
    "7": "Órgão Público Autônomo Federal",
}
EXTRACT_SUFFIX = "#orgaos-e-entidades-do-poder-executivo-federal"


def tail(uri: str | None) -> str | None:
    """SIORG cells hold URIs such as .../unidade-organizacional/26; keep the final code."""
    if not uri:
        return None
    return uri.rstrip("/").rsplit("/", 1)[-1] or None


def clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


class SiorgConnector(Connector):
    id = "br-siorg"
    version = "0.1.0"
    scopes = ("structure",)

    def latest_archive(self) -> tuple[str, str]:
        month = self.config.get("archive_month")
        if not month:
            listing = self.client.get(self.config.get("archive_dir", ARCHIVE_DIR), accept="text/html")
            months = sorted(set(ARCHIVE_RE.findall(listing.text)))
            if not months:
                raise ValueError("no SIORG archive listed")
            month = months[-1]
        return month, f"{self.config.get('archive_dir', ARCHIVE_DIR)}estrutura-organizacional-completa-{month}.zip"

    def fetch(self, scope: str) -> Batch:
        if scope != "structure":
            raise ValueError(f"unknown scope {scope}")
        batch = Batch(scope=scope)
        month, url = self.latest_archive()
        archive = self.client.get(url, accept="application/zip, */*;q=0.5")
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
            name = next((n for n in zf.namelist() if n.endswith(".csv")), CSV_NAME)
            text = zf.read(name).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        units: dict[str, int] = {}
        keep = []
        for row in rows:
            if tail(row.get("codigoEsfera")) != FEDERAL or tail(row.get("codigoPoder")) != EXECUTIVE:
                continue
            kind = tail(row.get("codigoTipoUnidade"))
            if kind in BODY_TYPES:
                keep.append(row)
            elif kind == "unidade-administrativa":
                owner = tail(row.get("codigoOrgaoEntidade"))
                if owner:
                    units[owner] = units.get(owner, 0) + 1
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0].keys()) if rows else [], lineterminator="\n")
        writer.writeheader()
        writer.writerows(keep)
        extract = FetchedResponse(
            url=url + EXTRACT_SUFFIX, status=archive.status, content=out.getvalue().encode(),
            headers={"content-type": "text/csv; charset=utf-8", "x-archive-url": url, "x-archive-month": month,
                     "x-archive-sha256": archive.sha256, "x-archive-file": name}
            | {k: v for k, v in archive.headers.items() if k in ("last-modified", "etag")},
            retrieved_at=archive.retrieved_at or datetime.now(UTC), response_format="csv",
        )
        batch.add_raw(RawResponse(extract, "siorg_bodies", month, parsed={"units": units}))
        return batch

    def normalize(self, batch: Batch) -> Batch:
        for idx, raw in enumerate(batch.raw):
            units = (raw.parsed or {}).get("units", {})
            month = raw.source_record_key
            rows = csv.DictReader(io.StringIO(raw.response.content.decode("utf-8")))
            for line, row in enumerate(rows):
                code = tail(row.get("codigoUnidade"))
                name = clean(row.get("nome"))
                if not code or not name:
                    batch.issues.append(Issue("warning", "siorg_row_incomplete", "row without code or name",
                                              {"line": line}, raw=idx))
                    continue
                batch.executive_bodies.append(ExecutiveBodyRecord(
                    code=code, name=name, unit_type=tail(row.get("codigoTipoUnidade")) or "orgao",
                    ref=Ref(idx, f"$[{line}]"), parent_code=tail(row.get("codigoUnidadePai")),
                    acronym=clean(row.get("sigla")),
                    legal_nature=LEGAL_NATURE.get(tail(row.get("codigoNaturezaJuridica")) or ""),
                    competence=clean(row.get("competencia")), purpose=clean(row.get("finalidade")),
                    mission=clean(row.get("missao")), legal_basis=clean(row.get("descricaoAtoNormativo")),
                    site=clean(row.get("site")), version=clean(row.get("versaoConsulta")),
                    version_start=parse_date(row.get("dataInicialVersaoConsulta")),
                    attributes={"archive_month": month, "administrative_units": units.get(code, 0),
                                "area": clean(row.get("areaAtuacao")), "email": clean(row.get("email")),
                                "phone": clean(row.get("telefone")), "city": clean(row.get("municipio")),
                                "uf": tail(row.get("uf"))},
                ))
        return batch

    def validate(self, batch: Batch) -> Batch:
        codes = [b.code for b in batch.executive_bodies]
        if len(codes) != len(set(codes)):
            batch.issues.append(Issue("error", "duplicate_body", "SIORG extract lists a unit code twice"))
        if not codes:
            batch.issues.append(Issue("error", "empty_structure", "no federal Executive organ found in the archive"))
        return batch
