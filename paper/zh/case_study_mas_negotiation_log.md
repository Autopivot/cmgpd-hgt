# MAS 博弈日志：1882 队列 P89414 的两轮印象演化

> 续 [`case_study_real_session.md`](case_study_real_session.md)。同一会话，丈夫 **P89414**（M / 1833 / North Liaoning / household 9183702103 / banner 不详 / persona = "modest means, banner unknown, prior marriage exposure"），6 名候选 wife。本文从真实 round-pip tooltip（即 V5 候选卡上鼠标悬停看到的 `H→W` / `W→H` 推理文本）逐字提取了 round 2 + round 3 完成时的双向打分原文，并按候选展开影响演化分析。

> 数据范围：截屏时刻 V5 已发布 `round_scores` 帧两次（R2 impressions、R3 deep-dive），R4 rebuttals 正在执行（仍在 LLM 调用中）。下文「R2 / R3」一栏的所有引文均为 Qwen 实际生成的英文原句，未做任何改写或翻译。

---

## 0 · 全局打分概览

按公式 $\text{score}_i = \tfrac{1}{2}(s_i + t_i) - 0.3\cdot|s_i - t_i|$ 计算第 6 轮排名（$\lambda = 0.3$）。下表把 R2 与 R3 的双向打分一并列出：

| 候选 | R2 t (丈夫→候选) | R2 c (候选→丈夫) | R2 final | R3 t | R3 c | R3 final | Δt | Δc | Δfinal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| c-P93553 | 4 | 5 | 4.2 | **7** | **8** | **7.2** | **+3** | **+3** | **+3.0** |
| **c-P92557** ← GT | **5** | **7** | **5.4** | **8** | **7** | **7.2** | **+3** | 0 | **+1.8** |
| c-P165718 | 3 | 7 | 3.8 | 6 | 7 | 6.2 | +3 | 0 | +2.4 |
| c-P69317 | 3 | 3 | 3.0 | 6 | 7 | 6.2 | +3 | **+4** | **+3.2** |
| c-P175690 | 3 | 5 | 3.4 | 5 | 8 | 5.6 | +2 | +3 | +2.2 |
| c-P165701 | 3 | 6 | 3.6 | 5 | 8 | 5.6 | +2 | +2 | +2.0 |

**第一眼能看出的模式**：

1. **R3 「deep-dive」整体上调**——所有 6 名候选的 $t$ 都被丈夫上调（Δt ∈ \{+2, +3\}），R2 的「impressions」一律偏苛。这一现象与 §6.2 中 round-focus 的设计一致：R2 关注「明显的红旗」，R3 关注「价值观、户内适配、共享优先级」，焦点拉宽自然让评分变温和。
2. **P93553 与 P92557 在 R3 后并列 7.2**。HGT 的错误 rank-1 候选（P93553，banner-4）凭借 R3 的 "shared banner values support lineage goals" 跃升，与真实 wife（P92557，banner-3、与丈夫同 community 252）形成 final-score 平手。如果会话在此处停下并按 R3 final 接受，**MAS 也无法分辨 P93553 与 P92557**。
3. **R2 t=5 / s=7（P92557）这一「双高 + 微小差距」的对称结构是 R2 末决策时 MAS 选 P92557 的根据**。R3 把 P93553 和 P92557 都拉成对称双高（前者 7/8、后者 8/7，|s-t|=1），$\lambda$ 项不再起决定性作用——这正是 §4.6 设计 $\lambda$ 项的初衷。

---

## 1 · 候选 c-P93553（HGT 的错误 rank-1，banner-4，1854 生）

### R2 H→W: t=4

> "21-year age gap exceeds ideal 0-5y range; prior marriage exposure warrants scrutiny **despite shared values**."

丈夫的 R2 印象：年龄差 21 岁、丈夫已有过婚姻经历是"红旗"，但承认「共享价值观」做了一定程度的折抵。t=4 是 6 候选中第二低的（仅次于 P92557 的 t=5）——这意味着如果 R2 立刻定夺，HGT 的最爱候选会被 MAS 第一票丢弃。

### R3 H→W: t=7（+3）

> "Age gap exceeds ideal 0-5y range, **but shared banner values support lineage goals**. Prior marriage exposure and banner-4 status require careful assessment of household fit."

R3 的转折在 "but shared banner values support lineage goals" 这一句：丈夫意识到 P93553 的 banner-4 与他的 lineage 大目标相容，把 t 从 4 一口气拉到 7。这是 R3 焦点（deep-dive on values + household fit）实际驱动评分的明证。

### W→H 视角

R2 的反向打分 c=5：「his unspecified banner status directly threatens my core value of banner endogamy. I must verify his household before proceeding.」 — 候选明确把 banner 不详当作核心顾虑。

R3 反向打分 c=8（+3）：「his pragmatic concern shows maturity. I value his shared priorities and respectful approach to household stewardship.」 — 候选把"务实关切"重新解读为成熟稳重，分数大幅上调。

**演化诊断**：双向 +3 的同步上调（t: 4→7, c: 5→8）让 P93553 从 R2 的边缘候选（final 4.2）跃升为 R3 的并列头名（final 7.2）。这是「deep-dive 焦点把表面冲突重述为价值兼容」的典型示例。

---

## 2 · 候选 c-P92557（真实婚姻，banner-3，1849 生，与丈夫同 community 252）

### R2 H→W: t=5

> "**Closest age match at 16 years**, shares core values, but prior marriage history requires clarification."

R2 印象：6 个候选里年龄最接近的（差 16 岁，仍超过理想 0–5 范围但相对最优），价值观共享。t=5 是 R2 全场最高分。

### R3 H→W: t=8（+3）

> "**Smallest age gap aligns best with norms**. Banner-3 status matches my values. Prior marriage exposure warrants inquiry on integrating into a modest household."

R3 把"年龄最近"从相对优势升级为 "aligns best with norms"，并明确点出 "Banner-3 status matches my values" —— 注意这里的 "matches my values" 是丈夫 persona 里的 "lineage continuity" 与 banner-3 之间的认定。t=8 是 R3 全场最高（与 P93553 的 c=8 并列）。

### W→H 视角

R2 c=7：「I score him fairly but await his banner confirmation」——保留态度，等待 banner 信息。R3 c=7（不变）：「his unknown banner affiliation and modest means give me pause; I must verify his household standing before fully committing」 —— 候选侧的态度**没有任何变化**，仍以 banner 不详为主要顾虑。

**演化诊断**：P92557 的特殊性在于 **W→H 完全停滞**（c=7→7）。她的 R3 反向打分理由 "his unknown banner affiliation and modest means give me pause" 与 R2 几乎逐字一致——她坚持要等 banner 确认。但丈夫一侧已经把她从 t=5 推到 t=8，靠 R3 的 deep-dive focus 把"年龄最接近 + 价值观契合"重新加权。final 5.4→7.2 的爬升完全由丈夫单侧驱动。

---

## 3 · 候选 c-P165718（banner-2，1859 生）

### R2 H→W: t=3

> "Substantial **26-year age gap** and banner-2 household may strain alignment with my modest means and unstated banner."

### R3 H→W: t=6（+3）

> "**Banner-2 status is favorable**, but 26y age gap challenges spousal harmony. Prior marriage history may complicate lineage continuity under modest means."

R3 把 R2 的「banner-2 household may strain alignment」（中性偏负）重新评估为 "Banner-2 status is favorable"（明显正面）——这是同一事实在 deep-dive 焦点下的再框定。

### W→H 视角

R2 c=7：「his respectful approach merits a fair initial rating」——给出尊重的初评。R3 c=7：基本不变。

**演化诊断**：与 P92557 类似的「丈夫单侧上调」模式（c=7→7，t=3→6）。R2 的 final 3.8 → R3 的 final 6.2 的跃升 2.4 个绝对值，完全来自丈夫的态度转向。但绝对水平仍在 P93553 / P92557 之下。

---

## 4 · 候选 c-P69317（banner-2，1859 生）：R3 涨幅最大的一位

### R2 H→W: t=3

> "**26-year age gap** poses lineage continuity concerns; household status may not align with my current standing."

### R3 H→W: t=6（+3）

> "**Shares banner-2 background and values**, yet significant age difference and prior marital ties raise questions about adapting to my modest household."

### W→H 视角（关键变化）

R2 c=3：「**His demanding tone lacks propriety**. His unlisted banner and advanced age jeopardize our endogamy and lineage continuity, while modest means offer little household security.」 —— **R2 的反向打分 3 是 6 候选中最低的**，候选明确指责丈夫语气失礼。

R3 c=7（+4）：「Shares my core values of endogamy and lineage. However, his unknown banner affiliation and age gap require careful verification before full commitment.」 —— 反向打分跃升 4 个百分位。「demanding tone lacks propriety」一句完全消失，被「shares my core values」替代。

**演化诊断**：**P69317 是 6 候选中双向打分演化幅度最大的一位（Δt+3, Δc+4, Δfinal+3.2）**。R2 时 mutual-low（3/3，final 3.0），R3 已变成 mutual-high（6/7，final 6.2）。这种「全面修复」模式说明，round 2 的初印象偏严苛、round 3 的 deep-dive 提供了实质性的态度纠偏机会。

---

## 5 · 候选 c-P175690（banner-6，1860 生，年龄差 22）

### R2 H→W: t=3 → R3 H→W: t=5（+2）

R2: "27-year gap and banner-6 status raise compatibility issues..." → R3: "Banner-6 status and 27y gap create distance from ideal norms..."

注意 R3 的丈夫调升幅度仅 +2（vs 其他候选 +3），**对 banner-6 持续保留态度**——丈夫 persona 中的 "banner endogamy" 价值观让他对 banner-6 候选始终更冷淡。

### W→H 视角：R3 跳到 c=8（+3）

R2 c=5: "His advanced age, modest means, and unspecified banner conflict with my preference for status and strict banner endogamy." → R3 c=8: "**Shared banner and lineage values align perfectly. His modest means suit my practical training. The age gap is notable but offset by his stability and shared priorities.**"

候选侧的转变是个有趣的反例：候选 R2 时质疑丈夫的 banner 与"strict banner endogamy"冲突，R3 却宣称"Shared banner and lineage values align perfectly"——**这两句之间存在直接矛盾**，因为丈夫的 banner 状态在 R2 与 R3 之间没有发生任何信息更新。这是 LLM 模型在 deep-dive 焦点下倾向于"找到对齐点"的副作用，也是 §10 LLM faithfulness 段落需要警示的事项之一。

**演化诊断**：双向不对称的「丈夫保留 / 候选热情」结构 (5/8) 让 |s-t|=3，使 final score 通过 $\lambda$ 项被罚 0.9 个绝对值，从 final 3.4 升到 5.6 但被对称性惩罚拉低。这是 $\lambda = 0.3$ 项实际起到调节作用的一个范本。

---

## 6 · 候选 c-P165701（banner-2，1861 生，年龄差最大 28）

### R2 H→W: t=3 → R3 H→W: t=5（+2）

R2: "Largest age gap (28y) complicates household harmony..." → R3: "Youngest candidate with 28y gap and banner-2 ties..."

与 P175690 同步——丈夫对 28 岁年龄差始终持保留。

### W→H：R3 c=8（+2）

R3 候选反向：「his direct inquiry shows sincerity and **deep respect for our traditions**.」 —— 候选称赞丈夫的"对传统的深切尊重"。

**演化诊断**：与 P175690 几乎同一模式（5/8，final 5.6，被对称性惩罚拉低）。

---

## 7 · 综合：MAS 博弈如何把「knife-edge HGT」转成「decisive MAS pick」

回到主线：HGT 的 rank-1 (P93553) 与真实 wife (P92557) 之间的 logit 差仅 0.0157——一个比模型分辨率小一个数量级的差距。MAS 是怎么把这道刀刃辨明的？

**R2 关键拐点**：
- P92557 立刻拿到 t=5（**6 候选中最高**）+ c=7，final 5.4。
- P93553 拿到 t=4 + c=5，final 4.2。
- 在 R2 末（impressions），P92557 已经领先 P93553 整整 1.2 个 final score。
- 我作为操作员**在此处接受了 c-P92557**，触发 V2 的 `MAS` only chip + V1 的 1/1 correct。

**如果继续到 R3**：
- P93553 和 P92557 都跃升至 final 7.2 并列。MAS 单独已无法决断；λ 项也无法分辨（两者 |s-t|=1）。
- 决断需要 R4–R6 的 rebuttals / alignment 焦点继续辨析，或操作员通过 hint console 注入额外信息。

**结论**：在这一案例中，**R2 的早期判断（impressions）实际上是 MAS 决断 P92557 的关键时刻**——后续轮次（R3 deep-dive）会因为焦点拓宽而把 P93553 等高 banner 候选提升至并列；R2 是 MAS 在 HGT 误判面前最有 discriminative power 的回合。这与论文 §6.2 的设计意图——「impressions 用于初步红旗、deep-dive 用于细化共识」——相符：错误候选在 R2 因红旗（年龄差 21、prior marriage）被低估，真实候选在 R2 因 closest age match + 同 community 被识别。

---

## 8 · 这次日志的诚实警示

1. **R4–R6 在截屏时刻仍在执行**（每轮 ~3.5 分钟，按目前进度 R6 final ranking 约在 12 分钟后到达）。本文止于 R3，**未捕获 round 6 final ranking 帧**。如果继续，最终 final score 可能再有变化（尤其是 P93553 的 deep-dive 跃升能否在 R4 rebuttals / R5 alignment 中持续）。
2. **persona 与打分推理中的 "banner-X household" 是数字编码**，未使用英文 banner 名（如 "Bordered Yellow"）—— prompt 已经传入 `banner_label`，但 LLM 倾向于写成简短数字形式。
3. **W→H 的反向打分推理出现自相矛盾**（如 P175690 R2 反对 banner、R3 称对齐"perfectly"），这是 LLM 在 deep-dive 焦点下倾向于"找到一致点"的副作用，应在 §10 LLM faithfulness 中明确指出。
4. **本日志只覆盖一次会话的一名丈夫的两个回合**。要做真正的 MAS-vs-HGT 整体分析，必须对整个 1882 / 1903 队列做 N>>6 的批量 ablation 实验（即 [TODO.md](TODO.md) Task 3）。

---

**源数据**：每条 `H→W` / `W→H` 引文均为 V5 候选卡 `.round-pip[title]` 属性的 verbatim 内容，可在 `paper/case_study_real_session.md` 一文末尾的会话元数据中按时间戳回溯到 WebSocket 帧记录。
