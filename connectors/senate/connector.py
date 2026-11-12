"""Senado Federal — Dados Abertos Legislativos (legis.senado.leg.br/dadosabertos)."""

import re
from datetime import UTC, date, datetime, timedelta

from connectors.base.http import SourceAccessError
from connectors.base.protocol import (
    AuthorRecord,
    Batch,
    Connector,
    EventRecord,
    Identifier,
    Issue,
    MandateRecord,
    PartyMembershipRecord,
    PartyRecord,
    PersonRecord,
    ProposalRecord,
    RawResponse,
    Ref,
    as_list,
    parse_date,
)

PERSON = "senado.parlamentar"
MANDATE = "senado.mandato"
PARTY = "senado.partido.sigla"
PARTY_CODE = "senado.partido.codigo"
MATERIA_URL = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{}"
IDENT_RE = re.compile(r"^(?P<sigla>[A-Z]+)\s+(?P<numero>[\dA-Z.-]+)/(?P<ano>\d{4})$")

AUTHOR_KINDS = {
    "SENADOR": "member",
    "COMISSAO": "committee",
    "PRESIDENTE_REPUBLICA": "executive",
    "DEPUTADO_FEDERAL": "external",
}


def _https(url: str | None) -> str | None:
    return url.replace("http://", "https://", 1) if url and url.startswith("http://") else url


class SenateConnector(Connector):
    id = "brazil-senate"
    version = "0.1.0"
    scopes = ("members", "proposals")

    @property
    def base(self) -> str:
        return self.config["base_url"].rstrip("/")

    # ------------------------------------------------------------------ fetch
    def fetch(self, scope: str) -> Batch:
        batch = Batch(scope=scope)
        if scope == "members":
            self._fetch_members(batch)
        elif scope == "proposals":
            self._fetch_proposals(batch)
        else:
            raise ValueError(f"unknown scope {scope}")
        return batch

    def _fetch_members(self, batch: Batch) -> None:
        resp = self.client.get(f"{self.base}/senador/lista/atual")
        idx = batch.add_raw(RawResponse(resp, "member_list"))
        members = as_list(
            batch.raw[idx].json().get("ListaParlamentarEmExercicio", {}).get("Parlamentares", {}).get("Parlamentar")
        )
        for m in members:
            code = m.get("IdentificacaoParlamentar", {}).get("CodigoParlamentar")
            if not code:
                continue
            try:
                r = self.client.get(f"{self.base}/senador/{code}/filiacoes")
                batch.add_raw(RawResponse(r, "party_affiliations", str(code)))
            except SourceAccessError as exc:
                batch.issues.append(
                    Issue("warning", "affiliations_unavailable", str(exc), {"codigoParlamentar": code})
                )

    def _fetch_proposals(self, batch: Batch) -> None:
        days = int(self.config.get("proposal_window_days", 45))
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        ids: list[int] = []
        for sigla in self.config.get("proposal_types", ["PL", "PLP", "PEC", "PDL", "PRS"]):
            params = {"sigla": sigla, "dataInicioApresentacao": start.isoformat(),
                      "dataFimApresentacao": end.isoformat()}
            resp = self.client.get(f"{self.base}/processo", params=params)
            idx = batch.add_raw(RawResponse(resp, "proposal_list", sigla))
            ids += [p["id"] for p in as_list(batch.raw[idx].json()) if "id" in p]
        limit = int(self.config.get("max_proposal_details", 400))
        if len(ids) > limit:
            batch.issues.append(Issue("info", "detail_limit", f"details fetched for {limit} of {len(ids)}"))
        for pid in ids[:limit]:
            try:
                r = self.client.get(f"{self.base}/processo/{pid}")
                batch.add_raw(RawResponse(r, "proposal_detail", str(pid)))
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "proposal_detail_unavailable", str(exc), {"id": pid}))

    # ------------------------------------------------------------------ normalize
    def normalize(self, batch: Batch) -> Batch:
        if batch.scope == "members":
            self._normalize_members(batch)
        else:
            self._normalize_proposals(batch)
        return batch

    def _normalize_members(self, batch: Batch) -> None:
        parties: dict[str, PartyRecord] = {}
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "member_list":
                continue
            root = raw.json().get("ListaParlamentarEmExercicio")
            if root is None:
                batch.issues.append(Issue("error", "schema_changed", "ListaParlamentarEmExercicio missing", raw=idx))
                continue
            members = as_list(root.get("Parlamentares", {}).get("Parlamentar"))
            batch.complete_member_list = bool(members)
            for i, m in enumerate(members):
                path = f"$.ListaParlamentarEmExercicio.Parlamentares.Parlamentar[{i}]"
                ident = m.get("IdentificacaoParlamentar") or {}
                code = ident.get("CodigoParlamentar")
                name = ident.get("NomeParlamentar")
                if not code or not name:
                    batch.issues.append(Issue("error", "missing_field", "member without code/name",
                                              {"path": path}, raw=idx))
                    continue
                pid = Identifier(PERSON, str(code))
                gender = {"Masculino": "male", "Feminino": "female"}.get(ident.get("SexoParlamentar", ""))
                batch.persons.append(PersonRecord(
                    identifier=pid, name=name.strip(), full_name=ident.get("NomeCompletoParlamentar"),
                    gender=gender, photo_url=_https(ident.get("UrlFotoParlamentar")),
                    profile_url=_https(ident.get("UrlPaginaParlamentar")), ref=Ref(idx, path),
                ))
                mand = m.get("Mandato") or {}
                first = mand.get("PrimeiraLegislaturaDoMandato") or {}
                second = mand.get("SegundaLegislaturaDoMandato") or {}
                exercises = as_list((mand.get("Exercicios") or {}).get("Exercicio"))
                current_ex = next((e for e in exercises if not e.get("DataFim")), None)
                participation = mand.get("DescricaoParticipacao", "")
                bloco = ident.get("Bloco") or {}
                batch.mandates.append(MandateRecord(
                    identifier=Identifier(MANDATE, f"{mand.get('CodigoMandato')}:{code}"),
                    person=pid, role_type="senator",
                    represented_unit=mand.get("UfParlamentar") or ident.get("UfParlamentar"),
                    participation="holder" if participation == "Titular" else "substitute_in_exercise",
                    start_date=parse_date(first.get("DataInicio")),
                    end_date=parse_date(second.get("DataFim") or first.get("DataFim")),
                    ref=Ref(idx, f"{path}.Mandato"),
                    attributes={
                        "source_participation": participation,
                        "legislatures": [x.get("NumeroLegislatura") for x in (first, second) if x],
                        "current_exercise_start": current_ex.get("DataInicio") if current_ex else None,
                        "holder": (mand.get("Titular") or {}).get("NomeParlamentar"),
                        "bloc": bloco.get("NomeBloco"),
                        "bloc_abbreviation": bloco.get("NomeApelido"),
                        "board_member": ident.get("MembroMesa") == "Sim",
                        "leadership_member": ident.get("MembroLideranca") == "Sim",
                        "public_code": ident.get("CodigoPublicoNaLegAtual"),
                    },
                ))
                sigla = ident.get("SiglaPartidoParlamentar")
                if sigla:
                    party_id = Identifier(PARTY, sigla)
                    party_ref = Ref(idx, f"{path}.IdentificacaoParlamentar")
                    parties.setdefault(sigla, PartyRecord(party_id, sigla, party_ref))
                    batch.memberships.append(PartyMembershipRecord(
                        person=pid, party=party_id, basis="current_listing", is_current=True,
                        ref=Ref(idx, f"{path}.IdentificacaoParlamentar.SiglaPartidoParlamentar"),
                    ))
                else:
                    batch.issues.append(Issue("warning", "missing_party", f"no party for {name}", raw=idx))

        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "party_affiliations":
                continue
            parl = (raw.json().get("FiliacaoParlamentar") or {}).get("Parlamentar") or {}
            pid = Identifier(PERSON, str(parl.get("Codigo") or raw.source_record_key))
            for i, f in enumerate(as_list((parl.get("Filiacoes") or {}).get("Filiacao"))):
                p = f.get("Partido") or {}
                sigla = p.get("SiglaPartido")
                if not sigla:
                    continue
                party_id = Identifier(PARTY, sigla)
                path = f"$.FiliacaoParlamentar.Parlamentar.Filiacoes.Filiacao[{i}]"
                rec = parties.setdefault(sigla, PartyRecord(party_id, sigla, Ref(idx, path)))
                rec.name = rec.name or p.get("NomePartido")
                if p.get("CodigoPartido") and not rec.extra_identifiers:
                    rec.extra_identifiers.append(Identifier(PARTY_CODE, str(p["CodigoPartido"])))
                batch.memberships.append(PartyMembershipRecord(
                    person=pid, party=party_id, basis="affiliation_history",
                    is_current=not f.get("DataDesfiliacao"), ref=Ref(idx, path),
                    valid_from=parse_date(f.get("DataFiliacao")), valid_to=parse_date(f.get("DataDesfiliacao")),
                ))
        batch.parties = list(parties.values())

    def _normalize_proposals(self, batch: Batch) -> None:
        details = {raw.source_record_key: (idx, raw.json()) for idx, raw in enumerate(batch.raw)
                   if raw.record_kind == "proposal_detail"}
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "proposal_list":
                continue
            items = raw.json()
            if not isinstance(items, list):
                batch.issues.append(Issue("error", "schema_changed", "proposal list is not an array", raw=idx))
                continue
            for i, item in enumerate(items):
                m = IDENT_RE.match((item.get("identificacao") or "").strip())
                if not m or "id" not in item:
                    batch.issues.append(Issue("warning", "unparsed_identifier", "cannot parse identificacao",
                                              {"value": item.get("identificacao")}, raw=idx))
                    continue
                prop = ProposalRecord(
                    source_id=str(item["id"]), type_code=m["sigla"], type_name=item.get("tipoDocumento") or m["sigla"],
                    number=m["numero"], year=int(m["ano"]), ref=Ref(idx, f"$[{i}]"),
                    ementa=item.get("ementa"), introduced_on=parse_date(item.get("dataApresentacao")),
                    status=item.get("situacaoAtual"), status_date=parse_date(item.get("dataSituacaoAtual")),
                    in_progress={"Sim": True, "Não": False}.get(item.get("tramitando")),
                    official_url=MATERIA_URL.format(item["codigoMateria"]) if item.get("codigoMateria") else None,
                    attributes={"document_url": item.get("urlDocumento"), "authorship_text": item.get("autoria"),
                                "content_type": item.get("tipoConteudo")},
                )
                detail = details.get(str(item["id"]))
                if detail:
                    didx, d = detail
                    prop.extra_refs.append(Ref(didx, "$"))
                    self._authors(prop, d)
                    self._events(prop, d)
                else:
                    prop.attributes["detail_missing"] = True
                batch.proposals.append(prop)

    @staticmethod
    def _authors(prop: ProposalRecord, d: dict) -> None:
        for i, a in enumerate(as_list(d.get("autoriaIniciativa"))):
            code = a.get("codigoParlamentar")
            kind = AUTHOR_KINDS.get((a.get("siglaTipo") or "").replace(" ", "_").upper(), "other")
            person = Identifier(PERSON, str(code)) if code and kind == "member" else None
            prop.authors.append(AuthorRecord(
                ordinal=int(a.get("ordem") or i + 1), name=a.get("autor") or "?", kind=kind, person=person,
                resolution="official_id" if person else "unresolved",
                epistemic_status="verified" if person else "extracted",
                attributes={"source_type": a.get("descricaoTipo"), "party": a.get("siglaPartido"),
                            "uf": a.get("uf"), "source_code": code},
            ))

    @staticmethod
    def _events(prop: ProposalRecord, d: dict) -> None:
        for aut in as_list(d.get("autuacoes")):
            for inf in as_list(aut.get("informesLegislativos")):
                if inf.get("id") is None:
                    continue
                when = inf.get("data")
                try:
                    dt = datetime.fromisoformat(when).replace(tzinfo=None) if when else None
                except ValueError:
                    dt = None
                colegiado = (inf.get("colegiado") or {}).get("sigla")
                prop.events.append(EventRecord(
                    source_event_id=str(inf["id"]), event_type="procedural_record", event_date=dt,
                    description=inf.get("descricao"), body=colegiado,
                ))


def today() -> date:
    return datetime.now(UTC).date()
