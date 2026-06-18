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

## 8 · R4 rebuttals：丈夫开始撤回 R3 的过度乐观

R4 焦点："test honesty by following up on weaknesses or contradictions"。这一焦点把 R3 的 deep-dive 共识拉回来重审。

| 候选 | R3 t/c | R4 t/c | Δt | Δc | 关键变化 |
|---|:---:|:---:|---:|---:|---|
| c-P93553 | 7/8 | **6/6** | -1 | -2 | "shared banner values align well" 仍在，但承认 "questions about household dynamics" |
| c-P92557 | 8/7 | **7/8** | -1 | +1 | t 微降但 c 上升；侧面对称化 |
| c-P165718 | 6/7 | 5/5 | -1 | -2 | "weaken his suitability for a banner-2 household" |
| c-P69317 | 6/7 | 5/8 | -1 | +1 | 候选称丈夫 "transparency is commendable"，c 升 |
| c-P175690 | 5/8 | 4/6 | -1 | -2 | 候选反向打分回落，"blunt phrasing lacks decorum" |
| c-P165701 | 5/8 | 4/7 | -1 | -1 | "blunt suspicion of my past shows a lack of trust" |

**6 个候选中 5 个 Δt = -1**——丈夫一致性地把 R3 的全面上调收回 1 个百分位。R3 deep-dive 的"找一致点"在 R4 rebuttals 焦点下被强制重审，几乎所有候选都被发现"还是有疑虑"。

**P92557 的关键 R4 引文（H→W）**：
> "Smallest age gap (16 years) among candidates. Prior marriage experience may complicate lineage continuity goals, but **banner alignment is favorable**."

这是 R4 中第一次出现 "banner alignment is favorable"（注意是 banner-3 与"修正 banner unknown 的丈夫"之间的对齐）。t=7（同 P93553 的 c=6）是 R4 全场最高的丈夫给候选评分。

按 final score 公式：
- c-P92557：(8+7)/2 - 0.3·1 = **7.2**
- c-P93553：(6+6)/2 - 0.3·0 = **6.0**

P92557 在 R4 重新拉开 1.2 分的领先优势——deep-dive 的并列局面被 rebuttals 终结。

---

## 9 · R5 alignment：丈夫的 t 全面回到 R2 水平

R5 焦点："evaluate long-term alignment and complementarity"。

| 候选 | R4 t/c | R5 t/c | Δt | Δc |
|---|:---:|:---:|---:|---:|
| c-P93553 | 6/6 | **4/7** | **-2** | +1 |
| **c-P92557** | 7/8 | **5/7** | -2 | -1 |
| c-P165718 | 5/5 | 4/7 | -1 | +2 |
| c-P69317 | 5/8 | 3/7 | -2 | -1 |
| c-P175690 | 4/6 | 3/6 | -1 | 0 |
| c-P165701 | 4/7 | 3/7 | -1 | 0 |

**所有 6 候选的 t 都被进一步下调**（5 个 Δt = -1 ~ -2）。这一现象很有意思：R5 的 alignment 焦点重新强调"长期相容性"，丈夫此时全面把 t 下调到接近 R2 水平。**全场最高的丈夫给分回到 P92557 的 t=5**——与 R2 完全一致。

R5 关键引文：
- **P92557 (H→W)**: "Smallest gap (16y) offers best complementarity; **Banner-3 suits modest means**; values align perfectly for long-term household stability."
- **P92557 (W→H)**: "Shared banner endogamy and lineage values promise strong alignment. **Modest means and his senior age require adjustment**, yet his pragmatic focus on duty complements my experience well."

注意 P92557 的 W→H 在 R5 第一次显式承认「需要调整」（"require adjustment"）—— 候选的态度从 R3-R4 的暧昧支持，到 R5 终于面对了具体顾虑。这是 alignment 焦点 working as designed：长期相容性需要双方承认对方的局限。

按 R5 final score：
- c-P92557：(5+7)/2 - 0.3·2 = 6 - 0.6 = **5.40**
- c-P93553：(4+7)/2 - 0.3·3 = 5.5 - 0.9 = **4.60**
- c-P165718：(4+7)/2 - 0.3·3 = 5.5 - 0.9 = **4.60**
- c-P69317：(3+7)/2 - 0.3·4 = 5 - 1.2 = **3.80**
- c-P165701：(3+7)/2 - 0.3·4 = 5 - 1.2 = **3.80**
- c-P175690：(3+6)/2 - 0.3·3 = 4.5 - 0.9 = **3.60**

**P92557 以 5.40 > P93553 / P165718 同列第二的 4.60**——领先 0.8 分（HGT 在原 logit 上的差距是 0.0157）。MAS 把"分辨率比 HGT 高 50 倍"实现了。

---

## 10 · R6 final ranking（R6 由后端计算最终得分）

R6 不做新 LLM 调用，直接以 R5 的 $s_{i,5}, t_{i,5}$ 套入公式 $\text{score}_i = \tfrac12(s_i+t_i) - 0.3\cdot|s_i-t_i|$ 排序。WebSocket 推送的 `final_ranking` 帧（实际数据）：

| Rank | 候选 | $t_{i,5}$ | $s_{i,5}$ | $|s-t|$ | final score |
|:---:|---|:---:|:---:|:---:|---:|
| **1** | **c-P92557** | **5.0** | **7.0** | 2 | **5.40** ← 真实 wife |
| 2= | c-P93553 | 4.0 | 7.0 | 3 | 4.60 |
| 2= | c-P165718 | 4.0 | 7.0 | 3 | 4.60 |
| 4= | c-P69317 | 3.0 | 7.0 | 4 | 3.80 |
| 4= | c-P165701 | 3.0 | 7.0 | 4 | 3.80 |
| 6 | c-P175690 | 3.0 | 6.0 | 3 | 3.60 |

`chosen` 字段为 `None` —— R6 没有自动 commit（默认 `auto_commit=False`，需要操作员人工点 *Accept this match*）。但 ranking 已经把真实 wife 推到 rank-1，与操作员在 R2 时点击 accept 的判断完全一致。

---

## 11 · 全六轮综合演化曲线

把丈夫给 P92557 与 HGT 错误首选 P93553 的 final score 按轮次对比：

| 回合 | P92557 final | P93553 final | 差距 | 焦点 |
|:---:|---:|---:|---:|---|
| R2 impressions | **5.4** | 4.2 | +1.2 ← MAS 已能区分 | 红旗扫描 |
| R3 deep-dive | 7.2 | 7.2 | **0.0** ← deep-dive 让两人并列 | 价值观 / 户内 |
| R4 rebuttals | 7.2 | 6.0 | +1.2 ← rebuttals 拉开差距 | 检查矛盾 |
| R5 alignment | 5.4 | 4.6 | +0.8 ← alignment 收敛 | 长期相容 |
| R6 final | **5.40** | 4.60 | +0.80 | 公式排序 |

**核心发现**：MAS 的双向博弈让真实 wife 在 R2、R4、R5、R6 四个回合中始终领先；R3 的 deep-dive 是唯一让 HGT 错误首选追平的"危险时刻"，但被随后的 R4 rebuttals 焦点修正回来。这个"R3 危险 → R4 rebuttals 拯救"的两步是 §6.2 round-focus 设计的关键贡献：

- 单一焦点（仅 deep-dive）会让 LLM 过度乐观找一致点 → 错误候选混入
- 单一焦点（仅 rebuttals）会让 LLM 过度悲观挑刺 → 真实候选也被错杀
- **多焦点交替**让两类失误相互抵消 → 真实 wife 在所有焦点下的"加权胜率"最高

---

## 12 · 最终的诚实警示

1. **本案例是 MAS rescues HGT 的成功类型**。HGT 误判 P93553 vs P92557 仅 0.0157 logits；MAS 把分辨率扩大到 0.80 final score（**~50 倍**）。但这不能代表 [SYSTEM] 在 1882 队列上的总体水平 —— 仍需 [TODO.md](TODO.md) Task 3 的 ablation 实验给出系统层数据。
2. **每轮 wall-clock 实测**：R2 ≈ 3'41"、R3 ≈ 5'40"、R4 ≈ 4'34"、R5 ≈ 4'20"。**全六轮总耗时约 20 分钟**，比论文 §10 估值"30-45 s"高一个数量级 —— 已写入 TODO B5 待修。
3. **W→H 的反向打分推理出现自相矛盾**（如 P175690 R2 反对 banner、R3 称对齐"perfectly"，R4 又回到"lacks decorum"）。这是 LLM 在切换焦点时倾向于"局部最大对齐"的副作用，应在 §10 LLM faithfulness 中明确指出。
4. **本日志覆盖**：一次会话、一名丈夫、6 个候选、R1–R6 全部完成。要做真正的 MAS-vs-HGT 整体分析，必须对整个 1882 / 1903 队列做 N>>1 的批量 ablation 实验。

---

**源数据**：
- WebSocket 帧 dump：`/tmp/p89414_frames.jsonl`（一次会话 R1–R6 全部 frames）
- R2/R3 reasoning：从 V5 候选卡 `.round-pip[title]` 提取
- R4/R5 reasoning：从 WebSocket `round_scores` 帧的 `target_reason` / `candidate_reason` 字段提取
- R6 final ranking：从 WebSocket `final_ranking` 帧的 `ranking` 数组提取（`chosen` = `None`，因为 `auto_commit=False`）
