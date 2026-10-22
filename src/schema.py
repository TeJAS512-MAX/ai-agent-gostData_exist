from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class TriageAction(str, Enum):
    REPLIED = "replied"
    ESCALATED = "escalated"
    BLOCKED = "blocked"
    PENDING_INFO = "pending_info"

class PriorityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class SecurityAssessment(BaseModel):
    is_safe: bool = Field(default=True, description="Whether prompt is free of adversarial injection")
    flagged_reason: Optional[str] = Field(default=None, description="Reason if injection was detected")
    sanitized_input: str = Field(default="", description="Sanitized clean content")

class RetrievalCitation(BaseModel):
    document_id: str = Field(description="Policy or doc identifier")
    title: str = Field(description="Title or section name")
    snippet: str = Field(description="Exact snippet supporting decision")
    relevance_score: float = Field(default=0.0, description="Match score")

class InputTicket(BaseModel):
    ticket_id: str = Field(description="Unique ticket/case ID")
    customer_id: Optional[str] = Field(default="CUST-UNKNOWN", description="Customer ID")
    subject: str = Field(description="Ticket subject line")
    description: str = Field(description="Detailed body of the ticket")
    channel: Optional[str] = Field(default="email", description="Channel: email, chat, api")
    created_at: Optional[str] = Field(default=None, description="Timestamp")

class AgentDecision(BaseModel):
    ticket_id: str
    action: TriageAction = Field(description="Final action: replied, escalated, blocked, pending_info")
    priority: PriorityLevel = Field(default=PriorityLevel.MEDIUM)
    category: str = Field(default="general_support", description="Classification category")
    justification: str = Field(description="Grounding reason backed by policy documents")
    response_draft: str = Field(description="Customer-facing answer or escalation notes")
    citations: List[RetrievalCitation] = Field(default_factory=list, description="Policy citations")
    requires_human: bool = Field(default=False)
    injection_detected: bool = Field(default=False)

class OutputRow(BaseModel):
    """Strict schema required for HackerRank output.csv evaluation."""
    ticket_id: str
    action: str
    priority: str
    category: str
    citation_id: str
    response_summary: str

