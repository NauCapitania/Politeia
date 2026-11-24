"""Exact posterior marginals for a secret ballot given individual priors and the official totals.

Each voter i casts exactly one vote with prior P_i(c). Conditioning on the observed totals N_c, the posterior
marginal is P(v_i = c | totals) = P_i(c) * P(others produce totals - e_c) / P(totals). One candidate (the one with
most votes) is implicit, so dynamic programming runs over counts of the remaining candidates only.
"""

from itertools import product


def posterior_marginals(priors: list[dict[str, float]], totals: dict[str, int]) -> list[dict[str, float]]:
    if sum(totals.values()) != len(priors):
        raise ValueError("totals must add up to the number of voters")
    cands = sorted(totals, key=lambda c: -totals[c])
    base, minor = cands[0], cands[1:]
    caps = tuple(totals[c] for c in minor)
    n = len(priors)
    norm = []
    for p in priors:
        z = sum(max(p.get(c, 0.0), 0.0) for c in cands)
        if z <= 0:
            raise ValueError("each voter needs a positive prior for at least one candidate")
        norm.append({c: max(p.get(c, 0.0), 0.0) / z for c in cands})

    def step(dist: dict, p: dict) -> dict:
        out: dict = {}
        for state, w in dist.items():
            out[state] = out.get(state, 0.0) + w * p[base]
            for j, c in enumerate(minor):
                if state[j] < caps[j]:
                    nxt = state[:j] + (state[j] + 1,) + state[j + 1:]
                    out[nxt] = out.get(nxt, 0.0) + w * p[c]
        return out

    zero = tuple(0 for _ in minor)
    forward = [{zero: 1.0}]
    for p in norm:
        forward.append(step(forward[-1], p))
    total = forward[n].get(caps, 0.0)
    if total <= 0:
        raise ValueError("the priors make the official result impossible")
    # backward[i][state]: probability that voters i..n-1 add exactly (caps - state)
    backward = [None] * (n + 1)
    backward[n] = {caps: 1.0}
    all_states = list(product(*(range(k + 1) for k in caps)))
    for i in range(n - 1, -1, -1):
        p, nxt, cur = norm[i], backward[i + 1], {}
        for state in all_states:
            v = nxt.get(state, 0.0) * p[base]
            for j, c in enumerate(minor):
                if state[j] < caps[j]:
                    v += nxt.get(state[:j] + (state[j] + 1,) + state[j + 1:], 0.0) * p[c]
            if v:
                cur[state] = v
        backward[i] = cur
    result = []
    for i, p in enumerate(norm):
        marg = {c: 0.0 for c in cands}
        for state, w in forward[i].items():
            marg[base] += w * p[base] * backward[i + 1].get(state, 0.0)
            for j, c in enumerate(minor):
                if state[j] < caps[j]:
                    marg[c] += w * p[c] * backward[i + 1].get(state[:j] + (state[j] + 1,) + state[j + 1:], 0.0)
        result.append({c: v / total for c, v in marg.items()})
    return result
