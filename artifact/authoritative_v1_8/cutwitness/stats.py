"""Frozen statistics: A12, ratio of medians, bootstrap CI, Mann-Whitney U, Holm, Kaplan-Meier, log-rank."""
from __future__ import annotations
import random
from statistics import median
from typing import List, Sequence, Tuple


def a12(x: Sequence[float], y: Sequence[float]) -> float:
    """Vargha-Delaney A12: P(X > Y) + 0.5 P(X = Y)."""
    gt = sum(1 for a in x for b in y if a > b); eq = sum(1 for a in x for b in y if a == b)
    return (gt + 0.5 * eq) / (len(x) * len(y))


def ratio_of_medians(x, y) -> float:
    my = median(y)
    return float("inf") if my == 0 else median(x) / my


def bootstrap_ci(x, stat=median, n: int = 10000, alpha: float = 0.05, seed: int = 0) -> Tuple[float, float]:
    rng = random.Random(seed)
    vals = sorted(stat([rng.choice(x) for _ in x]) for _ in range(n))
    return vals[int(n * alpha / 2)], vals[int(n * (1 - alpha / 2)) - 1]


def mann_whitney(x, y) -> float:
    """Two-sided Mann-Whitney U, asymptotic normal approximation with tie and continuity correction
    (identical to scipy.stats.mannwhitneyu(method='asymptotic', use_continuity=True))."""
    import math
    n1, n2 = len(x), len(y); allv = sorted([(v, 0) for v in x] + [(v, 1) for v in y]); ranks = {}
    i = 0; ties = 0.0; N = n1 + n2
    while i < N:
        j = i
        while j + 1 < N and allv[j + 1][0] == allv[i][0]:
            j += 1
        r = (i + j) / 2 + 1; t = j - i + 1; ties += t ** 3 - t
        for k in range(i, j + 1):
            ranks.setdefault(allv[k][0], r)
        i = j + 1
    r1 = sum(ranks[v] for v in x); u1 = r1 - n1 * (n1 + 1) / 2; u = max(u1, n1 * n2 - u1)
    mu = n1 * n2 / 2; sd = math.sqrt(n1 * n2 / 12 * ((N + 1) - ties / (N * (N - 1))))
    if sd == 0:
        return 1.0
    z = (u - mu - 0.5) / sd
    return min(1.0, math.erfc(z / math.sqrt(2)))


def holm(pvals: List[float]) -> List[float]:
    m = len(pvals); order = sorted(range(m), key=lambda i: pvals[i]); adj = [0.0] * m; run = 0.0
    for rank, i in enumerate(order):
        run = max(run, min(1.0, (m - rank) * pvals[i])); adj[i] = run
    return adj


def kaplan_meier(times: Sequence[float], events: Sequence[int]):
    """Right-censored survival curve: events[i]=1 if divergence observed at times[i], 0 if censored at budget."""
    pts = sorted(zip(times, events)); total = len(pts); at_risk = total; s = 1.0; curve = [(0.0, 1.0)]; i = 0
    while i < total:
        t = pts[i][0]
        group = [e for tt, e in pts[i:] if tt == t]
        d = sum(group)
        if d:
            s *= 1 - d / at_risk; curve.append((t, s))
        at_risk -= len(group); i += len(group)
    return curve


def logrank(t1, e1, t2, e2) -> float:
    import math
    times = sorted({t for t, e in zip(t1, e1) if e} | {t for t, e in zip(t2, e2) if e})
    o_minus_e = 0.0; var = 0.0
    for t in times:
        n1 = sum(1 for x in t1 if x >= t); n2 = sum(1 for x in t2 if x >= t)
        d1 = sum(1 for x, e in zip(t1, e1) if x == t and e); d2 = sum(1 for x, e in zip(t2, e2) if x == t and e)
        n = n1 + n2; d = d1 + d2
        if n < 2:
            continue
        o_minus_e += d1 - d * n1 / n
        var += d * (n1 / n) * (n2 / n) * (n - d) / (n - 1)
    if var == 0:
        return 1.0
    return math.erfc(math.sqrt(o_minus_e ** 2 / var / 2))  # chi-square(1) survival function


# ---------------------------------------------------------------- exact binomial (Amendment v1.5, RQ2b matched pairs)
def _binom_pmf(k: int, n: int, p: float) -> float:
    from math import comb
    return comb(n, k) * (p ** k) * ((1 - p) ** (n - k))


def sign_test_two_sided(w: int, n: int):
    """Exact two-sided binomial sign test of H0: P(win)=0.5; None when n == 0 (no informative pairs)."""
    if n == 0:
        return None
    lo = sum(_binom_pmf(k, n, 0.5) for k in range(0, w + 1))
    hi = sum(_binom_pmf(k, n, 0.5) for k in range(w, n + 1))
    return min(1.0, 2.0 * min(lo, hi))


def clopper_pearson(w: int, n: int, alpha: float = 0.05):
    """Exact (Clopper-Pearson) confidence interval for a binomial proportion, by bisection on the binomial tails."""
    if n == 0:
        return None, None
    def solve(f, target):
        a, b = 0.0, 1.0
        for _ in range(200):
            m = (a + b) / 2
            if f(m) > target:
                a = m
            else:
                b = m
        return (a + b) / 2
    lower = 0.0 if w == 0 else solve(lambda p: 1 - sum(_binom_pmf(k, n, p) for k in range(w, n + 1)), 1 - alpha / 2)
    upper = 1.0 if w == n else solve(lambda p: sum(_binom_pmf(k, n, p) for k in range(0, w + 1)), alpha / 2)
    return lower, upper
