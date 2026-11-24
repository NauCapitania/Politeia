"""Senate presidency 2025: party support vs official result and per-senator vote probabilities (never facts)."""

from collections import Counter
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from connectors.base.protocol import normalize_name
from engine.analysis.secret_ballot import posterior_marginals
from engine.db.models import Claim, DossierItem
from engine.senado import seats_on

DOSSIER = "presidencia-2025"


def _items(s: Session, dossier: str) -> list[DossierItem]:
    return list(s.scalars(select(DossierItem).where(DossierItem.dossier == dossier)))


def analysis_2025(s: Session) -> dict:
    items = _items(s, DOSSIER)
    if not items:
        return {"available": False, "reason": "Dossiê presidencia-2025 não carregado."}
    contest = next(i for i in items if i.kind == "contest")
    model = next(i for i in items if i.kind == "model").payload
    support = {i.payload["party"]: i for i in items if i.kind == "party_support"}
    on = date.fromisoformat(contest.payload["date"])
    voters = seats_on(s, on)
    totals = {r["candidate"]: r["votes"] for r in contest.payload["result"]}
    cands = list(totals)
    cand_by_name = {normalize_name(c): c for c in cands}
    claims = {c.subject_id: c for c in s.scalars(select(Claim).where(
        Claim.topic == "presidencia_2025_voto", Claim.claim_type.in_(("declaration", "official"))))
        if c.subject_id}

    priors, reasons = [], []
    for v in voters:
        why = []
        own = cand_by_name.get(normalize_name(v["name"]))
        party = v["party"] or "sem partido"
        sup = support.get(v["party"] or "")
        claim = claims.get(v["person_id"])
        if own:
            p = {c: (1 - model["self_vote"]) / (len(cands) - 1) for c in cands} | {own: model["self_vote"]}
            why.append({"kind": "analysis", "text": f"Candidato: hipótese de autovoto ({model['self_vote']:.0%})."})
            if own in model.get("candidate_party_override", {}):
                why.append({"kind": "press_report", "text": model["candidate_party_override"][own]})
        elif claim and claim.position in totals:
            p = {c: 0.05 for c in cands} | {claim.position: 0.9}
            why.append({"kind": claim.claim_type, "text": claim.statement, "sources": claim.sources})
        else:
            status = sup.payload["support"] if sup else "none"
            supported = sup.payload["candidate"] if sup else None
            p_main = model["support_prior"][status]
            aff = model["affinity"].get(v["party"] or "", model["affinity"]["default"])
            if supported and supported in totals:
                rest = [c for c in cands if c != supported]
                z = sum(aff.get(c, 0.5) for c in rest) or 1
                p = {supported: p_main} | {c: (1 - p_main) * aff.get(c, 0.5) / z for c in rest}
                label = {"declared": "declarou apoio a", "split": "dividiu-se; parte apoiou",
                         "own_candidate": "lançou candidato próprio:"}[status]
                why.append({"kind": "press_report", "text": f"{party} {label} {supported}.",
                            "sources": sup.sources})
            else:
                p = {c: 1 / len(cands) for c in cands}
                why.append({"kind": "analysis",
                            "text": f"Sem apoio partidário registrado para {party}: prior uniforme."})
            if v["party"] in model["affinity"]:
                why.append({"kind": "analysis", "text": f"Afinidade do {party} com candidaturas de oposição: "
                            + ", ".join(f"{c} {w:.0%}" for c, w in aff.items()) + " dos votos dissidentes."})
        priors.append(p)
        reasons.append(why)

    if len(voters) != sum(totals.values()):
        return {"available": False, "reason": f"Composição reconstruída tem {len(voters)} cadeiras; esperado "
                f"{sum(totals.values())}.", "voters": voters}
    post = posterior_marginals(priors, totals)
    rows = []
    for v, prior, pst, why in zip(voters, priors, post, reasons, strict=True):
        rows.append(v | {"prior": prior, "posterior": pst, "justification": why,
                         "most_likely": max(pst, key=pst.get)})
    by_party = Counter(v["party"] or "sem partido" for v in voters)
    parties = []
    for party, n in by_party.most_common():
        sup = support.get(party)
        exp = {c: sum(r["posterior"][c] for r in rows if (r["party"] or "sem partido") == party) for c in cands}
        parties.append({"party": party, "senators": n, "support": sup.payload if sup else None,
                        "support_sources": sup.sources if sup else [], "expected_votes": exp})
    declared = sum(n for p, n in by_party.items() if support.get(p) and support[p].payload["support"] == "declared"
                   and support[p].payload["candidate"] == cands[0])
    return {"available": True, "contest": contest.payload, "contest_sources": contest.sources, "model": model,
            "model_sources": next(i for i in items if i.kind == "model").sources, "parties": parties,
            "senators": sorted(rows, key=lambda r: -max(r["posterior"][c] for c in cands[1:])),
            "summary": {"declared_support_seats": declared, "votes": totals,
                        "expected_check": {c: round(sum(r["posterior"][c] for r in rows), 6) for c in cands}}}


def analysis_2027(s: Session) -> dict:
    items = _items(s, "presidencia-2027")
    if not items:
        return {"available": False, "reason": "Dossiê presidencia-2027 não carregado."}
    claims = list(s.scalars(select(Claim).where(Claim.dossier == "presidencia-2027")))
    group = {}
    for i in items:
        group.setdefault(i.kind, []).append({"id": i.id, **i.payload, "sources": i.sources})
    imp = list(s.scalars(select(Claim).where(Claim.topic == "impeachment_stf")))
    return {"available": True, **group, "claims": [_claim(c) for c in claims],
            "impeachment_claims": [_claim(c) for c in imp]}


def _claim(c: Claim) -> dict:
    return {"id": c.id, "topic": c.topic, "subject_id": c.subject_id, "subject_label": c.subject_label,
            "position": c.position, "statement": c.statement, "claim_type": c.claim_type,
            "confidence": c.confidence, "review_status": c.review_status, "stated_on": c.stated_on,
            "sources": c.sources}
