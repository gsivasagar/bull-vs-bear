from typing import TypedDict, Annotated, List, Dict, Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

from src.tools.market_data import get_stock_price, get_financials
from src.tools.news import get_market_news
from src.agents.prompts import BULL_AGENT_PROMPT, BEAR_AGENT_PROMPT, JUDGE_AGENT_PROMPT
import operator
import google.generativeai as genai
import time

# Helper to list models
def list_available_models(api_key):
    try:
        genai.configure(api_key=api_key)
        print("--- Available Models ---")
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(m.name)
        print("------------------------")
    except Exception as e:
        print(f"Error listing models: {e}")

def call_llm_with_retry(llm, messages, max_retries=3, initial_delay=15):
    """
    Calls the LLM with a robust retry mechanism for 429 errors.
    """
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return llm.invoke(messages)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str:
                print(f"RATE LIMIT HIT (Attempt {attempt+1}/{max_retries}). Sleeping for {delay} seconds...")
                time.sleep(delay)
                delay *= 1.5 # Exponential backoff
            else:
                raise e
    raise Exception("Max retries exceeded for Rate Limit")

# Define the State of the Graph
# Define the State of the Graph
class AgentState(TypedDict):
    ticker: str
    api_key: str # Added field for API key
    price_data: Dict[str, Any]
    financials: Dict[str, Any]
    news_data: List[Dict[str, str]]
    bull_argument: str
    bear_argument: str
    verdict: str
    recommendation: str

# Define the Nodes

def fetch_data_node(state: AgentState) -> AgentState:
    ticker = state["ticker"]
    print(f"--- Fecthing Data for {ticker} ---")
    
    price_data = get_stock_price(ticker)
    financials = get_financials(ticker)
    news_data = get_market_news(f"{ticker} stock news")
    
    return {
        "price_data": price_data,
        "financials": financials,
        "news_data": news_data
    }

def bull_agent_node(state: AgentState) -> AgentState:
    time.sleep(4) # Rate limit backoff
    print("--- Bull Agent Thinking ---")
    api_key = state.get("api_key")
    
    try:
        # Check if we should use Ollama (If no API key provided)
        if not api_key:
             llm = ChatOllama(model="gemma3:latest", temperature=0.7)
        else:
             llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7, google_api_key=api_key)
        
        data_context = f"""
        Ticker: {state['ticker']}
        Price Data: {state['price_data']}
        Financials: {state['financials']}
        News: {state['news_data']}
        """
        
        messages = [
            SystemMessage(content=BULL_AGENT_PROMPT),
            HumanMessage(content=f"Here is the data:\n{data_context}\n\nPresent your Bull Case.")
        ]
        
        response = call_llm_with_retry(llm, messages)
        return {"bull_argument": response.content}
    except Exception as e:
        print(f"ERROR in Bull Agent: {e}")
        list_available_models(api_key)
        return {"bull_argument": f"Error generating argument: {str(e)}"}

def bear_agent_node(state: AgentState) -> AgentState:
    time.sleep(4) # Rate limit backoff
    print("--- Bear Agent Thinking ---")
    api_key = state.get("api_key")
    
    try:
        if not api_key:
             llm = ChatOllama(model="gemma3:latest", temperature=0.7)
        else:
             llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7, google_api_key=api_key)
        
        data_context = f"""
        Ticker: {state['ticker']}
        Price Data: {state['price_data']}
        Financials: {state['financials']}
        News: {state['news_data']}
        """
        
        messages = [
            SystemMessage(content=BEAR_AGENT_PROMPT),
            HumanMessage(content=f"Here is the data:\n{data_context}\n\nPresent your Bear Case.")
        ]
        
        response = call_llm_with_retry(llm, messages)
        return {"bear_argument": response.content}
    except Exception as e:
        print(f"ERROR in Bear Agent: {e}")
        list_available_models(api_key)
        return {"bear_argument": f"Error generating argument: {str(e)}"}

def judge_agent_node(state: AgentState) -> AgentState:
    time.sleep(4) # Rate limit backoff
    print("--- Judge Agent Deciding ---")
    api_key = state.get("api_key")
    
    try:
        if not api_key:
             llm = ChatOllama(model="gemma3:latest", temperature=0.5)
        else:
             llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.5, google_api_key=api_key) # Lower temp for more stable output
        
        arguments_context = f"""
        Ticker: {state['ticker']}
        
        --- BULL ARGUMENT ---
        {state['bull_argument']}
        
        --- BEAR ARGUMENT ---
        {state['bear_argument']}
        
        --- RAW DATA ---
        Price Data: {state['price_data']}
        Financials: {state['financials']}
        News: {state['news_data']}
        """
        
        messages = [
            SystemMessage(content=JUDGE_AGENT_PROMPT),
            HumanMessage(content=f"Review the arguments and data below and render your verdict:\n{arguments_context}")
        ]
        
        response = call_llm_with_retry(llm, messages)
        content = response.content
        
        # Parse recommendation (First line)
        try:
            lines = content.strip().split('\n')
            recommendation = lines[0].strip().upper()
            if recommendation not in ["BUY", "SELL", "HOLD"]:
                # Fallback if model chatted a bit
                for word in ["BUY", "SELL", "HOLD"]:
                    if word in lines[0].upper():
                        recommendation = word
                        break
        except:
            recommendation = "HOLD" # Default safety
            
        return {"verdict": content, "recommendation": recommendation}
    except Exception as e:
        print(f"ERROR in Judge Agent: {e}")
        list_available_models(api_key)
        return {"verdict": f"Error generating verdict: {str(e)}"}
