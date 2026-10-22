from langgraph.graph import StateGraph, START, END
from src.agent.state import AgentState
from src.agent.nodes import security_node, retrieval_node, reasoning_node
from src.schema import InputTicket, AgentDecision

def should_skip_retrieval(state: AgentState) -> str:
    security = state.get("security")
    if security and not security.is_safe:
        return "reasoning"
    return "retrieval"

def build_agent_graph():
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("security", security_node)
    workflow.add_node("retrieval", retrieval_node)
    workflow.add_node("reasoning", reasoning_node)

    # Register edges
    workflow.add_edge(START, "security")
    workflow.add_conditional_edges(
        "security",
        should_skip_retrieval,
        {
            "retrieval": "retrieval",
            "reasoning": "reasoning"
        }
    )
    workflow.add_edge("retrieval", "reasoning")
    workflow.add_edge("reasoning", END)

    return workflow.compile()

# Global compiled agent instance
agent_app = build_agent_graph()

def process_ticket(ticket: InputTicket) -> AgentDecision:
    """Executes the autonomous agent graph for a single ticket."""
    initial_state: AgentState = {
        "ticket": ticket,
        "security": None,
        "citations": [],
        "raw_response": None,
        "decision": None,
        "error": None
    }
    result = agent_app.invoke(initial_state)
    return result["decision"]

