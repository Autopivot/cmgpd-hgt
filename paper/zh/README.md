# 论文章节

十三个 markdown 文件，按照其在 IEEE VIS 论文初稿中出现的顺序排列。
可以以任意顺序拼接；每一节都是自包含的。

本文在 **CMGPD-LN** 测试平台上验证 **[SYSTEM]** —— 一份清代三年一造的行政面板（ICPSR 第 27063 号研究），*而非* 家谱本身 —— 并主张将其部署到真实的中国家谱（jiapu，家谱）中，因为女性记录缺失的问题正是发生在那里，而真值（ground truth）也无从获得。
请在所有编辑中保持「测试平台 → 部署目标」这一一以贯之的轨迹。

| 文件 | 章节 | 大致篇幅 |
|---|---|---|
| [`00_abstract.md`](00_abstract.md) | Abstract（5 句式） | ½ 页 |
| [`01_introduction.md`](01_introduction.md) | 1 Introduction | 1.25 页 |
| [`02_related_work.md`](02_related_work.md) | 2 Related Work | 0.75 页 |
| [`03_domain_background.md`](03_domain_background.md) | 3 Domain Background and Task Abstraction | 1 页 |
| [`04_computational_backbone.md`](04_computational_backbone.md) | 4 Computational Backbone（HGT + SEAL + 公式 1） | 1 页 |
| [`05_visual_design.md`](05_visual_design.md) | 5 [SYSTEM]：Visual Analytics Design（V1–V6） | 3 页 |
| [`06_mas_protocol.md`](06_mas_protocol.md) | 6 Multi-Agent Negotiation Protocol（Algorithm 1） | 1 页 |
| [`07_implementation.md`](07_implementation.md) | 7 Implementation | 0.3 页 |
| [`08_use_cases.md`](08_use_cases.md) | 8 Use Cases（E1、E2、E3） | 1.5 页 |
| [`09_expert_study.md`](09_expert_study.md) | 9 Expert Study | 0.5 页 |
| [`10_discussion.md`](10_discussion.md) | 10 Discussion and Limitations | 0.5 页 |
| [`11_conclusion.md`](11_conclusion.md) | 11 Conclusion | 0.2 页 |

## 投稿前

1. 在所有 12 个文件中将 `[SYSTEM]` 替换为最终选定的系统名称（全局搜索替换）。
2. 将摘要 / 引言中所有 `XXX` 替换为实测数值（Hit@1、Hit@10、MRR、MAS 后的 precision）。
3. 比对所有 `[citation-key]` 占位符与 Semantic Scholar / CrossRef / arXiv —— 这些都尚未经过程序化校验。
