"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from scipy import stats as _sps

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _check_pair(x: Sequence, y: Sequence) -> None:
    if len(x) != len(y):
        raise ValueError(f"length mismatch: {len(x)} != {len(y)}")


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    _check_pair(human, judge)
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        if h == POS and j == POS:
            tp += 1
        elif h != POS and j == POS:
            fp += 1
        elif h == POS and j != POS:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    c = confusion(human, judge)
    p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
    r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
    return p, r


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    _check_pair(human, judge)
    n = len(human)
    if n == 0:
        raise ValueError("kappa undefined for empty input")
    p_o = sum(h == j for h, j in zip(human, judge)) / n
    p_e = sum((sum(h == c for h in human) / n) * (sum(j == c for j in judge) / n)
              for c in set(human) | set(judge))
    if math.isclose(p_e, 1.0):
        raise ValueError("kappa undefined: p_e == 1 (no variation in labels)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    for name, v in (("observed_rate", observed_rate), ("sensitivity", sensitivity),
                    ("specificity", specificity)):
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"{name} must be in [0, 1], got {v}")
    denom = sensitivity + specificity - 1
    if denom <= 0:
        raise ValueError("Rogan-Gladen undefined: sensitivity + specificity <= 1 (judge no better than chance)")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    _check_pair(a, b)
    if len(a) == 0:
        raise ValueError("empty input")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be in (0, 1)")
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)
    res = _sps.bootstrap((x, y), lambda u, v, axis=-1: np.mean(u, axis=axis) - np.mean(v, axis=axis),
                         paired=True, vectorized=True, n_resamples=n_resamples,
                         confidence_level=confidence, method="percentile",
                         rng=np.random.default_rng(rng))
    ci = res.confidence_interval
    return (float(x.mean() - y.mean()), float(ci.low), float(ci.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return math.comb(c, k) / math.comb(n, k)


def _check_nck(n: int, c: int, k: int) -> None:
    for name, v in (("n", n), ("c", c), ("k", k)):
        if isinstance(v, bool) or not isinstance(v, (int, np.integer)):
            raise ValueError(f"{name} must be an int, got {v!r}")
    if n < 1 or k < 1:
        raise ValueError("n and k must be >= 1")
    if c < 0 or c > n:
        raise ValueError("c must satisfy 0 <= c <= n")
    if k > n:
        raise ValueError("k must be <= n")
