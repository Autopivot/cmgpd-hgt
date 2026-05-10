# 2 Related Work

**Visual analytics for relational and historical archives.** 面向传记或历史数据的网络补全可视化长期以来都将 edge-uncertainty 提示与 mixed-initiative 探索结合起来。早期面向 prosopographical 档案的系统主要呈现共现与时间流信号 [vis-prosopography]，而更近期的工作把 link prediction 视为分析的基本单元，并研究分析者如何回应模型置信度 [vis-link-prediction-confidence]。**[SYSTEM]** 沿两条轴线推进这一脉络：它明确地以基于 GNN 的 ranking 作为开始探索的入口，并将 LLM agent transcript 作为一个一等公民的证据层，而非外部的解释工具。

**Heterogeneous graph learning and link prediction.** Heterogeneous graph transformer [hu2020hgt] 将注意力机制扩展到带类型的关系上，至今仍是多关系 link prediction 任务上一条颇具竞争力的基线。闭环式标注子图方法 —— SEAL [zhang2018seal] 及其扩展 —— 把支撑某次预测的局部结构 pattern 显式呈现出来。我们将这两者作为 backbone，但本工作的贡献并不在架构层面；我们更多是把它们的输出当作 *prior*，再交给一群基于 LLM 的 agent 去审议。

**LLM agents and multi-agent simulation.** 近期工作把 LLM-based agent 视为审议单元 [park2023generative]，并提出了能够呈现 persona-grounded 推理的 negotiation 与 preference-elicitation 协议 [abdelnabi2023negotiation]。我们沿这条线继续，但将其专门化：agent 由从 DS0003 中抽取的 life-history 证据来播种（事件来自 `EVENT_1/2`，收入来自 `ESTIMATED_INCOME`），并附加 HGT 的预打分与 SEAL motif 标签，使每一回合既有叙事来源，也有结构来源。

**Mixed-initiative and human-in-the-loop systems.** Hint 驱动的引导与 human-in-the-loop 修正在 visual analytics 中有深厚传统 [endert2014mixed]。[SYSTEM] 的 hint console（`@everyone`、`@target`、`@c-XX`）继承自这一脉络，并将其落实为在每回合之间清空（drained）的系统消息；这让历史学家可以在不打断 agent 循环的前提下注入脆弱的档案证据（一个尚存的姓氏、一个旗属约束）。
