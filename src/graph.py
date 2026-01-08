from langgraph.graph import StateGraph, END
from src.agents.nodes import AgentState, fetch_data_node, bull_agent_node, bear_agent_node, judge_agent_node

def create_graph():
    """
    Constructs the Investment Debate Graph.
    """
    workflow = StateGraph(AgentState)
    
    # Add Nodes
    workflow.add_node("fetch_data", fetch_data_node)
    workflow.add_node("bull_agent", bull_agent_node)
    workflow.add_node("bear_agent", bear_agent_node)
    workflow.add_node("judge_agent", judge_agent_node)
    
    # Add Edges
    # Start -> Fetch Data
    workflow.set_entry_point("fetch_data")
    
    # Bull & Bear -> Judge (Sequential)
    workflow.add_edge("fetch_data", "bull_agent")
    workflow.add_edge("bull_agent", "bear_agent")
    workflow.add_edge("bear_agent", "judge_agent")
    
    # Judge -> End
    workflow.add_edge("judge_agent", END)
    
    return workflow.compile()

# For testing
if __name__ == "__main__":
    app = create_graph()
    print("Graph created successfully.")
