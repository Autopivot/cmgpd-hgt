# 4 Computational Backbone

为完整起见，我们在此概述底层的计算组件；它们都是已有方法，并非本文的贡献。

## 4.1 图模式与消融

记 $G = (V, E, \mathcal{T}, \mathcal{R})$ 为由 CMGPD-LN 诱导出的异质图，节点类型 $\mathcal{T} = \{\text{person}, \text{household}, \text{community}, \text{banner}\}$，九种边类型 $\mathcal{R}$ 包括父系亲属（$r_{fs}$ 父→子，$r_{fd}$ 父→女）、母系亲属（$r_{ms}$ 母→子，$r_{md}$ 母→女）、兄弟姊妹（$r_{sib}$）、共居关系（$r_{hh}$ person→household，$r_{hc}$ household→community，$r_{cb}$ person→banner），以及带时间戳的婚姻边 $r_{hw}$，其 $\text{edge\_time} = y$（婚姻年份）。

**Jiapu-mirroring ablation** 按边类型逐一定义：对于 $r \in \{r_{hw}, r_{ms}, r_{md}\}$，索引张量被替换为一个空的 $2 \times 0$ 张量，但该关系类型仍保留在 $G.\text{metadata}()$ 中。这一不变量 —— *"ablate, don't delete"*（消融而非删除）—— 是必需的，因为按关系的线性投影是注册在 metadata 快照之上的。

任何后续的 **temporal subgraph** $G_t$ 还会进一步要求每条边 $e \in E_t$ 满足 $\text{edge\_time}(e) < t$，以防止年份 $t$ 之时尚未出现的队列发生信息泄漏。同样地，对于年份 $t$ 的婚姻队列，训练 / 评测过程中会从消息传递图中**额外**剔除：(i) 年份 $t$ 自身的目标对，(ii) 全部验证集与测试集对，从而避免被预测的边以邻居身份回流到 encoder。

## 4.2 特征工程

**person 节点** 携带五组并联特征，由 `PersonEmbedder` 统一投影到 $d = 128$ 维：

| 张量 | 维度 | 来源 | 处理 |
|---|---|---|---|
| `x_sex` | LongTensor $[N]$ | DS0001 SEX，未知=0 / 女=1 / 男=2 | `nn.Embedding(3, 8)` |
| `x_relationship` | LongTensor $[N]$ | DS0001 RELATIONSHIP，按词频取前 64 类，0 留给 `<UNK>` | `nn.Embedding(64, 16)` |
| `x_continuous` | FloatTensor $[N, 1]$ | 仅 BIRTHYEAR（AGE\_IN\_SUI 因依赖快照年份而被剔除以避免泄漏） | 按列 z-score；缺失位通过显式 mask 保留为 0 而非误判 |
| `x_occupational` | FloatTensor $[N, 3]$ | DS0001 POSITION / TITLE / SALARY 的二值化指示 | 直接拼接 |
| `x_macro` | FloatTensor $[K=5]$，每队列共享 | 对队列年份 $t-1$ 的宏观协变量（见下文） | 在 forward 阶段广播到 $N$ 行 |

`x_macro` 的五个分量来自 DS0009 / DS0011 + 干支编码：
$\textsf{cohort\_year\_z}$（z-scored 年份）、$\textsf{grain\_price\_z}$（DS0009 粮价）、$\textsf{grain\_price\_yoy}$（粮价同比变化）、$\textsf{era\_id}$（清代年号 ID：乾隆=0、嘉庆=1、…、宣统=6）、$\textsf{disaster\_flag}$（DS0011 灾年指示）。它们以 $(n_{\text{years}}, K)$ 的查找表 `macro_table` 形式挂在图对象上，由 `subgraph_at_year(t)` 在生成子图时取第 $t-1$ 行注入到 `person.x_macro`，使协变量与"被打分的队列年份"严格对齐 —— 而非泄漏快照年份的宏观状态。

`PersonEmbedder` 将以上五路拼接为 $8 + 16 + 1 + 3 + 5 = 33$ 维向量后，过一次 $\mathrm{Linear}(33, 128) \to \mathrm{GELU} \to \mathrm{LayerNorm}$ 得到 person 的输入嵌入：
$$
h^{(0)}_v = \mathrm{LN}\!\Bigl(\mathrm{GELU}\bigl(W_{\text{person}}\,[\,e_{\text{sex}}\;\Vert\;e_{\text{rel}}\;\Vert\;x_{\text{cont}}\;\Vert\;x_{\text{occ}}\;\Vert\;x_{\text{macro}}\,]\bigr)\Bigr) \in \mathbb{R}^{128}.
$$

**household 节点**: FloatTensor $[N_{\text{hh}}, 5]$ —— 户内人口规模、近似已婚配对数、世代数、户主是否有 POSITION、最末观测年份归一化值，按列后再过 $\mathrm{Linear}(5, 128) \to \mathrm{GELU} \to \mathrm{LayerNorm}$。

**community 节点**: FloatTensor $[N_{\text{co}}, 1]$ —— 村庄人口归一化，再投影到 128 维。

**banner 节点**: FloatTensor $[N_{\text{ba}}, N_{\text{ba}}]$，单位矩阵形式的 one-hot，再投影到 128 维。

## 4.3 HGT encoder 与 marriage scorer

HGT encoder [hu2020hgt] 的每一层通过沿边类型 $r \in \mathcal{R}$ 对邻居 $u$ 的注意力来更新节点 $v$ 的表示：
$$
\alpha_{u,v}^{r} = \mathrm{softmax}_u\!\left(
  \frac{\bigl(W^{q}_{\tau(v)} h_v^{(\ell)}\bigr)^{\!\top}\,
        W^{r}_{\mathrm{att}}\,
        \bigl(W^{k}_{\tau(u)} h_u^{(\ell)}\bigr)}
       {\sqrt{d / H}}
  \cdot \mu_{\tau(u),r,\tau(v)}\right)
$$
$$
h_v^{(\ell+1)} = \mathrm{LN}\!\left(
  h_v^{(\ell)} + \mathrm{Dropout}_p\!\Bigl(
  \sum_{r,u} \alpha_{u,v}^{r}\,
    W^{r}_{\mathrm{msg}}\,W^{v}_{\tau(u)} h_u^{(\ell)}\Bigr)
  \right)
$$
其中 $\tau(\cdot)$ 返回节点类型，$\mu \in \mathbb{R}^{|\mathcal{T}| \times |\mathcal{R}| \times |\mathcal{T}|}$ 为可学习的 relation-prior 张量，残差 + LayerNorm + dropout 包络 conv 输出（任何被 conv 漏掉的节点类型则回退到 $h_v^{(\ell)}$ 本身）。我们采用 PyG 的 `HGTConv` 实现。

**超参数**（`config.py` 单一来源）：隐藏维度 $d = 128$、层数 $L = 2$、注意力头数 $H = 4$、dropout $p = 0.2$、$|\mathcal{T}| = 4$、$|\mathcal{R}| = 9$。

经过 $L$ 层之后，对每一对候选 $(m, w)$ 由 marriage scorer
$$
\psi(h_m, h_w) = W_2\,\mathrm{Dropout}_p\!\bigl(\mathrm{GELU}(W_1\,[\,h_m\;\Vert\;h_w\;\Vert\;|h_m - h_w|\;\Vert\;h_m \odot h_w\,])\bigr) \in \mathbb{R}
$$
输出 logit，其中 $W_1 \in \mathbb{R}^{128 \times 512}$、$W_2 \in \mathbb{R}^{1 \times 128}$，输入是 $4d = 512$ 维的对偶交互向量。

## 4.4 训练流程

每个 epoch 内将训练年份打乱后，每次取 `BATCH_YEARS = 4` 个队列年份组成一个优化器 step。对每个队列年份 $t$ 调用 `subgraph_at_year(t, drop = train[t] ∪ all_val_pairs ∪ all_test_pairs)` 构造消息传递图（同时强制 $\text{edge\_time} < t$，并屏蔽掉年份 $t$ 自身的目标边以及全部验证 / 测试边，详见 §4.1 末段）；然后对 $t$ 队列的所有正样本对 $(m, w)$ 与每个正样本 `NEG_PER_POS = 4` 个**同队列内**采样得到的负样本 $(m, w')$ 一起，采用按对的二元交叉熵：
$$
\mathcal{L} \;=\; -\,\frac{1}{|\mathcal{B}|} \sum_{(m, w, y) \in \mathcal{B}} \Bigl[\,y\,\log\sigma(\psi(h_m, h_w)) \;+\; (1 - y)\,\log\bigl(1 - \sigma(\psi(h_m, h_w))\bigr)\Bigr].
$$
跨年份采样的负样本在该面板上过于平凡（远离正样本几何位置）会显著抬高度量；同队列负样本这一选择是由数据特性驱动而非工程偏好。

**优化**：AdamW，学习率 $\eta = 10^{-3}$，权重衰减 $10^{-2}$，梯度裁剪范数上限 1.0，训练 30 epoch。每个 epoch 末在验证集上以**逐队列 Hungarian recall@1** 选择最优；ablated 与 unablated 两条训练通道保存为独立 checkpoint（`best_ablated.pt` / `best_unablated.pt`）—— 一个仅在被消融图上训练得到的模型，对 $r_{ms} / r_{md}$ 的关系投影是随机初值，在未消融图上推理时会输出无意义的 delta，因此两套权重必须各自配对自己的图变体。

## 4.5 SEAL motif 抽取

对每一对候选 $(m, w)$，我们抽取其 *enclosing $k$-hop subgraph* $\mathcal{N}_k(m, w)$，并按 [zhang2018seal] 应用 Double-Radius Node Labelling (DRNL) 得到结构指纹 $\phi(\mathcal{N}_k(m, w)) \in \mathbb{N}^{|\mathcal{N}_k|}$。我们在该领域中预先定义了四种具有史学意义的 canonical motif —— $\mathsf{m}_1$ father-brother、$\mathsf{m}_2$ uncle-in-law、$\mathsf{m}_3$ same-household、$\mathsf{m}_4$ banner-endogamy —— 当某个候选的 DRNL 签名与示例的标注子图一致时，认为它命中了 $\mathsf{m}_k$。命中的 motif 集合会一字不差地呈现在 agent 的 persona prompt 中（§6）。

## 4.6 双向 negotiation 的最终得分

给定第 5 回合结束时候选 $i$ 的丈夫侧得分 $t_i \in [0, 10]$ 与妻子侧反向得分 $s_i \in [0, 10]$，第 6 回合的排名遵循
$$
\mathrm{score}_i \;=\; \tfrac{1}{2} (s_i + t_i) \;-\; \lambda\,|s_i - t_i|, \quad \lambda = 0.3.
\tag{1}
$$
这一定义奖励双方互评对称偏高的配置，惩罚不对称的赞同；$\lambda$ 在 V6（§5.7）中暴露给用户，其默认值 0.3 是在形成性访谈中由领域共识确定的。
