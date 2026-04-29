# 3 Domain Background and Task Abstraction

## 3.1 婚姻边为何重要，又为何缺失

**目标缺口（jiapu）。** 在中国家谱（*jiapu*，家谱）中，父系（patriline）是记录的基本单位。每一位男性后裔都按世代条目进入族谱，而女性后裔通常至多在父亲条目下出现一个姓氏 —— 在许多族谱中，她一旦出嫁便被彻底略去。*mujia*（母家）—— 妻子追溯其本宗的母方家户 —— 因此成为一个在结构上不可见、但在历史上至关重要的节点：它中介政治结盟、乳母网络、旗下劳役交换以及继承纠纷 [wang2007mujia]。父系记录传统因此在源头上阻断了任何从族谱本身重建 *mujia* 的尝试：横向的亲属通道在源头层面就根本不存在。

**经验抓手（CMGPD-LN）。** 直接对照家谱进行评测因此是不可能的 —— 我们想要恢复的边正是源头所略去的。我们改用 China Multi-Generational Panel Dataset, Liaoning（CMGPD-LN，ICPSR 27063）作为测试平台。CMGPD-LN 是一份独立于家谱的清代人口与行政面板，由辽宁旗务衙门所辖、1749 至 1909 年间三年一造的户口册编制而成；*与* 家谱不同，它在保留个人 life-history 记录的同时，也保留了 $r_{hw}$ 与 $r_{md}/r_{ms}$ 边。我们在方法论上正是利用这种不对称性：从 CMGPD-LN 中消融掉 $r_{hw}$、$r_{md}$ 与 $r_{ms}$ 以模拟家谱式的记录缺口，在被消融的图上训练重建系统，再将其输出对照该面板保留下来的真值进行打分。部署目标仍然是真实家谱，那里并不存在这样的真值。

## 3.2 Stakeholders 与任务

我们与三位领域专家进行了形成性访谈（E1：清代人口史家；E2：computational genealogist；E3：digital humanities 方法论专家）。他们的工作可提炼为三项典型分析原语：

- **T1. 在某个队列年份中识别高置信度的婚姻候选**，并知悉每个候选所依托的结构性支撑（亲属 motif）。
- **T2. 裁断不确定的候选**，提供一个能够注入局部档案证据（一个姓氏、一个旗属、一次已知的 in-marriage 事件）的表面，以及一个能够审视 agent 推理过程的表面。
- **T3. 审计累计的重建结果**，包括按边的 provenance trail 与一个在错误叠加时可用的回滚机制。

## 3.3 设计目标

上述任务塑造了贯穿 **[SYSTEM]** 各视图的六项设计目标（DG1–DG6）：

- **DG1. Cohort-as-canvas.** 必须能一次性看到整个婚姻年份队列，使排名 pattern 与离群点能够与具体候选并置呈现（T1）。
- **DG2. Provenance-by-construction.** 每一条被接受的边都必须带有多标签 provenance 标签（HGT、MAS，或两者）（T3）。
- **DG3. Narrative grounding.** 每个 agent 的 persona 必须可由具体的 life-history 证据导出，而不是从模型先验中合成（T2）。
- **DG4. Steerable deliberation.** 提示必须能在不打断循环的情况下抵达 agent，并可定向到具体角色（`@target`、`@c-XX`、`@everyone`）（T2）。
- **DG5. Reversibility.** 任何提交的回溯（trace-back）都必须一键可达，所有依赖视图协调更新（T3）。
- **DG6. Tight coupling.** 任意视图中的选择都必须通过一条共享总线传播到其他视图，使整个 workspace 表现为单一仪器（T1–T3）。
