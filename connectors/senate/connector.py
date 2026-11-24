"""Senado Federal — Dados Abertos Legislativos (legis.senado.leg.br/dadosabertos)."""

import re
from datetime import UTC, date, datetime, timedelta

from connectors.base.http import SourceAccessError
from connectors.base.protocol import (
    AuthorRecord,
    Batch,
    CommitteeMemberRecord,
    CommitteeRecord,
    Connector,
    EventRecord,
    ExerciseRecord,
    Identifier,
    IndividualVoteRecord,
    Issue,
    MandateRecord,
    PartyMembershipRecord,
    PartyRecord,
    PersonRecord,
    ProposalRecord,
    RawResponse,
    Ref,
    SpeechRecord,
    VoteEventRecord,
    as_list,
    parse_date,
)

PERSON = "senado.parlamentar"
MANDATE = "senado.mandato"
PARTY = "senado.partido.sigla"
PARTY_CODE = "senado.partido.codigo"
MATERIA_URL = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{}"
RESULTS = {"A": "aprovado", "R": "rejeitado"}
PHOTO_URL = "https://www.senado.leg.br/senadores/img/fotos-oficiais/senador{}.jpg"
PROFILE_URL = "https://www25.senado.leg.br/web/senadores/senador/-/perfil/{}"
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
    scopes = ("composition", "members", "votes", "speeches", "proposals", "committees")

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
        elif scope == "composition":
            self._fetch_composition(batch)
        elif scope == "votes":
            self._fetch_votes(batch)
        elif scope == "committees":
            self._fetch_committees(batch)
        elif scope == "speeches":
            self._fetch_speeches(batch)
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

    def _fetch_composition(self, batch: Batch) -> None:
        """Every senator listed in the configured legislatures, with mandates, exercises and party history."""
        codes: list[str] = []
        for leg in self.config.get("composition_legislatures", [57, 58]):
            resp = self.client.get(f"{self.base}/senador/lista/legislatura/{leg}")
            idx = batch.add_raw(RawResponse(resp, "legislature_list", str(leg)))
            root = batch.raw[idx].json().get("ListaParlamentarLegislatura")
            if root is None:
                batch.issues.append(Issue("error", "schema_changed", "ListaParlamentarLegislatura missing", raw=idx))
                continue
            for m in as_list((root.get("Parlamentares") or {}).get("Parlamentar")):
                code = str((m.get("IdentificacaoParlamentar") or {}).get("CodigoParlamentar") or "")
                if code and code not in codes:
                    codes.append(code)
        for code in codes:
            try:
                r = self.client.get(f"{self.base}/senador/{code}/mandatos")
                batch.add_raw(RawResponse(r, "mandates", code))
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "mandates_unavailable", str(exc), {"codigoParlamentar": code}))

    def _fetch_votes(self, batch: Batch) -> None:
        start = parse_date(self.config.get("votes_since", "2025-01-01"))
        end = today()
        while start <= end:
            nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
            stop = min(nxt - timedelta(days=1), end)
            params = {"dataInicio": start.isoformat(), "dataFim": stop.isoformat()}
            try:
                r = self.client.get(f"{self.base}/votacao", params=params)
                batch.add_raw(RawResponse(r, "vote_list", start.strftime("%Y-%m")))
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "votes_unavailable", str(exc), params))
            start = nxt

    def _fetch_committees(self, batch: Batch) -> None:
        """Active committees by type, then each committee's current composition (/comissao/{codigo})."""
        seen: list[str] = []
        for kind in self.config.get("committee_types", ["permanente", "temporaria", "cpi"]):
            try:
                resp = self.client.get(f"{self.base}/comissao/lista/{kind}")
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "committee_list_unavailable", str(exc), {"tipo": kind}))
                continue
            idx = batch.add_raw(RawResponse(resp, "committee_list", kind))
            for group in as_list(((batch.raw[idx].json().get("ListaBasicaComissoes") or {}).get("colegiado") or {})
                                 .get("colegiados")):
                for c in as_list(group.get("colegiado")):
                    code = str(c.get("CodigoColegiado") or "")
                    if code and code not in seen:
                        seen.append(code)
        for code in seen:
            try:
                r = self.client.get(f"{self.base}/comissao/{code}")
                batch.add_raw(RawResponse(r, "committee", code))
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "committee_unavailable", str(exc), {"codigoColegiado": code}))

    def _fetch_speeches(self, batch: Batch) -> None:
        resp = self.client.get(f"{self.base}/senador/lista/atual")
        idx = batch.add_raw(RawResponse(resp, "member_list"))
        members = as_list((batch.raw[idx].json().get("ListaParlamentarEmExercicio") or {})
                          .get("Parlamentares", {}).get("Parlamentar"))
        since = parse_date(self.config.get("speeches_since", "2025-01-01"))
        params = {"dataInicio": since.strftime("%Y%m%d"), "dataFim": today().strftime("%Y%m%d")}
        for m in members:
            code = (m.get("IdentificacaoParlamentar") or {}).get("CodigoParlamentar")
            if not code:
                continue
            try:
                r = self.client.get(f"{self.base}/senador/{code}/discursos", params=params)
                batch.add_raw(RawResponse(r, "speeches", str(code)))
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "speeches_unavailable", str(exc), {"codigoParlamentar": code}))

    # ------------------------------------------------------------------ normalize
    def normalize(self, batch: Batch) -> Batch:
        normalizers = {"members": self._normalize_members, "proposals": self._normalize_proposals,
                       "composition": self._normalize_composition, "votes": self._normalize_votes,
                       "speeches": self._normalize_speeches, "committees": self._normalize_committees}
        normalizers[batch.scope](batch)
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

    def _normalize_composition(self, batch: Batch) -> None:
        names: dict[str, dict] = {}
        parties: dict[str, PartyRecord] = {}
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "legislature_list":
                continue
            root = raw.json().get("ListaParlamentarLegislatura") or {}
            for i, m in enumerate(as_list((root.get("Parlamentares") or {}).get("Parlamentar"))):
                ident = m.get("IdentificacaoParlamentar") or {}
                code = str(ident.get("CodigoParlamentar") or "")
                if code and ident.get("NomeParlamentar"):
                    names.setdefault(code, {"ident": ident, "ref": Ref(idx, f"$.ListaParlamentarLegislatura"
                                                                          f".Parlamentares.Parlamentar[{i}]")})
        for code, info in names.items():
            ident = info["ident"]
            batch.persons.append(PersonRecord(
                identifier=Identifier(PERSON, code), name=ident["NomeParlamentar"].strip(),
                full_name=ident.get("NomeCompletoParlamentar"),
                gender={"Masculino": "male", "Feminino": "female"}.get(ident.get("SexoParlamentar", "")),
                photo_url=PHOTO_URL.format(code), profile_url=PROFILE_URL.format(code), ref=info["ref"],
            ))
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "mandates":
                continue
            parl = (raw.json().get("MandatoParlamentar") or {}).get("Parlamentar") or {}
            code = str(parl.get("Codigo") or raw.source_record_key)
            pid = Identifier(PERSON, code)
            for i, mand in enumerate(as_list((parl.get("Mandatos") or {}).get("Mandato"))):
                path = f"$.MandatoParlamentar.Parlamentar.Mandatos.Mandato[{i}]"
                first = mand.get("PrimeiraLegislaturaDoMandato") or {}
                second = mand.get("SegundaLegislaturaDoMandato") or {}
                legs = [x.get("NumeroLegislatura") for x in (first, second) if x]
                if not mand.get("CodigoMandato") or not any(int(x or 0) >= 56 for x in legs):
                    continue
                participation = mand.get("DescricaoParticipacao", "")
                exercises = as_list((mand.get("Exercicios") or {}).get("Exercicio"))
                end = parse_date(second.get("DataFim") or first.get("DataFim"))
                open_ex = any(not e.get("DataFim") for e in exercises)
                mid = Identifier(MANDATE, f"{mand['CodigoMandato']}:{code}")
                batch.mandates.append(MandateRecord(
                    identifier=mid, person=pid, role_type="senator", represented_unit=mand.get("UfParlamentar"),
                    participation="holder" if participation == "Titular" else "substitute",
                    start_date=parse_date(first.get("DataInicio")), end_date=end,
                    status="in_exercise" if open_ex and (end is None or end >= today()) else "not_in_exercise",
                    ref=Ref(idx, path),
                    attributes={
                        "source_participation": participation, "legislatures": legs,
                        "seat_code": str(mand["CodigoMandato"]),
                        "holder_code": (mand.get("Titular") or {}).get("CodigoParlamentar") or
                        (code if participation == "Titular" else None),
                        "holder": (mand.get("Titular") or {}).get("NomeParlamentar"),
                        "substitutes": [
                            {"code": x.get("CodigoParlamentar"), "name": x.get("NomeParlamentar"),
                             "order": x.get("DescricaoParticipacao")}
                            for x in as_list((mand.get("Suplentes") or {}).get("Suplente"))],
                    },
                ))
                for j, e in enumerate(exercises):
                    batch.exercises.append(ExerciseRecord(
                        person=pid, mandate=mid, source_exercise_id=str(e.get("CodigoExercicio") or j),
                        ref=Ref(idx, f"{path}.Exercicios.Exercicio[{j}]"), start_date=parse_date(e.get("DataInicio")),
                        end_date=parse_date(e.get("DataFim")), end_cause_code=e.get("SiglaCausaAfastamento"),
                        end_cause=e.get("DescricaoCausaAfastamento"),
                    ))
                for j, pt in enumerate(as_list((mand.get("Partidos") or {}).get("Partido"))):
                    sigla = pt.get("Sigla")
                    if not sigla:
                        continue
                    ppath = f"{path}.Partidos.Partido[{j}]"
                    rec = parties.setdefault(sigla, PartyRecord(Identifier(PARTY, sigla), sigla, Ref(idx, ppath)))
                    rec.name = rec.name or pt.get("Nome")
                    if pt.get("CodigoPartido") and not rec.extra_identifiers:
                        rec.extra_identifiers.append(Identifier(PARTY_CODE, str(pt["CodigoPartido"])))
                    batch.memberships.append(PartyMembershipRecord(
                        person=pid, party=Identifier(PARTY, sigla), basis="affiliation_history",
                        is_current=not pt.get("DataDesfiliacao"), ref=Ref(idx, ppath),
                        valid_from=parse_date(pt.get("DataFiliacao")), valid_to=parse_date(pt.get("DataDesfiliacao")),
                    ))
        batch.parties = list(parties.values())

    def _normalize_votes(self, batch: Batch) -> None:
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "vote_list":
                continue
            data = raw.json()
            if not isinstance(data, list):
                batch.issues.append(Issue("error", "schema_changed", "vote list is not a JSON array", raw=idx))
                continue
            for i, v in enumerate(data):
                sid = v.get("codigoSessaoVotacao")
                if sid is None:
                    batch.issues.append(Issue("warning", "missing_field", "vote without codigoSessaoVotacao", raw=idx))
                    continue
                ev = VoteEventRecord(
                    source_id=str(sid), ref=Ref(idx, f"$[{i}]"), held_on=parse_date(v.get("dataSessao")),
                    description=v.get("descricaoVotacao"), secret=v.get("votacaoSecreta") == "S",
                    result=RESULTS.get(v.get("resultadoVotacao"), v.get("resultadoVotacao")),
                    session_code=str(v.get("codigoSessao") or "") or None, matter=v.get("identificacao"),
                    matter_code=str(v.get("codigoMateria") or "") or None,
                    totals={k: v.get(k) for k in ("totalVotosSim", "totalVotosNao", "totalVotosAbstencao")
                            if v.get(k) is not None},
                    attributes={k: v.get(k) for k in ("sequencialSessao", "idProcesso", "informeLegislativo")
                                if v.get(k) is not None},
                )
                for vote in as_list(v.get("votos")):
                    code = vote.get("codigoParlamentar")
                    if code is None:
                        continue
                    ev.votes.append(IndividualVoteRecord(
                        person=Identifier(PERSON, str(code)), name=vote.get("nomeParlamentar") or str(code),
                        party=vote.get("siglaPartidoParlamentar"), unit=vote.get("siglaUFParlamentar"),
                        vote_code=vote.get("siglaVotoParlamentar"), vote_label=vote.get("descricaoVotoParlamentar"),
                    ))
                batch.vote_events.append(ev)

    def _normalize_committees(self, batch: Batch) -> None:
        listed: dict[str, dict] = {}
        for raw in batch.raw:
            if raw.record_kind != "committee_list":
                continue
            for group in as_list(((raw.json().get("ListaBasicaComissoes") or {}).get("colegiado") or {})
                                 .get("colegiados")):
                for c in as_list(group.get("colegiado")):
                    listed.setdefault(str(c.get("CodigoColegiado")), c)
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "committee":
                continue
            cols = as_list(((raw.json().get("ComissoesCongressoNacional") or {}).get("Colegiados") or {})
                           .get("Colegiado"))
            if not cols:
                batch.issues.append(Issue("warning", "committee_empty", "Colegiado missing", raw=idx))
                continue
            c, base = cols[0], "$.ComissoesCongressoNacional.Colegiados.Colegiado[0]"
            code = str(c.get("CodigoColegiado") or raw.source_record_key)
            info = listed.get(code, {})
            sec = c.get("InformacoesSecretaria") or {}
            qty = (c.get("QuantidadesMembros") or {}).get("Distribuicao") or {}
            rec = CommitteeRecord(
                source_code=code, name=c.get("NomeColegiado") or info.get("NomeColegiado") or code,
                abbreviation=c.get("SiglaColegiado"), ref=Ref(idx, base),
                committee_type=(c.get("TipoColegiado") or {}).get("TipoColegiado"),
                attributes={
                    "active": True, "subtitle": info.get("DescricaoSubtitulo"), "purpose": info.get("TextoFinalidade"),
                    "start_date": info.get("DataInicio") or c.get("DataInicio"),
                    "seats": {"titulares": qty.get("SenadoresTitulares"), "suplentes": qty.get("SenadoresSuplentes")},
                    "secretary": sec.get("Secretario"), "email": sec.get("eMail"),
                    "meetings": sec.get("AgendaReuniao"),
                    "url": f"https://legis.senado.leg.br/comissoes/comissao?codcol={code}",
                },
            )
            roles = {str(x.get("CodigoParlamentar")): x.get("TipoCargo")
                     for x in as_list((c.get("Cargos") or {}).get("Cargo")) if x.get("CodigoParlamentar")}
            for b, pb in enumerate(as_list((c.get("MembrosBlocoSF") or {}).get("PartidoBloco"))):
                for i, m in enumerate(as_list((pb.get("MembrosSF") or {}).get("Membro"))):
                    pcode = str(m.get("CodigoParlamentar") or "")
                    if not pcode:
                        continue
                    kind = "suplente" if (m.get("TipoVaga") or "").lower().startswith("supl") else "titular"
                    rec.members.append(CommitteeMemberRecord(
                        person=Identifier(PERSON, pcode),
                        name=(m.get("NomeParlamentar") or "").removeprefix("Senadora ").removeprefix("Senador "),
                        ref=Ref(idx, f"{base}.MembrosBlocoSF.PartidoBloco[{b}].MembrosSF.Membro[{i}]"),
                        seat_kind=kind, party=m.get("Partido"), unit=m.get("SiglaUf"),
                        bloc=pb.get("UnidadePartidaria"), role=roles.get(pcode) if kind == "titular" else None,
                    ))
            batch.committees.append(rec)

    def _normalize_speeches(self, batch: Batch) -> None:
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "speeches":
                continue
            parl = (raw.json().get("DiscursosParlamentar") or {}).get("Parlamentar") or {}
            code = str((parl.get("IdentificacaoParlamentar") or {}).get("CodigoParlamentar") or raw.source_record_key)
            items = as_list((parl.get("Pronunciamentos") or {}).get("Pronunciamento"))
            for i, d in enumerate(items):
                if not d.get("CodigoPronunciamento"):
                    continue
                sess = d.get("SessaoPlenaria") or {}
                batch.speeches.append(SpeechRecord(
                    source_id=str(d["CodigoPronunciamento"]), person=Identifier(PERSON, code),
                    ref=Ref(idx, f"$.DiscursosParlamentar.Parlamentar.Pronunciamentos.Pronunciamento[{i}]"),
                    delivered_on=parse_date(d.get("DataPronunciamento")),
                    kind=(d.get("TipoUsoPalavra") or {}).get("Descricao"), summary=d.get("TextoResumo"),
                    indexing=d.get("Indexacao"),
                    session=" ".join(x for x in (sess.get("SiglaTipoSessao"), sess.get("NumeroSessao"),
                                                 sess.get("DataSessao")) if x) or None,
                    url=d.get("UrlTexto"), text_url=d.get("UrlTextoBinario"),
                ))

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
                                "content_type": item.get("tipoConteudo"),
                                "codigo_materia": str(item["codigoMateria"]) if item.get("codigoMateria") else None},
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
