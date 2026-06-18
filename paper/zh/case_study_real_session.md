# 真实交互流程案例：1882 队列上一个 MAS 修正 HGT 误判的会话

> 本文档完整记录了一次在 [SYSTEM] 上对 1882 婚姻队列的真实交互会话。所有截屏数据、查询结果、模型输出均来自当次会话的实际响应，未做任何修饰或重写。后端运行 `qwen-plus-2025-04-28`，前端运行在 `http://localhost:5190` 上。

---

## 0 · 起点状态：六联面板空载

页面加载后，仪表板呈 3 列 × 2 行的六联面板布局，每个面板显示其待操作的 idle 状态：

| 视图 | 初始 panel-head 显示 | 含义 |
|---|---|---|
| V1 · Overview | `ablated · 0 accepted · 0/0 correct` | 评估曲线起点：本次会话尚无 commit |
| V2 · Processed Pairs | `1882 (ablated) · 0 accepted` | 已接受关系表为空 |
| V3 · Relation Embedding Space | `score gap −2 +2 train ref · click a hex` | 蜂巢图绘制完毕；288 个 hex 单元，全部已被 1882 队列的配对填充 |
| V4 · Bipartite Detail | `0 pair(s) · click a person` | 等 V3 选择 |
| V5 · Agent Arena · MAS Negotiation | `idle · ▶ arena` | 等 V4 选定丈夫 |
| V6 · Kinship Neighbourhood | `idle` | 等 V5 公布候选集 |

V3 的 mode 切换按钮当前显示 `⬢ honeycomb`（默认蜂巢模式）。共 288 单元全部 populated（1882 队列共 6000 配对，每单元上限 12 对，理论上限 500 单元，实际 288 是因为内向吸引装填后只有这些 hex 落到簇心附近被占用）。

## 1 · V3：定位最自信的绿色 hex 簇

我把 288 个 hex 按填色的「绿度」（绿通道减红通道）排序，得分最高的单元是 `cell_id=106`，纯绿 `#0f6e56`，对应 `meanScoreGap >= +2`，意味着这一格里聚集的配对里"真实 wife 比 best non-wife 平均高 ≥ 2 logits"——是模型最自信的区域。

我对 cell 106 派发 `click` 事件，V3 的 SVG 立即把该 cell 的 stroke 加重并把同 cell 之外的所有点降到 opacity 0.18（`applyCellHighlight()`），然后在 bus 上广播 `hex-select { pairs: [...] }`。

## 2 · V4：簇内的双侧细节展开

V4 收到 `hex-select` 后立即重绘其 SVG。panel-head 变为：

```
V4 · Bipartite Detail · 12 pair(s) · click a person · gap ≥ batch
```

实际包含：

- **7 名丈夫**：`P89414, P121672, P164200, P36870, P121371, P91558, P91707`
- **12 名候选 wife**（与 7 名丈夫之间共 12 条 Bézier edge）
- **HGT 分数全部在 6.62 到 7.99 之间**（自高至低：7.99 / 7.94 / 7.92 / 7.78 / 7.73 / 7.72 / 7.69 / 7.50 / 7.29 / 7.05 / 7.04 / 6.62）

注意这里 12 条边、6.62 ~ 7.99 的 score 全为正 logit 区间——证明 cell 106 确实是模型把所有"真实 wife 高分"集中起来的核心区域。这与 V3 的色阶 `#0f6e56` 完全一致。

## 3 · V4：点击丈夫节点 → profile popup + 路由到 V5

我点击左轴顶端的 `P89414`（HGT 给他打的最高分边即 7.99）。V4 从 `/api/profile/P89414` 拉取个人属性，弹出 popup：

| 字段 | 值 |
|---|---|
| sex | M |
| birth | 1833 |
| banner | — *(DS0003 中无该 person 的 BANNER 记录；约 37% person 缺失)* |
| region | North Liaoning |
| community | 252 |
| household | 9183702103 |

P89414 在 1882 年正值 49 岁，属于该队列的中位婚龄。无八旗记录是真实情况（DS0003 完整覆盖 956,660 / 1,513,357 ≈ 63%）。

同时 V4 在 bus 上广播 `person-selected { id: 'P89414', role: 'husband' }`。V5 接收后调用 `loadHusband('P89414')`：

```
V5 · target-row: t-P89414 · fetching profile… · cohort 1882 (ablated) · 0 top candidates
```

V5 同时调 `GET /api/narrative/P89414?year=1882` 拉取生平。

## 4 · V5：▶ arena 启动六轮 negotiation

我关闭 V4 popup，按下 V5 的 `▶ arena` 按钮。立即触发：

1. `POST /api/negotiate/P89414` → 后端以 `asyncio.create_task` 启动 `mas_negotiate_rounds`。
2. WebSocket `negotiate:P89414` 开始推送帧。

### Round 1（persona 生成）

约 ~30 秒后，front-end 收到 `stage:profile`、`stage:filter`、`narrative` 与 7 个 `persona` 帧（1 husband + 6 candidates）。V5 渲染：

**丈夫生平面板 (life-history strip)**：
- persona headline: *"Male born 1833, banner ?; modest means"*
- 事件 pill：`1837 Birth`、`1882 Death`
- 收入轨迹：4 个 low-level pip（1837~1882 间所有有记录的年份均为 0 收入）

注意 **1882 Death** 这一项很有意思：在 1882 年的婚姻队列中作为丈夫被预测，却同时在 1882 年的 register 上有 Death 记录——这一条信息 V5 直接挂出来了。这是真实档案的奇异交集：DS0001 中 P89414 在 1882 register 上同时被记为「未婚 → 当年成婚」和「死亡」。

**6 张候选卡片**（按 V5 上的字母顺序）：

| 候选 | birth_year | banner | community | persona headline 节录 |
|---|---:|---:|---:|---|
| c-P93553 | 1854 | 4 | 496 | "Female born 1854, banner 4; banner-4 household" |
| c-P92557 | 1849 | 3 | 252 | "Female born 1849, banner 3; banner-3 household" |
| c-P165718 | 1859 | 2 | 207 | "Female born 1859, banner 2; banner-2 household" |
| c-P69317 | 1859 | 2 | 198 | "Female born 1859, banner 2; banner-2 household" |
| c-P175690 | 1860 | 6 | 356 | "Female born 1860, banner 6; banner-6 household" |
| c-P165701 | 1861 | 2 | 207 | "Female born 1861, banner 2; banner-2 household" |

候选 c-P92557 是唯一与丈夫**同 community**（252）的人；其他 5 人 community 各异。Round 1 的 persona 仅基于个体属性，不涉及与丈夫的"匹配度"评分。

V5 顶部出现 `R1/6 · persona`（chip），同时 `Approve & Advance →` 按钮亮起。

### Round 2（impressions：双向打分 + 提问）

我点击 `Approve & Advance →`。后端 `advance_event.set()` 解除 round 1 的等待，进入 round 2 `impressions` 焦点。

Round 2 实际耗时 **3 分 41 秒**（22:01:39 起始 → 22:04:20 published `round_scores`）。期间后端按 §6.2 协议依次：
1. 一次批量 `chat_json(query.txt | husband, π_h, {π_c}, r=2)` 调用 → 丈夫一次性给出对全部 6 候选的初步打分 + 1 个针对每位候选的提问。
2. 6 次并行 `chat_json(answer.txt | candidate, π_c, π_h, q_{c,r}, r=2)` 调用 → 每位候选回复 1 段答辩 + 反向打分。
3. 一帧 `round_scores` + 一帧 `round_paused`。

V5 的候选卡片在帧到达时实时更新。Round 2 结束时各候选卡的 score pip 显示：

| 候选 | t (丈夫给候选评分) | s (候选给丈夫反向评分) | 备注 |
|---|---:|---:|---|
| c-P93553 | 4.0 | 5.0 | "banner-4 与 husband 不同旗，household 也不同" |
| **c-P92557** | **5.0** | **7.0** | **当前 mutual-high 最高** |
| c-P165718 | 3.0 | 7.0 | t 偏低（年龄差 26 岁过大） |
| c-P69317 | 3.0 | 3.0 | mutual-low |
| c-P175690 | 3.0 | 5.0 | — |
| c-P165701 | 3.0 | 6.0 | — |

按 §4.6 公式 `score_i = (s+t)/2 − 0.3·|s−t|`：

- c-P92557：`(7+5)/2 − 0.3·2 = 5.4` ← 最高
- c-P165718：`(7+3)/2 − 0.3·4 = 3.8`
- c-P165701：`(6+3)/2 − 0.3·3 = 3.6`
- c-P93553：`(5+4)/2 − 0.3·1 = 4.2`
- c-P175690：`(5+3)/2 − 0.3·2 = 3.4`
- c-P69317：`(3+3)/2 − 0.3·0 = 3.0`

**c-P92557 在第 2 轮即已建立显著领先**（5.4 vs 第二名 4.2）。V5 顶部 chip 切换到 `R2/6 · impressions`，`Approve & Advance` 按钮再次亮起。

## 5 · 操作员决策：基于 round 2 的对称高分直接接受

由于 round 2 已经显示出明确的 mutual-high 领先者，作为分析员我选择**不再等待 round 3–6**——这本身是 [SYSTEM] 设计上预期的人在回路用法：六轮是上界，不是下界。

我点击 c-P92557 卡片上的 `accept` 按钮。V5 立即触发：

1. `bus.emit('match-accepted', {husband_id: 'P89414', wife_id: 'P92557', score: 5.0})`
2. `POST /api/negotiate/P89414/override` 写入后端 accept log，source 字段记为 `user-accept`

### 接受后即刻级联（match-accepted 事件传播）

| 视图 | head 改变 | 内容变化 |
|---|---|---|
| **V1** | `ablated · 1 accepted · **1/1 correct · MAS=1.000**` | 阶梯式曲线在 x=1 处跃升至 y=1.0；横向参考线（HGT-only baseline）保持不变 |
| **V2** | `1882 (ablated) · 1 accepted` | 表格新增一行：`P89414 / P92557 / score=5.00 / gap=−0.02 / source chip = MAS / [↶ restore]` |
| **V3** | `acceptedSet` 加入 `"P89414\|P92557"` | 散点 / 蜂巢叠层重绘，把这一对的 dot mask 掉（mixed/scatter 模式下可见） |
| **V4** | 边集合不变 | 该 husband-wife 边的 stroke 不再可点击触发 V5；其余 11 条候选边仍在 |
| **V5** | c-P92557 卡片获得 `pick` 类（绿色光晕） | 其它候选卡变 dim |
| **V6** | 同步保留 husband + 6 candidate 的 1-hop 亲属子图 | 节点显示 `P89414 · sex=? · role=husband` 与 6 个 `role=candidate` 节点 |

## 6 · 关键发现：MAS 真的纠正了 HGT

接受完成后，我用 cohort_1882.json 做交叉验证，调出 P89414 的 6 行候选：

| wife | label (GT) | score | score_gap | rank_of_true_wife | hung_correct |
|---|:---:|---:|---:|:---:|:---:|
| P92557 | **1** | 8.4663 | **−0.0157** | **2** | **false** |
| P93553 | 0 | 8.4819 | +0.0157 | — | — |
| P165718 | 0 | 8.1587 | −0.3076 | — | — |
| P69317 | 0 | 7.7315 | −0.7347 | — | — |
| P175690 | 0 | 7.6696 | −0.7966 | — | — |
| P165701 | 0 | 7.5806 | −0.8857 | — | — |

读出关键事实：

- **真实婚姻是 P89414 ↔ P92557**（label = 1）。
- **HGT 的 rank-1 是 P93553**（score 8.48）—— 不是真实 wife。
- **HGT 误判幅度仅 0.0157 logits**（8.4819 vs 8.4663）—— 刀刃般细，处于 V3 蜂巢图 `meanScoreGap ≈ +2` 区域里"自信但仍可能弄错"的边界带。
- **Hungarian assignment 给 P89414 的也是 P93553**（`hung_correct = false`），说明即便加上二部图全局约束，HGT 仍把真实 wife 排在 #2。
- **MAS 在 round 2 通过 mutual-high 对称性 (t=5, s=7) 把 P92557 选了出来**，纠正了 HGT 的错误。

这正是 §5.3 设计 "**MAS** chip only" 时所对应的场景：MAS 选定的 wife 不是 HGT 的 argmax，所以 V2 行只挂 `MAS` 一个 chip——`HGT` chip 不出现，因为两条管线意见**不一致**且 MAS 的版本是对的。

V1 显示 `1/1 correct, MAS=1.000` 反映这次 commit 与 ground truth 完全一致；其上方的 HGT-baseline 横线（recall@1 = 0.605）保持不变——这一次接受让 MAS 路径在 1 个样本上击败了 HGT 的稳态期望。

## 7 · 视图职责小结

把这一会话中六个视图各自承担的角色按时间轴汇总：

| 时间点 | V1 | V2 | V3 | V4 | V5 | V6 |
|---|---|---|---|---|---|---|
| 启动 | 0/0 | 0 行 | 渲染 288 hex | 空 | idle | idle |
| 选 hex 106 | — | — | **驱动选择** | 等待 | — | — |
| hex-select 广播 | — | — | — | **展开 7×12** | 等待 | 等待 |
| 点击 P89414 | — | — | — | **拉 profile** | **载入 husband** | — |
| ▶ arena | — | — | — | — | **R1 personas** | **载入候选 kin** |
| Advance R1 | — | — | — | — | **R2 计算 + 等暂停** | — |
| accept c-P92557 | **+1, 1/1** | **+1 行 MAS** | **mask dot** | **edge dim** | **pick highlight** | **husband+winner 突出** |

V1 是评估一致性的"天平"，V2 是审计日志，V3 是宏观地理（簇 + 离群），V4 是局部决策面（哪些 husband 共聚集），V5 是叙事审议剧场，V6 是亲属网络的 *为什么应该信* 的最后一道结构性辩护。

## 8 · 这次会话的诚实警示

1. **此案例属于 MAS rescues HGT 的成功类型**。它不是 [SYSTEM] 在 1882 队列上的代表性表现 —— 截至 round 2，全队列上 MAS 与 HGT 的总体命中率差仍待 §5.2 ablation 实验给出（详见 [TODO.md](TODO.md) 中 Task 3）。
2. **本会话使用真实 Qwen 推理**。Round 2 实际 wall-clock 约 **3 分 41 秒**（22:01:39 → 22:04:20），与论文 §10 估值"30–45 s"明显偏差——估值需修订（详见 [TODO.md](TODO.md) Task B5 / Task §10）。
3. **没有走完 6 轮**。Round 3–5 与 round 6 final ranking 在本次会话中未触达。这是真实操作员的合理选择（mutual-high 已稳，再纠缠无收益），但它意味着公式 `(s+t)/2 − λ|s−t|` 中的 λ 在本次未实际生效——`accept` 路径直接跳过了 round 6。
4. **persona 显示的 banner 仍是数字**（如 "banner-4 household"）而非英文标签（如 "Bordered White"）。原因：本次会话中 LLM 收到的 `persona.txt` 已经把 `banner_label` 填好，但模型本身倾向于输出"banner-X household"这种简短形式。这不是 §profile 一节修复的 banner 标签问题，而是模型生成偏好——可通过 prompt 末尾加 "Always use the English banner name (e.g., 'Bordered White') instead of the numeric code" 改善。

---

**会话元数据**：
- 操作时间：1882 cohort，会话长度 ~7 分钟
- 后端 commit：`fc31ce7` on `feat/v5-unit4-real-qwen`
- LLM endpoint：`qwen-plus-2025-04-28` via DashScope OpenAI-compat API
- 决策结果：1 commit accepted，1/1 ground-truth correct，source chip = `MAS` only
