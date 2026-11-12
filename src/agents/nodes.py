import json
import logging
import operator
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Dict, List, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.agents.prompts import BEAR_AGENT_PROMPT, BULL_AGENT_PROMPT, JUDGE_AGENT_PROMPT
from src.cancel import check
from src.errors import DataSourceError, DataUnavailableError
from src.llm import get_llm, invoke_structured, invoke_with_retry
from src.tools.market_data import get_financials, get_stock_price
from src.tools.news import clean, get_market_news
from src.tools.quant import agent_view, get_quant_signals
from src.verdict import JudgeVerdict, parse_recommendation, render_memo

log = logging.getLogger(__name__)


class AgentState(TypedDict, total=False):
    ticker: str
    api_key: str | None          # used only to build the model client; never returned or logged
    price_data: Dict[str, Any]
    financials: Dict[str, Any]
    quant: Dict[str, Any]        # the full volatility block for the browser; the agents get agent_view() of it
    news_data: List[Dict[str, str]]
    bull_argument: str
    bear_argument: str
    verdict: str
    recommendation: str
    judge: Dict[str, Any]        # the structured verdict (confidence, reasons, risks, cited figures), when available
    model: str | None            # overrides the default Gemini model (demo mode uses a cheaper one)
    judge_order: str             # "bull_first" (default) or "bear_first": which argument the Judge reads first
    usage: Annotated[List[Dict[str, int]], operator.add]   # token counts from every model call (parallel nodes append)


def format_data(state: AgentState) -> str:
    """The evidence block shared by all agents. It is wrapped in <data> tags and told to be treated as untrusted."""
    price = dict(state.get("price_data") or {})
    price["summary"] = clean(price.get("summary"), 600)
    body = json.dumps({
        "ticker": state["ticker"],
        "price_data": price,
        "financials": state.get("financials") or {},
        "quant": agent_view(state.get("quant") or {}),
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
    # The news search and the quant history download do not depend on each other, so they run together.
    with ThreadPoolExecutor(max_workers=2) as pool:
        news_job = pool.submit(get_market_news, news_query(ticker, price.get("company_name")))
        quant_job = pool.submit(_quant_or_empty, ticker)
        news, quant = news_job.result(), quant_job.result()
    return {"price_data": price, "financials": financials, "quant": quant, "news_data": news}


def news_query(ticker: str, company: str | None) -> str:
    """Short tickers ('F', 'T', 'ON') match unrelated news, so search by company name as well."""
    name = (company or "").strip()
    return f"{name} {ticker} stock news" if name and name.upper() != ticker.upper() else f"{ticker} stock news"


def _quant_or_empty(ticker: str) -> Dict[str, Any]:
    """The quant block is a bonus: if it cannot be computed (short history, provider hiccup), the debate goes on."""
    try:
        result = get_quant_signals(ticker)
    except Exception:
        log.exception("Quant signals failed for %s", ticker)
        return {}
    return {} if "error" in result else result


def _ask(state: AgentState, config: RunnableConfig, system_prompt: str, request: str, temperature: float):
    """One plain-text model call. Returns (text, usage list)."""
    check(config)                              # the visitor may have left while an earlier step was running
    api_key = state.get("api_key")
    llm = get_llm(api_key, temperature, state.get("model"))
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=request)]
    usage: list = []
    text = invoke_with_retry(llm, messages, api_key=api_key, usage_sink=usage)
    return text, usage


def bull_agent_node(state: AgentState, config: RunnableConfig) -> AgentState:
    text, usage = _ask(state, config, BULL_AGENT_PROMPT,
                       f"Here is the data:\n{format_data(state)}\n\nPresent your Bull Case.", 0.7)
    return {"bull_argument": text, "usage": usage}


def bear_agent_node(state: AgentState, config: RunnableConfig) -> AgentState:
    text, usage = _ask(state, config, BEAR_AGENT_PROMPT,
                       f"Here is the data:\n{format_data(state)}\n\nPresent your Bear Case.", 0.7)
    return {"bear_argument": text, "usage": usage}


def judge_agent_node(state: AgentState, config: RunnableConfig) -> AgentState:
    check(config)
    bull = f"--- BULL ARGUMENT ---\n{state['bull_argument']}"
    bear = f"--- BEAR ARGUMENT ---\n{state['bear_argument']}"
    first, second = (bear, bull) if state.get("judge_order") == "bear_first" else (bull, bear)
    context = f"{first}\n\n{second}\n\n--- RAW DATA ---\n{format_data(state)}"
    request = f"Review the arguments and data below and render your verdict:\n{context}"

    api_key = state.get("api_key")
    llm = get_llm(api_key, 0.5, state.get("model"))
    messages = [SystemMessage(content=JUDGE_AGENT_PROMPT), HumanMessage(content=request)]
    usage: list = []
    parsed = invoke_structured(llm, messages, JudgeVerdict, api_key=api_key, usage_sink=usage)
    if isinstance(parsed, JudgeVerdict):
        return {"verdict": render_memo(parsed), "recommendation": parsed.recommendation,
                "judge": parsed.model_dump(), "usage": usage}
    # The model could not give structured output (some local models cannot): ask for the memo as text instead.
    log.info("Structured verdict unavailable; falling back to the text memo")
    check(config)
    text = invoke_with_retry(llm, messages, api_key=api_key, usage_sink=usage)
    return {"verdict": text, "recommendation": parse_recommendation(text), "judge": {}, "usage": usage}
