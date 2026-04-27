# 5 [SYSTEM]：Visual Analytics Design

## 5.1 系统概览

**[SYSTEM]** 以 3 列 2 行的网格布局组织六个相互链接的视图，由一台 FastAPI 服务器在后端支撑，并通过 WebSocket fan-out 向前端推送 agent 流（图 1）。前端是一个 Vue 3 + Vite 单页应用，持有一份内存中的队列上下文（cohort context），并通过共享总线（`hex-select`、`person-selected`、`match-accepted`、`match-restored`）路由选择事件。后端则缓存清洗后的 CMGPD-LN parquet、HGT 训练得到的模型 checkpoint，以及由 DS0003 派生的按人 life history。

> **图 1（题注）。** [SYSTEM] 一览。六个相互链接的视图（V1–V6）通过共享事件总线协同：V3 的 honeycomb 队列画布驱动选择；V4 展开二部细节；V5 承载六回合 agent negotiation；V2 用多标签 provenance 标签记录每一次提交；V1 跟踪运行中的 MAS recall@1 相对静态 HGT 基线的变化；V6 让分析者调整宏观特征权重与 motif 开关。每一次提交都可一键回滚。

## 5.2 V1 —— Acceptance curve 与消融诊断

最左上的面板把整个会话锚定在评测语境里。横轴按累计 *accepted-edge* 的步数推进；纵轴绘出操作员提交的 running recall@1 相对该队列已知真值的变化。一条水平参照线标出仅 HGT 的静态基线，由按队列的 Hungarian assignment 计算得到。该曲线在 `match-accepted` 与 `match-restored` 时进行响应式更新，使分析者实时看到 LLM-augmented 管线相对于 HGT-only 上限是在缩小差距还是在拉大差距。

*编码选择：* 我们使用阶梯函数而非平滑曲线，以便每一次个体提交的贡献都清晰可见；其理由是该视图同时也是一个自审计仪表（DG2）。

## 5.3 V2 —— 带多标签 provenance 的已处理配对

V2 是 *至此为止已被提交内容* 的持久化记录。每一项被接受的匹配显示为一行，携带丈夫 ID、妻子 ID、HGT score、score gap、该配对的 Hungarian-decoder 判定，以及 [SYSTEM] 的核心制品：一组 *source* chip。chip 规则如下：

- 由 V4 batch 操作产生的提交获得 chip **HGT**（sage green）。Batch 总是按 HGT score 选择丈夫的 $\arg\max$，因此该标签是无歧义的。
- 由 V5 MAS arena 产生的提交获得 chip **MAS**（amber）。如果 MAS 选定的妻子恰好与丈夫的 HGT $\arg\max$ 一致，则该行同时携带 *两个* chip，标识两条管线的会聚（convergent agreement）。

每一行末尾的 ↶ *restore* 按钮会向 `/api/negotiate/{id}/restore` 发起 HTTP `POST`，将该条目从内存中的 accept log 中移除，并在总线上广播 `match-restored`，进而触发 V1 曲线重新计算、V3 中被遮蔽的点重新显示，以及 V4 中的二部边在其所在 hex 仍处于激活态时重新进入选择集。这就是 DG5 的具体实现：单击一次即可在四个依赖视图中同步回滚一次糟糕的提交。

## 5.4 V3 —— Honeycomb embedding canvas

V3 承担 cohort-as-canvas 这一需求（DG1）。配对通过按队列的 metric multidimensional scaling 在 HGT 联合 embedding 上投影到二维，再经由一种 ASight 风格的迭代 inward-attraction packer 装入一个 flat-top 的 hex grid（同簇 hex 连续涂色，每格容量上限 12 对）。前景模式有三种：

- **`honeycomb`**：单元颜色按 mean signed score gap 编码，使用以 $\pm 2\,\text{logits}$ 为锚的发散色阶；具有不同 cluster ID 的相邻单元之间绘制簇边界。
- **`scatter`**：每对一点，使用百分位裁剪（2nd–98th percentile）后的 MDS 坐标；score-gap 色阶与 honeycomb 模式保持一致，以便跨模式可读。
- **`mixed`**：hex 透明度降到 0.55，点叠加在按单元抖动的位置上，使簇几何与单对噪声可同时阅读。

点击 hex（或一个点，或一次套索 brush）即选中相应配对，并发出 `hex-select`；V4 与 V5 随之响应。表头中的 *score gap* 发散图例（$-2 \dots +2$）使色阶不言自明。重要的是，V3 会 *遮蔽* 那些 $(h, w)$ 配对已落入 running accepted set 的点，并在 `match-restored` 时恢复其完整色阶：因此画布在任意时刻所反映的都是「还剩下什么待提交」，而非静态的 HGT 预测。

## 5.5 V4 —— 双侧丈夫–妻子细节、batch 操作与按人 profile

V4 把 V3 所选的配对展开为一个二部布局：丈夫位于左轴，候选妻子位于右轴，Bézier 边按 HGT score 加权（线条粗细加居中的 score chip）。这里设有两项操作员可用 affordance。

第一项是 *profile popup*：点击任意节点可打开，向 `/api/profile/{id}` 拉取该人在清洗后 parquet 上的属性；旗属（banner）以八旗的真实英文标签显示（如 *Solid White*），地理区域（geographic region）使用 CMGPD-LN 的四分区代码（如 *South Liaoning*）。

第二项是 *batch* 按钮，让分析者在一击之间提交所有 score gap 高于可配置阈值（默认 1.0，按 1882 队列校准至约 87% 的 precision）的丈夫的 HGT $\arg\max$。Batch 提交在 V2 中以仅 **HGT** chip 出现。点击丈夫节点还会发出 `person-selected`，V5 会接收该事件并把该丈夫加载为 negotiation target。

## 5.6 V5 —— Agent arena

V5 是 [SYSTEM] 的审议核心，也是落实 DG3 与 DG4 的表面。在加载某位丈夫之后，V5 会显示一个可折叠的 *life history* 面板，概要呈现：

- 一行 persona 标题（由 LLM 基于真实 DS0003 事件与收入产生，详见 §6）；
- 一排匹配到的 SEAL motif chip；
- 一条 event pill 条带，每个 pill 含年份与英文标签（如 1864 *Birth*、1880 *In-Marriage*）；
- 一条以阶梯式 pip（low / mid / high）渲染的收入轨迹。

下方的候选网格为 top-K 妻子各渲染一张 `CandidateCard`，每张卡片包含 persona 摘要、按回合的 score pip（`R<N>:t<X>/c<Y>`，分别对应丈夫侧得分 $t_i$ 与妻子侧得分 $s_i$），以及一个可展开的 chevron，用于查看每回合完整的问答 transcript。

网格上方的 *hint console* 接受任意自由文本消息，可寻址到 `@everyone`、`@target` 或按 ID 寻址到具体候选；提交的 hint 落入服务器端按丈夫维护的 `asyncio.Queue`，在每回合之间被清空（drained），并作为系统上下文插值进入下一回合的 prompt。

## 5.7 V6 —— Macro 与 motif 规则注入器

V6 闭合了引导回路。Macro 半区暴露一组小型滑杆（paternal-lineage importance、sibling overlap、household share、banner match、macro era），用以重新加权 SEAL motif 的预先 prior。Motif 半区为 $\mathsf{m}_1$–$\mathsf{m}_4$ 暴露四个布尔开关，让分析者从 persona prompt 中抑制特定 motif（例如，测试在没有 same-household 证据时匹配是否仍然成立）。同时还为公式 1 中的 $\lambda$ 暴露一个标量输入，便于在 gap penalty 上做敏感性探索。

## 5.8 联动交互模型

四种总线事件 —— `hex-select`、`person-selected`、`match-accepted`、`match-restored` —— 构成视图间协同的中枢（DG6）。接受流水线如下：

1. V4 batch 或 V5 final-rank 的接受动作发出 `match-accepted`；
2. V2 在表头插入新行，V1 重新加载曲线，V3 遮蔽对应的点，V4 把该边从激活选择中移除。

恢复流水线在 `match-restored` 时对称地反向执行。这种单一事实源的设计正是让 [SYSTEM] 表现为单一仪器、而非一组挂件的关键。
