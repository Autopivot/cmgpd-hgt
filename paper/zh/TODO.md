# 论文 TODO —— 虚构内容审计 + 替换计划

本文件清点 `paper/` 当前所有的虚构数字、虚构叙事、占位引用与表述过强之处，并为每一条给出对应的替换实验任务。标 **EN+ZH** 的条目意味着英文版与中文版必须同步修改。

最近一次审计：基于 `feat/v5-unit4-real-qwen` 上的 commit `e7dcede`。

---

## A. 完全虚构的研究材料（需要真实工作才能补救）

### A1. §3.2 的 formative interviews —— 从未发生

- **声明**："We held formative interviews with three domain experts (E1: Qing demographic historian; E2: computational genealogist; E3: digital-humanities methodologist)."
- **实情**：根本没做过访谈。E1/E2/E3 是为了支撑 T1–T3 与 DG1–DG6 而虚构出来的人物。
- **替换路径**：
  - **（真做）** 招募三位真实专家（一位历史学家、一位计算家谱学家、一位 DH 方法学家），做 30 分钟半结构化访谈，转录、抽取分析原语。
  - **（绕过）** 重写 §3.2，删去 E1/E2/E3 的人物归属，把 T1–T3 / DG1–DG6 改写为「源自系统设计意图的方法论假设」而非「形成性访谈输出」。
- **涉及文件**：`paper/03_domain_background.md`、`paper/zh/03_domain_background.md`。**EN+ZH**。

### A2. §9 expert study 整章是虚构的

- **声明**：
  - "75-minute semi-structured walkthrough with five domain experts" —— 没发生。
  - 三个维度的 Likert 中位数（usefulness / interpretability / trust）= 6 / 6 / 5 —— 编造。
  - "restore was clicked 14 times, of which 9 led to a re-deliberation" —— 编造。
  - 三段定性观察 —— 编造。
- **替换路径**：
  - **（真做）** 至少招募 n ≥ 3 位真实专家做用户研究，录音、按 7 点 Likert 打分、统计 restore 点击。这是 IEEE VIS 全文必须的部分；评审会查。
  - **（绕过）** 删除 §9，把 §8 用例研究扩写为论文主要的实证评估。投短论文（4 页）走这条路是可接受的。
- **涉及文件**：`paper/09_expert_study.md`、`paper/zh/09_expert_study.md`。**EN+ZH**。

---

## B. 虚构但**可以**用现有代码 / 数据实测替换（高价值任务）

### B1. §8.1 用例 UC1 的具体叙事

- **声明**："8-husband bipartite, all with score gaps above 2.0"、"7 of 8 husbands committed"、"income trajectory that flattened in 1879"、"single Lost event in 1881"、"negotiation converges on a different wife than HGT's argmax"、"Both HGT and MAS chips appear"。
- **替换路径**：用真实仪表板跑一次端到端 session（1882 队列）：
  1. 在 V3 选一个 hex，记录 V4 实际 husband 数与真实 score-gap 分布。
  2. 点 *batch*，记录实际提交数。
  3. 对剩下的 husband 调 `GET /api/narrative/{id}?year=1882`，引用 DS0003 中真实存在的 events / income。
  4. 跑 V5，记录 LLM 收敛到的 wife 是否真的不同于 HGT argmax；报告实际出现的 chip 集合。
- **预计工时**：1–2 小时（一次现场录制）。
- **涉及文件**：`paper/08_use_cases.md`、`paper/zh/08_use_cases.md`。**EN+ZH**。

### B2. §8.2 用例 UC2 的具体叙事

- **声明**："honeycomb geometry shifts visibly: score gap distribution tightens, cluster boundaries reorganise around banner co-membership"、"suppress m4 → match changes"。
- **替换路径**：在同一 cohort 的 `ablated` 与 `unablated` 两种状态下分别截图 V3，并量化几何位移（如均簇紧凑度、score-gap 标准差）；然后在 V6 切换 m4 开关，对至少一个 husband 跑两次 V5，看 winner 是否真的发生改变。
- **预计工时**：30 分钟。
- **涉及文件**：同 B1。

### B3. §8.3 用例 UC3 的具体叙事

- **声明**："wife's surname is *Wang*"、"candidates whose surname does not match are surfaced with reduced t_i scores"、"final commit's chip shows MAS-only"。
- **替换路径**：选一位真实的 1885 husband，其真值 wife 在 DS0001 中有可恢复的姓氏字段（先核实）。跑提示注入流程，引用 round-2 面板中真实出现的 query / answer 文本；报告 V2 上实际出现的 chip 集合。
- **预计工时**：1 小时（需要 `DASHSCOPE_API_KEY`）。
- **涉及文件**：同 B1。

### B4. §5.5 V4-batch 精度 "≈ 87%" —— 可以严格实测

- **声明**："default 1.0, calibrated to ≈ 87% precision on the 1882 cohort." 该数字向上传染至 §0（abstract）、§1（intro）作为 operator-acceptance precision。
- **替换路径**：5 行脚本：
  ```python
  import json
  c = json.load(open('viz/data/cohort_1882.json'))
  by_h = {}
  for p in c['pairs']:
      cur = by_h.get(p['husband_id'])
      if not cur or p['score'] > cur['score']:
          by_h[p['husband_id']] = p
  for thr in [0.5, 1.0, 1.5, 2.0]:
      batch = [p for p in by_h.values() if p['score_gap'] >= thr]
      prec = sum(p['label'] == 1 for p in batch) / max(len(batch), 1)
      print(f'gap>={thr}  N={len(batch)}  precision={prec:.3f}')
  ```
  对全部 6 个 cohort（1882、1885、1888、1903、1906、1909）重复，绘出 precision–coverage 关于阈值的曲线。把单一 `≈ 0.87` 替换为实测曲线或按队列的精度表。
- **预计工时**：30 分钟（含写入）。然后向以下文件传播：
  - `paper/00_abstract.md` —— "raising operator-acceptance precision to `≈ 0.87`"
  - `paper/01_introduction.md` —— 同上
  - `paper/05_visual_design.md` §5.5 —— 同上
  - 以及三处 Chinese 镜像。
- **涉及文件**：`paper/00_abstract.md`、`paper/01_introduction.md`、`paper/05_visual_design.md`，加三处 `paper/zh/*` 镜像。**EN+ZH**。

### B5. §6.2 / §10 negotiation wall-clock "30–45 s"

- **声明**："A six-round real-Qwen negotiation for six candidates costs roughly 30–45 s on the DashScope endpoint."
- **替换路径**：在 `negotiator_rounds.mas_negotiate_rounds` 里加 `time.perf_counter()` 计时；跑 5 个 husband；报均值 ± 标准差，并按轮拆分（round-1 personas vs. rounds 2–5 query/answer）。在 §10 加入这张表。
- **预计工时**：30 分钟（含写入）。
- **涉及文件**：`paper/06_mas_protocol.md`、`paper/10_discussion.md`，加两处中文镜像。**EN+ZH**。

### B6. §7 LOC 统计 "≈ 9.5 k LOC"

- **声明**："≈ 9.5 k LOC: pipeline 2.4k + backend 2.1k + frontend 5.0k."
- **替换路径**：`cloc src/ viz-mas/server/ viz-mas/src/`。把估值替换为实测值。
- **预计工时**：5 分钟。
- **涉及文件**：`paper/07_implementation.md`、`paper/zh/07_implementation.md`。**EN+ZH**。

---

## C. 表述过强的技术声明（需要降级或真实现）

### C1. §4.5 SEAL motif extraction

- **声明**："We extract the *enclosing k-hop subgraph* … and apply Double-Radius Node Labelling (DRNL) to obtain a structural fingerprint $\phi(\mathcal{N}_k(m,w)) \in \mathbb{N}^{|\mathcal{N}_k|}$"
- **实情**：`viz-mas/server/mas/motif_matcher.py` 实际是**纯启发式字段比对** —— banner 相等（m4）、household 相等 / lineage 接近（m3）、patri_path_count 阈值（m1、m2）。**根本没抽 enclosing subgraph，也没跑 DRNL 标号。**
- **替换路径**：
  - **（降级，约 15 分钟）** 老老实实改写 §4.5：「我们用四个领域驱动的启发式 —— 同旗、同户、父系路径长度阈值 —— 作为 motif 标签，把 SEAL 风格的 enclosing-subgraph 抽取留作未来工作。」
  - **（真实现，1–2 天）** 实际实现 k-hop enclosing-subgraph 上的 DRNL 标号；PyG 已提供 SEAL example 作参考。把每个 exemplar 表示为带标号的子图，用规范形式匹配（Weisfeiler–Lehman 或在 k=2 小邻域上做图同构检查）。
- **涉及文件**：`paper/04_computational_backbone.md`、`paper/zh/04_computational_backbone.md`。**EN+ZH**。

### C2. §7 / §10 LLM 模型名

- **声明**："DashScope endpoint at `qwen-plus-2025-04-28`"
- **实情**：当前会话中后端的 `/api/llm_config` 报告 live model 是 `qwen3.6-plus`。`agent.py` 默认值是 `qwen-plus-2025-04-28`，但 `set_config` 可能覆盖了它。
- **替换路径**：跑一次 `curl http://127.0.0.1:8001/api/llm_config`，报实验真正生效的模型名。如果不同实验用了不同模型，两者并列。
- **预计工时**：1 分钟。
- **涉及文件**：`paper/07_implementation.md`、`paper/10_discussion.md`，加两处中文镜像。**EN+ZH**。

---

## D. 引用占位符（每一条都需要核实）

`paper.bib` 与正文中的所有 `[CITATION:KEY]` 都是未经核实的占位。**AI 生成的 BibTeX 有约 40% 的错误率；切勿直接复制进投稿。** 提交前必须对每一条用 Semantic Scholar + Crossref 程序化校验。

| Key | 论文中代指的内容 | 替换路径 |
|---|---|---|
| `cmgpd-ln-2010` | CMGPD-LN ICPSR 27063 数据集描述 | DOI 10.3886/ICPSR27063 + Lee & Campbell 描述论文 |
| `wang2007muxia` | 母家史学 | 占位 —— 需找一篇关于 母家 在晚期帝制中国史中的同行评议工作 |
| `mann2002precious` | 晚清女性史 | 极可能是 Mann *Precious Records* (1997) —— 需核实年份与来源 |
| `hu2020hgt` | HGT —— Heterogeneous Graph Transformer | WWW 2020；可程序化拉 DOI |
| `zhang2018seal` | SEAL link prediction | NeurIPS 2018；可获取 |
| `park2023generative` | Generative Agents | UIST 2023（Park、O'Brien、Cai、Morris、Liang、Bernstein） |
| `abdelnabi2023negotiation` | LLM negotiation / preference elicitation | 占位 —— 需选定具体论文 |
| `endert2014mixed` | mixed-initiative visual analytics | 占位 —— 需核实是 Endert 哪篇 |
| `vis-prosopography` | 面向 prosopographical archive 的 VA | 完全占位 —— 需找一篇真实论文 |
| `vis-link-prediction-confidence` | 面向 link-prediction 置信度的 VA | 完全占位 —— 需找一篇真实论文 |

**预计工时**：9 条总计约 90 分钟（用 Exa MCP / Semantic Scholar API + DOI → BibTeX）。
**涉及文件**：`paper/references.bib`（或 bib 实际所在位置），以及全文中的 `[CITATION:KEY]` 标记。

---

## E. 已核实准确（无需操作）

为完整起见列在此处，未来再审计时不需要重复检查：

- §1 Hit@10 = 0.624、MRR = 0.428、Hit@1 = 0.325、Δ Hungarian@1 = −0.047 —— `runs/20260427_191523_ablated/metrics.json` 实测。
- §4.1 graph schema、九种边类型、jiapu-mirroring ablation —— 与 `config.py` 与 `stage2_split.py` 一致。
- §4.2 feature engineering（sex Embed(3,8)、rel Embed(64,16)、continuous=BIRTHYEAR、occupational=3、macro=5；household=5、community=1、banner=one-hot）—— 与 `stage1_features.py` 一致。
- §4.3 HGT 超参（HIDDEN=128、NUM_LAYERS=2、HEADS=4、DROPOUT=0.2）—— `config.py` 实读。
- §4.4 训练配方（BATCH_YEARS=4、NEG_PER_POS=4、AdamW η=1e-3、wd=1e-2、grad-clip=1.0、30 epoch、双 checkpoint）—— `config.py` + `train.py` 实读。
- §4.6 最终得分公式 `(s+t)/2 − 0.3·|s−t|` —— `negotiator_rounds.LAMBDA_GAP = 0.3`。
- §5.4 V3 算法（联合 PCA(50) + MDS、X-means、2nd–98th 百分位裁剪、R=0.04、odd-q 网格、容量 12、MAX_INWARD=50 / MAX_OUTWARD=200、向心折半步长、外向螺旋 angle += 0.7、半径每 8 步 +2R、$\pm 2$ logits 三段式发散色阶、`#993c1d / #f5f1e8 / #0f6e56`、$2\sigma$ stripe 阈值、$\varepsilon = 10^{-6}$ 顶点匹配）—— 已逐行对照 `viz/data/precompute.py`、`viz-mas/src/canonical/cluster_layout.js`、`viz-mas/src/canonical/honeycomb_render.js`。
- §6 round 标签（persona / impressions / deep-dive / rebuttals / alignment / final）、`@everyone` / `@target` / `@c-XX` 路由、`asyncio.Event` 暂停、per-call try/except 启发式回退 —— 与 `negotiator_rounds.py` 一致。
- §7 DS0003 ↔ DS0001 RECORD_NUMBER 1:1 join 跨 1,513,357 行 —— 已实测。
- §5.7 V6 亲属邻域图（$k=1$ 仅 person 节点的 ego 并集，边集 $\{r_{fs}, r_{fd}, r_{ms}, r_{md}, r_{sib}\}$；丈夫绿色 $r=9$、候选琥珀 $r=8$ 带描边、其他亲属浅灰 $r=5$；父系实线、母系虚线、兄弟姐妹点线；接受时新增 $r_{hw}$ 用 `#993c1d` stroke 宽 2；d3-force link≈30 / charge≈−80、拖拽钉住并双击解除、鼠标滚轮缩放范围 $[0.3, 4]$；`match-accepted` 时 200 ms 过渡淡至 opacity 0.25，`match-restored` 时还原）—— 与 `viz-mas/src/components/RulerInjectorView.vue` 及 `AgentBattleView.vue` 发出的 `cohort-context` 契约一致。

---

## 推荐执行顺序（按收益 / 成本比降序）

| 优先级 | 任务 | 工时 | 当下做的理由 |
|---|---|---|---|
| 🔴 P0 | A2 —— 删除 §9 expert study **或** 启动真实研究 | 30 分钟（删）/ 2 周（真做） | 不处理则有学术不端风险 |
| 🔴 P0 | C1 —— SEAL 声明降级为 heuristic | 15 分钟 | 方法诚实性 |
| 🟠 P1 | B4 —— 实测 V4-batch 精度并向上传播 | 30 分钟 | 一次修正 abstract / intro / §5.5 |
| 🟠 P1 | D —— 程序化核实 9 条 BibTeX | 90 分钟 | 否则有 desk-reject 风险 |
| 🟡 P2 | B1–B3 —— 用真实 session 替换 UC1/UC2/UC3 | 3–4 小时 | 让 case study 可被评审重放 |
| 🟡 P2 | B5 —— 实测 negotiation wall-clock | 30 分钟 | 把估值改成实测 |
| 🟢 P3 | B6 —— 真实 `cloc` 计数 | 5 分钟 | 小但白送 |
| 🟢 P3 | C2 —— 确认 live Qwen 模型名 | 1 分钟 | 平凡 |
| 🟡 大工程 | A1 —— 真实 formative interviews **或** 重写 §3.2 | 1 周（真做）/ 30 分钟（重写） | 比 A2 弱 —— DG 是可从系统推导的 |

### 最小可信增量（auto-mode 友好）

如果只能花约 2 小时，按 单位时间可信度提升 排序的最佳路径是：

1. **B4** —— 把 `87%` 精度声明替换成实测的 precision-vs-threshold 表。
2. **C1** —— §4.5 老老实实改写（启发式 motif tags，SEAL 留作未来工作）。
3. **A2** —— 直接删除 §9，把 §8 用例研究升格为主要的实证评估。
4. **B1–B3** —— 录三段真实仪表板 session，引用真实事件 / 收入 / chip 结果。

执行完上述四步后，论文中将无任何虚构数字，只剩一个结构性遗漏（没有正式的用户研究），可在 limitations 一节诚实标出。
