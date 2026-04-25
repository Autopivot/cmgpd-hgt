"""HGT encoder + pair scorer for marriage edge prediction.

Architecture:
  PersonEmbedder (sex + relationship + continuous + occupational) -> HIDDEN
  HouseholdEmbedder, CommunityEmbedder, BannerEmbedder            -> HIDDEN
  NUM_LAYERS × HGTConv (PyG) with residual + LayerNorm + dropout
  MarriageScorer: MLP over [h_m, h_w, |h_m-h_w|, h_m*h_w] -> logit

The graph passed at forward time must have all edge type keys present in
config.EDGE_TYPES (even if some are empty after ablation), because HGTConv
registers per-edge-type linear projections from `metadata`.
"""
from __future__ import annotations

import logging

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.data import HeteroData
from torch_geometric.nn import HGTConv

from .. import config

log = logging.getLogger(__name__)


# ── Per-node-type input embedders ──────────────────────────────────────

class PersonEmbedder(nn.Module):
    """Project the structured person features (sex/relationship/continuous/occ)
    into a single HIDDEN-dim vector.
    """

    def __init__(self, n_continuous: int, n_occ: int, vocab_size_rel: int, hidden: int):
        super().__init__()
        self.sex_embed = nn.Embedding(3, 8)              # 0/1/2
        self.rel_embed = nn.Embedding(vocab_size_rel, 16)
        in_dim = 8 + 16 + n_continuous + n_occ
        self.proj = nn.Sequential(nn.Linear(in_dim, hidden), nn.GELU(), nn.LayerNorm(hidden))

    def forward(self, data: HeteroData) -> torch.Tensor:
        s = self.sex_embed(data["person"].x_sex.clamp(0, 2))
        r = self.rel_embed(data["person"].x_relationship.clamp(min=0, max=self.rel_embed.num_embeddings - 1))
        x = torch.cat([s, r, data["person"].x_continuous, data["person"].x_occupational], dim=-1)
        return self.proj(x)


class _SimpleEmbedder(nn.Module):
    """Linear projection used for household / community / banner."""

    def __init__(self, in_dim: int, hidden: int):
        super().__init__()
        self.proj = nn.Sequential(nn.Linear(in_dim, hidden), nn.GELU(), nn.LayerNorm(hidden))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(x)


# ── HGT encoder ────────────────────────────────────────────────────────

class HGT(nn.Module):
    def __init__(
        self,
        metadata,
        n_continuous: int,
        n_occ: int,
        vocab_size_rel: int,
        n_household_feat: int,
        n_community_feat: int,
        n_banner_feat: int,
        hidden: int = config.HIDDEN,
        num_layers: int = config.NUM_LAYERS,
        heads: int = config.HEADS,
        dropout: float = config.DROPOUT,
    ):
        super().__init__()
        self.hidden = hidden
        self.dropout = dropout

        self.embedders = nn.ModuleDict({
            "person": PersonEmbedder(n_continuous, n_occ, vocab_size_rel, hidden),
            "household": _SimpleEmbedder(n_household_feat, hidden),
            "community": _SimpleEmbedder(n_community_feat, hidden),
            "banner": _SimpleEmbedder(n_banner_feat, hidden),
        })

        self.convs = nn.ModuleList([
            HGTConv(in_channels=hidden, out_channels=hidden, metadata=metadata, heads=heads)
            for _ in range(num_layers)
        ])
        self.norms = nn.ModuleList([
            nn.ModuleDict({nt: nn.LayerNorm(hidden) for nt in metadata[0]})
            for _ in range(num_layers)
        ])

    def forward(self, data: HeteroData) -> dict[str, torch.Tensor]:
        x_dict = {
            "person": self.embedders["person"](data),
            "household": self.embedders["household"](data["household"].x),
            "community": self.embedders["community"](data["community"].x),
            "banner": self.embedders["banner"](data["banner"].x),
        }
        edge_index_dict = {et: data[et].edge_index for et in data.edge_types}

        for conv, norm_d in zip(self.convs, self.norms):
            h_dict = conv(x_dict, edge_index_dict)
            new_x: dict[str, torch.Tensor] = {}
            for nt, h in h_dict.items():
                # HGTConv may return only node types that received messages.
                # Add residual + norm and fall back to the input for any
                # missing node type.
                z = h + x_dict[nt]
                z = norm_d[nt](z)
                z = F.dropout(z, p=self.dropout, training=self.training)
                new_x[nt] = z
            for nt in x_dict:
                if nt not in new_x:
                    new_x[nt] = x_dict[nt]
            x_dict = new_x
        return x_dict


# ── Pair scorer ────────────────────────────────────────────────────────

class MarriageScorer(nn.Module):
    """Score (man, woman) pairs from their HGT embeddings."""

    def __init__(self, hidden: int = config.HIDDEN, dropout: float = config.DROPOUT):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(4 * hidden, hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )

    def forward(self, h_m: torch.Tensor, h_w: torch.Tensor) -> torch.Tensor:
        feat = torch.cat([h_m, h_w, (h_m - h_w).abs(), h_m * h_w], dim=-1)
        return self.mlp(feat).squeeze(-1)


# ── Convenience constructor ────────────────────────────────────────────

def build_model(graph: HeteroData) -> tuple[HGT, MarriageScorer]:
    """Build HGT + MarriageScorer matching the graph's feature shapes."""
    n_continuous = graph["person"].x_continuous.size(1)
    n_occ = graph["person"].x_occupational.size(1)
    vocab_rel = max(int(graph["person"].x_relationship.max().item()) + 1,
                    config.CATEGORICAL_FEATURES["RELATIONSHIP"]["vocab_size"])
    n_hh = graph["household"].x.size(1)
    n_co = graph["community"].x.size(1)
    n_ba = graph["banner"].x.size(1)
    hgt = HGT(
        metadata=graph.metadata(),
        n_continuous=n_continuous,
        n_occ=n_occ,
        vocab_size_rel=vocab_rel,
        n_household_feat=n_hh,
        n_community_feat=n_co,
        n_banner_feat=n_ba,
    )
    scorer = MarriageScorer()
    return hgt, scorer
