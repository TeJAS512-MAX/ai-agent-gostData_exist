from typing import TypedDict, List, Optional
from src.schema import InputTicket, SecurityAssessment, RetrievalCitation, AgentDecision

class AgentState(TypedDict):
    ticket: InputTicket
    security: Optional[SecurityAssessment]
    citations: List[RetrievalCitation]
    raw_response: Optional[str]
    decision: Optional[AgentDecision]
    error: Optional[str]

