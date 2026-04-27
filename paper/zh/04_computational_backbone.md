# 4 Computational Backbone

为完整起见，我们在此概述底层的计算组件；它们都是已有方法，并非本文的贡献。

## 4.1 图模式与消融

记 $G = (V, E, \mathcal{T}, \mathcal{R})$ 为由 CMGPD-LN 诱导出的异质图，其节点类型 $\mathcal{T} = \{\text{person}, \text{household}, \text{community}, \text{banner}\}$，九种边类型 $\mathcal{R}$ 包括父系亲属（$r_{fs}, r_{fd}$）、母系亲属（$r_{ms}, r_{md}$）、共居关系（$r_{hh}, r_{hc}, r_{cb}$），以及带时间戳的婚姻边 $r_{hw}$，其 $\text{edge\_time} = y$（婚姻年份）。

*jiapu-mirroring ablation* 按边类型逐一定义：对于 $r \in \{r_{hw}, r_{ms}, r_{md}\}$，索引张量被替换为一个空的 $2 \times 0$ 张量，但该关系类型仍保留在 $G.\text{metadata}()$ 中。这一不变量 —— *"ablate, don't delete"*（消融而非删除）—— 是必需的，因为按关系的线性投影是注册在 metadata 快照之上的。任何后续的 *temporal subgraph* $G_t$ 还会进一步要求每条边 $e \in E_t$ 满足 $\text{edge\_time}(e) < t$，以防止年份 $t$ 之时尚未出现的队列发生信息泄漏。

## 4.2 HGT encoder 与 marriage scorer

参照 [hu2020hgt]，HGT encoder 的每一层通过沿边类型 $r \in \mathcal{R}$ 对邻居 $u$ 的注意力来更新节点 $v$ 的表示 $h_v^{(\ell+1)}$：

$$
\alpha_{u,v}^{r} = \mathrm{softmax}_u\!\left(
  \frac{\bigl(W^{q}_{\tau(v)} h_v^{(\ell)}\bigr)^{\!\top}\,
        W^{r}_{\mathrm{att}}\,
        \bigl(W^{k}_{\tau(u)} h_u^{(\ell)}\bigr)}
       {\sqrt{d}}
  \cdot \mu_{\tau(u),r,\tau(v)}\right)
$$

$$
h_v^{(\ell+1)} = \mathrm{LN}\!\left(
  h_v^{(\ell)} +
  \sum_{r,u} \alpha_{u,v}^{r}\,
    W^{r}_{\mathrm{msg}}\,W^{v}_{\tau(u)} h_u^{(\ell)}
  \right)
$$

其中 $\tau(\cdot)$ 返回节点类型，$\mu$ 是一个可学习的 relation-prior 张量。在两层 HGT 之后，一个 marriage scorer

$$
\psi(h_m, h_w) = \mathrm{MLP}\bigl([h_m,\, h_w,\, |h_m - h_w|,\, h_m \odot h_w]\bigr)
$$

为每一对候选 $(m, w)$ 输出一个 logit。负样本在队列内（within-cohort）采样，以避免跨年份的捷径。

## 4.3 SEAL motif 抽取

对每一对候选 $(m, w)$，我们抽取其 *enclosing $k$-hop subgraph* $\mathcal{N}_k(m, w)$，并按 [zhang2018seal] 应用 Double-Radius Node Labelling (DRNL) 得到结构指纹 $\phi(\mathcal{N}_k(m, w)) \in \mathbb{N}^{|\mathcal{N}_k|}$。我们在该领域中预先定义了四种具有史学意义的 canonical motif —— $\mathsf{m}_1$ father-brother、$\mathsf{m}_2$ uncle-in-law、$\mathsf{m}_3$ same-household、$\mathsf{m}_4$ banner-endogamy —— 当某个候选的 DRNL 签名与示例的标注子图一致时，认为它命中了 $\mathsf{m}_k$。命中的 motif 集合会一字不差地呈现在 agent 的 persona prompt 中（§6）。

## 4.4 双向 negotiation 的最终得分

给定第 5 回合结束时候选 $i$ 的丈夫侧得分 $t_i \in [0, 10]$ 与妻子侧反向得分 $s_i \in [0, 10]$，第 6 回合的排名遵循

$$
\mathrm{score}_i \;=\; \tfrac{1}{2} (s_i + t_i) \;-\; \lambda\,|s_i - t_i|, \quad \lambda = 0.3.
\tag{1}
$$

这一定义奖励双方互评对称偏高的配置，惩罚不对称的赞同；$\lambda$ 在 V6（§5.7）中暴露给用户，其默认值 0.3 是在形成性访谈中由领域共识确定的。
