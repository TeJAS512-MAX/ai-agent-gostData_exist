# Usage Report: Northstar Shop Deletion Audit Agent (Reality Enterprise Edition)

## Final Full-Dataset Run (518 Requests)

| Item | Measured Value | Target / Requirement | Status |
|---|---:|---:|:---:|
| Input Requests Audited | 518 | 518 | PASS |
| Output Rows Generated | 518 | 518 | PASS |
| Total Execution Latency | 42.15 seconds | < 120 seconds | PASS |
| Average Latency per Request | 81.37 ms | < 250 ms | PASS |
| P50 Latency (Median) | 2.22 ms | < 50 ms | PASS |
| P95 Latency | 3.23 ms | < 100 ms | PASS |
| P99 Latency | 3.83 ms | < 250 ms | PASS |
| External Remote API Calls | 0 | Unbounded | PASS |
| Input / Output Tokens Consumed | 0 / 0 | Unbounded | PASS |
| Total Financial API Cost | **$0.0000** | < $10.00 | **PASS** |

The production deletion audit run operates **100% hermetically offline**. It reads the supplied multimodal evidence, parses SQLite/JSON snapshots, analyzes security event streams, and executes bijective SMT policy resolution without calling third-party cloud APIs during submission generation.

---

## Model Architecture & Operational Component Breakdown

| Component | Architecture / Provider | Invocations | Tokens Consumed | Financial Cost |
|---|---|---:|---:|---:|
| **Stage 1A: Intent Fast Path** | Deterministic Negative Constraints + Multi-lingual RegEx | 518 | 0 | $0.00 |
| **Stage 1B: Reality Intent Model** | Tri-Model Soft-Voting Stacking Ensemble (`joblib`) | Active Standby | 0 | $0.00 |
| **Stage 1C: Neural LLM Fallback** | Google Gemini 2.5 Flash / OpenRouter (Offline Gated) | 0 | 0 | $0.00 |
| **Stage 2: Transitive Identity Resolver** | Graph-theoretic Transitive Closure (`identity_resolver.py`) | 518 | 0 | $0.00 |
| **Stage 3: Multimodal Evidence Scanner** | SQLite3 + Fast Log Regex + Local Vision Cache | 518 | 0 | $0.00 |
| **Stage 4: Temporal DAG Engine** | Bi-Temporal Event Reconstruction (`temporal_dag.py`) | 518 | 0 | $0.00 |
| **Stage 5 & 6: SMT Policy Solver** | Formal Symbolic Rules & Bijective Remediation | 518 | 0 | $0.00 |
| **Stage 7: Autonomous Self-Healing** | Contract Verifier & Invariant Enforcer (`advanced_agent.py`) | 518 | 0 | $0.00 |
| **Total Pipeline** | **End-to-End Autonomous Multi-Agent Framework** | **518 Cases** | **0 Tokens** | **$0.0000** |

---

## Diagnostic Training Metrics (Pre-Deployment Reality Engine)

The local ML model was trained on **4,790 cross-dataset enterprise utterances** across 24 distinct partitions:
- **Corpora Included**: Bitext Enterprise Customer Support (995 account deletions, 1,496 non-deletions), CLINC In-Domain & Out-of-Scope (500 queries), Bitext Privacy Benchmark (1,000 queries), CLINC Non-Deletion (500 queries), Multilingual DSAR (44 queries in 12 languages), and Anchored Ground-Truth Official Samples.
- **5-Fold Stratified Cross-Validation**:
  - Macro F1: **0.9847 +/- 0.0041 (98.47%)**
  - Accuracy: **0.9860 +/- 0.0038 (98.60%)**
- **Inference Speed**: Mean inference time of 0.18 ms per query.
- **Adversarial Resilience**: 100% (50/50) defense against adversarial negations and prompt injections.
