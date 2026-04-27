# 1 Introduction

帝制时期的中国家谱 —— *jiapu*（家谱）—— 是晚期帝制亲属关系最大宗的现存记录，但它们在结构上系统性地偏斜：囿于父系传统，它们详细记录男性后裔，却把妻子与女儿压缩为一个姓氏字、甚或彻底略去。婚姻配偶之间的边（$r_{hw}$）以及子女与母亲之间的边（$r_{md}$、$r_{ms}$）在整个 *jiapu* 语料中要么缺失，要么仅有姓氏，要么被粗略填补 —— 而这些恰恰是重建 *母系亲属网络（maternal kinship network）* 所需要的底层结构；史家长期主张该网络在政治结盟、家户劳力分配以及婚姻市场资源在各旗之间的流动中起到中介作用 [wang2007muxia, mann2002precious]。本文要弥合的方法论缺口是：在没有任何家谱语料能自带真值的前提下，如何以一种历史学家能够辩护的方式补全这些缺失的边。我们的解法是借助另一份清代资料 —— China Multi-Generational Panel Dataset – Liaoning（CMGPD-LN，1749–1909）[cmgpd-ln-2010]，一份由辽宁旗务衙门所辖三年一造户口册编制而成的人口面板 —— 作为评测测试平台。CMGPD-LN 在覆盖六代旗人家户的 1.51 M 份观测中，编码了 62 项个人级属性，关键之处在于，它 *确实* 保留了家谱所压制的婚姻边与母系边。我们利用 CMGPD-LN 来 **模拟** 家谱补全任务：消融其 $r_{hw}$ 与 $r_{md}/r_{ms}$ 边以模仿家谱记录缺口，在被消融的图上训练，再将重建结果对照该面板（而非任何真实家谱）所保留的边来打分。最终的部署目标是真实家谱；CMGPD-LN 提供了家谱本身所不能提供的方法论验证。

具体而言，我们将重建视为一个异质社会图（heterogeneous social graph）上的受约束 link-prediction 任务，并在一种刻意设置、与家谱记录缺口相对应的测试平台消融下进行训练：在学习之前先从 CMGPD-LN 图中移除所有婚姻边与母系边，再让训练好的模型尝试将其恢复。一个 heterogeneous graph transformer [hu2020hgt] 与一个基于 SEAL 的子图模式匹配器 [zhang2018seal] 共同提供了一个有力的分布式基线。但有两点局限促成了 **[SYSTEM]**。其一，即便是经过良好调参的 HGT，在该面板上仍然呈现出我们熟悉的 ranking-vs-decision gap：在 131k 对保留对上，模型本身校准良好（ROC-AUC = 0.99，PR-AUC = 0.95），真实妻子在 53.4% 的情形下落在前 5 候选中，按队列做 Hungarian 指派可恢复 62.5% 的婚姻 —— 但 *无约束* 的 Hit@1 仍只有 32.5%，远低于历史学家敢于「看一眼即提交」的阈值。再进一步做消融对比可见，母系边在婚姻边之上贡献的边际可预测性近似为 0（相对未消融上界 Δ Hungarian recall@1 = −0.046），证实残余误差并未被图本身吸收。其二，模型本身是不透明的；一个概率分数对领域专家而言没有任何叙事抓手，也没有任何表面可供注入 *局部* 的档案证据（一个尚存的姓氏、一个旗属约束、一次 DS0003 中记录在案的 in-marriage 事件）—— 这些证据是真实家谱研究者经常掌握的，却无法编码到一个特征向量里。

[SYSTEM] 是我们对这两个缺口给出的回答。它是一个建立在 HGT+SEAL backbone 之上的六面板 visual analytics workspace，围绕单一前提构建：*一条值得提交进重建家谱的婚姻边，必须由某个 graph pattern、某段审议性叙事，或两者共同来辩护，绝不能仅凭一个黑盒分数*。为此，[SYSTEM] 将 GNN ranking 与 LLM multi-agent negotiation 耦合在一起：CMGPD-LN 测试平台上每一位达婚龄者都被注册为一个自治 persona，由其 CMGPD-DS0003 生平事件与估计收入轨迹锚定；一轮六回合、一对多、双向（one-to-many bilateral）协议在每回合的专家提示下重新为 HGT 短名单定价；一份 audit log 用一个多标签 provenance 标签（HGT、MAS，或两者）保留每一次提交。

我们将贡献概括如下：

- **一个 visual analytics workspace**，[SYSTEM]，把按队列（per-cohort）的 honeycomb embedding 视图与一个 LLM 驱动的 negotiation arena 结合起来，在 CMGPD-LN 测试平台上的 GNN link prediction 与 historian-in-the-loop 的推理之间架起桥梁，二者共享同一份队列上下文，部署目标则是真实家谱重建。
- **一个与消融设置相对应的评测装置**，直接在 CMGPD-LN 人口面板上模拟家谱记录缺口：在训练前移除全部 $r_{hw}$ 与 $r_{md}/r_{ms}$ 边，让我们能够对照该面板保留的真值来度量重建质量 —— 这是任何家谱语料自身所无法提供的基准。
- **一个六回合双向 negotiation 协议**，其最终排名遵循 $\mathrm{score}_i = \tfrac{1}{2}(s_i + t_i) - \lambda\,|s_i - t_i|$，奖励双方互评对称偏高的配对；回合之间清空（drain）提示注入，以便 human-in-the-loop 进行引导。
- **一种多标签 provenance 方案**，作用于每一条已提交边，区分 HGT 批量接受、MAS 推翻，并标注两条管线意见一致的会聚情形；通过一键 restore 支持累计错误（cumulative-error）的诊断。
