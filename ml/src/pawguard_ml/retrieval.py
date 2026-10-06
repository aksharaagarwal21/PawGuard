"""Open-set retrieval evaluation (identification against an enrolled gallery — not pairwise verification).

Definitions (all per query image):
- Gallery: enrolled identities' gallery images. Identity score = aggregation of image similarities (cosine).
- Closed-set: rank of the true identity among enrolled identities → top-k accuracy, MRR; image-level mAP.
- Open-set with threshold τ and a candidate list of at most K identities with score ≥ τ:
  coverage@K  — enrolled query whose true identity is in the shown list (what the reviewer needs);
  false rejection — enrolled query for which nothing is shown;
  FPIR — unknown query (identity not enrolled) for which anything is shown.
τ is chosen on validation only. Intervals: identity-clustered bootstrap (queries of a resampled identity move
together), gallery held fixed.
"""

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

AGGREGATIONS = ("max", "mean", "centroid")


@dataclass
class SplitData:
    gallery_ids: np.ndarray  # [G] identity label per gallery image
    gallery: np.ndarray  # [G, D] L2-normalised
    query_ids: np.ndarray  # [Q]
    query: np.ndarray  # [Q, D]
    unknown_ids: np.ndarray  # [U] (identity labels of unknown queries; used only for clustering)
    unknown: np.ndarray  # [U, D]


def cap_gallery(d: SplitData, per_identity: int | None, seed: int = 0) -> SplitData:
    """Keep at most `per_identity` gallery images per identity (deterministic choice) — gallery-size probe."""
    if per_identity is None:
        return d
    rng = np.random.default_rng(seed)
    keep = []
    for ident in np.unique(d.gallery_ids):
        idx = np.flatnonzero(d.gallery_ids == ident)
        keep.extend(sorted(rng.permutation(idx)[:per_identity]))
    keep = np.array(sorted(keep))
    return SplitData(d.gallery_ids[keep], d.gallery[keep], d.query_ids, d.query, d.unknown_ids, d.unknown)


def subsample_identities(d: SplitData, fraction: float, seed: int = 0) -> SplitData:
    """Enrol only a fraction of identities; queries of dropped identities are removed (not turned into unknowns)."""
    rng = np.random.default_rng(seed)
    ids = np.unique(d.gallery_ids)
    keep_ids = set(rng.permutation(ids)[: max(1, round(len(ids) * fraction))])
    g = np.array([i in keep_ids for i in d.gallery_ids])
    q = np.array([i in keep_ids for i in d.query_ids])
    return SplitData(d.gallery_ids[g], d.gallery[g], d.query_ids[q], d.query[q], d.unknown_ids, d.unknown)


def identity_scores(queries: np.ndarray, d: SplitData, aggregation: str) -> tuple[np.ndarray, np.ndarray]:
    """Returns (identity labels [I], scores [N, I])."""
    labels = np.unique(d.gallery_ids)
    if aggregation == "centroid":
        cents = np.stack([d.gallery[d.gallery_ids == lab].mean(0) for lab in labels])
        cents /= np.linalg.norm(cents, axis=1, keepdims=True)
        return labels, queries @ cents.T
    sims = queries @ d.gallery.T
    out = np.empty((queries.shape[0], len(labels)), dtype=np.float32)
    for j, lab in enumerate(labels):
        cols = sims[:, d.gallery_ids == lab]
        out[:, j] = cols.max(1) if aggregation == "max" else cols.mean(1)
    return labels, out


@dataclass
class Scored:
    """Per-query quantities from which every metric (and every bootstrap resample) is computed."""

    q_ident: np.ndarray  # identity of each enrolled query
    rank: np.ndarray  # 1-based rank of true identity
    true_score: np.ndarray
    top: np.ndarray  # [Q, K] top-K identity scores, descending
    ap: np.ndarray  # image-level average precision per query
    u_ident: np.ndarray
    u_top1: np.ndarray


def score(d: SplitData, aggregation: str, k: int = 5) -> Scored:
    labels, s = identity_scores(d.query, d, aggregation)
    col = {lab: j for j, lab in enumerate(labels)}
    true_j = np.array([col[i] for i in d.query_ids])
    true_score = s[np.arange(len(true_j)), true_j]
    rank = (s > true_score[:, None]).sum(1) + 1
    top = -np.sort(-s, axis=1)[:, :k]
    # image-level mAP over gallery images
    sims = d.query @ d.gallery.T
    order = np.argsort(-sims, axis=1)
    rel = d.gallery_ids[order] == d.query_ids[:, None]
    cum = np.cumsum(rel, axis=1)
    prec = cum / np.arange(1, rel.shape[1] + 1)
    ap = (prec * rel).sum(1) / np.maximum(rel.sum(1), 1)
    _, su = identity_scores(d.unknown, d, aggregation)
    return Scored(d.query_ids, rank, true_score, top, ap, d.unknown_ids, su.max(1))


def threshold_for_fpir(u_top1: np.ndarray, target: float) -> float:
    """Smallest τ with FPIR(τ) = mean(u_top1 ≥ τ) ≤ target."""
    u = np.sort(u_top1)[::-1]
    allowed = int(np.floor(target * len(u)))
    if allowed >= len(u):
        return float(u[-1])
    return float(np.nextafter(np.float32(u[allowed]), np.float32(np.inf)))


def metrics(sc: Scored, tau: float | None, k_list: int = 3, q_idx: np.ndarray | None = None,
            u_idx: np.ndarray | None = None) -> dict:
    qi = slice(None) if q_idx is None else q_idx
    ui = slice(None) if u_idx is None else u_idx
    rank, true_score, top, ap = sc.rank[qi], sc.true_score[qi], sc.top[qi], sc.ap[qi]
    out = {"top1": float((rank <= 1).mean()), "top3": float((rank <= 3).mean()), "top5": float((rank <= 5).mean()),
           "mrr": float((1.0 / rank).mean()), "map_image": float(ap.mean())}
    if tau is not None:
        u = sc.u_top1[ui]
        out["fpir"] = float((u >= tau).mean())
        out[f"coverage_at_{k_list}"] = float(((rank <= k_list) & (true_score >= tau)).mean())
        out["false_rejection"] = float((top[:, 0] < tau).mean())
        out["mean_candidates_shown"] = float((top[:, :k_list] >= tau).sum(1).mean())
        # Known dogs: the single best suggestion is the right dog AND confident / the wrong dog but confident.
        out["known_top1_correct_accepted"] = float(((rank <= 1) & (true_score >= tau)).mean())
        out["known_top1_wrong_accepted"] = float(((rank > 1) & (top[:, 0] >= tau)).mean())
    return out


def bootstrap(sc: Scored, tau: float | None, reps: int = 1000, seed: int = 0) -> dict:
    """Identity-clustered percentile bootstrap (95%)."""
    rng = np.random.default_rng(seed)
    q_groups: dict[str, list[int]] = defaultdict(list)
    for i, ident in enumerate(sc.q_ident):
        q_groups[ident].append(i)
    u_groups: dict[str, list[int]] = defaultdict(list)
    for i, ident in enumerate(sc.u_ident):
        u_groups[ident].append(i)
    qg, ug = list(q_groups.values()), list(u_groups.values())
    samples: dict[str, list[float]] = defaultdict(list)
    for _ in range(reps):
        qi = np.concatenate([qg[j] for j in rng.integers(0, len(qg), len(qg))])
        ui = np.concatenate([ug[j] for j in rng.integers(0, len(ug), len(ug))]) if ug else None
        for k, v in metrics(sc, tau, q_idx=qi, u_idx=ui).items():
            samples[k].append(v)
    point = metrics(sc, tau)
    return {k: {"value": round(point[k], 4), "ci95": [round(float(np.percentile(v, 2.5)), 4),
                                                     round(float(np.percentile(v, 97.5)), 4)]}
            for k, v in samples.items()}


def margin_analysis(sc: Scored, tau: float) -> dict:
    """Does the gap between the top two identity scores separate right from wrong top-1 among shown queries?"""
    shown = sc.top[:, 0] >= tau
    correct = (sc.rank == 1) & shown
    wrong = (sc.rank > 1) & shown
    m = sc.top[:, 0] - sc.top[:, 1]
    a, b = m[correct], m[wrong]
    if len(a) == 0 or len(b) == 0:
        return {"auroc": None, "n_correct": len(a), "n_wrong": len(b)}
    auroc = float((a[:, None] > b[None, :]).mean() + 0.5 * (a[:, None] == b[None, :]).mean())
    return {"auroc": round(auroc, 4), "n_correct": len(a), "n_wrong": len(b),
            "median_margin_correct": round(float(np.median(a)), 4), "median_margin_wrong": round(float(np.median(b)), 4)}
