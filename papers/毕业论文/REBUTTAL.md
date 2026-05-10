# 自审 Rebuttal 与修订清单

协调者通读 11 个章节后，扮演毕业答辩委员会列出的可执行修订意见。每条都已按下方标记是否回写到源文件。

## R1（事实/拼写）— Chap_02 第 7 行

**问题**：写作 "GenoQuilts"，但 bib 条目 `bezerianos2010genealogy` 标题为 "GeneaQuilts: A System for Exploring Large Genealogies"。专有名词错拼。
**修订**：`GenoQuilts` → `GeneaQuilts`。
**状态**：已修订。

## R2（事实/伪作者）— Chap_02 第 25 行

**问题**：写作 "Green 与 Hu\citep{green2009mixedinitiative}"，但 bib 条目作者为 `Green, T. M. and Ribarsky, W. and Fisher, B.`，并无 "Hu"。"Hu" 系编造的合著者。
**修订**：`Green 与 Hu` → `Green 等`。
**状态**：已修订。

## R3（引用错误归属）— Chap_03 第 9 行

**问题**：在介绍 CMGPD-LN 时引用 `\citep{calderon2025analysing}`，但该文献内容为基于人口微观仿真分析家谱偏差，并非 CMGPD-LN 的数据卷。CMGPD-LN 的正确引用是 `campbell2011data`。
**修订**：`\citep{calderon2025analysing}` → `\citep{campbell2011data}`。
**状态**：已修订。

## R4（不变量违反）— Chap_06 第 7 行

**问题**：写作"母系边 \(r_{ms}, r_{md}\) 已删"，与第 4 章"消融而不删除"不变量直接矛盾。术语 "已删" 暗示从元数据中移除，会破坏 HGT 的关系投影注册。
**修订**：`母系边 $r_\mathrm{ms}, r_\mathrm{md}$ 已删` → `母系边 $r_\mathrm{ms}, r_\mathrm{md}$ 已按 \S\ref{sec:ablation} 的镜像消融策略置空（保留元数据键）`。
**状态**：已修订。

## R5（编译错误风险）— Chap_07 多处使用 `\cref{}`

**问题**：第 7 章使用了 `\cref{sec:mas-hint}`、`\cref{alg:negotiation}`、`\cref{eq:final-score}`、`\cref{tab:hint-routing}`，但模板 `Style/artratex.sty` 默认不加载 `cleveref` 宏包。直接编译会报 `Undefined control sequence`。
**修订**：`\cref{xxx}` 替换为带前缀名的 `\ref{xxx}`，例如 `\cref{tab:hint-routing}` → `表~\ref{tab:hint-routing}`。
**状态**：已修订（4 处全部替换）。

## R6（数字错误）— Chap_11 第 23 行

**问题**：写作"六分制 Likert 量表"，但第 10 章及 STYLE_BRIEF 均为 1–7 七点制。属内部数字不一致。
**修订**：`六分制 Likert 量表` → `七分制 Likert 量表`。
**状态**：已修订。

## R7（中英混排）— Chap_01 第 7 行

**问题**：写作"约 1.51 million 条人年记录"，中英文混排不符合学术中文。
**修订**：`约 1.51 million 条人年记录` → `约 151 万条人年记录`。
**状态**：已修订。

## R8（DG6 衔接弱）— Chap_03 第 39 行 + Chap_08 第 7 行

**问题**：DG6 在第 3 章定义为"通过空间先验跨队列复用规则"，第 8 章 §8.1 总体框架对应该段说"避免逐对实例记忆，是 DG6 的主要落点"，已显式回扣。无需修订。
**状态**：无须修订。

## R9（章节交叉引用稳健性）— 全文

**问题**：核对所有 \ref / \eqref 是否指向真实存在的 label。已对 chap、sec、tab、eq、fig、alg label 做了一次全文 grep，发现以下 cross-ref 全部目标 label 存在：
- `\ref{chap:hgt}`、`\ref{chap:data}`、`\ref{chap:mas}` ✓
- `\ref{sec:ablation}`（在 R4 修订中新增引用）✓
- `\ref{tab:edge-types}`、`\ref{tab:features}`、`\ref{tab:hyperparams}`、`\ref{tab:motif-catalog}`、`\ref{tab:six-views}`、`\ref{tab:expert-likert}`、`\ref{tab:hint-routing}` ✓
- `\eqref{eq:subgraph}`、`\eqref{eq:embedder}`、`\eqref{eq:hgt-att}`、`\eqref{eq:hgt-upd}`、`\eqref{eq:scorer}`、`\eqref{eq:loss}`、`\eqref{eq:final-score}`、`\eqref{eq:drnl}`、`\eqref{eq:rgcn-update}` ✓
- `\ref{fig:framework}`、`\ref{fig:system}` — 图文件未实际拷贝到 `Img/`，但首轮编译会以方框占位，不阻塞 PDF 生成；待最终成稿前由用户从 `papers/VIS_SHORT_Genealogy/figures/` 拷入对应 PDF。

**状态**：cross-ref 完整，仅图文件待用户在最终稿落盘前拷贝（此项非论文内容缺陷，列入交付说明）。

## R10（致谢与个人信息）— Frontpages.tex / Backmatter.tex

**问题**：用户明确要求致谢留空，封面个人信息留空。
**确认**：`Frontpages.tex` 中 `author={}`、`ID={}`、`entranceYear={}`、`advisor={}` 均为空字符串；`Backmatter.tex` 致谢章节正文为注释占位。已合规。
**状态**：无须修订。

---

## 修订汇总

| 编号 | 章节 | 类型 | 已应用 |
|---|---|---|---|
| R1 | Chap_02 | 拼写 | 是 |
| R2 | Chap_02 | 伪作者 | 是 |
| R3 | Chap_03 | 误引用 | 是 |
| R4 | Chap_06 | 不变量 | 是 |
| R5 | Chap_07 | cleveref 兼容 | 是（4 处） |
| R6 | Chap_11 | 数字一致性 | 是 |
| R7 | Chap_01 | 中英混排 | 是 |
| R8 | — | 衔接 | 无须 |
| R9 | — | 交叉引用 | 无须 |
| R10 | Frontpages/Backmatter | 隐私 | 无须 |

共 7 项可执行修订，全部回写到对应 `.tex` 文件。
