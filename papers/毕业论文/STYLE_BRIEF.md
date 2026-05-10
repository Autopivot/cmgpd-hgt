# 毕业论文撰稿规范（STYLE_BRIEF）

> 本文件由协调者在并行 worker spawn 前写入，是所有章节作者必须遵守的硬约束。
> 项目母仓库：`D:\projects\cmgpd-hgt`。论文目录：`papers/毕业论文/`。
> 模板：`Style/ucasthesis.cls`（上海科技大学本科毕业论文，基于国科大 ucasthesis）。
> 编译引擎：xelatex；引用：`\usepackage[super,myhdr,list]{Style/artratex}` 即上标顺序编码制（gbt7714）。

---

## 1. 术语表（Glossary）

下表是固定的中英对照，**章节文件中只能使用"中文"列写法**。英文列仅用于第一次出现时的中英文对照，例如"异构图变换器（Heterogeneous Graph Transformer，HGT）"。

| 中文（强制） | 英文 / 缩写 | 备注 |
|---|---|---|
| 异构图变换器 | Heterogeneous Graph Transformer / HGT | 不写"异质图""图变压器""图转换器" |
| 子图链路预测 | SEAL（Subgraph Embedding And Labeling） | 引用 `zhang2018seal` |
| 双半径节点标注 | Double-Radius Node Labeling / DRNL | 不写"双半径标号""二重半径标记" |
| 多智能体模拟 | Multi-Agent Simulation / MAS | |
| 智能体 | agent | 在 MAS 上下文中固定使用"智能体"，不写"代理"或"智体" |
| 大语言模型 | Large Language Model / LLM | |
| 图卷积网络 | Graph Convolutional Network / GCN | 引用 `kipf2016gcn` |
| 关系图卷积网络 | Relational GCN / R-GCN | |
| 链路预测 | link prediction | |
| 父系世系图 | patrilineal genealogy / 家谱 | 不写"父权家谱""父系族谱"等 |
| 母家 | mujia / 母家 | 历史档案学界沿用术语，引用 `zhao2001chinese` |
| 队列年 | cohort year | 不写"群体年""组群年" |
| 队列内负样本 | within-cohort negative | |
| 候选对 | candidate pair | (man, woman) 二元组 |
| 来源标记 | provenance chip | UI 上的小色条 |
| 蜂窝画布 | honeycomb canvas | View C 主体 |
| 多维标度法 | Multi-Dimensional Scaling / MDS | |
| 边消融 | edge ablation | 不写"边剥离""边删去" |
| 嵌入空间 | embedding space | |
| 元数据快照 | metadata snapshot | `graph.metadata()` 调用所返回的图元信息 |
| 形成性研究 | formative study | 不写"探索性研究""前期访谈""前置研究" |
| 设计目标 | Design Goal / DG1–DG6 | |
| 时间因果子图 | temporal subgraph at year *t* | 形式定义 \(G_t\)：所有 \(\text{edge\_time}<t\) 的边 |
| 八旗 | Eight Banners | |
| 旗内婚 | banner endogamy | |
| 中国多代人口面板 | China Multi-Generational Panel Dataset / CMGPD-LN | 引用 `campbell2011data` |
| 注意力机制 | attention mechanism | 引用 `vaswani2017attention` |
| 思维链 | Chain-of-Thought / CoT | 引用 `wei2022cot` |
| 生成式智能体 | generative agent | 引用 `park2023generative` |
| 混合主动 | mixed-initiative | 引用 `green2009mixedinitiative` |
| 知识生成模型 | knowledge generation model | 引用 `sacha2014knowledge` |

## 2. Label 命名空间

下面是已经在协调者层面预先约定的 label，章节作者按需引用：

### 章节 label

| 章 | label |
|---|---|
| 1 引言 | `chap:intro` |
| 2 相关工作 | `chap:related` |
| 3 形成性研究 | `chap:formative` |
| 4 数据与图建模 | `chap:data` |
| 5 HGT 编码器与婚姻评分 | `chap:hgt` |
| 6 SEAL 子图模式提取 | `chap:seal` |
| 7 多智能体协商协议 | `chap:mas` |
| 8 可视化系统设计 | `chap:vis` |
| 9 系统实现 | `chap:impl` |
| 10 案例研究与专家评估 | `chap:case` |
| 11 讨论与结论 | `chap:conclusion` |

### 图 label（已存在或建议）

| label | 文件 | 出处 |
|---|---|---|
| `fig:framework` | `figures/Framework.pdf`（已存在） | VIS 论文系统总体两阶段框架图 |
| `fig:system` | `figures/system.pdf`（已存在） | VIS 论文 6 视图 teaser |
| `fig:hex-canvas` | （建议复用 system.pdf 的 C 子图） | 嵌入视图蜂窝画布 |
| `fig:mas-arena` | （建议复用 system.pdf 的 E 子图） | MAS 协商竞技场 |

> 注意：现有 `figures/` 目录在 `papers/VIS_SHORT_Genealogy/figures/`，但毕业论文模板的 `Img/` 目录不同。worker 不需要复制图片，可在 .tex 中暂以 `\includegraphics[width=0.9\linewidth]{Framework}` 引用，由协调者在 Phase 2 统一拷贝。

### 表 label

| label | 出现位置（章节） |
|---|---|
| `tab:cmgpd-stats` | 第 4 章 数据集规模 |
| `tab:edge-types` | 第 4 章 9 种边类型 |
| `tab:features` | 第 5 章 PersonEmbedder 输入流 |
| `tab:hyperparams` | 第 5 章 训练超参 |
| `tab:motif-catalog` | 第 6 章 13 motif |
| `tab:agent-rounds` | 第 7 章 六轮协商角色 |
| `tab:hint-routing` | 第 7 章 提示路由语义 |
| `tab:six-views` | 第 8 章 视图 A–F |
| `tab:expert-likert` | 第 10 章 Likert 评分 |

### 公式 label

| label | 含义 | 来源 |
|---|---|---|
| `eq:embedder` | PersonEmbedder 拼接 | VIS 注释 545 |
| `eq:hgt-att` | HGT 注意力 | VIS 注释 566 |
| `eq:hgt-upd` | HGT 节点更新 | VIS 注释 574 |
| `eq:scorer` | Marriage Scorer logit | VIS 注释 590 |
| `eq:loss` | BCE 训练损失 | VIS 注释 611 |
| `eq:final-score` | MAS 最终得分 | VIS 正文 159 |
| `eq:drnl` | DRNL 标号 | SEAL 论文 |
| `eq:rgcn-update` | R-GCN 卷积更新 | seal/REPORT.md |

### 算法 label

| label | 含义 |
|---|---|
| `alg:negotiation` | 六轮 MAS 协商伪代码 |
| `alg:packer` | 蜂窝画布内向吸引装填算法 |

## 3. 引用风格

模板采用 **上标顺序编码制（super）**。worker 一律使用 `\citep{key}`（括号上标）和 `\citet{key}`（文本带上标），不使用 `\cite{key}` 裸调用。

- 单条：`\citep{hu2020hgt}`
- 多条：`\citep{hu2020hgt, zhang2018seal, kipf2016gcn}`
- 中文文献额外要求 `key={Pinyin Author Year}` 字段以便排序（已在 ref.bib 模板示例中演示）

新增条目规则：

- worker 严禁直接修改 `papers/毕业论文/Biblio/ref.bib`
- worker 须将本章新条目追加到自己的 `papers/毕业论文/Biblio/refs_chapNN.bib`（NN 是 01..11 的两位数字）
- 协调者在 Phase 2 把所有 `refs_chapNN.bib` 合并去重进 `ref.bib`

## 4. 章节字数与重要级

| 章节 | 重要级 | 目标字数 | 目标页数 |
|---|---|---|---|
| 1 引言 | M | 1,200 | 2.5 |
| 2 相关工作 | M | 1,400 | 3 |
| 3 形成性研究 | **H（重点扩充）** | 2,000 | 4 |
| 4 数据与图建模 | M | 1,300 | 2.5 |
| 5 HGT 编码器与婚姻评分 | **H（重点扩充）** | 2,000 | 4 |
| 6 SEAL 子图模式提取 | **H（重点扩充）** | 1,800 | 3.5 |
| 7 多智能体协商协议 | M | 1,400 | 3 |
| 8 可视化系统设计 | M | 1,400 | 3 |
| 9 系统实现 | M | 800 | 1.5 |
| 10 案例研究与专家评估 | M | 1,200 | 2.5 |
| 11 讨论与结论 | L | 700 | 1.5 |
| **合计** | | **15,200 字 / 30 页** | |

字数按汉字 + 标点（不含空格）粗略估算；公式、图表、伪代码不计入。worker 应将章节正文压在目标字数 ±15% 区间内。

## 5. 写作约束（强制）

- **学术中文**：第三人称为主，避免连续以"我们"开头；公式中文行文以"上式""其中""易知"等过渡；段落以连接性副词（"具体而言""值得注意""综上所述"）适度承接
- **严禁造词**：术语表外的 4 字以上自造名词组合一律不允许；英文专有名词第一次出现给"中文（English，缩写）"对照，之后用中文
- **严禁虚假宣称**：所有数字必须能在 `src/`、`seal/REPORT.md`、`papers/VIS_SHORT_Genealogy/paper.tex`（含注释段）中找到来源
  - HGT：Hit@10 = 0.624，MRR = 0.428，recall@1 提升 62.6%（来自 VIS 正文 147 与注释 1004–1011）
  - SEAL：Hit@1 = 0.975，MRR = 0.984，参数量 97,889，80 query 测试集，父亲缺失消融 Hit@1 = 0.429（来自 `seal/REPORT.md`）
  - 专家研究：n=5、Usefulness=6.0(0.71)、Interpretability=6.0(0.71)、Trust in MAS-only=5.0(1.00)（来自 VIS 注释 1066–1077）
  - HGT 超参：HIDDEN=128、NUM_LAYERS=2、HEADS=4、DROPOUT=0.2、AdamW lr=1e-3、wd=1e-2、BATCH_YEARS=4、NEG_PER_POS=4、grad clip=1.0、30 epochs（来自 `src/config.py`）
  - 数据集：CMGPD-LN，1,513,357 条 person-year 记录（VIS 注释 974）；约 266,091 person 节点 / 85,538 婚姻；时间跨度 1749–1909
  - 关于"约 9,500 LOC"：来自 VIS 注释 939
- **严禁编造作者、致谢内容、答辩日期、个人邮箱**等隐私／空白信息；`Frontpages.tex` 中作者、学号、入学年、指导教师等字段保持现有占位符或留空，不要替换为任何具体姓名。`Backmatter.tex` 致谢章节正文整段删除/留空（保留 `\chapter{致\quad 谢}\chaptermark{致\quad 谢}`）
- **图片占位**：worker 在自己的 .tex 中可以使用形如 `\includegraphics[width=0.9\linewidth]{Framework}` 的引用，无须实际拷贝图片；协调者在 Phase 2 集成时统一调整路径
- **公式引用**：使用 `\eqref{eq:xxx}` 而非 `(\ref{eq:xxx})`，`\cref` 仅在 worker 已 `\usepackage{cleveref}` 时使用——简单起见，worker 直接用 `\eqref` / `\ref`
- **章节内不要写 `\bibliography{}` 或 `\bibliographystyle{}`**：这两个命令只在 `Thesis.tex` 主文件出现一次

## 6. 交付与提交

每个 worker 完成后：

1. 仅提交本章 `Tex/Chap_NN_*.tex` 与可选 `Biblio/refs_chapNN.bib`
2. 不修改 `STYLE_BRIEF.md`、`ref.bib`、`Mainmatter.tex`、`Frontpages.tex`、`Backmatter.tex`、`Thesis.tex`、`Style/`、`Img/`
3. commit 标题：`paper(thesis): 第 NN 章 <章名> 初稿`
4. 一行报告：`PR: <url>` 或 `PR: none — <reason>`

协调者负责 Phase 2 集成、Phase 3 自审 rebuttal、Phase 4 PDF 编译与交付。

---

# v2 增补（rebuttal 第二轮，2026-05-10）

第一轮交付后用户给出评审意见，对叙述风格与版面提出新约束。下列 §7–§10 与 §1–§6 同等强制。冲突时以本节较新规则为准。

## §7 路径与扩展名禁令

下列字符串 **不得出现在任何章节正文** 中（公式与算法伪代码内的极少量符号除外，且需先与协调者评估必要性）：

- 路径片段（含尾斜杠）：`src/`、`server/`、`viz-mas/`、`seal/`、`data/`、`papers/`、`checkpoints/`、`Tex/`、`Biblio/`、`Style/`、`Img/`
- 文件扩展名：`.rda`、`.json`、`.parquet`、`.tex`、`.pt`、`.csv`、`.gz`、`.py`、`.bib`、`.bat`、`.sh`、`.cls`、`.sty`、`.md`、`.mp4`、`.svg`、`.eps`

如必须指代某模块层，统一使用：
- "数据与模型层"代替 `src/`
- "后端服务层"代替 `server/`
- "前端界面层"代替 `viz-mas/`
- "子图模式提取模块"代替 `seal/`
- "数据缓存目录"代替 `data/processed/...`
- "训练快照"代替 `checkpoints/best.pt`
- "超参集中文件"代替 `src/config.py`

## §8 英文字段中文化对照表（强制替换）

下表左列在正文中 **不得直接出现**，必须替换为右列。首次出现外部专有名词时可以"中文（English）"对照，之后只用中文：

| 原英文标识 | 中文替换 |
|---|---|
| `x_sex` / `SEX` | 性别字段 / 性别向量 |
| `x_relationship` / `RELATIONSHIP` | 关系字段 / 关系嵌入 |
| `x_continuous` / `BIRTHYEAR` | 连续特征 / 出生年 |
| `x_occupational` / `POSITION` / `TITLE` / `SALARY` | 任职特征 / 官职、品阶、俸禄三项指示位 |
| `x_macro` | 宏观协变量 |
| `RECORD_NUMBER` | 记录编号 |
| `EVENT_1` / `EVENT_2` | 第一事件代码 / 第二事件代码 |
| `FATHER_ID` / `MOTHER_ID` / `HOUSEHOLD_ID` / `PERSON_ID` | 父亲编号 / 母亲编号 / 家户编号 / 个体编号 |
| `PersonEmbedder` | 人物嵌入器 |
| `subgraph_at_year` | 时间因果子图构造函数 |
| `BATCH_YEARS` | 批队列年数 |
| `NEG_PER_POS` | 每正例负样本数 |
| `HGTConv` | 异构图卷积层 |
| `asyncio.gather` / `asyncio.Event` / `asyncio.Queue` | 并行调度原语 / 推进信号 / 提示队列 |
| `DASHSCOPE_API_KEY` | 大模型服务凭证 |
| `qwen-plus-2025-04-28` | 千问 Plus 模型（具体版本） |
| `event_value_labels.json` | 事件代码翻译词典 |
| `macro_table` | 宏观协变量查找表 |
| `Apache Parquet` | 列式存储 |
| `WebSocket` | 流式通信通道 |
| `FastAPI` | 后端服务框架 |
| `Vue 3 + Vite` | 前端组件框架 |
| `mitt` / `Pinia` | 事件总线库 / 状态管理库 |

## §9 章节合并约束（新章节标签命名空间）

第二轮修订 **不再使用** 下列旧标签：`chap:data`、`chap:hgt`、`chap:seal`、`chap:mas`。它们一律合并为 `chap:backend`，下设 4 个子节标签：
- `sec:backend-graph`（旧 chap:data 内容）
- `sec:backend-hgt`（旧 chap:hgt 内容）
- `sec:backend-seal`（旧 chap:seal 内容）
- `sec:backend-mas`（旧 chap:mas 内容）

新章节目录标签如下：

| 编号 | 标题 | 章节标签 |
|---|---|---|
| 1 | 引言 | `chap:intro` |
| 2 | 相关工作 | `chap:related` |
| 3 | 形成性研究 | `chap:formative` |
| 4 | **系统概述** | `chap:overview`（新） |
| 5 | **后端引擎** | `chap:backend`（合并） |
| 6 | 可视分析系统设计 | `chap:vis` |
| 7 | 系统实现 | `chap:impl` |
| 8 | 案例研究与专家评估 | `chap:case` |
| 9 | 讨论、局限与结论 | `chap:conclusion` |

跨章引用的迁移规则：
- 任何 `\ref{chap:hgt}` / `\ref{chap:data}` / `\ref{chap:seal}` / `\ref{chap:mas}` → 改为 `\ref{chap:backend}`
- 任何 `\ref{sec:ablation}`（原 chap:data 内）→ 改为 `\ref{sec:backend-graph}`

## §10 叙述风格指引（参考本科毕业论文规范）

本论文是工科本科毕业论文，非学术会议短论文。叙述应：
- 先说"为什么这样设计"（动机、用户需求、设计目标）；再说"具体怎么做"（核心方法、关键参数、关键公式）；最后说"做完后的效果或衔接到下游"（量化指标 / 章节衔接）
- 每节 3–6 段，每段 3–6 句；避免过长段落
- 不逐一罗列代码符号；不直贴 API 名；不展开实现细节超过两行
- 公式只在必要处给出（HGT 注意力、HGT 节点更新、婚姻评分、损失、双半径标号、关系图卷积、最终评分），其余只用文字描述
- 尽量减少表格层数；超过三层嵌套的表格改为段落式叙述
- 中英文混排时，英文专有名词括注一次后即弃用；不出现 `\texttt{...}` 包裹的英文 token（公式内或算法伪代码内除外）

## §11 建模假设与真实场景差距（rebuttal r3 增补）

第三轮评审指出当前论文把 CMGPD-LN 与"父系家谱"画等号，并把"母系边消融"作为对真实家谱缺失模式的等价镜像，会让读者产生关键误解。本节给出修订后的统一术语与简化清单。

### §11.1 建模术语（强制使用）

| 术语 | 含义 |
|---|---|
| 带标注训练源 A | 指 CMGPD-LN，作为辽宁清代户籍面板已记载夫妻关系与母子/母女关系，是父系登记经历婚姻边补全后的亲属网络。包含完整婚姻边真值 |
| 目标域 B | 指真实田野家谱的集合。父系单线编纂，无婚姻边真值，孤立树森林 |
| 封闭性假设 | B 内男性与 B 内女性穷尽对应，即不存在 B 内男性与 B 外女性的婚姻；这是本工作做出的简化假定 |
| 特征对齐假设 | B 与 A 的人物特征空间一致或可线性对齐；这是本工作做出的简化假定 |
| 父系镜像消融 | 在 A 上对母系边类型 \(r_{ms}, r_{md}\) 与目标年婚姻边 \(r_{hw}\) 实施"消融而不删除"，构造 B 真实场景的**简化代理**——并非等价 |
| 简化代理 | A 经父系镜像消融后形成的图，可让模型在受控条件下学到对 B 类场景有意义的结构信号；不主张"代理 ≡ B" |

### §11.2 简化清单（行文中需系统提及）

下列四条简化必须在第 9 章局限性中显式给出，并在主流叙述中至少一处指明这是简化而非等价。

- **S1（女子入谱体例）**：女子入谱体例随时代变化。部分时期女性仅以妻子身份录入而不进入母家谱系；部分时期女儿、妻、妾的特征记录极稀疏，甚至仅为占位姓氏。引 `\citep{yan2009nuzi}`（阎爱民《清代族谱中的女子书法》，《中国社会历史评论》2009）作为依据
- **S2（跨域学习简化）**：真实情况下 A 与 B 的特征不对齐、B 的真值完全不暴露给 A——这是一个跨域图学习问题。本工作做了简化（在 A 上做受控代理实验），未直接求解 A→B 的真实跨域迁移
- **S3（特征稀疏）**：CMGPD-LN 自身的收入、官职、八旗等字段在不同年份与不同人群上记载稀疏与缺失，本工作以零值与缺失掩码处理，但稀疏样本上的判据仍偏弱
- **S4（一夫一妻制简化）**：MAS 协商按一夫一妻制建模，忽略妾室入籍。当庶出子女在记载上归并到正室时，会引入"父子关系正确但母子关系不正确"的小型偏差

### §11.3 引用规范

第 5 章 §5.1 父系镜像消融段（首次出现 \(r_{ms}, r_{md}\) 消融的位置）与第 9 章 S1 局限项至少各引 `\citep{yan2009nuzi}` 一次。bib key `yan2009nuzi` 已在 `Biblio/ref.bib` 中。



