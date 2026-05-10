# 8 Use Cases

We illustrate **[SYSTEM]** through three scenarios drawn from formative sessions with E1–E3.

## 8.1 Use Case 1 — Cohort triage of the 1882 marriages (E1)

E1, a Qing demographic historian, opens the 1882 ablated cohort from the CMGPD-LN panel (used here as evaluation testbed). V3 shows the honeycomb canvas with the divergent score-gap fill; she notices a tight cluster of green hexes in the upper-right and clicks one. V4 unfolds the 8-husband bipartite, all with score gaps above 2.0. She runs a batch commit at threshold 1.0; 7 of the 8 husbands are committed in one stroke, surfacing in V2 with the **HGT** chip. V1's curve advances cleanly above the static baseline.

The remaining husband is routed to V5, where E1 inspects the agent arena. The arena's persona reveals an income trajectory that flattened in 1879 and a single *Lost* event in 1881 — both present in DS0003. E1, recognising this as a known absconding pattern, types `@everyone be skeptical of stability claims` into the hint console; rounds 3–5 reflect this in their queries and final scores. The negotiation converges on a different wife than HGT's $\arg\max$. Both **HGT** and **MAS** chips appear once she accepts: V2 records that the two pipelines disagreed.

## 8.2 Use Case 2 — Probing the maternal-edge ablation (E3)

E3, a digital-humanities methodologist, works inside a CMGPD-LN cohort (the evaluation testbed) to verify whether maternal edges ($r_{ms}, r_{md}$) carry independent predictability beyond the marriage edges. She switches the cohort ablation to `ablated` (only $r_{hw}$ suppressed) and `unablated` (full graph) via the toolbar. The honeycomb geometry shifts visibly: the score gap distribution tightens, and the cluster boundaries reorganise around banner co-membership.

She uses V6 to suppress $\mathsf{m}_4$ (banner endogamy) and re-runs a single husband's negotiation in V5; the match changes, demonstrating that the system surfaces the motif-level dependency rather than absorbing it silently. V2's source chips for the two commits accumulate a documented divergence she can later report.

## 8.3 Use Case 3 — Real-jiapu evidence injection (E2)

E2, a computational genealogist, simulates the deployment scenario: she uses [SYSTEM] *as if* the cohort were a real jiapu in which a wife's surname (*Wang*) is the only recorded fact, even though under the hood the data is still a CMGPD-LN cohort with hidden ground truth available for grading. She loads the 1885 cohort, selects the husband whose record she wants to complete, and runs V5. After round 1, she inspects the candidate personas and types `@everyone wife's surname is Wang` in the hint console.

The orchestrator drains the hint into round 2's prompt; candidates whose surname does not match are surfaced with reduced $t_i$ scores in their explanations, and the surname-Wang candidate's persona is reasoned about explicitly in the next round's transcript (visible in the expandable conversation panel). The final commit's chip shows **MAS**-only — HGT's $\arg\max$ was a different wife — and V2's audit trail records this divergence, which E2 exports for manuscript-level cross-referencing.
