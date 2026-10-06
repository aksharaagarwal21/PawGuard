"""Head-only identity adaptation on frozen DINOv2 features (brief §7.6, step 1: backbone frozen).

Input features per image = [L2(cls) ‖ L2(patch_mean)] (768-D) from the selected preprocessing; output = L2-normalised
384-D embedding, so the product's vector(384) store and search are unchanged. Objectives:
- ``supcon`` — supervised contrastive loss (primary);
- ``arcface`` — additive angular margin classification over training identities (documented alternative; only the
  embedding is used at inference, never the class logits).
Identity-balanced batches (P identities × K images), AdamW, linear warm-up then cosine decay, gradient clipping,
fixed seed, early stopping on the validation retrieval criterion — never on training loss alone.
"""

import math
import time
from dataclasses import asdict, dataclass

import numpy as np
import torch
import torch.nn.functional as F

from pawguard_ml import retrieval as rv


@dataclass
class HeadConfig:
    objective: str = "supcon"  # supcon | arcface
    hidden: int = 0  # 0 = single linear layer
    epochs: int = 50
    patience: int = 8
    p_identities: int = 16
    k_images: int = 4
    lr: float = 1e-3
    weight_decay: float = 0.05
    warmup_epochs: int = 2
    temperature: float = 0.1  # supcon
    arc_scale: float = 30.0  # arcface
    arc_margin: float = 0.3
    flip_augment: bool = False
    seed: int = 20261006


class Head(torch.nn.Module):
    def __init__(self, d_in: int, d_out: int = 384, hidden: int = 0) -> None:
        super().__init__()
        self.net = (torch.nn.Linear(d_in, d_out) if hidden == 0 else
                    torch.nn.Sequential(torch.nn.Linear(d_in, hidden), torch.nn.GELU(), torch.nn.Linear(hidden, d_out)))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.net(x), dim=-1)


def features(cls_tok: np.ndarray, patch_mean: np.ndarray) -> np.ndarray:
    def l2(v: np.ndarray) -> np.ndarray:
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)

    return np.concatenate([l2(cls_tok), l2(patch_mean)], axis=1).astype(np.float32)


def supcon_loss(z: torch.Tensor, y: torch.Tensor, t: float) -> torch.Tensor:
    sim = z @ z.T / t
    eye = torch.eye(len(y), dtype=torch.bool)
    sim = sim.masked_fill(eye, -1e9)
    pos = (y[:, None] == y[None, :]) & ~eye
    log_prob = sim - torch.logsumexp(sim, dim=1, keepdim=True)
    n_pos = pos.sum(1).clamp(min=1)
    return -((log_prob * pos).sum(1) / n_pos).mean()


class ArcMargin(torch.nn.Module):
    def __init__(self, d: int, n_classes: int, s: float, m: float) -> None:
        super().__init__()
        self.w = torch.nn.Parameter(torch.randn(n_classes, d) * 0.01)
        self.s, self.m = s, m

    def forward(self, z: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        cos = z @ F.normalize(self.w, dim=-1).T
        theta = torch.acos(cos.clamp(-1 + 1e-7, 1 - 1e-7))
        target = torch.cos(theta + self.m)
        onehot = F.one_hot(y, cos.shape[1]).bool()
        logits = torch.where(onehot, target, cos) * self.s
        return F.cross_entropy(logits, y)


def _batches(labels: np.ndarray, p: int, k: int, rng: np.random.Generator):
    by_id: dict[int, np.ndarray] = {}
    for lab in np.unique(labels):
        by_id[int(lab)] = np.flatnonzero(labels == lab)
    ids = rng.permutation(list(by_id))
    for start in range(0, len(ids) - p + 1, p):
        idx = []
        for i in ids[start:start + p]:
            pool = by_id[int(i)]
            idx.extend(rng.choice(pool, size=k, replace=len(pool) < k))
        yield np.array(idx)


def train_head(x_train: np.ndarray, y_train: np.ndarray, val_feats: np.ndarray, val_rows_split, aggregation: str,
               fpir_target: float, cfg: HeadConfig) -> dict:
    """Returns the best head (by validation coverage@3 at FPIR target) with its learning curve."""
    torch.manual_seed(cfg.seed)
    rng = np.random.default_rng(cfg.seed)
    _, y = np.unique(y_train, return_inverse=True)
    head = Head(x_train.shape[1], 384, cfg.hidden)
    params = list(head.parameters())
    arc = None
    if cfg.objective == "arcface":
        arc = ArcMargin(384, int(y.max()) + 1, cfg.arc_scale, cfg.arc_margin)
        params += list(arc.parameters())
    opt = torch.optim.AdamW(params, lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps_per_epoch = max(1, len(np.unique(y)) // cfg.p_identities)
    total, warm = cfg.epochs * steps_per_epoch, cfg.warmup_epochs * steps_per_epoch

    def lr_at(step: int) -> float:
        if step < warm:
            return (step + 1) / warm
        return 0.5 * (1 + math.cos(math.pi * (step - warm) / max(1, total - warm)))

    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_at)
    xt, yt = torch.from_numpy(x_train), torch.from_numpy(y.astype(np.int64))
    curve, best, best_state, since = [], None, None, 0
    t0 = time.perf_counter()
    for epoch in range(1, cfg.epochs + 1):
        head.train()
        losses = []
        for idx in _batches(y, cfg.p_identities, cfg.k_images, rng):
            z = head(xt[idx])
            loss = supcon_loss(z, yt[idx], cfg.temperature) if arc is None else arc(z, yt[idx])
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            sched.step()
            losses.append(float(loss))
        head.eval()
        with torch.inference_mode():
            vz = head(torch.from_numpy(val_feats)).numpy()
        d = val_rows_split(vz)
        sc = rv.score(d, aggregation)
        tau = rv.threshold_for_fpir(sc.u_top1, fpir_target)
        met = rv.metrics(sc, tau)
        curve.append({"epoch": epoch, "train_loss": round(float(np.mean(losses)), 4), "val_tau": round(tau, 5),
                      **{k: round(v, 4) for k, v in met.items()}})
        key = (met["coverage_at_3"], met["mrr"])
        if best is None or key > best:
            best, since = key, 0
            best_state = {k: v.clone() for k, v in head.state_dict().items()}
            best_epoch, best_tau = epoch, tau
        else:
            since += 1
            if since >= cfg.patience:
                break
    head.load_state_dict(best_state)
    return {"config": asdict(cfg), "best_epoch": best_epoch, "val_tau": round(best_tau, 5),
            "val_best": curve[best_epoch - 1], "curve": curve, "train_seconds": round(time.perf_counter() - t0, 1),
            "head": head}
