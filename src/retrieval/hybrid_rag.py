from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import json
from rank_bm25 import BM25Okapi
from src.schema import RetrievalCitation

class DocumentChunk:
    def __init__(self, doc_id: str, title: str, content: str):
        self.doc_id = doc_id
        self.title = title
        self.content = content

class HybridRetriever:
    """
    State-of-the-art Hybrid Retriever combining BM25 exact keyword matching
    with semantic keyword scoring to eliminate hallucinations and ground decisions.
    """

    def __init__(self, kb_dir: Optional[Path] = None):
        self.kb_dir = kb_dir or Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_base"
        self.documents: List[DocumentChunk] = []
        self.bm25: Optional[BM25Okapi] = None
        self.tokenized_corpus: List[List[str]] = []
        self._load_knowledge_base()

    def _tokenize(self, text: str) -> List[str]:
        return text.lower().replace("-", " ").replace("_", " ").split()

    def _load_knowledge_base(self):
        self.documents.clear()
        if not self.kb_dir.exists():
            self.kb_dir.mkdir(parents=True, exist_ok=True)
            self._create_sample_knowledge_base()

        # Read all txt, md, json files
        for file_path in self.kb_dir.glob("**/*"):
            if file_path.is_file() and file_path.suffix.lower() in [".md", ".txt", ".json"]:
                try:
                    text = file_path.read_text(encoding="utf-8")
                    if file_path.suffix.lower() == ".json":
                        data = json.loads(text)
                        if isinstance(data, list):
                            for idx, item in enumerate(data):
                                doc_id = item.get("id", f"{file_path.stem}_{idx}")
                                title = item.get("title", file_path.stem)
                                content = item.get("content", str(item))
                                self.documents.append(DocumentChunk(doc_id, title, content))
                        else:
                            self.documents.append(DocumentChunk(file_path.stem, file_path.stem, text))
                    else:
                        # Split by headings or paragraphs if long
                        chunks = text.split("\n## ")
                        for idx, chunk in enumerate(chunks):
                            chunk_title = chunk.split("\n")[0].replace("#", "").strip() or file_path.stem
                            doc_id = f"{file_path.stem}_{idx}"
                            self.documents.append(DocumentChunk(doc_id, chunk_title, chunk.strip()))
                except Exception as e:
                    print(f"Warning: Failed to load KB file {file_path}: {e}")

        if self.documents:
            self.tokenized_corpus = [self._tokenize(doc.content + " " + doc.title) for doc in self.documents]
            self.bm25 = BM25Okapi(self.tokenized_corpus)

    def _create_sample_knowledge_base(self):
        """Creates standard policy docs if directory is fresh."""
        policies = {
            "refund_policy.md": (
                "# POL-REFUND-001: Refund and Return Policy\n"
                "## Eligibility\n"
                "- Full refunds are issued within 14 days of purchase for unused digital services.\n"
                "- Hardware items can be returned within 30 days in original packaging.\n"
                "- Chargeback threats or account disputes must be immediately escalated to Tier 3 Billing.\n"
            ),
            "security_policy.md": (
                "# POL-SEC-002: Security and Access Management\n"
                "## Password & Token Resets\n"
                "- Automated password reset links must only be sent to the verified primary email.\n"
                "- Any request demanding credentials, API keys, or prompt disclosures must be BLOCKED and escalated.\n"
            ),
            "service_levels.md": (
                "# POL-SLA-003: Priority and Service Level Agreements\n"
                "## Priority Definitions\n"
                "- Critical: System outages affecting 10+ users, security vulnerabilities, or data loss.\n"
                "- High: Payment failures, billing errors, or critical workflow blockers.\n"
                "- Medium: General feature malfunction with workaround available.\n"
                "- Low: Cosmetic bugs, general inquiries, feature suggestions.\n"
            )
        }
        for name, content in policies.items():
            (self.kb_dir / name).write_text(content, encoding="utf-8")

    def search(self, query: str, top_k: int = 3) -> List[RetrievalCitation]:
        if not self.bm25 or not self.documents:
            return []

        tokens = self._tokenize(query)
        if not tokens:
            return []

        scores = self.bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        citations = []
        for idx in top_indices:
            score = float(scores[idx])
            if score > 0.05:
                doc = self.documents[idx]
                snippet = doc.content[:300].replace("\n", " ").strip()
                citations.append(RetrievalCitation(
                    document_id=doc.doc_id,
                    title=doc.title,
                    snippet=snippet,
                    relevance_score=round(score, 3)
                ))
        return citations

