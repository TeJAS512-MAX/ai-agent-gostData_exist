# HackerRank Orchestrate: Autonomous AI Agent Architecture

A production-grade, state-machine driven autonomous AI agent engineered specifically for the **HackerRank Orchestrate Hackathon**. Built to achieve maximum scores across all four evaluation pillars: **Code Architecture**, **Output Precision**, **AI Fluency**, and **The AI Judge Defense**.

---

## 🏛️ Architecture Overview

The system implements a deterministic, multi-stage **LangGraph** state machine with dual-layer adversarial guardrails and hybrid grounding.

```
                    ┌─────────────────────────┐
                    │      Incoming Ticket    │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Security Guardrail    │
                    │  (Injection & Jailbreak)│
                    └────────────┬────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
        [Threat Detected]                 [Input Safe]
                 │                               │
                 ▼                               ▼
    ┌─────────────────────────┐     ┌─────────────────────────┐
    │ Immediate Action:       │     │     Hybrid Retrieval    │
    │ BLOCKED / ESCALATE      │     │  (BM25 + Semantic RAG)  │
    └────────────┬────────────┘     └────────────┬────────────┘
                 │                               │
                 │                               ▼
                 │                  ┌─────────────────────────┐
                 │                  │     Reasoning Node      │
                 │                  │  (Strict Grounding)     │
                 │                  └────────────┬────────────┘
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │    Output Validation    │
                    │   (Pydantic & CSV Schema)│
                    └─────────────────────────┘
```

---

## 🎯 Evaluation Pillars Addressed

### 1. Code & Architecture (The Repository)
- **Separation of Concerns:** Isolated modules for Security (`src/security`), Retrieval (`src/retrieval`), Agent Logic (`src/agent`), and Validation (`src/evaluation`).
- **Dual-Layer Injection Defense:** Regex delimiter sanitization + semantic boundary containment to prevent instruction override attacks.
- **Hybrid Grounding:** Combines **RankBM25** (exact error code, SKU, and policy ID matching) with semantic document chunking to eliminate hallucinations.
- **Deterministic Fallbacks:** Fallback heuristics guarantee that even during upstream API outages or ambiguous context, decisions fail safely to `escalated`.

### 2. Output Accuracy (The CSV Evaluation)
- Built-in `src/evaluation/validator.py` guarantees strict compliance with expected columns:
  `ticket_id,action,priority,category,citation_id,response_summary`
- Type and enum validation prevent invalid fields or null values.

### 3. AI Collaboration Transcripts
- Run `python export_transcript.py` to automatically generate `outputs/chat_transcript.md` and `outputs/log.txt` demonstrating iterative prompt engineering and AI collaboration.

### 4. AI Judge Defense
- See [JUDGE_INTERVIEW_PREP.md](JUDGE_INTERVIEW_PREP.md) for pre-formulated justifications of every architectural decision, failure mode, and system trade-off.

---

## 🚀 Quickstart Guide

### 1. Configure Environment
Copy `.env.example` to `.env` and insert your API key:
```powershell
cp .env.example .env
```
Supported providers: Google Gemini, OpenAI, Groq, Anthropic, or local offline mode.

### 2. Interactive Testing
Test single tickets in real time through the terminal interface:
```powershell
python main.py
```

### 3. Run Benchmark on Dataset
Process test dataset, generate `outputs/output.csv`, and run automated schema validation:
```powershell
python run_benchmark.py --input data/raw/sample_tickets.csv --output outputs/output.csv
```

### 4. Export AI Transcript for Submission
```powershell
python export_transcript.py
```

