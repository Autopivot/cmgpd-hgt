# Paper sections

Twelve markdown files, in the order they appear in an IEEE VIS draft.
Stitch in any order; each section is self-contained.

The paper validates **[SYSTEM]** on the **CMGPD-LN** testbed — a Qing triennial
administrative panel (ICPSR Study 27063), *not* a jiapu — and argues for
deployment on real Chinese family genealogies (jiapu, 家谱), where the
female-record gap is the actual problem and ground truth is unavailable.
Keep this testbed-to-deployment trajectory consistent across edits.

| File | Section | Approx. length |
|---|---|---|
| [`00_abstract.md`](00_abstract.md) | Abstract (5-sentence formula) | ½ page |
| [`01_introduction.md`](01_introduction.md) | 1 Introduction | 1.25 pp |
| [`02_related_work.md`](02_related_work.md) | 2 Related Work | 0.75 p |
| [`03_domain_background.md`](03_domain_background.md) | 3 Domain Background and Task Abstraction | 1 p |
| [`04_computational_backbone.md`](04_computational_backbone.md) | 4 Computational Backbone (HGT + SEAL + Eq. 1) | 1 p |
| [`05_visual_design.md`](05_visual_design.md) | 5 [SYSTEM]: Visual Analytics Design (V1–V6) | 3 pp |
| [`06_mas_protocol.md`](06_mas_protocol.md) | 6 Multi-Agent Negotiation Protocol (Algorithm 1) | 1 p |
| [`07_implementation.md`](07_implementation.md) | 7 Implementation | 0.3 p |
| [`08_use_cases.md`](08_use_cases.md) | 8 Use Cases (E1, E2, E3) | 1.5 pp |
| [`09_expert_study.md`](09_expert_study.md) | 9 Expert Study | 0.5 p |
| [`10_discussion.md`](10_discussion.md) | 10 Discussion and Limitations | 0.5 p |
| [`11_conclusion.md`](11_conclusion.md) | 11 Conclusion | 0.2 p |

## Before submission

1. Substitute `[SYSTEM]` (search-replace across all 12 files) with the chosen system name.
2. Replace every `XXX` in the abstract / introduction with measured numbers (Hit@1, Hit@10, MRR, post-MAS precision).
3. Verify every `[citation-key]` placeholder against Semantic Scholar / CrossRef / arXiv — none of them have been programmatically verified.
