# Northstar Shop AI-Powered Deletion Audit Agent

**Competition:** HackerRank Orchestrate (October 2026) — *Ghost Data Still Exists*  
**Organization:** Northstar Shop Privacy Engineering & Governance  
**Challenge URL:** `https://wwww.hackerrank.com/contests/hackerrank-orchestrate-october26/challenges/ghost-data-still-exists`  

---

## 1. Overview

Northstar Shop faced severe financial and regulatory exposure after a supposedly deleted customer resurfaced as a "ghost" in its distributed production systems. What appeared as a simple signup error exposed widespread retention across secondary databases, support attachments, search indexes, analytics exports, access logs, and active synchronization pipelines.

This repository provides an autonomous, deterministic, multimodal **Deletion Audit Agent** capable of proving whether a customer's personal data has been completely and irreversibly eradicated across all systems, or whether ghost data, exposed PII, active sync jobs, or restore risks persist.

### Key Capabilities
- **Multimodal Evidence Ingestion:** Ingests SQL snapshots, JSON data lakes, structured access logs, PDF support documents, and terminal/screenshot images (via OCR cache).
- **Identity Resolution & Alias Graphs:** Reconstructs historical email changes, phone numbers, full names, account tombstones, and SHA-256 email hashes across user audit logs.
- **Trace-Level Log Disambiguation:** Correlates multi-line distributed access logs sharing trace IDs to connect lookup queries with outcome response codes.
- **Deterministic Regulatory Policy Enforcement:** Applies all 15 operational deletion rules (`deletion_rules.csv`) governing account tombstones, security audit log retentions, search indexes, CRM backups, and marketing sync pipelines.
- **Zero Hallucination Remediation & Verification Sequencing:** Automatically generates strictly ordered finding, remediation, and verification steps complying with the required phase order (`FINDING` $\to$ `REMEDIATION` $\to$ `VERIFICATION`) and operation hierarchies.

---

## 2. Directory Structure

```text
code/
├── main.py                      # CLI entry point for batch auditing
├── requirements.txt             # Python dependencies
├── README.md                    # Project documentation & operational guide
├── engine/
│   ├── __init__.py
│   ├── audit_engine.py          # Core policy engine, tombstone checker & sequencer
│   ├── evidence_scanner.py      # Multimodal evidence parser (SQL, JSON, Log, PDF, Image)
│   ├── identity_resolver.py     # User identity graph & historical alias resolution
│   └── request_classifier.py    # Multilingual intent classifier with negative constraints
└── evaluation/
    ├── evaluation_report.md     # Detailed benchmarks, 3 custom cases & failure analyses
    └── usage_report.md          # Token usage, model calls, and cost accounting ($0.00)
```

---

## 3. Installation & Setup

### Prerequisites
- Python 3.10+
- Pip package manager

### Installation
From the root of this submission package:
```bash
pip install -r requirements.txt
```

*Note: All multimodal image OCR extractions are pre-indexed into `dataset/evidence/images_ocr_cache.json`, enabling 100% offline, deterministic execution without requiring external API keys or network access.*

---

## 4. Usage Instructions

Run the audit agent via the command line:

```bash
python main.py --input ../dataset/deletion_requests.csv --output ../output.csv --dataset-dir ../dataset
```

Or when running from the parent repository root:
```bash
python code/main.py --input dataset/deletion_requests.csv --output output.csv --dataset-dir dataset
```

### CLI Arguments
| Flag | Description | Default |
| :--- | :--- | :--- |
| `--input` | Path to input deletion requests CSV | `dataset/deletion_requests.csv` |
| `--output` | Path to target output CSV file | `output.csv` |
| `--dataset-dir` | Path to directory containing dataset files and evidence | `dataset` |

---

## 5. Benchmark Performance Summary

| Metric | Target / Benchmark | Achieved Result |
| :--- | :---: | :---: |
| **Case-Level Status Accuracy** | Golden Benchmark (32 cases) | **100.00% (32/32)** |
| **Step-Level Phase Accuracy** | Golden Benchmark | **100.00%** |
| **Citation Precision (`evidence_id`)** | Golden Benchmark | **100.00%** |
| **Full Production Throughput** | 518 cases (`deletion_requests.csv`) | **5.82 seconds (89 cases/sec)** |
| **Submission Output Validity** | 518 rows sorted numerically by `case_id` | **100% Validated (0 errors)** |
| **Total Incurred Financial Cost** | Full dataset evaluation | **$0.0000 (100% Free Tier)** |

Refer to `evaluation/evaluation_report.md` for comprehensive performance metrics, three custom adversarial evaluation cases, and root cause analyses. Refer to `evaluation/usage_report.md` for token and cost accounting.
