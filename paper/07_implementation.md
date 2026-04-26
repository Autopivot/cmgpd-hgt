# 7 Implementation

**[SYSTEM]** comprises ≈ 9.5 k LOC:

- a **Python pipeline** (`NEW/src/`, ≈ 2.4 k LOC) implementing the four training stages;
- a **FastAPI backend** (`NEW/viz-mas/server/`, ≈ 2.1 k LOC) hosting the cohort / profile / narrative endpoints, the WebSocket fan-out, and the `negotiator_rounds` orchestrator;
- a **Vue 3 + Vite frontend** (`NEW/viz-mas/src/`, ≈ 5.0 k LOC).

HGT training uses PyTorch + PyTorch Geometric. LLM calls are routed to the DashScope OpenAI-compatible endpoint with model `qwen-plus-2025-04-28`; a deterministic stub agent provides a zero-key fallback so the protocol remains exercisable offline. DS0003 narratives are joined to DS0001 by `RECORD_NUMBER` (1:1 over 1,513,357 rows) and persisted as a parquet for sub-second per-person lookup.
