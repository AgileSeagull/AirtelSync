"""Lead propensity: P(activation) from facts known when a lead arrives.

Explainable logistic regression (numpy, L2) on smb_leads.csv. Deliberately excludes
anything observed later in the funnel (stage dates, drop reasons, outcomes). Validated
on a time split: Apr–May train, June test."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from ..data_store import gstin_registry, leads

CATEGORICAL = ["lead_source", "segment", "city_tier", "has_gstin", "gstin_status", "has_udyam", "current_internet",
               "annual_turnover_band", "contact_role"]
NUMERIC = ["log_employees", "log_sites", "log_spend", "n_interests"]

LABELS = {
    "lead_source": "Source", "segment": "Segment", "city_tier": "City tier", "has_gstin": "Has GSTIN",
    "gstin_status": "GSTIN status", "has_udyam": "Has Udyam", "current_internet": "Current internet",
    "annual_turnover_band": "Turnover", "contact_role": "Contact", "log_employees": "Staff size",
    "log_sites": "Number of sites", "log_spend": "Telecom spend", "n_interests": "Products asked about",
}


def features(r: dict) -> dict:
    g = (r.get("gstin") or "").strip()
    status = gstin_registry().get(g, {}).get("status", "None") if g else "None"
    spend = float(r.get("monthly_telecom_spend_inr") or 0)
    interests = [x for x in (r.get("products_of_interest") or "").split(";") if x]
    return {
        "lead_source": r.get("lead_source") or "Unknown", "segment": r.get("segment") or "Unknown",
        "city_tier": str(r.get("city_tier") or "2"), "has_gstin": r.get("has_gstin") or "N", "gstin_status": status,
        "has_udyam": r.get("has_udyam") or "N", "current_internet": r.get("current_internet") or "Unknown",
        "annual_turnover_band": r.get("annual_turnover_band") or "Unknown", "contact_role": r.get("contact_role") or "Owner",
        "log_employees": math.log1p(float(r.get("employee_count") or 1)), "log_sites": math.log1p(float(r.get("num_sites") or 1)),
        "log_spend": math.log1p(spend), "n_interests": float(len(interests)),
    }


class Model:
    def __init__(self, rows: list[dict], y: np.ndarray, l2: float = 1.0, iters: int = 3000, lr: float = 0.3):
        feats = [features(r) for r in rows]
        self.levels = {c: sorted({f[c] for f in feats}) for c in CATEGORICAL}
        X = self._matrix(feats, fit=True)
        w = np.zeros(X.shape[1])
        b = math.log(y.mean() / (1 - y.mean()))
        n = len(y)
        for _ in range(iters):
            p = 1 / (1 + np.exp(-(X @ w + b)))
            w -= lr * ((X.T @ (p - y)) / n + l2 * w / n)
            b -= lr * float((p - y).mean())
        self.w, self.b = w, b

    def _matrix(self, feats: list[dict], fit: bool = False) -> np.ndarray:
        cols = []
        self.names = []
        for c in CATEGORICAL:
            for lv in self.levels[c][1:]:  # first level is the baseline
                cols.append([1.0 if f[c] == lv else 0.0 for f in feats])
                self.names.append((c, lv))
        num = np.array([[f[c] for c in NUMERIC] for f in feats])
        if fit:
            self.mu, self.sd = num.mean(0), num.std(0) + 1e-9
        num = (num - self.mu) / self.sd
        for j, c in enumerate(NUMERIC):
            cols.append(list(num[:, j]))
            self.names.append((c, None))
        return np.array(cols).T

    def predict(self, rows: list[dict]) -> np.ndarray:
        X = self._matrix([features(r) for r in rows])
        return 1 / (1 + np.exp(-(X @ self.w + self.b)))

    def explain(self, row: dict, top: int = 3) -> list[dict]:
        """Top drivers for one lead: contribution of each active feature vs the baseline lead."""
        X = self._matrix([features(row)])[0]
        contrib = X * self.w
        order = np.argsort(-np.abs(contrib))
        out = []
        for i in order[:top]:
            if abs(contrib[i]) < 0.05:
                continue
            c, lv = self.names[i]
            label = f"{LABELS[c]}: {lv}" if lv is not None else (f"{LABELS[c]} {'above' if X[i] > 0 else 'below'} average")
            out.append({"factor": label, "effect": "up" if contrib[i] > 0 else "down", "weight": round(float(contrib[i]), 2)})
        return out


def auc(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(p)
    ranks = np.empty(len(p))
    ranks[order] = np.arange(1, len(p) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def _y(rows):
    return np.array([1.0 if r["outcome"] == "Activated" else 0.0 for r in rows])


@lru_cache
def evaluation() -> dict:
    rows = leads()
    train = [r for r in rows if r["created_date"] < "2026-06-01"]
    test = [r for r in rows if r["created_date"] >= "2026-06-01"]
    m = Model(train, _y(train))
    p, y = m.predict(test), _y(test)
    k = max(1, len(test) // 10)
    top = np.argsort(-p)[:k]
    top3 = np.argsort(-p)[: max(1, int(len(test) * 0.3))]
    return {"train_rows": len(train), "test_rows": len(test), "test_auc": round(auc(y, p), 3),
            "base_rate": round(float(y.mean()), 4), "top_decile_rate": round(float(y[top].mean()), 4),
            "top_decile_lift": round(float(y[top].mean() / y.mean()), 2),
            "top30_share_of_activations": round(float(y[top3].sum() / y.sum()), 3)}


@lru_cache
def model() -> Model:
    rows = leads()
    return Model(rows, _y(rows))


def coefficients(top: int = 12) -> list[dict]:
    m = model()
    order = np.argsort(-np.abs(m.w))[:top]
    out = []
    for i in order:
        c, lv = m.names[i]
        out.append({"factor": f"{LABELS[c]}: {lv}" if lv else f"{LABELS[c]} (per s.d.)", "weight": round(float(m.w[i]), 2)})
    return out


def score(row: dict) -> dict:
    m = model()
    return {"score": round(float(m.predict([row])[0]), 4), "drivers": m.explain(row)}
