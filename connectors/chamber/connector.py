"""Câmara dos Deputados — Dados Abertos (dadosabertos.camara.leg.br/api/v2)."""

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
    VoteEventRecord,
    parse_date,
)

PERSON = "camara.deputado"
MANDATE = "camara.mandato"
# Party abbreviations are shared with the Senado pack so a party is one entity across both houses.
PARTY = "senado.partido.sigla"
PARTY_CODE = "camara.partido"
COMMITTEE = "camara.orgao"
PLENARIO = 180
PROFILE_URL = "https://www.camara.leg.br/deputados/{}"
PROPOSAL_URL = "https://www.camara.leg.br/propostas-legislativas/{}"
COMMITTEE_URL = "https://www.camara.leg.br/comissoes/{}"
CLOSED = ("arquivad", "transformad", "retirad", "prejudicad", "vetad", "rejeitad")
ID_RE = re.compile(r"/(\d+)$")
GENDER = {"M": "male", "F": "female"}


def legislature_end(leg: int) -> date:
    """Legislature 57 runs from 2023-02-01 to 2027-01-31; each lasts four years."""
    return date(2027 + 4 * (leg - 57), 1, 31)


def _id_from_uri(uri: str | None) -> str | None:
    m = ID_RE.search(uri or "")
    return m.group(1) if m else None


def _dt(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def today() -> date:
    return datetime.now(UTC).date()


def _author_kind(tipo: str, uri: str | None) -> str:
    t = (tipo or "").lower()
    if "/deputados/" in (uri or ""):
        return "member"
    if "comiss" in t or "órgão" in t and "legislativo" in t:
        return "committee"
    if "executivo" in t or "presidência da república" in t:
        return "executive"
    if "senad" in t:
        return "external"
    return "other"


class ChamberConnector(Connector):
    id = "brazil-chamber"
    version = "0.1.0"
    scopes = ("members", "proposals", "votes", "committees")

    @property
    def base(self) -> str:
        return self.config["base_url"].rstrip("/")

    # ------------------------------------------------------------------ fetch
    def fetch(self, scope: str) -> Batch:
        batch = Batch(scope=scope)
        {"members": self._fetch_members, "proposals": self._fetch_proposals, "votes": self._fetch_votes,
         "committees": self._fetch_committees}[scope](batch)
        return batch

    def _pages(self, batch: Batch, path: str, params: dict, kind: str, key: str | None = None) -> list[int]:
        """Follow the API's `links[rel=next]` pagination; each page is kept as its own raw response."""
        url, query, out = f"{self.base}{path}", dict(params, itens=params.get("itens", 100)), []
        for page in range(1, int(self.config.get("max_pages", 50)) + 1):
            resp = self.client.get(url, params=dict(query, pagina=page))
            idx = batch.add_raw(RawResponse(resp, kind, key))
            out.append(idx)
            body = batch.raw[idx].json()
            if not isinstance(body, dict) or not any(link.get("rel") == "next" for link in body.get("links") or []):
                break
        return out

    def _detail(self, batch: Batch, path: str, kind: str, key: str, issue: str) -> int | None:
        try:
            return batch.add_raw(RawResponse(self.client.get(f"{self.base}{path}"), kind, key))
        except SourceAccessError as exc:
            batch.issues.append(Issue("warning", issue, str(exc), {"id": key}))
            return None

    def _fetch_members(self, batch: Batch) -> None:
        idxs = self._pages(batch, "/deputados", {"ordem": "ASC", "ordenarPor": "nome"}, "member_list")
        ids = [str(d["id"]) for i in idxs for d in batch.raw[i].json().get("dados") or [] if d.get("id")]
        for code in ids:
            self._detail(batch, f"/deputados/{code}", "member_detail", code, "member_detail_unavailable")
            self._detail(batch, f"/deputados/{code}/historico", "member_history", code, "history_unavailable")

    def _fetch_proposals(self, batch: Batch) -> None:
        end = today()
        start = end - timedelta(days=int(self.config.get("proposal_window_days", 30)))
        ids: list[str] = []
        for sigla in self.config.get("proposal_types", ["PEC", "PLP", "PL", "MPV", "PDL"]):
            params = {"siglaTipo": sigla, "dataApresentacaoInicio": start.isoformat(),
                      "dataApresentacaoFim": end.isoformat(), "ordem": "DESC", "ordenarPor": "id"}
            for idx in self._pages(batch, "/proposicoes", params, "proposal_list", sigla):
                ids += [str(p["id"]) for p in batch.raw[idx].json().get("dados") or [] if p.get("id")]
        limit = int(self.config.get("max_proposal_details", 300))
        if len(ids) > limit:
            batch.issues.append(Issue("info", "detail_limit", f"details fetched for {limit} of {len(ids)}"))
        for pid in ids[:limit]:
            if self._detail(batch, f"/proposicoes/{pid}", "proposal_detail", pid, "proposal_detail_unavailable"):
                self._detail(batch, f"/proposicoes/{pid}/autores", "proposal_authors", pid, "authors_unavailable")
                self._detail(batch, f"/proposicoes/{pid}/tramitacoes", "proposal_events", pid,
                             "events_unavailable")

    def _fetch_votes(self, batch: Batch) -> None:
        end = today()
        since = parse_date(self.config.get("votes_since")) or end - timedelta(days=90)
        start = max(since, end - timedelta(days=int(self.config.get("votes_window_days", 120))))
        ids: list[str] = []
        while start <= end:  # the API rejects ranges that cross a month boundary on large windows
            stop = min(end, (start.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1))
            params = {"idOrgao": PLENARIO, "dataInicio": start.isoformat(), "dataFim": stop.isoformat(),
                      "ordem": "DESC", "ordenarPor": "dataHoraRegistro"}
            for idx in self._pages(batch, "/votacoes", params, "vote_list", start.isoformat()[:7]):
                ids += [str(v["id"]) for v in batch.raw[idx].json().get("dados") or [] if v.get("id")]
            start = stop + timedelta(days=1)
        for vid in ids[: int(self.config.get("max_vote_details", 600))]:
            self._detail(batch, f"/votacoes/{vid}/votos", "vote_ballots", vid, "ballots_unavailable")

    def _fetch_committees(self, batch: Batch) -> None:
        ids: list[str] = []
        for cod in self.config.get("committee_types", [2, 4]):
            try:
                for idx in self._pages(batch, "/orgaos", {"codTipoOrgao": cod}, "committee_list", str(cod)):
                    ids += [str(o["id"]) for o in batch.raw[idx].json().get("dados") or [] if o.get("id")]
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "committee_list_unavailable", str(exc), {"codTipoOrgao": cod}))
        for oid in ids:
            if self._detail(batch, f"/orgaos/{oid}", "committee", oid, "committee_unavailable") is None:
                continue
            try:
                self._pages(batch, f"/orgaos/{oid}/membros", {}, "committee_members", oid)
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "committee_unavailable", str(exc), {"id": oid}))

    # ------------------------------------------------------------------ normalize
    def normalize(self, batch: Batch) -> Batch:
        {"members": self._normalize_members, "proposals": self._normalize_proposals,
         "votes": self._normalize_votes, "committees": self._normalize_committees}[batch.scope](batch)
        return batch

    @staticmethod
    def _by_key(batch: Batch, kind: str) -> dict[str, tuple[int, object]]:
        return {r.source_record_key: (i, r.json().get("dados")) for i, r in enumerate(batch.raw)
                if r.record_kind == kind and isinstance(r.json(), dict)}

    def _normalize_members(self, batch: Batch) -> None:
        details, histories = self._by_key(batch, "member_detail"), self._by_key(batch, "member_history")
        parties: dict[str, PartyRecord] = {}

        def party(sigla: str, ref: Ref, uri: str | None) -> Identifier:
            rec = parties.setdefault(sigla, PartyRecord(Identifier(PARTY, sigla), sigla, ref))
            code = _id_from_uri(uri)
            if code and not rec.extra_identifiers:
                rec.extra_identifiers.append(Identifier(PARTY_CODE, code))
            return rec.identifier

        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "member_list":
                continue
            rows = raw.json().get("dados") if isinstance(raw.json(), dict) else None
            if not isinstance(rows, list):
                batch.issues.append(Issue("error", "schema_changed", "deputados.dados missing", raw=idx))
                continue
            batch.complete_member_list = batch.complete_member_list or bool(rows)
            for i, d in enumerate(rows):
                path = f"$.dados[{i}]"
                code, name = d.get("id"), (d.get("nome") or "").strip()
                if not code or not name:
                    batch.issues.append(Issue("error", "missing_field", "deputy without id/name",
                                              {"path": path}, raw=idx))
                    continue
                code = str(code)
                pid = Identifier(PERSON, code)
                _, det = details.get(code, (None, None))
                det = det if isinstance(det, dict) else {}
                status = det.get("ultimoStatus") or {}
                batch.persons.append(PersonRecord(
                    identifier=pid, name=name, full_name=(det.get("nomeCivil") or "").title() or None,
                    gender=GENDER.get(det.get("sexo") or ""), photo_url=d.get("urlFoto"),
                    profile_url=PROFILE_URL.format(code), ref=Ref(idx, path),
                ))
                leg = int(d.get("idLegislatura") or 57)
                hidx, hist = histories.get(code, (None, None))
                hist = sorted((h for h in hist or [] if isinstance(h, dict)), key=lambda h: h.get("dataHora") or "")
                entries = [h for h in hist if h.get("idLegislatura") == leg and h.get("situacao") == "Exercício"]
                start = parse_date(entries[-1]["dataHora"]) if entries else None
                condition = status.get("condicaoEleitoral") or (
                    entries[-1].get("condicaoEleitoral") if entries else None)
                batch.mandates.append(MandateRecord(
                    identifier=Identifier(MANDATE, f"{leg}:{code}"), person=pid, role_type="deputy",
                    represented_unit=d.get("siglaUf"),
                    participation="substitute_in_exercise" if condition == "Suplente" else "holder",
                    start_date=start, end_date=legislature_end(leg), ref=Ref(idx, path),
                    attributes={
                        "legislature": leg, "source_participation": condition, "situation": status.get("situacao"),
                        "email": d.get("email"), "office": (status.get("gabinete") or {}).get("nome"),
                        "birth_date": det.get("dataNascimento"), "birth_place": " / ".join(
                            x for x in (det.get("municipioNascimento"), det.get("ufNascimento")) if x) or None,
                        "education": det.get("escolaridade"), "social": det.get("redeSocial") or [],
                        "website": det.get("urlWebsite"),
                    },
                ))
                sigla = d.get("siglaPartido")
                if sigla:
                    batch.memberships.append(PartyMembershipRecord(
                        person=pid, party=party(sigla, Ref(idx, path), d.get("uriPartido")),
                        basis="current_listing", is_current=True, ref=Ref(idx, f"{path}.siglaPartido")))
                else:
                    batch.issues.append(Issue("warning", "missing_party", f"no party for {name}", raw=idx))
                if hidx is not None:
                    self._party_periods(batch, pid, hidx, hist, sigla, party)
        batch.parties = list(parties.values())

    @staticmethod
    def _party_periods(batch, pid, hidx, hist, current, party) -> None:
        """Party periods as recorded by the Câmara (not TSE filiation): consecutive entries with one sigla."""
        raw_rows = batch.raw[hidx].json().get("dados") or []
        periods: list[list] = []
        for h in hist:
            sigla = h.get("siglaPartido")
            if not sigla:
                continue
            if periods and periods[-1][0] == sigla:
                continue
            if periods:
                periods[-1][2] = parse_date(h.get("dataHora"))
            periods.append([sigla, parse_date(h.get("dataHora")), None, raw_rows.index(h)])
        for n, (sigla, start, end, i) in enumerate(periods):
            ref = Ref(hidx, f"$.dados[{i}]")
            batch.memberships.append(PartyMembershipRecord(
                person=pid, party=party(sigla, ref, raw_rows[i].get("uriPartido")), basis="chamber_record",
                is_current=n == len(periods) - 1 and sigla == current, ref=ref, valid_from=start, valid_to=end,
                epistemic_status="derived"))

    def _normalize_proposals(self, batch: Batch) -> None:
        details = self._by_key(batch, "proposal_detail")
        authors, events = self._by_key(batch, "proposal_authors"), self._by_key(batch, "proposal_events")
        seen: set[str] = set()
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "proposal_list":
                continue
            rows = raw.json().get("dados") if isinstance(raw.json(), dict) else None
            if not isinstance(rows, list):
                batch.issues.append(Issue("error", "schema_changed", "proposicoes.dados missing", raw=idx))
                continue
            for i, item in enumerate(rows):
                pid = str(item.get("id") or "")
                if not pid or pid in seen or not item.get("siglaTipo") or not item.get("ano"):
                    continue
                seen.add(pid)
                didx, d = details.get(pid, (None, None))
                d = d if isinstance(d, dict) else {}
                st = d.get("statusProposicao") or {}
                situation = st.get("descricaoSituacao")
                prop = ProposalRecord(
                    source_id=pid, type_code=item["siglaTipo"], type_name=d.get("descricaoTipo") or item["siglaTipo"],
                    number=str(item.get("numero")), year=int(item["ano"]), ref=Ref(idx, f"$.dados[{i}]"),
                    ementa=item.get("ementa"), introduced_on=parse_date(item.get("dataApresentacao")),
                    status=situation, status_date=parse_date(st.get("dataHora")),
                    in_progress=(not any(w in situation.lower() for w in CLOSED)) if situation else None,
                    official_url=PROPOSAL_URL.format(pid),
                    attributes={"keywords": d.get("keywords") or None, "full_text_url": d.get("urlInteiroTeor"),
                                "status_body": st.get("siglaOrgao"), "regime": st.get("regime"),
                                "appreciation": st.get("apreciacao"), "last_dispatch": st.get("despacho")},
                )
                if didx is None:
                    prop.attributes["detail_missing"] = True
                else:
                    prop.extra_refs.append(Ref(didx, "$.dados"))
                aidx, alist = authors.get(pid, (None, None))
                for n, a in enumerate(alist or []):
                    code = _id_from_uri(a.get("uri")) if "/deputados/" in (a.get("uri") or "") else None
                    person = Identifier(PERSON, code) if code else None
                    prop.authors.append(AuthorRecord(
                        ordinal=int(a.get("ordemAssinatura") or n + 1), name=a.get("nome") or "?",
                        kind=_author_kind(a.get("tipo"), a.get("uri")), person=person,
                        resolution="official_id" if person else "unresolved",
                        epistemic_status="verified" if person else "extracted",
                        attributes={"source_type": a.get("tipo"), "proponent": a.get("proponente") == 1,
                                    "source_code": code}))
                if aidx is not None:
                    prop.extra_refs.append(Ref(aidx, "$.dados"))
                _, elist = events.get(pid, (None, None))
                for e in elist or []:
                    if e.get("sequencia") is None:
                        continue
                    text = " — ".join(x for x in (e.get("descricaoTramitacao"), e.get("despacho")) if x)
                    prop.events.append(EventRecord(
                        source_event_id=f"{pid}:{e['sequencia']}", event_type="procedural_record",
                        event_date=_dt(e.get("dataHora")), description=text or None, body=e.get("siglaOrgao")))
                batch.proposals.append(prop)

    def _normalize_votes(self, batch: Batch) -> None:
        ballots = self._by_key(batch, "vote_ballots")
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind != "vote_list":
                continue
            rows = raw.json().get("dados") if isinstance(raw.json(), dict) else None
            if not isinstance(rows, list):
                batch.issues.append(Issue("error", "schema_changed", "votacoes.dados missing", raw=idx))
                continue
            for i, v in enumerate(rows):
                if not v.get("id"):
                    continue
                vid = str(v["id"])
                result = {1: "aprovado", 0: "rejeitado"}.get(v.get("aprovacao"))
                ev = VoteEventRecord(
                    source_id=vid, ref=Ref(idx, f"$.dados[{i}]"), held_on=parse_date(v.get("data")),
                    description=v.get("descricao"), secret=False, result=result,
                    session_code=_id_from_uri(v.get("uriEvento")), matter=v.get("proposicaoObjeto"),
                    matter_code=_id_from_uri(v.get("uriProposicaoObjeto")) or vid.split("-")[0],
                    attributes={"registered_at": v.get("dataHoraRegistro"), "body": v.get("siglaOrgao")},
                )
                bidx, blist = ballots.get(vid, (None, None))
                for b in blist or []:
                    dep = b.get("deputado_") or {}
                    if not dep.get("id"):
                        continue
                    ev.votes.append(IndividualVoteRecord(
                        person=Identifier(PERSON, str(dep["id"])), name=dep.get("nome") or str(dep["id"]),
                        party=dep.get("siglaPartido"), unit=dep.get("siglaUf"),
                        vote_code=b.get("tipoVoto"), vote_label=b.get("tipoVoto")))
                if ev.votes:
                    tally: dict[str, int] = {}
                    for x in ev.votes:
                        tally[x.vote_label or "?"] = tally.get(x.vote_label or "?", 0) + 1
                    ev.totals = {"totalVotosSim": tally.get("Sim", 0), "totalVotosNao": tally.get("Não", 0),
                                 "totalVotosAbstencao": tally.get("Abstenção", 0),
                                 "totalVotosObstrucao": tally.get("Obstrução", 0)}
                ev.attributes["nominal"] = bool(ev.votes)
                batch.vote_events.append(ev)

    def _normalize_committees(self, batch: Batch) -> None:
        details = self._by_key(batch, "committee")
        members: dict[str, list[tuple[int, int, dict]]] = {}
        for idx, raw in enumerate(batch.raw):
            if raw.record_kind == "committee_members" and isinstance(raw.json(), dict):
                for i, m in enumerate(raw.json().get("dados") or []):
                    members.setdefault(raw.source_record_key, []).append((idx, i, m))
        now = today()
        for oid, (idx, c) in details.items():
            if not isinstance(c, dict):
                batch.issues.append(Issue("warning", "committee_empty", "orgao.dados missing", raw=idx))
                continue
            if c.get("dataFim") and (parse_date(c["dataFim"]) or now) < now:
                continue
            rec = CommitteeRecord(
                source_code=oid, scheme=COMMITTEE, name=c.get("nome") or oid, abbreviation=c.get("sigla"),
                committee_type=c.get("tipoOrgao"), ref=Ref(idx, "$.dados"),
                attributes={"active": True, "subtitle": c.get("nomeResumido") or c.get("apelido"),
                            "start_date": c.get("dataInicio"), "installed_on": c.get("dataInstalacao"),
                            "room": c.get("sala"),
                            "url": c.get("urlWebsite") or COMMITTEE_URL.format((c.get("sigla") or "").lower())},
            )
            for midx, i, m in members.get(oid, []):
                end = parse_date(m.get("dataFim"))
                if not m.get("id") or (end and end < now):
                    continue
                title = m.get("titulo") or ""
                role = "PRESIDENTE" if title == "Presidente" else "VICE-PRESIDENTE" if "Vice" in title else None
                rec.members.append(CommitteeMemberRecord(
                    person=Identifier(PERSON, str(m["id"])), name=m.get("nome") or str(m["id"]),
                    ref=Ref(midx, f"$.dados[{i}]"), seat_kind="suplente" if title == "Suplente" else "titular",
                    party=m.get("siglaPartido"), unit=m.get("siglaUf"), role=role))
            batch.committees.append(rec)
