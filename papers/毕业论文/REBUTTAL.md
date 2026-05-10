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

---

# 第二轮 Rebuttal（用户编译后的评审意见，2026-05-10）

用户在本机编译 PDF 后给出第二轮意见，主要涉及版面与叙述风格。

## RA — 版面：标题页缺失

**问题**：编译产物缺少中英文封面页与作者声明页。`Frontpages.tex` 中的 `\maketitle`、`\makeenglishtitle`、`\makedeclaration` 在原模板示例中均被注释。
**修订**：去掉三条命令前的注释符；`\setcounter{page}{1}` 与 `\pagenumbering{Roman}` 移到三条 \make* 命令之后、第一个 `\chapter*{摘要}` 之前，使罗马数字页码从摘要起算，封面与英文封面用模板默认页码。
**位置**：`Tex/Frontpages.tex`
**状态**：已修订（Worker 1 → PR #32）。

## RB — 版面：正文太靠页面顶端

**问题**：与 RA 相关。封面缺失使第一章直接落到首页，`ucasthesis.cls` 的 `\voffset=-17.4mm`、`\topmargin=20pt` 在缺乏封面缓冲下令章首与页眉过近。
**修订**：启用标题页后该问题自然缓解，因为封面页占据首页垂直空间，章首被推到正常位置。
**状态**：已修订（与 RA 同源）。

## RC — 版面：长公式越框

**问题**：`eq:loss` 与 `eq:scorer` 单行字符接近 200，逼近 146.6 mm 文本宽度阈值，可能溢出。
**修订**：两式均重写为 `\begin{aligned}` 多行形式。`eq:scorer` 拆为先定义交互向量 \(\mathbf{p}_{m,w}\) 再计算 \(\psi\)；`eq:loss` 拆为先定义批均值再展开单样本损失 \(\ell(m,w,y)\)。
**位置**：`Tex/Chap_05_Backend.tex` §5.2
**状态**：已修订（Worker 3 → PR #36）。

## RD — 内容：去除路径与文件扩展名

**问题**：原稿 `Chap_05_HGT`、`Chap_07_MAS`、`Chap_09_Impl` 等含路径片段（`src/`、`server/`、`viz-mas/` 等）与扩展名（`.json`、`.parquet`、`.py` 等）。
**修订**：以 STYLE_BRIEF v2 §7 的概念名替换；如 `src/` → "数据与模型层"、`Apache Parquet` → "列式存储"、`asyncio.gather` → "并行调度原语"。
**位置**：`Tex/Chap_05_Backend.tex` §5.4、`Tex/Chap_07_Impl.tex` 整章
**状态**：已修订（Worker 3、5 → PR #36、#35）。

## RE — 内容：英文字段中文化

**问题**：原稿大量直接出现 `x_sex`、`PersonEmbedder`、`BIRTHYEAR`、`RECORD_NUMBER` 等代码标识，可读性差。
**修订**：按 STYLE_BRIEF v2 §8 对照表全文替换为"性别字段"、"人物嵌入器"、"出生年"、"记录编号"等；外部专有名词首次出现给"中文（English）"对照，之后只用中文。
**状态**：已修订（涉及 Worker 3、5、6、7）。

## RF — 内容：参考本科论文叙述风格、合并精简

**问题**：原 11 章过细，技术细节占比过高，与本科毕业论文综述式叙述风格不符。
**修订**：
- 合并旧 §4–§7（数据、HGT、SEAL、MAS）为单一"后端引擎"章 `chap:backend`，下设四节 `sec:backend-graph` / `sec:backend-hgt` / `sec:backend-seal` / `sec:backend-mas`；删去 `tab:features`、`tab:hyperparams` 等过细表格，改为段落叙述；保留核心公式与必要表格。
- 新增"系统概述"章 `chap:overview` 置于"后端引擎"之前，从高层介绍后端 + 前端各做了什么、回应哪些用户需求、遵循哪些可视化设计规则。
- 旧 chap 8/9/10/11 顺次 rename 为 chap 6/7/8/9。
- 跨章引用：`\ref{chap:hgt|data|seal|mas}` → `\ref{chap:backend}`；`\ref{sec:ablation}` → `\ref{sec:backend-graph}`。
**位置**：新增 `Tex/Chap_04_Overview.tex`；新增 `Tex/Chap_05_Backend.tex`；`Tex/Chap_06_Vis.tex`、`Tex/Chap_08_Case.tex`、`Tex/Chap_09_Conclusion.tex` 同步更新引用。
**状态**：已修订（Worker 2、3、4、6、7）。

## 第二轮修订汇总

| 编号 | 类型 | 涉及单元 | PR |
|---|---|---|---|
| RA | 版面：标题页 | Worker 1 | #32 |
| RB | 版面：顶部空白 | Worker 1 | #32 |
| RC | 版面：长公式 | Worker 3 | #36 |
| RD | 内容：去路径 | Worker 3、5 | #36、#35 |
| RE | 内容：英文字段中文化 | Worker 3、5、6、7 | #36、#35、#11、#34 |
| RF | 结构：合并 + 概述 + 重命名 | Worker 2、3、4、6、7 | #11、#36、#33、#11、#34 |

## 修订后字数与目录

| 编号 | 标题 | 字数 |
|---|---|---:|
| 1 | 引言 | 1,419 |
| 2 | 相关工作 | 1,630 |
| 3 | 形成性研究 | 2,289 |
| 4 | 系统概述（新） | 1,708 |
| 5 | 后端引擎（合并） | 4,953 |
| 6 | 可视分析系统设计 | 1,853 |
| 7 | 系统实现 | 883 |
| 8 | 案例研究与专家评估 | 1,624 |
| 9 | 讨论、局限与结论 | 950 |
| **合计** | | **17,309** |

正文 ≥10,000 字硬指标维持达标，结构由 11 章精简至 9 章。第二轮 6 项 rebuttal 全部回写。

---

# 第三轮 Rebuttal（建模假设与真实场景差距，2026-05-10 晚间）

用户在二轮 PDF 上给出的关键反馈：

1. CMGPD-LN 与"父系家谱"并不等同——前者是已含夫妻关系与母子/母女关系真值的辽宁清代户籍面板（即"带标注训练源 A"），后者是无婚姻 GT 的目标域 B；当前论文叙述把二者画等号，会让不熟悉数据集的读者产生关键误解
2. 当前"父系镜像消融"被表述为"等价镜像真实家谱缺失"，应改为"在 A 上构造 B 的简化代理"
3. 论文未系统提出该简化与真实场景的差距：女子入谱体例随时代变化、女性记录稀疏（参 \citep{yan2009nuzi}）、A↔B 特征对齐与跨域学习问题、一夫一妻制忽略妾室入籍

## RG — 引言与摘要：A→B 范式重构

**修订处**：`Tex/Chap_01_Intro.tex`、`Tex/Frontpages.tex`（中英文摘要正文段）。
**改动**：引言起首两段引入"带标注训练源 A"与"目标域 B"对照；贡献清单第一条"消融而不删除"补一句"该方案是 B 真实场景的简化代理"；中英文摘要弱化"以 CMGPD-LN 为实验载体"措辞，改为"以 A 上的边消融为受控代理探索 B 上的婚姻边重建"。
**字数**：Chap_01 1,419→1,556（+9.7%）；中文摘要 706→742（+5.1%）；英文摘要 273→312 词（+14.3%）。
**状态**：已修订（Worker 1 → PR #37）。

## RH — 形成性研究：访谈背景微调

**修订处**：`Tex/Chap_03_Formative.tex` §3.1、§3.2。
**改动**：CMGPD-LN 描述从泛指"历史档案"调整为"已经过婚姻边补全的亲属面板"；E5 访谈描述补一句"对女子入谱体例随时代变化的关切"，引 `\citep{yan2009nuzi}`。
**字数**：增加约 30 字（< 5%）。
**状态**：已修订（Worker 2，commit `c1fd410`，因网络 TLS 错误未推送至远端，本地已落盘）。

## RI — 后端引擎 §5.1：A→B 范式形式化 + 简化代理

**修订处**：`Tex/Chap_05_Backend.tex` §5.1 异构图建模章节。
**改动**：重写 §5.1 起首段，先给出 A（带标注训练源）与 B（目标域）的形式化对照；引入封闭性假设（B 内婚姻封闭）与特征对齐假设；明确"父系镜像消融"是 A 上构造 B 的简化代理而非等价。父系镜像消融段引 `\citep{yan2009nuzi}`，并以承接句"该简化代理相对真实场景的差距将在 \S\ref{sec:conclusion-limit} 系统讨论"指向第 9 章。
**字数**：§5.1 增加约 500 字（全章变化 < 15%）。
**状态**：已修订（Worker 3，commit `93af445`，因网络 TLS 错误未推送至远端，本地已落盘）。

## RJ — 局限性扩充 + 跨域真实迁移未来方向

**修订处**：`Tex/Chap_09_Conclusion.tex` §9.2 局限性、§9.3 未来工作。
**改动**：局限性新增 4 项（保留原有 4 项）：
- **S1（女子入谱体例）**：随时代变化，部分时期女性仅作妻子录入而不进入母家；部分时期女儿、妻、妾的特征记录极稀疏甚至仅占位（引 `\citep{yan2009nuzi}`）
- **S2（跨域学习简化）**：A↔B 特征对齐与 B 真值不暴露给 A 是真实场景核心难点；本工作仅在简化代理上做受控实验
- **S3（特征稀疏）**：CMGPD-LN 自身的收入、官职、八旗等字段记载稀疏与缺失
- **S4（一夫一妻制简化）**：MAS 协商按一夫一妻制建模，忽略妾室入籍，正室与庶出归并到正室的记载会引入"父子关系正确但母子关系不正确"等小型偏差

未来工作新增第 5 项："跨域真实迁移"——把简化代理上验证的方法移植到 A→B 真实跨域设置。
**字数**：增加约 350 字（950→1,300）。
**状态**：已修订（Worker 4，commit `2a5d891`，因网络 TLS 错误未推送至远端，本地已落盘）。

## 第三轮修订汇总

| 编号 | 类型 | 涉及单元 | 修改文件 |
|---|---|---|---|
| RG | A→B 范式（引言 + 摘要） | Worker 1 | `Tex/Chap_01_Intro.tex`、`Tex/Frontpages.tex` |
| RH | 形成性研究术语微调 | Worker 2 | `Tex/Chap_03_Formative.tex` |
| RI | 后端引擎 §5.1 形式化 + 简化代理 | Worker 3 | `Tex/Chap_05_Backend.tex` |
| RJ | 局限性 + 跨域真实迁移 | Worker 4 | `Tex/Chap_09_Conclusion.tex` |
| 协调者 | 术语与简化清单 | Phase 0 | `STYLE_BRIEF.md`（新增 §11）、`Biblio/ref.bib`（新增 `yan2009nuzi`） |

## 共修改章节清单

按用户要求"列出都修改了哪些章节的叙述"：

1. **第 1 章 引言**：起首两段引入 A/B 范式对照；贡献清单第一条补充"简化代理"措辞
2. **第 3 章 形成性研究**：§3.1 CMGPD-LN 描述微调；§3.2 E5 角色补充体例关切并引 `yan2009nuzi`
3. **第 5 章 后端引擎**：§5.1 重写为 A→B 形式化对照 + 父系镜像消融段重构为"简化代理"叙述 + 引 `yan2009nuzi` + 承接到 §9
4. **第 9 章 讨论、局限与结论**：§9.2 新增 S1–S4 共 4 项局限；§9.3 未来工作新增"跨域真实迁移"第 5 项
5. **中英文摘要**（Frontpages.tex）：弱化"CMGPD-LN 为实验载体"措辞，引入"简化代理"
6. **STYLE_BRIEF.md**：新增 §11"建模假设与真实场景差距"含强制术语与简化清单
7. **Biblio/ref.bib**：新增 `yan2009nuzi`（阎爱民《清代族谱中的女子书法》）

未触动：第 2、4、6、7、8 章；附录；Mainmatter；Style/。

