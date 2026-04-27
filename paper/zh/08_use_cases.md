# 8 Use Cases

我们通过与 E1–E3 的形成性会话中提炼出的三个场景来阐释 **[SYSTEM]**。

## 8.1 Use Case 1 —— 1882 年队列的婚姻分诊（E1）

E1 是一位清代人口史家，她从 CMGPD-LN 面板（在此用作评测测试平台）中打开 1882 年的被消融队列。V3 显示 honeycomb 画布并以发散色阶填充 score gap；她注意到右上方一簇紧凑的绿色 hex，便点击其中之一。V4 展开了一个 8 位丈夫的二部布局，所有配对的 score gap 均高于 2.0。她以阈值 1.0 执行 batch 提交，8 位丈夫中的 7 位一击落定，在 V2 中以 **HGT** chip 出现。V1 的曲线干净利落地越过了静态基线。

剩下的那位丈夫被路由到 V5，E1 在 agent arena 中审视。该 arena 的 persona 揭示出一条在 1879 年趋于平缓的收入轨迹，以及 1881 年的一次单次 *Lost* 事件 —— 两者都来源于 DS0003。E1 将其识别为一种已知的 absconding pattern，于是在 hint console 中输入 `@everyone be skeptical of stability claims`；第 3–5 回合的 query 与最终得分中均反映出该指令。Negotiation 最终收敛到一位与 HGT $\arg\max$ 不同的妻子。她接受后，**HGT** 与 **MAS** chip 同时出现：V2 记录下两条管线的不一致。

## 8.2 Use Case 2 —— 探测母系边消融（E3）

E3 是一位 digital-humanities 方法论专家，她在某个 CMGPD-LN 队列（评测测试平台）内部工作，以验证母系边（$r_{ms}, r_{md}$）是否在婚姻边之外仍承载独立的可预测性。她通过工具栏在 `ablated`（仅压制 $r_{hw}$）与 `unablated`（完整图）之间切换队列消融状态。Honeycomb 几何形态发生明显位移：score gap 分布收紧，簇边界围绕 banner 共属性重新组织。

她使用 V6 抑制 $\mathsf{m}_4$（banner endogamy），并在 V5 重新跑一位丈夫的 negotiation；匹配结果发生变化，表明系统是把 motif 层面的依赖关系显式呈现出来，而非默默吸收它。V2 上这两次提交所累积的 source chip 形成了一份可日后报告的、有据可查的分歧记录。

## 8.3 Use Case 3 —— 真实家谱证据注入（E2）

E2 是一位 computational genealogist，她模拟部署场景：她 *假装* 该队列是一份真实家谱，其中妻子的姓氏（*Wang*）是唯一被记录的事实，尽管底层数据其实仍然是 CMGPD-LN 队列、隐含的真值仍可用于打分。她加载 1885 年的队列，选中她想要补全记录的丈夫，并启动 V5。第 1 回合结束后，她审视各候选的 persona，并在 hint console 中输入 `@everyone wife's surname is Wang`。

编排器把这条 hint 清空进入第 2 回合的 prompt；姓氏不匹配的候选在其解释中以更低的 $t_i$ 得分浮现，而姓氏为 Wang 的候选的 persona 在下一回合的 transcript 里被显式地纳入推理（可在可展开的对话面板中看到）。最终提交的 chip 仅显示 **MAS** —— HGT 的 $\arg\max$ 是另一位妻子 —— V2 的 audit trail 记录了这一分歧，E2 将其导出，用于稿件层面的交叉对照。
