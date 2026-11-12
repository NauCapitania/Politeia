"""ALEPE — Assembleia Legislativa de Pernambuco, Dados Abertos (dadosabertos.alepe.pe.gov.br/api/v1)."""

import re

from defusedxml import ElementTree

from connectors.base.protocol import (
    AuthorRecord,
    Batch,
    Connector,
    Identifier,
    Issue,
    MandateRecord,
    PartyMembershipRecord,
    PartyRecord,
    PersonRecord,
    ProposalRecord,
    RawResponse,
    Ref,
    normalize_name,
    parse_date,
)

PERSON = "alepe.parlamentar.nome"
MANDATE = "alepe.mandato"
PARTY = "alepe.partido.sigla"
AUTHOR_KINDS = {"DEPUTADO": "member", "EXTERNO": "external", "COMISSAO": "committee"}


def _type_code(name: str, codes: dict[str, str]) -> str:
    if name in codes:
        return codes[name]
    return "".join(w[0] for w in re.findall(r"[A-ZÀ-Ú]+", name.upper()) if len(w) > 2) or name


class AlepeConnector(Connector):
    id = "pernambuco-alepe"
    version = "0.1.0"
    scopes = ("members", "proposals")

    @property
    def base(self) -> str:
        return self.config["base_url"].rstrip("/")

    def fetch(self, scope: str) -> Batch:
        batch = Batch(scope=scope)
        if scope == "members":
            batch.add_raw(RawResponse(self.client.get(f"{self.base}/parlamentares/"), "member_list"))
        elif scope == "proposals":
            for year in self.config.get("proposal_years") or [None]:
                params = {"ano": year} if year else None
                resp = self.client.get(f"{self.base}/proposicoes/projetos/", params=params,
                                       accept="application/xml")
                batch.add_raw(RawResponse(resp, "proposal_list", str(year or "current")))
        else:
            raise ValueError(f"unknown scope {scope}")
        return batch

    def normalize(self, batch: Batch) -> Batch:
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind == "member_list":
                self._members(batch, idx, raw)
            elif raw.record_kind == "proposal_list":
                self._proposals(batch, idx, raw)
        return batch

    def _members(self, batch: Batch, idx: int, raw: RawResponse) -> None:
        data = raw.json()
        if not isinstance(data, list):
            batch.issues.append(Issue("error", "schema_changed", "member list is not an array", raw=idx))
            return
        parties: dict[str, PartyRecord] = {}
        for i, m in enumerate(data):
            name = (m.get("nomeParlamentar") or "").strip() if isinstance(m, dict) else ""
            path = f"$[{i}]"
            if not name:
                batch.issues.append(Issue("error", "missing_field", "member without nomeParlamentar",
                                          {"path": path}, raw=idx))
                continue
            pid = Identifier(PERSON, normalize_name(name), quality="name-derived")
            batch.persons.append(PersonRecord(identifier=pid, name=name, ref=Ref(idx, path)))
            batch.mandates.append(MandateRecord(
                identifier=Identifier(MANDATE, f"{pid.value}:current", quality="name-derived"),
                person=pid, role_type="state_deputy", represented_unit="PE", participation=None,
                ref=Ref(idx, path), epistemic_status="verified",
                attributes={"dates_available": False},
            ))
            sigla = (m.get("partido") or "").strip()
            if sigla:
                party_id = Identifier(PARTY, sigla)
                parties.setdefault(sigla, PartyRecord(party_id, sigla, Ref(idx, f"{path}.partido")))
                batch.memberships.append(PartyMembershipRecord(
                    person=pid, party=party_id, basis="current_listing", is_current=True,
                    ref=Ref(idx, f"{path}.partido"),
                ))
            else:
                batch.issues.append(Issue("warning", "missing_party", f"no party for {name}", raw=idx))
        batch.parties = list(parties.values())
        batch.complete_member_list = bool(batch.persons)

    def _proposals(self, batch: Batch, idx: int, raw: RawResponse) -> None:
        try:
            root = ElementTree.fromstring(raw.response.content)
        except ElementTree.ParseError as exc:
            batch.issues.append(Issue("error", "invalid_xml", str(exc), raw=idx))
            return
        codes = self.config.get("proposal_type_codes", {})
        for i, el in enumerate(root.iter("projeto")):
            a = el.attrib
            if not a.get("docid") or not a.get("numero") or not (a.get("ano") or "").isdigit():
                batch.issues.append(Issue("warning", "missing_field", "projeto without docid/numero/ano",
                                          {"index": i}, raw=idx))
                continue
            type_name = (a.get("tipo") or "").strip()
            prop = ProposalRecord(
                source_id=a["docid"], type_code=_type_code(type_name, codes), type_name=type_name,
                number=a["numero"], year=int(a["ano"]), ref=Ref(idx, f"/projetos/projeto[{i + 1}]"),
                ementa=(a.get("ementa") or "").strip() or None, introduced_on=parse_date(a.get("dataPublicacao")),
                official_url=f"{self.base}/proposicoes/projetos/?numero={a['numero']}&ano={a['ano']}",
                attributes={"subtype": (a.get("subtipo") or "").strip() or None,
                            "legislature": (a.get("legislatura") or "").strip() or None,
                            "date_semantics": "publication"},
            )
            for j, au in enumerate(el.iter("autor")):
                name = (au.get("nome") or "").strip()
                kind = AUTHOR_KINDS.get((au.get("tipo") or "").strip().upper(), "other")
                person = Identifier(PERSON, normalize_name(name), "name-derived") if kind == "member" else None
                prop.authors.append(AuthorRecord(
                    ordinal=j + 1, name=name, kind=kind, person=person,
                    resolution="name_match" if person else "unresolved", epistemic_status="extracted",
                    attributes={"source_type": au.get("tipo")},
                ))
            batch.proposals.append(prop)
