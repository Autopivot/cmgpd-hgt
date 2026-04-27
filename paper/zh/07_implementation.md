# 7 Implementation

**[SYSTEM]** 共约 9.5 k LOC：

- 一条 **Python pipeline**（`NEW/src/`，约 2.4 k LOC），实现四个训练阶段；
- 一套 **FastAPI backend**（`NEW/viz-mas/server/`，约 2.1 k LOC），承载 cohort / profile / narrative 端点、WebSocket fan-out，以及 `negotiator_rounds` 编排器；
- 一套 **Vue 3 + Vite frontend**（`NEW/viz-mas/src/`，约 5.0 k LOC）。

HGT 训练使用 PyTorch + PyTorch Geometric。LLM 调用路由到 DashScope 提供的 OpenAI 兼容端点，模型为 `qwen-plus-2025-04-28`；同时提供一个确定性的 stub agent 作为零密钥（zero-key）回退，使协议在离线状态下仍可被走通。DS0003 narratives 通过 `RECORD_NUMBER` 与 DS0001 一对一连接（在 1,513,357 行上 1:1），并以 parquet 持久化，从而实现亚秒级的按人查询。
