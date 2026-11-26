"""Projection of the current União into the ontology tables (state, process, behavior and the new core,
analysis, media and evidence tables).

The projection is rebuilt from scratch on every run, inside one transaction, from the ingested tables, the
loaded dossiers and the curated map in ontology/uniao.json. It never modifies or deletes rows of the source
tables; the only rows it adds outside the projection are persons for office holders no connector covers
(STF ministers, the President, the PGR), with stable ids.
"""

import json
import re
import uuid
from collections import defaultdict
from datetime import date
from pathlib import Path

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from connectors.base.protocol import normalize_name, parse_date
from engine.db import models as M
from engine.media import political_news

ONTOLOGY_FILE = Path(__file__).resolve().parent.parent.parent / "ontology" / "uniao.json"
FEDERAL = ("ins_br_senado", "ins_br_camara", "ins_br_executivo")
CHAMBER_BODY = {"ins_br_senado": "bod_senado", "ins_br_camara": "bod_camara"}
MANDATE_OFFICE = {"senator": ("off_senador", "direct_election"), "deputy": ("off_deputado", "direct_election"),
                  "minister_of_state": ("off_ministro_estado", "free_appointment")}
COMMITTEE_OFFICE = {"PRESIDENTE": "off_pres_comissao", "VICE-PRESIDENTE": "off_vice_comissao"}
OFFICIAL_SOURCES = {"src_br_senado_dadosabertos", "src_br_camara_dadosabertos"}
MEMBERSHIP_PRIORITY = {"current_listing": 0, "chamber_record": 1, "affiliation_history": 2}
VOTE_CHOICES = ("Sim", "Não", "Abstenção", "Obstrução")
MIN_SHARED_VOTES = 10
# Children first, so the rebuild can delete in this order.
PROJECTION = (M.FactSource, M.NewsLink, M.Estimate, M.AnalysisEntity, M.Analysis, M.ObservedLink, M.Deadline,
              M.Step, M.Participant, M.Proceeding, M.OfficeHolding, M.Affiliation, M.OrganizationLink,
              M.Organization, M.PersonName, M.Competence, M.Office, M.Body, M.LegalBasis, M.Power,
              M.FederativeUnit, M.Legislature)
PROCEEDING_TOPICS = {"caso_master": "prc_master_relatorios_pf", "pgr": "prc_master_relatorios_pf",
                     "impeachment_stf": "prc_master_impeachment",
                     "presidencia_senado": "prc_presidencia_senado_2027"}
ACTOR_BODIES = (("senado", "bod_senado"), ("pgr", "bod_pgr"), ("stf", "bod_stf"))


class OntologyError(ValueError):
    pass


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", normalize_name(value)).strip("_")


def read_ontology(path: Path = ONTOLOGY_FILE) -> dict:
    doc = json.loads(path.read_text(encoding="utf-8"))
    bases = {b["id"] for b in doc["legal_bases"]}
    bodies = {b["id"] for b in doc["bodies"]}
    offices = {o["id"] for o in doc["offices"]}
    for row in doc["bodies"] + doc["offices"] + doc["competences"]:
        if row.get("legal_basis") not in bases:
            raise OntologyError(f"{row['id']}: legal_basis {row.get('legal_basis')!r} is not in legal_bases")
    for c in doc["competences"]:
        if not (c.get("holder_body") in bodies) ^ (c.get("holder_office") in offices):
            raise OntologyError(f"{c['id']}: needs exactly one holder_body or holder_office")
        for key, known in (("target_body", bodies), ("target_office", offices)):
            if c.get(key) and c[key] not in known:
                raise OntologyError(f"{c['id']}: unknown {key} {c[key]}")
    for h in doc["holdings"]:
        if h["office"] not in offices or not h.get("sources"):
            raise OntologyError(f"holding of {h['person']}: unknown office or no sources")
    return doc


class _Loader:
    def __init__(self, s: Session, doc: dict):
        self.s = s
        self.doc = doc
        self.rows: dict[type, list[dict]] = defaultdict(list)
        self.facts: list[dict] = []
        self.persons_by_name = self._person_index()
        self.dossiers = defaultdict(lambda: defaultdict(list))
        for item in s.scalars(select(M.DossierItem).order_by(M.DossierItem.id)):
            self.dossiers[item.dossier][item.kind].append(item)

    # ------------------------------------------------------------------ helpers

    def add(self, model: type, **row) -> dict:
        self.rows[model].append(row)
        return row

    def fact(self, table: str, row_id: str, *, kind: str = "official", raw_record_id=None, url=None, outlet=None,
             published_on=None, generated_by: str = "connector") -> None:
        self.facts.append(dict(table_name=table, row_id=row_id, source_kind=kind, raw_record_id=raw_record_id,
                               url=url, outlet=outlet, published_on=published_on, generated_by=generated_by))

    def cite(self, table: str, row_id: str, sources: list[dict], generated_by: str = "dossier") -> None:
        for src in sources:
            self.fact(table, row_id, kind=src.get("kind") or "official", url=src.get("url"),
                      outlet=src.get("outlet"), published_on=parse_date(src.get("date")), generated_by=generated_by)

    def _person_index(self) -> dict[str, str | None]:
        current = set(self.s.scalars(select(M.Mandate.person_id).where(
            M.Mandate.institution_id.in_(FEDERAL), M.Mandate.status == "in_exercise")))
        index: dict[str, str | None] = {}
        for pid, name, full in self.s.execute(select(M.Person.id, M.Person.name, M.Person.full_name)
                                              .order_by(M.Person.id)):
            for n in {name, full} - {None}:
                key = normalize_name(n)
                if key not in index:
                    index[key] = pid
                elif index[key] != pid:
                    prev = index[key]
                    index[key] = pid if pid in current and prev not in current else (
                        prev if prev in current and pid not in current else None)
        return index

    def person(self, name: str, *, full_name: str | None = None, new_id: str | None = None) -> str:
        keys = [normalize_name(n) for n in (full_name, name) if n]
        for key in keys:
            if self.persons_by_name.get(key):
                return self.persons_by_name[key]
        if any(key in self.persons_by_name for key in keys):
            raise OntologyError(f"{name}: more than one person has this name; add full_name to disambiguate")
        pid = new_id or f"per_ont_{slug(name)}"
        self.s.execute(pg_insert(M.Person).values(id=pid, name=name, full_name=full_name, alternative_names=[])
                       .on_conflict_do_nothing(index_elements=[M.Person.id]))
        self.persons_by_name[normalize_name(name)] = pid
        return pid

    # ------------------------------------------------------------------ state

    def state(self) -> None:
        d = self.doc
        for row in d["federative_units"]:
            self.add(M.FederativeUnit, **row)
        for row in d["powers"]:
            self.add(M.Power, **row)
        for row in d["legislatures"]:
            self.add(M.Legislature, number=row["number"], starts_on=date.fromisoformat(row["starts_on"]),
                     ends_on=date.fromisoformat(row["ends_on"]))
        self.legal_url = {}
        for row in d["legal_bases"]:
            self.add(M.LegalBasis, **row)
            self.legal_url[row["id"]] = row["url"]
            self.fact("state.legal_bases", row["id"], url=row["url"], outlet=row["norm"], generated_by="ontology_file")

        siorg = {e.siorg_code: e for e in self.s.scalars(select(M.ExecutiveBody).where(
            M.ExecutiveBody.institution_id == "ins_br_executivo", M.ExecutiveBody.is_current))}
        by_acronym = {e.acronym: e for e in siorg.values() if e.acronym}
        self.body_by_siorg: dict[str, str] = {}
        curated = []
        for b in d["bodies"]:
            eb = by_acronym.get(b.get("siorg_acronym"))
            if eb:
                self.body_by_siorg[eb.siorg_code] = b["id"]
            curated.append((b, eb))
        for code, eb in siorg.items():
            self.body_by_siorg.setdefault(code, f"bod_{eb.id}")
        institutions = set(self.s.scalars(select(M.Institution.id)))
        for b, eb in curated:
            parent = b.get("parent")
            if parent and parent.startswith("siorg:"):
                target = by_acronym.get(parent.removeprefix("siorg:"))
                parent = self.body_by_siorg[target.siorg_code] if target else "bod_presidencia"
            self.add(M.Body, id=b["id"], name=b["name"], acronym=b.get("acronym"), body_type=b["body_type"],
                     power_id=b["power"], federative_unit_id="fu_uniao", parent_id=parent, seats=b.get("seats"),
                     description=b.get("description"), legal_basis_id=b["legal_basis"],
                     institution_id=b.get("institution") if b.get("institution") in institutions else None,
                     committee_id=None, executive_body_id=eb.id if eb else None, origin="curated",
                     url=b.get("url") or (eb.site if eb else None))
            self.fact("state.bodies", b["id"], url=self.legal_url[b["legal_basis"]], generated_by="ontology_file")
            if eb and eb.raw_record_id:
                self.fact("state.bodies", b["id"], raw_record_id=eb.raw_record_id, outlet="SIORG")
        for code, eb in siorg.items():
            if self.body_by_siorg[code] != f"bod_{eb.id}":
                continue
            body_type = "ministerio" if eb.unit_type == "orgao" and eb.name.startswith("Ministério") else eb.unit_type
            self.add(M.Body, id=f"bod_{eb.id}", name=eb.name, acronym=eb.acronym, body_type=body_type,
                     power_id="pow_executivo", federative_unit_id="fu_uniao",
                     parent_id=self.body_by_siorg.get(eb.parent_code or "", "bod_presidencia"), seats=None,
                     description=eb.competence or eb.purpose, legal_basis_id=None, institution_id=None,
                     committee_id=None, executive_body_id=eb.id, origin="siorg", url=eb.site)
            self.fact("state.bodies", f"bod_{eb.id}", raw_record_id=eb.raw_record_id, outlet="SIORG")
        for c in self.s.scalars(select(M.Committee).where(M.Committee.institution_id.in_(CHAMBER_BODY))
                                .order_by(M.Committee.id)):
            seats = (c.attributes or {}).get("seats") or {}
            titulares = str(seats.get("titulares") or "")
            self.add(M.Body, id=f"bod_{c.id}", name=c.name, acronym=c.abbreviation, body_type="comissao",
                     power_id="pow_legislativo", federative_unit_id="fu_uniao",
                     parent_id=CHAMBER_BODY[c.institution_id], seats=int(titulares) if titulares.isdigit() else None,
                     description=(c.attributes or {}).get("purpose") or c.committee_type, legal_basis_id="cf_art58",
                     institution_id=None, committee_id=c.id, executive_body_id=None, origin="committee",
                     url=(c.attributes or {}).get("url"))
            self.fact("state.bodies", f"bod_{c.id}", raw_record_id=c.raw_record_id, url=(c.attributes or {}).get("url"))
        self.body_ids = {r["id"] for r in self.rows[M.Body]}
        self.body_by_name = {normalize_name(r["name"]): r["id"] for r in self.rows[M.Body]
                             if r["power_id"] in ("pow_executivo", "pow_controle")}

        for o in d["offices"]:
            self.add(M.Office, id=o["id"], body_id=o.get("body"), name=o["name"], seats=o.get("seats"),
                     term_years=o.get("term_years"), provision=o["provision"], description=o.get("description"),
                     legal_basis_id=o["legal_basis"])
            self.fact("state.offices", o["id"], url=self.legal_url[o["legal_basis"]], generated_by="ontology_file")
        for c in d["competences"]:
            self.add(M.Competence, id=c["id"], holder_body_id=c.get("holder_body"),
                     holder_office_id=c.get("holder_office"), verb=c["verb"], target_body_id=c.get("target_body"),
                     target_office_id=c.get("target_office"), target_label=c["target_label"],
                     quorum=c.get("quorum"), exclusive=c.get("exclusive", True), flow=c.get("flow"),
                     flow_order=c.get("flow_order"), legal_basis_id=c["legal_basis"], provision=c.get("provision"),
                     description=c.get("description"))
            self.fact("state.competences", c["id"], url=self.legal_url[c["legal_basis"]],
                      generated_by="ontology_file")

    # ------------------------------------------------------------------ actors

    def organizations(self) -> None:
        self.org_by_abbrev: dict[str, str] = {}
        for party in self.s.scalars(select(M.Party).order_by(M.Party.first_observed_at, M.Party.id)):
            key = normalize_name(party.abbreviation).upper()
            if key in self.org_by_abbrev:
                continue
            oid = f"org_party_{slug(party.abbreviation)}"
            self.org_by_abbrev[key] = oid
            self.add(M.Organization, id=oid, kind="partido", abbreviation=party.abbreviation, name=party.name,
                     party_id=party.id)
            self.fact("core.organizations", oid, outlet=party.source_system_id)
        for org in self.doc["organizations"]:
            self.add(M.Organization, id=org["id"], kind=org["kind"], abbreviation=org.get("abbreviation"),
                     name=org.get("name"), party_id=None)
            self.fact("core.organizations", org["id"], kind="press_report", generated_by="ontology_file")

    def org(self, abbreviation: str | None) -> str | None:
        return self.org_by_abbrev.get(normalize_name(abbreviation).upper()) if abbreviation else None

    def holdings(self) -> None:
        held: dict[str, list[str]] = defaultdict(list)
        mandate_evidence = dict(self.s.execute(
            select(M.EntityEvidence.entity_id, func.min(M.EntityEvidence.raw_record_id.cast(M.Text)))
            .where(M.EntityEvidence.entity_kind == "mandate").group_by(M.EntityEvidence.entity_id)).all())
        self.minister_party: dict[str, str] = {}
        profile = dict(self.s.execute(select(M.Person.id, M.Person.profile_url)).all())
        mandates = self.s.scalars(select(M.Mandate).where(M.Mandate.institution_id.in_(FEDERAL),
                                                          M.Mandate.status == "in_exercise").order_by(M.Mandate.id))
        for m in mandates:
            office, provision = MANDATE_OFFICE[m.role_type]
            body = CHAMBER_BODY.get(m.institution_id)
            if m.role_type == "minister_of_state":
                title = re.sub(r"\s*\(Brasil\)$", "", (m.attributes or {}).get("ministry_title") or "")
                body = self.body_by_name.get(normalize_name(title), "bod_presidencia")
                if (m.attributes or {}).get("party"):
                    self.minister_party[m.person_id] = m.attributes["party"]
            hid = f"hold_{m.id}"
            self.add(M.OfficeHolding, id=hid, person_id=m.person_id, office_id=office, body_id=body,
                     provision=provision, nominated_by="Presidente da República" if office == "off_ministro_estado"
                     else None, represented_unit=m.represented_unit, seat_kind=m.participation or "holder",
                     since=m.start_date, mandate_id=m.id, committee_membership_id=None, origin="mandate")
            held[m.person_id].append(hid)
            if m.source_system_id in OFFICIAL_SOURCES:
                raw = mandate_evidence.get(m.id)
                self.fact("core.office_holdings", hid, raw_record_id=uuid.UUID(raw) if raw else None,
                          url=profile.get(m.person_id), outlet=m.source_system_id)
            else:
                refs = (m.attributes or {}).get("refs") or []
                self.cite("core.office_holdings", hid, [dict(r, kind="press_report") for r in refs] or
                          [{"kind": "analysis", "outlet": m.source_system_id}], generated_by="connector")
        memberships = self.s.execute(
            select(M.CommitteeMembership, M.Committee.institution_id).join(M.Committee)
            .where(M.CommitteeMembership.is_current, M.Committee.institution_id.in_(CHAMBER_BODY))
            .order_by(M.CommitteeMembership.id))
        for cm, _ in memberships:
            office = COMMITTEE_OFFICE.get((cm.role or "").upper(), "off_membro_comissao")
            hid = f"hold_{cm.id}"
            self.add(M.OfficeHolding, id=hid, person_id=cm.person_id, office_id=office,
                     body_id=f"bod_{cm.committee_id}",
                     provision="party_indication" if office == "off_membro_comissao" else "elected_by_peers",
                     nominated_by=cm.bloc or cm.party_abbreviation, represented_unit=cm.represented_unit,
                     seat_kind=cm.seat_kind, since=cm.valid_from, mandate_id=cm.mandate_id,
                     committee_membership_id=cm.id, origin="committee_membership")
            self.fact("core.office_holdings", hid, raw_record_id=cm.raw_record_id)

        def curated(person_id, office, sources, *, since=None, nominated_by=None, origin="dossier", hid=None):
            office_row = next(o for o in self.rows[M.Office] if o["id"] == office)
            hid = hid or f"hold_{office}_{person_id}"
            self.add(M.OfficeHolding, id=hid, person_id=person_id, office_id=office, body_id=office_row["body_id"],
                     provision=office_row["provision"], nominated_by=nominated_by, represented_unit=None,
                     seat_kind="holder", since=since, mandate_id=None, committee_membership_id=None, origin=origin)
            self.cite("core.office_holdings", hid, sources,
                      generated_by="ontology_file" if origin == "ontology_file" else "dossier")

        for h in self.doc["holdings"]:
            pid = self.person(h["person"], full_name=h.get("full_name"))
            curated(pid, h["office"], h["sources"], since=parse_date(h.get("since")),
                    nominated_by=h.get("nominated_by"), origin="ontology_file")
        self.executive_party: dict[str, str] = {}
        for item in self.dossiers["poder-executivo"]["office"]:
            p = item.payload
            office = "off_vice" if p["role"].startswith("Vice") else "off_pres_republica"
            pid = self.person(p["name"])
            self.executive_party[pid] = p.get("party")
            curated(pid, office, item.sources, since=parse_date(p.get("since")))
        self.stf_people: dict[str, str] = {}
        for item in self.dossiers["stf-caso-master"]["minister"]:
            p = item.payload
            pid = self.person(p["name"], full_name=p.get("full_name"), new_id=f"per_{item.id}")
            self.stf_people[item.id] = pid
            since = parse_date(p.get("took_office"))
            curated(pid, "off_ministro_stf", item.sources, since=since, nominated_by=p.get("nominated_by"))
            role = normalize_name(p.get("role") or "")
            if role.startswith("presidente do stf"):
                curated(pid, "off_pres_stf", item.sources)
            elif role.startswith("vice-presidente do stf"):
                curated(pid, "off_vice_stf", item.sources)
            for alias in p.get("aliases") or []:
                self.add(M.PersonName, person_id=pid, name=alias, kind="alias", origin="dossier")
        self.held_persons = {r["person_id"] for r in self.rows[M.OfficeHolding]}

    def affiliations(self) -> None:
        best: dict[str, M.PartyMembership] = {}
        rows = self.s.scalars(select(M.PartyMembership).where(
            M.PartyMembership.is_current, M.PartyMembership.institution_id.in_(FEDERAL),
            M.PartyMembership.person_id.in_(self.held_persons)))
        for pm in rows:
            cur = best.get(pm.person_id)
            rank = (MEMBERSHIP_PRIORITY.get(pm.basis, 9), -(pm.valid_from or date.min).toordinal())
            if cur is None or rank < (MEMBERSHIP_PRIORITY.get(cur.basis, 9), -(cur.valid_from or date.min).toordinal()):
                best[pm.person_id] = pm
        party_abbrev = dict(self.s.execute(select(M.Party.id, M.Party.abbreviation)).all())
        for pid, pm in best.items():
            org = self.org(party_abbrev.get(pm.party_id))
            if org:
                self.add(M.Affiliation, person_id=pid, organization_id=org, since=pm.valid_from,
                         party_membership_id=pm.id, basis=pm.basis)
                self.fact("core.affiliations", pid, outlet=pm.basis)
        for pid, abbrev in {**self.minister_party, **self.executive_party}.items():
            org = self.org(abbrev)
            if org and pid not in best:
                best[pid] = None
                self.add(M.Affiliation, person_id=pid, organization_id=org, since=None, party_membership_id=None,
                         basis="executive_listing")
                self.fact("core.affiliations", pid, kind="press_report", outlet="executive_listing")

    def person_names(self) -> None:
        seen = {(r["person_id"], r["name"]) for r in self.rows[M.PersonName]}
        for pid, name, full in self.s.execute(select(M.Person.id, M.Person.name, M.Person.full_name)
                                              .where(M.Person.id.in_(self.held_persons))):
            for n, kind in ((name, "parliamentary"), (full, "civil")):
                if n and (pid, n) not in seen:
                    seen.add((pid, n))
                    self.add(M.PersonName, person_id=pid, name=n, kind=kind, origin="core.persons")

    # ------------------------------------------------------------------ processes and analyses

    def proceedings(self) -> None:
        master = self.dossiers["stf-caso-master"]
        if master["current_status"]:
            status = master["current_status"][0]
            p = status.payload
            pid = "prc_master_relatorios_pf"
            self.add(M.Proceeding, id=pid, kind="relatorio_pf", title="Relatórios da PF sobre ministros do STF",
                     body_id="bod_pgr", competence_id="cmp_pgr_denuncia_ministro_stf", status=p["title"],
                     summary=p.get("responsible"), dossier="stf-caso-master")
            self.cite("process.proceedings", pid, status.sources)
            for item in master["minister"]:
                report = item.payload.get("master_report") or {}
                if report.get("status") in (None, "not_reported"):
                    continue
                self.add(M.Participant, id=f"par_{pid}_{item.id}", proceeding_id=pid,
                         person_id=self.stf_people[item.id], body_id=None, organization_id=None,
                         label=item.payload["name"], role=f"citado_{report['status']}", detail=report.get("label"),
                         epistemic_status="press_report")
            for actor, body, role in (("Polícia Federal", "bod_pf", "autor"), ("PGR", "bod_pgr", "analisa"),
                                      ("Banco Master", None, "empresa_do_caso")):
                self.add(M.Participant, id=f"par_{pid}_{slug(actor)}", proceeding_id=pid, person_id=None,
                         body_id=body, organization_id=None if body else "org_banco_master", label=actor, role=role,
                         detail=None, epistemic_status="press_report")
            for item in master["procedure_actor"]:
                a = item.payload
                body = next((b for key, b in ACTOR_BODIES if key in normalize_name(a["actor"])), None)
                self.add(M.Participant, id=f"par_{pid}_{item.id}", proceeding_id=pid, person_id=None, body_id=body,
                         organization_id=None, label=a["actor"], role="ator_processual", detail=a.get("powers"),
                         epistemic_status="official")
            events = sorted(master["timeline_event"], key=lambda i: (i.payload.get("date") or "", i.id))
            for n, item in enumerate(events):
                self.add(M.Step, id=f"stp_{item.id}", proceeding_id=pid, ordinal=n, title=item.payload.get("track"),
                         text=item.payload["text"], happened_on=parse_date(item.payload.get("date")), status="done",
                         decided_by_body_id=None)
                self.cite("process.steps", f"stp_{item.id}", item.sources)
            for k, outcome in enumerate(p.get("possible_outcomes") or []):
                self.add(M.Step, id=f"stp_{pid}_outcome_{k}", proceeding_id=pid, ordinal=len(events) + k,
                         title=outcome["outcome"], text=outcome.get("then") or outcome["outcome"], happened_on=None,
                         status="possible", decided_by_body_id="bod_pgr")
            if p.get("deadline_estimate"):
                self.add(M.Deadline, id=f"ddl_{pid}", proceeding_id=pid, due_on=parse_date(p["deadline_estimate"]),
                         basis="politeia_estimate", note=p.get("deadline_note"))
        if master["impeachment_step"]:
            pid = "prc_master_impeachment"
            self.add(M.Proceeding, id=pid, kind="impeachment", title="Impeachment de ministro do STF (rito)",
                     body_id="bod_senado", competence_id="cmp_senado_julga_ministro_stf",
                     status="Caminho possível, previsto na Lei nº 1.079/1950", summary=None, dossier="stf-caso-master")
            self.fact("process.proceedings", pid, url=self.legal_url["lei1079"], generated_by="ontology_file")
            for item in sorted(master["impeachment_step"], key=lambda i: i.payload.get("order", 0)):
                self.add(M.Step, id=f"stp_{item.id}", proceeding_id=pid, ordinal=item.payload.get("order", 0),
                         title=item.payload.get("step"), text=item.payload["text"], happened_on=None,
                         status="possible", decided_by_body_id="bod_senado")
                self.cite("process.steps", f"stp_{item.id}", item.sources)

        race = self.dossiers["presidencia-2027"]
        if race["contest"]:
            contest = race["contest"][0]
            c = contest.payload
            pid = "prc_presidencia_senado_2027"
            self.add(M.Proceeding, id=pid, kind="eleicao_interna", title=c["title"], body_id="bod_senado",
                     competence_id="cmp_senadores_elegem_presidente",
                     status="Disputa ainda não oficializada (imprensa e declarações)", summary=c.get("note"),
                     dossier="presidencia-2027")
            self.cite("process.proceedings", pid, contest.sources)
            for item in race["candidate"]:
                cand = item.payload
                self.add(M.Participant, id=f"par_{item.id}", proceeding_id=pid,
                         person_id=cand.get("person_id") or self.person(cand["name"]), body_id=None,
                         organization_id=self.org(cand.get("party")), label=cand["name"], role="candidato",
                         detail=cand.get("status"), epistemic_status="press_report")
                self.cite("process.participants", f"par_{item.id}", item.sources)
            if c.get("date"):
                self.add(M.Deadline, id=f"ddl_{pid}", proceeding_id=pid, due_on=parse_date(c["date"]),
                         basis="scheduled", note=f"{c.get('voters')} eleitores; maioria de {c.get('majority')} votos, "
                                                 "em escrutínio secreto.")

    def analyses(self) -> None:
        proceedings = {r["id"]: r for r in self.rows[M.Proceeding]}
        participants = self.rows[M.Participant]
        for a in self.doc["analyses"]:
            items = self.dossiers.get(a["dossier"]) or {}
            as_of = next((i.as_of for kind in items.values() for i in kind), None)
            self.add(M.Analysis, id=a["id"], title=a["title"], dossier=a["dossier"], questions=a["questions"],
                     as_of=as_of)
            entities = {(kind, eid): role for kind, eid, role in a["entities"]}
            for prc in proceedings.values():
                if prc["dossier"] == a["dossier"]:
                    entities[("proceeding", prc["id"])] = prc["title"]
            for par in participants:
                if proceedings[par["proceeding_id"]]["dossier"] == a["dossier"] and par["person_id"]:
                    entities.setdefault(("person", par["person_id"]), par["role"])
            for claim_id, in self.s.execute(select(M.Claim.id).where(M.Claim.dossier == a["dossier"])):
                entities[("claim", claim_id)] = "afirmação"
            for (kind, eid), role in sorted(entities.items()):
                self.add(M.AnalysisEntity, analysis_id=a["id"], entity_kind=kind, entity_id=eid, role=role)
        for item in self.dossiers["presidencia-2027"]["scenarios"]:
            for i, sc in enumerate(item.payload.get("scenarios") or []):
                for j, cand in enumerate(sc.get("candidates") or []):
                    eid = f"est_{item.id}_{i}_{j}"
                    self.add(M.Estimate, id=eid, analysis_id="ana_presidencia_2027", scenario=sc["name"],
                             subject_label=cand["name"], low=cand.get("low"), high=cand.get("high"),
                             basis=cand.get("basis"), method=item.payload.get("note") or "", label="inferência")
                    self.cite("analysis.estimates", eid, item.sources)

    def news(self) -> None:
        topics = {t: a["id"] for a in self.doc["analyses"] for t in a["news_topics"]}
        proceedings = {r["id"] for r in self.rows[M.Proceeding]}
        candidates = self.s.scalars(select(M.NewsItem).order_by(M.NewsItem.id)).all()
        for item in political_news(self.s, candidates):
            news_id, links = item.id, set()
            for t in item.topics or []:
                if t in topics:
                    links.add(("analysis", topics[t], t))
                if PROCEEDING_TOPICS.get(t) in proceedings:
                    links.add(("proceeding", PROCEEDING_TOPICS[t], t))
            seen = set()
            for kind, target, topic in sorted(links):
                if (kind, target) not in seen:
                    seen.add((kind, target))
                    self.add(M.NewsLink, news_item_id=news_id, target_kind=kind, target_id=target, topic=topic)

    # ------------------------------------------------------------------ write

    def write(self) -> dict[str, int]:
        for model in PROJECTION:
            self.s.execute(delete(model))
        stats = {}
        for model in reversed(PROJECTION):
            rows = self.facts if model is M.FactSource else self.rows.get(model, [])
            if model is M.Body:
                rows = _parents_first(rows)
            if model is M.ObservedLink:
                stats["behavior.observed_links"] = observed_links(self.s)
                continue
            for start in range(0, len(rows), 2000):
                self.s.execute(insert(model), rows[start:start + 2000])
            stats[f"{model.__table__.schema}.{model.__tablename__}"] = len(rows)
        return stats


def _parents_first(bodies: list[dict]) -> list[dict]:
    by_id = {b["id"]: b for b in bodies}

    def depth(body: dict) -> int:
        n, seen = 0, set()
        while body.get("parent_id") in by_id and body["id"] not in seen:
            seen.add(body["id"])
            body, n = by_id[body["parent_id"]], n + 1
        return n

    for b in bodies:
        if b["parent_id"] and b["parent_id"] not in by_id:
            raise OntologyError(f"{b['id']}: unknown parent {b['parent_id']}")
    return sorted(bodies, key=depth)


def observed_links(s: Session) -> int:
    """Pairwise agreement over open roll calls, for members in exercise in each chamber."""
    result = s.execute(text("""
        INSERT INTO behavior.observed_links
            (institution_id, person_a_id, person_b_id, kind, shared, agreements, weight, window_start, window_end)
        SELECT ve.institution_id, a.person_id, b.person_id, 'vote_agreement', count(*),
               count(*) FILTER (WHERE a.vote_code = b.vote_code),
               round(count(*) FILTER (WHERE a.vote_code = b.vote_code)::numeric / count(*), 4),
               min(ve.held_on), max(ve.held_on)
        FROM legislative.vote_events ve
        JOIN legislative.individual_votes a ON a.vote_event_id = ve.id
        JOIN legislative.individual_votes b ON b.vote_event_id = ve.id AND a.person_id < b.person_id
        WHERE NOT ve.secret AND ve.institution_id IN ('ins_br_senado', 'ins_br_camara')
          AND a.vote_code = ANY(:choices) AND b.vote_code = ANY(:choices)
          AND EXISTS (SELECT 1 FROM core.mandates m WHERE m.person_id = a.person_id
                      AND m.institution_id = ve.institution_id AND m.status = 'in_exercise')
          AND EXISTS (SELECT 1 FROM core.mandates m WHERE m.person_id = b.person_id
                      AND m.institution_id = ve.institution_id AND m.status = 'in_exercise')
        GROUP BY ve.institution_id, a.person_id, b.person_id
        HAVING count(*) >= :min_shared
    """), {"choices": list(VOTE_CHOICES), "min_shared": MIN_SHARED_VOTES})
    return result.rowcount


def load_ontology(s: Session, path: Path = ONTOLOGY_FILE) -> dict[str, int]:
    loader = _Loader(s, read_ontology(path))
    loader.state()
    loader.organizations()
    loader.holdings()
    loader.affiliations()
    loader.person_names()
    loader.proceedings()
    loader.analyses()
    loader.news()
    return loader.write()
