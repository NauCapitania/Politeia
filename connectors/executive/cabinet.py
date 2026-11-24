"""Cabinet of the President (ministers and their terms) from the pt.wikipedia cabinet list.

No official machine-readable feed of minister terms is reachable (planalto.gov.br blocks automated clients), so the
collaborative list is used and every term keeps its cited references; terms are marked `extracted`, not `verified`.
"""

import re
from datetime import date

from connectors.base.protocol import (
    Batch,
    Connector,
    Identifier,
    Issue,
    MandateRecord,
    PersonRecord,
    RawResponse,
    Ref,
    normalize_name,
)

API = "https://pt.wikipedia.org/w/api.php"
DEFAULT_PAGE = "Lista de membros do gabinete de Lula (2023–presente)"
MONTHS = {m: i for i, m in enumerate(("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                                      "setembro", "outubro", "novembro", "dezembro"), start=1)}
DATE_RE = re.compile(r"(\d{1,2})(?:\.º|º)?\s+de\s+(\w+)\s+de\s+(\d{4})", re.I)
LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
FILE_RE = re.compile(r"^\[\[(?:Ficheiro|Arquivo|File|Imagem|Image):", re.I)
ATTR_RE = re.compile(r'^\s*(?:(?:rowspan|colspan|style|class|align)\s*=\s*"[^"]*"\s*)+\|(?!\|)')
REF_RE = re.compile(r"<ref[^>/]*>(.*?)</ref>", re.S)
TPL_FIELD = re.compile(r"\|\s*(url|t[ií]tulo|titulo|data|website|publicado|obra)\s*=\s*([^|}]*)")


def pt_date(text: str | None) -> date | None:
    m = DATE_RE.search(text or "")
    if not m or m.group(2).lower() not in MONTHS:
        return None
    return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))


def plain(text: str) -> str:
    text = REF_RE.sub("", text)
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = LINK_RE.sub(lambda m: m.group(2) or m.group(1), text)
    text = re.sub(r"\{\{[^{}]*\|([^{}|]*)\}\}", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text).replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", text).strip()


def refs(cell: str) -> list[dict]:
    out = []
    for body in REF_RE.findall(cell):
        fields = {k.lower(): v.strip() for k, v in TPL_FIELD.findall(body)}
        if fields.get("url"):
            out.append({"url": fields["url"], "title": fields.get("titulo") or fields.get("título"),
                        "date": fields.get("data"),
                        "outlet": plain(fields.get("website") or fields.get("publicado") or fields.get("obra") or "")
                        or None})
    return out


def split_cells(row: str) -> list[str]:
    cells = []
    for line in row.split("\n"):
        if line.startswith("|") and not line.startswith(("|}", "|-", "|+")):
            cells.append(ATTR_RE.sub("", line[1:]).strip())
        elif cells and not line.startswith("!"):
            cells[-1] += "\n" + line
    return cells


def first_table(wikitext: str) -> str:
    start = wikitext.find("{|")
    end = wikitext.find("\n|}", start)
    return wikitext[start:end] if start >= 0 else ""


def parse_cabinet(wikitext: str) -> tuple[list[dict], list[str]]:
    """Rows of the first wikitable: ministry cells span several term rows (rowspan)."""
    terms, problems = [], []
    ministry = None
    for n, row in enumerate(first_table(wikitext).split("\n|-")[1:]):
        cells = split_cells(row)
        if len(cells) < 4:
            continue
        if not FILE_RE.match(cells[0]) and len(cells) >= 5 and not pt_date(cells[2]):
            link = LINK_RE.search(cells[0])
            ministry = {"title": link.group(1).strip() if link else plain(cells[0]), "label": plain(cells[0])}
            cells = cells[1:]
        if ministry is None:
            problems.append(f"row {n}: no ministry")
            continue
        if cells and FILE_RE.match(cells[0]):
            cells = cells[1:]
        if len(cells) < 4:
            problems.append(f"row {n}: too few cells")
            continue
        person_cell, party_cell, start_cell, end_cell = cells[:4]
        ref_cells = "\n".join(cells[4:])
        link = LINK_RE.search(person_cell)
        name = plain(re.sub(r"<br\s*/?>.*", "", person_cell, flags=re.S))
        start = pt_date(start_cell)
        if not name or not start:
            problems.append(f"row {n}: missing name or start date")
            continue
        party = plain(party_cell)
        party_abbr, _, uf = party.partition("/")
        end_text = plain(end_cell)
        terms.append({
            "row": n, "ministry_title": ministry["title"], "ministry": ministry["label"],
            "person_title": link.group(1).strip() if link and not FILE_RE.match(person_cell) else None,
            "name": name, "interim": bool(re.search(r"interin[oa]", person_cell, re.I)),
            "party": None if normalize_name(party_abbr) in ("sem partido", "") else party_abbr.strip(),
            "uf": uf.strip() or None, "start": start, "end": pt_date(end_cell),
            "end_note": None if pt_date(end_cell) else (end_text or None), "refs": refs(ref_cells),
        })
    return terms, problems


class CabinetConnector(Connector):
    id = "ptwiki-cabinet"
    version = "0.1.0"
    scopes = ("members",)

    def fetch(self, scope: str) -> Batch:
        if scope != "members":
            raise ValueError(f"unknown scope {scope}")
        batch = Batch(scope=scope, complete_member_list=True)
        page = self.config.get("page", DEFAULT_PAGE)
        resp = self.client.get(self.config.get("api_url", API), params={
            "action": "parse", "page": page, "prop": "wikitext|revid", "format": "json", "formatversion": "2"})
        batch.add_raw(RawResponse(resp, "cabinet_wikitext", page))
        return batch

    def normalize(self, batch: Batch) -> Batch:
        for idx, raw in enumerate(batch.raw):
            parsed = raw.json().get("parse", {})
            terms, problems = parse_cabinet(parsed.get("wikitext", ""))
            for p in problems:
                batch.issues.append(Issue("warning", "cabinet_row_skipped", p, raw=idx))
            seen: set[str] = set()
            for t in terms:
                key = t["person_title"] or normalize_name(t["name"])
                person = Identifier("ptwiki" if t["person_title"] else "ptwiki_name", key,
                                    "community" if t["person_title"] else "name-derived")
                ref = Ref(idx, f"$.parse.wikitext#row{t['row']}")
                if key not in seen:
                    seen.add(key)
                    batch.persons.append(PersonRecord(
                        identifier=person, name=t["name"], ref=ref,
                        profile_url=f"https://pt.wikipedia.org/wiki/{t['person_title'].replace(' ', '_')}"
                        if t["person_title"] else None))
                batch.mandates.append(MandateRecord(
                    identifier=Identifier("ptwiki_cabinet_term",
                                          f"{t['ministry_title']}|{key}|{t['start'].isoformat()}"),
                    person=person, role_type="minister_of_state", ref=ref,
                    represented_unit=t["ministry"], participation="interim" if t["interim"] else "holder",
                    start_date=t["start"], end_date=t["end"],
                    status="ended" if t["end"] else "in_exercise", epistemic_status="extracted",
                    attributes={"ministry_title": t["ministry_title"], "party": t["party"], "uf": t["uf"],
                                "end_note": t["end_note"], "refs": t["refs"], "wiki_revision": parsed.get("revid")},
                ))
            if not terms:
                batch.issues.append(Issue("error", "cabinet_empty", "no cabinet term parsed", raw=idx))
        return batch
