# 4 Computational Backbone

We summarise the underlying computational pieces here for completeness; all are existing methods and are not the contribution of this paper.

## 4.1 Graph schema and ablation

Let $G = (V, E, \mathcal{T}, \mathcal{R})$ denote the heterogeneous graph induced by CMGPD-LN with node types $\mathcal{T} = \{\text{person}, \text{household}, \text{community}, \text{banner}\}$ and nine edge types $\mathcal{R}$ including patrilineal kinship ($r_{fs}, r_{fd}$), matrilineal kinship ($r_{ms}, r_{md}$), co-residence ($r_{hh}, r_{hc}, r_{cb}$), and timed marriage edges $r_{hw}$ carrying $\text{edge\_time} = y$ (the marriage year).

The *jiapu-mirroring ablation* is defined edge-type-wise: for $r \in \{r_{hw}, r_{ms}, r_{md}\}$, the index tensor is replaced with an empty $2 \times 0$ tensor while the relation type is preserved in $G.\text{metadata}()$. This invariant — *"ablate, don't delete"* — is required because per-relation linear projections are registered on the metadata snapshot. Any subsequent *temporal subgraph* $G_t$ further enforces $\text{edge\_time}(e) < t$ for every $e \in E_t$, preventing leakage from cohorts not yet observed at year $t$.

## 4.2 HGT encoder and marriage scorer

Following [hu2020hgt], each layer of the HGT encoder updates $h_v^{(\ell+1)}$ for node $v$ by attention over neighbours $u$ along edge type $r \in \mathcal{R}$:

$$
\alpha_{u,v}^{r} = \mathrm{softmax}_u\!\left(
  \frac{\bigl(W^{q}_{\tau(v)} h_v^{(\ell)}\bigr)^{\!\top}\,
        W^{r}_{\mathrm{att}}\,
        \bigl(W^{k}_{\tau(u)} h_u^{(\ell)}\bigr)}
       {\sqrt{d}}
  \cdot \mu_{\tau(u),r,\tau(v)}\right)
$$

$$
h_v^{(\ell+1)} = \mathrm{LN}\!\left(
  h_v^{(\ell)} +
  \sum_{r,u} \alpha_{u,v}^{r}\,
    W^{r}_{\mathrm{msg}}\,W^{v}_{\tau(u)} h_u^{(\ell)}
  \right)
$$

where $\tau(\cdot)$ returns the node type and $\mu$ is a learned relation-prior tensor. After two HGT layers, a marriage scorer

$$
\psi(h_m, h_w) = \mathrm{MLP}\bigl([h_m,\, h_w,\, |h_m - h_w|,\, h_m \odot h_w]\bigr)
$$

emits a logit for every candidate pair $(m, w)$. Negatives are sampled within-cohort to prevent cross-year shortcuts.

## 4.3 SEAL motif extraction

For each candidate pair $(m, w)$ we extract the *enclosing $k$-hop subgraph* $\mathcal{N}_k(m, w)$ and apply Double-Radius Node Labelling (DRNL) to obtain a structural fingerprint $\phi(\mathcal{N}_k(m, w)) \in \mathbb{N}^{|\mathcal{N}_k|}$ following [zhang2018seal]. We pre-define four canonical motifs of historical interest in this domain — $\mathsf{m}_1$ father-brother, $\mathsf{m}_2$ uncle-in-law, $\mathsf{m}_3$ same-household, $\mathsf{m}_4$ banner-endogamy — and a candidate matches $\mathsf{m}_k$ when its DRNL signature is consistent with the exemplar's labelled subgraph. The matched-motif set is surfaced verbatim in the agent's persona prompt (§6).

## 4.4 Bilateral negotiation final score

Given husband-side score $t_i \in [0, 10]$ and wife-side counter-score $s_i \in [0, 10]$ for candidate $i$ at the close of round 5, the round-6 ranking obeys

$$
\mathrm{score}_i \;=\; \tfrac{1}{2} (s_i + t_i) \;-\; \lambda\,|s_i - t_i|, \quad \lambda = 0.3.
\tag{1}
$$

This rewards mutual-high configurations while penalising asymmetric agreements; $\lambda$ is exposed in V6 (§5.7) and was set to 0.3 by domain consensus during formative interviews.
