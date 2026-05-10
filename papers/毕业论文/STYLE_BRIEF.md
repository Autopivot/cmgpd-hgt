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
