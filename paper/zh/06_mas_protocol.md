# 6 Multi-Agent Negotiation Protocol

## 6.1 Persona 实例化

对每一位参与者（一位丈夫加上每一位 top-K 候选），我们用以下来自数据的字段来渲染 persona prompt：

- **profile**：性别、出生年份、旗属（以英文标签呈现）、地理区域（以英文标签呈现）、community ID、household ID；
- 该候选相对该丈夫的 **HGT pre-score**；
- **event block**，格式为 `{year}: {event_1_label} / {event_2_label}`，由 DS0003 中 `EVENT_1/2` 编码经 `event_value_labels.json` 替换而来（如 1=Death、7=In-Marriage、13=Returned-after-absconding）；
- **income block**，格式为 `{year}: {income} ({level})`，按队列的第 33 / 66 百分位分桶；
- 命中的 **SEAL motif** 标签集合；
- 以及任何寻址到该角色、由队列中清空（drained）出来的 **hints**。

LLM 返回一个 JSON 对象，包含四个固定字段 —— `headline`、`traits`、`values`、`red_flags` —— 客户端会把它们按字面渲染为 chip（V5）。

## 6.2 回合结构

> **Algorithm 1.** 六回合双向 negotiation。
>
> ```
> Input: husband h, candidate set C, cohort year y, ablation a
>
>  1: publish stage:profile, stage:filter
>  2: load DS0003 narratives for h and each c ∈ C
>  3: π_h ← chat_json(persona.txt | h);  publish persona, motifs ∅
>  4: for each c ∈ C in parallel:
>  5:    π_c ← chat_json(persona.txt | c)
>  6:    publish persona, motifs = M(h, c)
>  7: wait for advance_event;  drain hint queue
>
>  8: for round r = 2, 3, 4, 5:                          # focus rotates
>  9:    (S_r, Q_r) ← chat_json(query.txt | h, π_h, {π_c}, r)
> 10:    for each c ∈ C in parallel:
> 11:       (a_{c,r}, s_{c,r}) ← chat_json(answer.txt | c, π_c, π_h, q_{c,r}, r)
> 12:       publish query, answer
> 13:    publish round_scores for round r
> 14:    publish round_paused;  wait;  drain hints
>
> 15: compute score_i per Eq. 1 using s_{i,5}, t_{i,5};  rank descending
> 16: publish final_ranking
> 17: on user accept:  commit_match;  broadcast match-accepted
> ```

Algorithm 1 形式化了回合循环。第 1 回合并行生成各 persona；第 2–5 回合通过把焦点描述插值进 prompt，依次走过四个典型审议焦点（*impressions*、*deep-dive*、*rebuttals*、*alignment*）；第 6 回合计算公式 1。

关键的是，每一回合都在一个 `round_paused` 帧处终止，orchestrator 会在一个 `asyncio.Event` 上挂起，只有当操作员点击 **Approve & Advance** 时才被置位。这一闸控机制实现了 DG4：在暂停期间提交的 hint 会在下一回合开始前被处理。每次调用都包裹在 try / except 中，并在出错时回退到一个确定性的启发式，使协议在 LLM 端点报错时仍然完整、帧流（frame stream）保持连续。

## 6.3 Hint 语义

Hint 寻址解析为：

| 寻址 | 路由 |
|---|---|
| `@target` | 仅丈夫的 prompt |
| `@c-XX` | 仅候选 `XX` |
| `@everyone` *（或不写寻址）* | 全部参与者 |

动词（**boost**、**penalise**、**eliminate**、**accept**）会触发客户端的镜像效果（例如，**eliminate** 时该候选卡片立即变灰），让操作员的意图在下一条 prompt 实例化之前就已可见。
