# 3 Domain Background and Task Abstraction

## 3.1 Why marriage edges matter, and why they are missing

**The target gap (jiapu).** In Chinese family genealogies (*jiapu*, 家谱), the patriline is the unit of record. Each male descendant is enumerated as a generation entry in the lineage book, while a female descendant typically appears at most as a surname on her father's entry — and in many lineage books she is omitted entirely upon marriage. The *muxia* (母家) — the maternal household to which a wife traces her natal lineage — is therefore a structurally invisible but historically pivotal node: it mediated political alliances, wet-nurse networks, banner-tax labour exchange, and inheritance disputes [wang2007muxia]. The patrilineal record convention thus blocks any reconstruction of the *muxia* from the genealogical record itself: the lateral kinship channel is simply absent from the source.

**The empirical handle (CMGPD-LN).** Direct evaluation against jiapu is therefore impossible — the very edges we wish to recover are the ones the source omits. We instead use the China Multi-Generational Panel Dataset, Liaoning (CMGPD-LN, ICPSR 27063) as a testbed. CMGPD-LN is a separate Qing demographic and administrative panel compiled from the triennial population registers maintained by the Banner administration in Liaoning between 1749 and 1909; *unlike* jiapu, it preserves the $r_{hw}$ and $r_{md}/r_{ms}$ edges along with individual life-history records. We exploit this asymmetry methodologically: ablate $r_{hw}$, $r_{md}$, and $r_{ms}$ from CMGPD-LN to simulate the jiapu record gap, train the reconstruction system on the ablated graph, and grade its output against the panel's held-out ground truth. The deployment target remains real jiapu, where no such ground truth exists.

## 3.2 Stakeholders and tasks

We held formative interviews with three domain experts (E1: Qing demographic historian; E2: computational genealogist; E3: digital humanities methodologist). Their tasks distilled into three canonical analytic primitives:

- **T1. Identify high-confidence marriage candidates within a cohort year**, with awareness of the structural support (kinship motifs) underpinning each candidate.
- **T2. Adjudicate uncertain candidates**, with surface for injecting partial archival evidence (a surname, a banner, a known in-marriage event) and surface for inspecting the agents' reasoning.
- **T3. Audit the cumulative reconstruction**, with a per-edge provenance trail and a reversal mechanism in case errors compound.

## 3.3 Design goals

The tasks above shaped six design goals (DG1–DG6) that govern every view in **[SYSTEM]**:

- **DG1. Cohort-as-canvas.** An entire marriage-year cohort must be visible at once so that ranking patterns and outliers are perceptible alongside specific candidates (T1).
- **DG2. Provenance-by-construction.** Every accepted edge must carry a multi-label provenance tag (HGT, MAS, or both) (T3).
- **DG3. Narrative grounding.** Each agent's persona must be derivable from concrete life-history evidence, not synthesised out of model priors (T2).
- **DG4. Steerable deliberation.** Hints must reach the agents without breaking the loop, addressed to specific roles (`@target`, `@c-XX`, `@everyone`) (T2).
- **DG5. Reversibility.** A trace-back of any commit must be possible in one click, with all dependent views updating coherently (T3).
- **DG6. Tight coupling.** Selection in any view must propagate to every other view through a shared bus, so that the workspace behaves as a single instrument (T1–T3).
