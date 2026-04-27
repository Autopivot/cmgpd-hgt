# 10 Discussion and Limitations

**超越 CMGPD-LN 测试平台的泛化。** [SYSTEM] 在 CMGPD-LN —— 一份清代三年一造的行政面板，其稠密的按人字段为每一项设计决策的打分提供了所需的真值 —— 上得到验证；但部署目标是真实的中国家谱（jiapu，家谱），那里女性记录缺失才是真正的问题，而真值无从获得。真实家谱所携带的按人证据远比 CMGPD-LN 面板稀疏，persona prompt 在字段缺失时必须能够优雅降级。我们的 event-block 与 income-block 格式化器已经能在不打断 LLM 调用的前提下渲染 `(no events on register)`；面向合成稀疏度面板的字段级消融研究，是「测试平台到家谱」轨迹上接下来的直接一步。

**LLM provenance 的可审计性。** 尽管按回合的 transcript 都被一字不差地保留下来，但模型输出仍可能听起来合理却并不正确。我们的防御性设计将编排器与任何单次糟糕的调用隔离开（按调用的 try / except + 启发式回退），但要做到完全可审计的语料，则需要为每一次调用的 prompt + response 配对附加密码学证明（cryptographic attestations），而我们尚未做到这一点。

**单一文化先验。** 清代 persona prompt 显式嵌入了 banner endogamy 与 lineage-continuity 价值取向。把同一套 prompt 模板复用于另一种父系社会（韩国、越南、其它地区的汉人）将需要重新设计这些默认值；DG3 之所以这样写，正是为了把这一点显式呈现出来，使 prompt 模板成为本设计的一等制品。

**计算成本边界。** 在 DashScope 端点上，使用 `qwen-plus-2025-04-28` 对六位候选进行一轮六回合的真实 Qwen negotiation 大约耗时 30–45 秒。界面之所以仍然响应迅速，是因为第 1 回合 personas 与第 2–5 回合 answers 都通过 `asyncio.gather` 并行派发；尽管如此，对于高置信度案例，V4 的 batch 提交仍然是更合适的入口，V5 则保留给值得审议的案例。
