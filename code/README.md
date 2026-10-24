# Northstar Shop Deletion Audit Agent — NSTVE v2.0
# Architecture Documentation & Evaluation Guide

**Challenge:** HackerRank Orchestrate (October 2026) — *Ghost Data Still Exists*  
**URL:** `https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists`  
**Architecture:** 7-Stage Neuro-Symbolic Temporal Verification Engine (NSTVE)  
**Golden Benchmark:** **100.00% Case Status Accuracy (32/32)**

---

## 1. Architecture Overview: The 7-Stage NSTVE

```text
DELETE REQUEST
     │
     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Stage 1: Semantic Intent Gate                  engine/intent_gate.py   │
│  0-token regex + optional LLM micro-classifier                          │
│  → NOT_APPLICABLE (short-circuit) or DELETION intent                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Stage 2: Transitive Identity Closure           engine/identity_graph.py│
│  Union-Find (DSU) across user_identities + user_audit_log               │
│  → Immutable IdentityFootprint (emails, phones, names, SHA-256/MD5)     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────┼─────────────┐
                    │            │              │
                    ▼            ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌───────────────────────────────────┐
│  Stage 3     │  │  Stage 4     │  │  Stage 4 (cont.)                  │
│  Temporal    │  │  SQL: SQLite │  │  JSON: AST traversal              │
│  DAG         │  │  in-memory   │  │  Log: substring scan              │
│  (Petri Net) │  │  0-token     │  │  PDF: pypdf text                  │
│  temporal_   │  │  evidence_   │  │  Image: OCR cache → VLM fallback  │
│  dag.py      │  │  transducer  │  │                                   │
└──────┬───────┘  └──────┬───────┘  └──────────────────┬────────────────┘
       │                 │                              │
       └─────────────────┴──────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Stage 5 + 6: Symbolic SMT Policy Solver        engine/policy_solver.py │
│  Evaluates deletion_rules.csv against all evidence observations          │
│  Bijective remediation synthesis (1 FINDING → 1 REMEDIATION + VERIFYs) │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Stage 7: Canonical Tuple Compiler              engine/canonical_compiler│
│  Deduplication → canonical sort → step_no → assertion gate              │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
                          output.csv (518 rows)
```

### Module Responsibilities

| Stage | File | Responsibility | Token Cost |
|:---|:---|:---|:---:|
| 1 | `engine/intent_gate.py` | Regex + LLM binary classifier | 0 (regex) / ~5 (LLM fallback) |
| 2 | `engine/identity_graph.py` | Union-Find transitive identity closure | 0 |
| 3 | `engine/temporal_dag.py` | Bi-temporal DAG, Petri-Net flow/restore risk | 0 |
| 4 | `engine/evidence_transducer.py` | Multimodal evidence ingestion (SQL/JSON/Log/PDF/Image) | 0 (symbolic) / variable (VLM) |
| 5+6 | `engine/policy_solver.py` | Policy evaluation + bijective remediation synthesis | 0 |
| 7 | `engine/canonical_compiler.py` | Dedup, sort, step_no, assertions | 0 |
| Orch. | `engine/nstve.py` | 7-stage orchestration + proven engine integration | 0 |
| CLI | `main.py` | Batch CLI entry point with progress reporting | 0 |

---

## 2. Installation & Setup

### Prerequisites
- Python 3.10+
- Pip

### Install
```bash
pip install -r requirements.txt
```

**No API keys required for deterministic production mode.** All 11 visual evidence artifacts are pre-transcribed in `dataset/evidence/images_ocr_cache.json`. The Stage 1B LLM fallback and Stage 4 VLM paths are disabled by default and only activate with `OPENROUTER_API_KEY` or `GEMINI_API_KEY` set in environment.

---

## 3. Running the Agent

From the repo root:
```bash
python main.py \
    --input  dataset/deletion_requests.csv \
    --output output.csv \
    --dataset-dir dataset
```

Or from within `code/`:
```bash
python main.py \
    --input  ../dataset/deletion_requests.csv \
    --output ../output.csv \
    --dataset-dir ../dataset
```

| Flag | Description | Default |
|:---|:---|:---|
| `--input` | Deletion requests CSV | `dataset/deletion_requests.csv` |
| `--output` | Output CSV path | `output.csv` |
| `--dataset-dir` | Dataset root directory | `dataset` |

### Reproducibility

The production run is **100% deterministic**:
- All evidence parsing uses in-memory SQLite, JSON AST traversal, and regex — no external calls.
- OCR results for all 11 PNG screenshots are pre-cached in `dataset/evidence/images_ocr_cache.json`.
- Stage 1B LLM fallback and Stage 4 VLM paths are explicitly disabled in production mode.
- Re-running `python main.py` on the same inputs always produces bit-identical `output.csv`.

---

## 4. Running the Evaluator

```bash
python evaluation/evaluator.py \
    --predictions output.csv \
    --ground-truth dataset/sample_output.csv
```

---

## 5. Golden Benchmark Performance

| Metric | Achieved |
|:---|:---:|
| Case Status Accuracy (32 samples) | **100.00%** (32/32) |
| Exact Sequence Match | **62.50%** (20/32) |
| Step-Level Tuple Accuracy | **88.60%** (171/193) |
| Phase Accuracy | **100.00%** |
| Evidence Citation Accuracy | **100.00%** |
| Full Dataset Execution (518 cases) | **~5.8 seconds** |
| Total Financial Cost | **\$0.0000** |

---

## 6. Key Design Decisions

### Why Symbolic ≫ Neural for Final Verdicts
LLMs are excluded from all final policy decisions, step sorting, and evidence citations. They are constrained to:
1. **Stage 1B**: Binary intent classification (5 output tokens max).
2. **Stage 4 VLM**: Verbatim-grounded structured extraction from images/PDFs when symbolic text extraction fails.

### Tombstone Semantics
Per `rule_15`, account tombstones (identity_service) retain a stable `user_id` reference. The policy solver checks for prohibited PII tokens (email, name, phone, hash) in the raw observation text. A `REDACTED` state means the tombstone is compliant; `PRESENT` with PII tokens → `REPORT_EXPOSED_PII` finding.

### Trace-Level Log Disambiguation
Multi-line distributed log entries sharing a `trace_id` are merged before state resolution. This ensures `http_status=404` or `rows=0` from a completion log is correctly joined to the identity lookup that initiated it.

### Batch-Window Account ID Correlation
When the account ID cannot be directly resolved from evidence, the agent correlates it to the deletion_worker activity batch window around `reported_at`, using the temporal order of concurrent cases sharing the same `reported_at` to match accounts deterministically.

---

## 7. AI Interview Defense Guide

**Q: Why not use GPT-4o/Claude for all steps?**  
A: Non-deterministic LLMs hallucinate evidence IDs, misorder JSON arrays, and can fabricate step numbers. Our SMT policy solver and canonical tuple compiler enforce strict invariants (no hallucination possible) at 0 token cost.

**Q: How do you handle ghost data in secondary systems?**  
A: Stage 4 (Evidence Transducer) ingests all 94 evidence files in parallel using format-specific 0-token parsers. The Stage 3 Temporal DAG evaluates every active sync/restore pipeline to catch ghost-data recreation risks proactively.

**Q: How is ordering guaranteed?**  
A: Stage 7 (Canonical Compiler) sorts by a strict 4-tuple key `(Phase_Rank, Operation_Rank, system_id ASC, resource_id ASC)` and assigns consecutive `step_no` values, then runs assertion checks before writing output.

**Q: How is multilingual intent handled?**  
A: Stage 1A uses Unicode-safe regex patterns covering Portuguese, French, Spanish, German, Japanese, Korean, and Arabic deletion keywords. For truly ambiguous requests, Stage 1B invokes a lightweight LLM with a 5-token binary output schema.
