import json
import logging
from typing import Any, Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.prompts import BEAR_AGENT_PROMPT, BULL_AGENT_PROMPT, JUDGE_AGENT_PROMPT
from src.errors import DataSourceError, DataUnavailableError
from src.llm import get_llm, invoke_with_retry
from src.tools.market_data import get_financials, get_stock_price
from src.tools.news import clean, get_market_news
from src.verdict import parse_recommendation

log = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    ticker: str
    api_key: str | None          # used only to build the model client; never returned or logged
    price_data: Dict[str, Any]
    financials: Dict[str, Any]
    news_data: List[Dict[str, str]]
    bull_argument: str
    bear_argument: str
    verdict: str
    recommendation: str


def format_data(state: AgentState) -> str:
    """The evidence block shared by all agents. It is wrapped in <data> tags and told to be treated as untrusted."""
    price = dict(state.get("price_data") or {})
    price["summary"] = clean(price.get("summary"), 600)
    body = json.dumps({
        "ticker": state["ticker"],
        "price_data": price,
        "financials": state.get("financials") or {},
        "news": state.get("news_data") or [],
    }, indent=2, default=str)
    return "<data>\n" + body.replace("</data", "< /data") + "\n</data>"


def fetch_data_node(state: AgentState) -> AgentState:
    ticker = state["ticker"]
    price = get_stock_price(ticker)
    if "error" in price:
        if price.get("kind") == "not_found":
            raise DataUnavailableError(f"No market data was found for '{ticker}'. Check the ticker symbol.")
        raise DataSourceError()
    financials = get_financials(ticker)
    if "error" in financials:
        financials = {}                       # ratios are nice to have; the debate can go on without them
    return {"price_data": price, "financials": financials, "news_data": get_market_news(f"{ticker} stock news")}


def _ask(state: AgentState, system_prompt: str, request: str, temperature: float) -> str:
    api_key = state.get("api_key")
    llm = get_llm(api_key, temperature)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=request)]
    return invoke_with_retry(llm, messages, api_key=api_key)


def bull_agent_node(state: AgentState) -> AgentState:
    text = _ask(state, BULL_AGENT_PROMPT, f"Here is the data:\n{format_data(state)}\n\nPresent your Bull Case.", 0.7)
    return {"bull_argument": text}


def bear_agent_node(state: AgentState) -> AgentState:
    text = _ask(state, BEAR_AGENT_PROMPT, f"Here is the data:\n{format_data(state)}\n\nPresent your Bear Case.", 0.7)
    return {"bear_argument": text}


def judge_agent_node(state: AgentState) -> AgentState:
    context = (f"--- BULL ARGUMENT ---\n{state['bull_argument']}\n\n"
               f"--- BEAR ARGUMENT ---\n{state['bear_argument']}\n\n--- RAW DATA ---\n{format_data(state)}")
    request = f"Review the arguments and data below and render your verdict:\n{context}"
    text = _ask(state, JUDGE_AGENT_PROMPT, request, 0.5)
    return {"verdict": text, "recommendation": parse_recommendation(text)}
