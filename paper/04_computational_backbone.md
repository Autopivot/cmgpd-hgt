# 4 Computational Backbone

We summarise the underlying computational pieces here for completeness; all are existing methods and are not the contribution of this paper.

## 4.1 Graph schema and ablation

Let $G = (V, E, \mathcal{T}, \mathcal{R})$ denote the heterogeneous graph induced by CMGPD-LN with node types $\mathcal{T} = \{\text{person}, \text{household}, \text{community}, \text{banner}\}$ and nine edge types $\mathcal{R}$ comprising patrilineal kinship ($r_{fs}$ father→son, $r_{fd}$ father→daughter), matrilineal kinship ($r_{ms}$ mother→son, $r_{md}$ mother→daughter), siblings ($r_{sib}$), co-residence ($r_{hh}$ person→household, $r_{hc}$ household→community, $r_{cb}$ person→banner), and timed marriage edges $r_{hw}$ carrying $\text{edge\_time} = y$ (the marriage year).

The **jiapu-mirroring ablation** is defined edge-type-wise: for $r \in \{r_{hw}, r_{ms}, r_{md}\}$ the index tensor is replaced with an empty $2 \times 0$ tensor while the relation type is preserved in $G.\text{metadata}()$. This invariant — *"ablate, don't delete"* — is required because per-relation linear projections are registered on the metadata snapshot.

Any subsequent **temporal subgraph** $G_t$ further enforces $\text{edge\_time}(e) < t$ for every $e \in E_t$, preventing leakage from cohorts not yet observed at year $t$. For the year-$t$ marriage cohort, training and evaluation additionally drop from the message-passing graph (i) the year-$t$ target pairs themselves and (ii) all validation- and test-set pairs, so a predicted edge cannot leak back into the encoder as a neighbour.

## 4.2 Feature engineering

**Person nodes** carry five parallel feature streams that `PersonEmbedder` projects into a single $d = 128$-dim vector:

| Tensor | Shape | Source | Treatment |
|---|---|---|---|
| `x_sex` | LongTensor $[N]$ | DS0001 SEX, unknown=0 / female=1 / male=2 | `nn.Embedding(3, 8)` |
| `x_relationship` | LongTensor $[N]$ | DS0001 RELATIONSHIP, top-64 by frequency, index 0 reserved for `<UNK>` | `nn.Embedding(64, 16)` |
| `x_continuous` | FloatTensor $[N, 1]$ | BIRTHYEAR only — AGE\_IN\_SUI removed because it depended on the snapshot year and leaked post-marriage state | column z-score, with explicit missingness mask so legitimate zeros are not coerced to the column mean |
| `x_occupational` | FloatTensor $[N, 3]$ | DS0001 POSITION / TITLE / SALARY indicator flags | concatenated as-is |
| `x_macro` | FloatTensor $[K=5]$, shared per cohort | macro covariates for cohort year $t-1$ (see below) | broadcast across $N$ rows at forward time |

The five components of `x_macro` come from DS0009 / DS0011 plus reign-period coding: $\textsf{cohort\_year\_z}$ (z-scored year), $\textsf{grain\_price\_z}$ (DS0009 grain prices), $\textsf{grain\_price\_yoy}$ (year-over-year change), $\textsf{era\_id}$ (Qing reign id: Qianlong=0, Jiaqing=1, …, Xuantong=6), $\textsf{disaster\_flag}$ (DS0011). They live on a $(n_{\text{years}}, K)$ lookup `macro_table` attached to the graph; `subgraph_at_year(t)` reads row $t-1$ and stashes it on `person.x_macro` so the covariates align with the cohort year being scored — not the snapshot year.

`PersonEmbedder` concatenates the five streams into an $8 + 16 + 1 + 3 + 5 = 33$-dim vector and applies $\mathrm{Linear}(33, 128) \to \mathrm{GELU} \to \mathrm{LayerNorm}$:
$$
h^{(0)}_v = \mathrm{LN}\!\Bigl(\mathrm{GELU}\bigl(W_{\text{person}}\,[\,e_{\text{sex}}\;\Vert\;e_{\text{rel}}\;\Vert\;x_{\text{cont}}\;\Vert\;x_{\text{occ}}\;\Vert\;x_{\text{macro}}\,]\bigr)\Bigr) \in \mathbb{R}^{128}.
$$

**Household nodes**: FloatTensor $[N_{\text{hh}}, 5]$ — household size, approximate married-couple count, generation count, head-of-household-has-position indicator, last-observation year normalised — followed by $\mathrm{Linear}(5, 128) \to \mathrm{GELU} \to \mathrm{LayerNorm}$.

**Community nodes**: FloatTensor $[N_{\text{co}}, 1]$ — village population normalised — projected to 128.

**Banner nodes**: FloatTensor $[N_{\text{ba}}, N_{\text{ba}}]$ identity-style one-hot — projected to 128.

## 4.3 HGT encoder and marriage scorer

Each layer of the HGT encoder [hu2020hgt] updates $h_v^{(\ell+1)}$ for node $v$ by attention over neighbours $u$ along edge type $r \in \mathcal{R}$:
$$
\alpha_{u,v}^{r} = \mathrm{softmax}_u\!\left(
  \frac{\bigl(W^{q}_{\tau(v)} h_v^{(\ell)}\bigr)^{\!\top}\,
        W^{r}_{\mathrm{att}}\,
        \bigl(W^{k}_{\tau(u)} h_u^{(\ell)}\bigr)}
       {\sqrt{d / H}}
  \cdot \mu_{\tau(u),r,\tau(v)}\right)
$$
$$
h_v^{(\ell+1)} = \mathrm{LN}\!\left(
  h_v^{(\ell)} + \mathrm{Dropout}_p\!\Bigl(
  \sum_{r,u} \alpha_{u,v}^{r}\,
    W^{r}_{\mathrm{msg}}\,W^{v}_{\tau(u)} h_u^{(\ell)}\Bigr)
  \right)
$$
where $\tau(\cdot)$ returns the node type and $\mu \in \mathbb{R}^{|\mathcal{T}| \times |\mathcal{R}| \times |\mathcal{T}|}$ is a learned relation-prior tensor. A residual + LayerNorm + dropout envelope wraps the conv output (any node type the conv omits falls back to $h_v^{(\ell)}$). We use PyG's `HGTConv`.

**Hyperparameters** (single source: `config.py`): hidden dimension $d = 128$, depth $L = 2$, attention heads $H = 4$, dropout $p = 0.2$; $|\mathcal{T}| = 4$, $|\mathcal{R}| = 9$.

After $L$ layers, a marriage scorer
$$
\psi(h_m, h_w) = W_2\,\mathrm{Dropout}_p\!\bigl(\mathrm{GELU}(W_1\,[\,h_m\;\Vert\;h_w\;\Vert\;|h_m - h_w|\;\Vert\;h_m \odot h_w\,])\bigr) \in \mathbb{R}
$$
emits a logit per candidate pair $(m, w)$, with $W_1 \in \mathbb{R}^{128 \times 512}$, $W_2 \in \mathbb{R}^{1 \times 128}$, and the $4d = 512$-dim pair-interaction vector concatenating the two embeddings, their absolute difference, and their Hadamard product.

## 4.4 Training loop

Each epoch shuffles the training years and groups them into optimizer steps of `BATCH_YEARS = 4` cohorts. For each cohort year $t$, `subgraph_at_year(t, drop = train[t] ∪ all_val_pairs ∪ all_test_pairs)` constructs the message-passing subgraph (enforcing $\text{edge\_time} < t$, dropping the year-$t$ target pairs and every val/test pair as described at the end of §4.1). The loss sums binary cross-entropy over the cohort's positive pairs $(m, w)$ together with `NEG_PER_POS = 4` **within-cohort** negatives $(m, w')$ per positive:
$$
\mathcal{L} \;=\; -\,\frac{1}{|\mathcal{B}|} \sum_{(m, w, y) \in \mathcal{B}} \Bigl[\,y\,\log\sigma(\psi(h_m, h_w)) \;+\; (1 - y)\,\log\bigl(1 - \sigma(\psi(h_m, h_w))\bigr)\Bigr].
$$
Cross-year negatives are too easy on this panel (the geometric distance from the positive is large) and inflate the metrics; the within-cohort choice is data-driven, not a stylistic preference.

**Optimisation**: AdamW with learning rate $\eta = 10^{-3}$, weight decay $10^{-2}$, gradient norm clipped to 1.0, 30 epochs. Each epoch validates by **per-cohort Hungarian recall@1** and the best checkpoint is retained; the ablated and unablated training tracks are saved separately (`best_ablated.pt` / `best_unablated.pt`) — a model trained on the ablated graph has random-init projections for $r_{ms}/r_{md}$ and would produce nonsense deltas if evaluated on the unablated graph, so each weight set must be paired with its own graph variant.

## 4.5 SEAL motif extraction

For each candidate pair $(m, w)$ we extract the *enclosing $k$-hop subgraph* $\mathcal{N}_k(m, w)$ and apply Double-Radius Node Labelling (DRNL) to obtain a structural fingerprint $\phi(\mathcal{N}_k(m, w)) \in \mathbb{N}^{|\mathcal{N}_k|}$ following [zhang2018seal]. We pre-define four canonical motifs of historical interest in this domain — $\mathsf{m}_1$ father-brother, $\mathsf{m}_2$ uncle-in-law, $\mathsf{m}_3$ same-household, $\mathsf{m}_4$ banner-endogamy — and a candidate matches $\mathsf{m}_k$ when its DRNL signature is consistent with the exemplar's labelled subgraph. The matched-motif set is surfaced verbatim in the agent's persona prompt (§6).

## 4.6 Bilateral negotiation final score

Given husband-side score $t_i \in [0, 10]$ and wife-side counter-score $s_i \in [0, 10]$ for candidate $i$ at the close of round 5, the round-6 ranking obeys
$$
\mathrm{score}_i \;=\; \tfrac{1}{2} (s_i + t_i) \;-\; \lambda\,|s_i - t_i|, \quad \lambda = 0.3.
\tag{1}
$$
This rewards mutual-high configurations while penalising asymmetric agreements; $\lambda$ is exposed in V6 (§5.7) and was set to 0.3 by domain consensus during formative interviews.
