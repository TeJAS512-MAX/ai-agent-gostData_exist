# Usage Report

## Final full-dataset run

| Item | Measured value |
|---|---:|
| Input requests | 518 |
| Output rows | 518 |
| Pipeline elapsed time | 80.84 seconds |
| Average elapsed time per request | 156.1 ms |
| External API calls | 0 |
| External input/output tokens | 0 / 0 |
| Estimated API cost | $0.00 |

The standard run is offline. It reads the supplied evidence, including cached
OCR text, without calling a remote model provider.

## Model and call counts

| Component | Provider/model | Calls in full run | Tokens/cost |
|---|---|---:|---:|
| Intent fast path | Local deterministic patterns | 518 | 0 tokens |
| Trained intent model | Local scikit-learn TF-IDF + Logistic Regression | 0 | 0 tokens |
| LLM fallback | None (disabled by the production pipeline) | 0 | 0 tokens |
| Vision model | None (cached OCR is used) | 0 | 0 tokens |

All 518 request texts were resolved by the deterministic intent fast path, so
the trained classifier artifact was not invoked during this production run.
Text-token counts are not applicable to local feature extraction; the API-token
totals above are zero because no API calls occurred.

The local classifier artifact was trained separately on 127 cross-dataset examples
spanning 17 distinct partitions (official ground truth samples, 12 languages,
DSAR Articles 15/16/18/20/21, e-commerce maintenance, and adversarial boundary cases).
Its training report records 5-fold macro F1 of 0.8474 ± 0.0567 and 100.0% (14/14)
stress-test adversarial accuracy across boundary cases. That CV score is diagnostic
only and is not a production-run metric.
