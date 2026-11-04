import functools

from langgraph.graph import END, StateGraph

from src.agents.nodes import AgentState, bear_agent_node, bull_agent_node, fetch_data_node, judge_agent_node


def create_graph():
    """fetch_data -> (bull_agent, bear_agent run in parallel) -> judge_agent.

    The Bull and Bear never read each other's argument, so they run at the same time; the Judge waits for both."""
    workflow = StateGraph(AgentState)
    workflow.add_node("fetch_data", fetch_data_node)
    workflow.add_node("bull_agent", bull_agent_node)
    workflow.add_node("bear_agent", bear_agent_node)
    workflow.add_node("judge_agent", judge_agent_node)

    workflow.set_entry_point("fetch_data")
    workflow.add_edge("fetch_data", "bull_agent")
    workflow.add_edge("fetch_data", "bear_agent")
    workflow.add_edge(["bull_agent", "bear_agent"], "judge_agent")   # waits for both branches
    workflow.add_edge("judge_agent", END)
    return workflow.compile()


@functools.lru_cache(maxsize=1)
def get_graph():
    return create_graph()
