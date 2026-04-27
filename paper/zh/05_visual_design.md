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

V3 承担 cohort-as-canvas 这一需求（DG1）。整个视图由四阶计算流程加四层叠加渲染构成。

### 5.4.1 配对嵌入 pipeline（上游，Python 端）

对每一对测试配对 $(m, w)$ 我们先构造其 128 维的 *配对交互向量*

$$
z_{m,w} \;=\; W_1\,[\,h_m\,\Vert\,h_w\,\Vert\,|h_m - h_w|\,\Vert\,h_m \odot h_w\,] \;\in\; \mathbb{R}^{128}
$$

—— 这恰好是 marriage scorer（§4.3）的第一层隐藏激活，因此 V3 的几何与驱动 ranking 的同一表征严格锚定。我们额外从训练桶（train bucket）中采样最多 $S = 1000$ 个正样本配对，使其经过同一 scorer 投影头；记 $Z_{\text{test}} \in \mathbb{R}^{n \times 128}$、$Z_{\text{train}} \in \mathbb{R}^{S \times 128}$。

我们在二者拼接后**统一拟合一个 MDS 坐标系**：
1. 对 $Z = [Z_{\text{test}};\,Z_{\text{train}}]$ 按列做标准化（零均值、单位方差）；
2. 通过 PCA 降至 $r = \min(50,\,n+S,\,128)$ 个分量；
3. 形成 $(n+S) \times (n+S)$ 欧式距离不相似度矩阵 $D_{ij} = \|z^{\text{PCA}}_i - z^{\text{PCA}}_j\|_2$，按 $(D + D^\top)/2$ 对称化、对角清零；
4. 以 $D$ 为预先算好的 dissimilarity 拟合 metric MDS（`n_init=1, max_iter=200, normalized_stress="auto", random_state=0`）至 2 维；结果矩阵的前 $n$ 行即为该队列坐标 $\hat{u}_i \in \mathbb{R}^2$，后 $S$ 行作为 *训练参考背景*，被前端渲染为密度热力图叠在画布之下。

联合拟合是关键：它把测试与训练放进 *同一个* 二维坐标系，使热力图在三种模式下保持可比。簇标签则在 PCA 后的潜空间 $z^{\text{PCA}}$ 上而非 MDS 空间上计算（MDS 的微小畸变会污染边界），采用以 BIC 为分裂准则的 X-means、上界 $k_{\max} = 10$；当 `pyclustering` 不可用时回退至以 silhouette 在 $K \in [2, \min(k_{\max}, \lfloor n/5 \rfloor)]$ 范围内择优的 K-means。$\hat{u}_i$ 与簇标签 $\kappa_i \in \{0, \dots, K-1\}$ 一并写入前端读取的 cohort JSON。

### 5.4.2 坐标归一化

原始 MDS 坐标常有少数极端离群值，把 $\min/\max$ 上下界拉开 3–5 倍，以致 90% 配对挤在画布的 6% 区域里。我们改用 2nd–98th 百分位边界裁剪后再映射到单位方阵：

$$
u_{i,j} \;=\; \mathrm{clip}\!\left(\frac{\hat{u}_{i,j} - q_{2}(\hat{u}_{:,j})}{q_{98}(\hat{u}_{:,j}) - q_{2}(\hat{u}_{:,j})},\; 0,\; 1\right), \quad j \in \{x, y\}.
$$

scatter 模式与背景热力图重用同一组百分位边界，使三种前景模式共享同一坐标系。

### 5.4.3 Flat-top 六边形网格

我们用以归一化坐标度量的 flat-top 正六边形（外接圆半径 $R = 0.04$，约 750 px 画布上的 30 px）平铺 $[0,1]^2$。每个单元由轴向偏移坐标 $(q, r)$ 寻址：

$$
\textsf{cx}(q, r) \;=\; 1.5R\,q, \qquad
\textsf{cy}(q, r) \;=\; \sqrt{3}\,R\,r \;+\; \begin{cases} \tfrac{\sqrt{3}}{2}R & q \text{ 奇} \\ 0 & q \text{ 偶} \end{cases},
$$

即 odd-$q$ 偏移：列步长 $1.5R$，行步长 $\sqrt{3}\,R$。单元 $(q, r)$ 的六个顶点为 $(\textsf{cx} + R\cos\theta_k,\; \textsf{cy} + R\sin\theta_k)$，$\theta_k = k\pi/3$，$k = 0, \dots, 5$。我们保留一倍半径的边距，使中心略在 $[0,1]^2$ 之外但内部仍切到画布的格子被保留。在 $R = 0.04$ 时该网格约有 350–500 单元，规模小到「线性扫描求最近格」比构建 KD-tree 更快。

`cluster-borders` 所需的邻接表预先建好一次：单元 $(q, r)$ 的六个轴向邻居为

$$
\mathcal{N}(q, r) \;=\; (q, r) \;\oplus\;
\begin{cases}
\{(+1,0),(+1,-1),(0,-1),(-1,-1),(-1,0),(0,+1)\} & q \text{ 偶} \\
\{(+1,+1),(+1,0),(0,-1),(-1,0),(-1,+1),(0,+1)\} & q \text{ 奇}.
\end{cases}
$$

### 5.4.4 迭代 inward-attraction packer

每对配对 $i$ 都有归一化位置 $u_i$、簇标签 $\kappa_i$，以及一个目标 *簇质心* $c_{\kappa_i} = \mathbb{E}_{j:\,\kappa_j = \kappa_i}[u_j]$。把配对装入 hex 单元的过程满足三条约束：

- **(C1) 同簇单元**：每个单元至多容纳一种簇的点；
- **(C2) 容量**：每个单元至多容纳 $C = 12$ 个点；
- **(C3) 簇紧凑性**：每个簇的单元应在 $c_\kappa$ 附近形成连片岛屿。

算法（Algorithm 2）：按 $\|u_i - c_{\kappa_i}\|_2$ 升序排序所有配对，使每个簇最稠密的核心率先入位、占据中心 hex；离群点向外扩散。

```
for each i in order:
    p ← u_i;  cl ← κ_i;  c ← c_cl;  placed ← False

    # ── 内向吸引（向质心几何级数收敛）──
    for it = 1 .. 50:
        p ← (p + c) / 2                          # 每轮缩半
        cell ← argmin_{cells} ||p - centre(cell)||²
        if cell.occupants < C ∧ (cell.cluster ∈ {None, cl}):
            cell.add(i);  placed ← True;  break

    # ── 外向径向螺旋回退 ──
    if not placed:
        radius ← 2R;   angle ← Uniform(0, 2π)
        for it = 1 .. 200:
            p ← c + (radius·cos angle, radius·sin angle)
            cell ← argmin_{cells} ||p - centre(cell)||²
            if cell.occupants < C ∧ (cell.cluster ∈ {None, cl}):
                cell.add(i);  placed ← True;  break
            angle ← angle + 0.7         # 旋转约 40°
            if it mod 8 == 7: radius ← radius + 2R   # 阿基米德步进

    # ── 兜底扫描（实际很少触发）──
    if not placed:
        for cell in cells:
            if cell.occupants < C ∧ (cell.cluster ∈ {None, cl}):
                cell.add(i);  break
```

内向回路的折半步长有闭式上界：$t$ 轮后 $\|p^{(t)} - c\| = 2^{-t}\,\|u_i - c\|$，因此在 6–7 轮内候选位置就稳定地落入质心所在的 hex。外向回退实际上是一条围绕质心的阿基米德螺旋 $r(\theta) = 2R\,(1 + \lfloor\theta/(8 \cdot 0.7)\rfloor)$；$0.7\,\text{rad}$ 的角步长约等于半径 $2R$ 处一个 hex 所张的角，使每条同心环在外推前都被均匀覆盖。

### 5.4.5 单元聚合量

对每个非空单元（占据者集合 $P_c$）我们计算四个诊断聚合：

$$
\textsf{meanScoreGap}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathrm{gap}(p),
\qquad
\textsf{posRatio}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathbb{1}[\mathrm{label}(p) = 1],
$$
$$
\textsf{patriPathMean}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathrm{patriPathCount}(p),
\qquad
\textsf{sameLinFrac}_c = \frac{1}{|P_c|}\sum_{p \in P_c} \mathbb{1}[\mathrm{sameLineage}(p)].
$$

`meanScoreGap` 驱动发散填色；`posRatio` 驱动 outlier 条纹叠层；`patriPathMean` 与 `sameLinFrac` 在 tooltip 中暴露给单元级 inspection。

### 5.4.6 渲染层与视觉编码

层 1 —— **hex 单元**。单元填色按 `meanScoreGap` 走三段式发散色阶，以 $\pm 2$ logits 为锚，在 sRGB 中线性插值：

$$
\mathrm{color}(v) = \begin{cases}
\mathrm{lerp}(\mathsf{COLOR\_LOW},\,\mathsf{COLOR\_MID},\,(v + 2)/2) & -2 \le v < 0 \\
\mathrm{lerp}(\mathsf{COLOR\_MID},\,\mathsf{COLOR\_HIGH},\,v/2) & 0 \le v \le +2 \\
\mathsf{COLOR\_LOW} & v < -2 \\
\mathsf{COLOR\_HIGH} & v > +2
\end{cases}
$$

其中 $\mathsf{COLOR\_LOW} = \texttt{\#993c1d}$（terracotta）、$\mathsf{COLOR\_MID} = \texttt{\#f5f1e8}$（cream）、$\mathsf{COLOR\_HIGH} = \texttt{\#0f6e56}$（sage）。$\pm 2$ 的锚点是有意为之：单对 $\mathrm{gap} \in [-13, +13]$，但单元均值因平均了至多 12 个对而集中分布于 $[-2, +2]$；早期试运行表明，更宽的锚会把发散信号压成大片中性色。

层 2 —— **outlier 条纹**。设 $\mu = \mathbb{E}[\textsf{posRatio}_c]$、$\sigma = \mathrm{Std}[\textsf{posRatio}_c]$（在所有非空单元上估计）。满足 $|\textsf{posRatio}_c - \mu| > 2\sigma$ 的单元叠加 45° 旋转的对角条纹（4 px 周期、1.5 px 描边、60% 不透明度），在不破坏底层填色的情况下标记结构性偏多/偏少正样本的簇内口袋。

层 3 —— **簇边界**。对每对邻居 $(c_a, c_b) \in \mathcal{N}$，若 $\mathrm{cluster}(c_a) \ne \mathrm{cluster}(c_b)$ 且两者皆非空，则绘制其共享边 —— 即两个多边形共有的两个顶点，由 $\varepsilon = 10^{-6}$ 的坐标匹配在投影后的顶点集合上找出。

层 4 —— **散点叠层**（仅 `scatter` 与 `mixed` 模式）。每对一点，绘于 $u_i$ 处（在 `mixed` 模式下绘于 $\textsf{centre}(\textsf{cell}(i)) + \delta_i$，$\delta_i$ 是单元内的确定哈希抖动）；同一发散色阶按单对 $\mathrm{gap}$ 着色，跨模式可读。模式开关给出三种读法：
- **`honeycomb`** —— 一眼可读簇及其密度；
- **`scatter`** —— 单对噪声可见；
- **`mixed`** —— hex 透明度降到 0.55、点叠加；可在不丢失簇上下文的同时下钻到具体配对。

### 5.4.7 选择与已接受配对的遮蔽

点击 hex（或一个点、或 scatter 模式下的套索 brush）即选中相应配对，发出 `hex-select`；V4 与 V5 随之响应。表头中的 *score gap* 发散图例（$-2 \dots +2$）使色阶不言自明。重要的是，V3 会 *遮蔽* 那些 $(h, w)$ 配对已落入 running accepted set 的点，并在 `match-restored` 时恢复其完整色阶 —— 画布在任意时刻所反映的，是「还剩下什么待提交」，而非静态的 HGT 预测。

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
