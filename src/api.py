import sys
import os

# Add the project root to sys.path to allow running this file directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from src.graph import create_graph
from src.data.tickers import TICKERS

app = FastAPI(title="Investment Debate API")

# Allow CORS for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DebateRequest(BaseModel):
    ticker: str
    api_key: str = None

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Investment Debate API is running"}

@app.get("/api/search")
def search_tickers(q: str = ""):
    if not q:
        return []
    
    q = q.lower()
    results = []
    
    # Simple rigorous filtering
    for t in TICKERS:
        if q in t["symbol"].lower() or q in t["name"].lower():
            results.append(t)
            if len(results) >= 10: # Limit to 10 results
                break
                
    return results

@app.post("/api/debate")
async def run_debate(request: DebateRequest):
    """
    Triggers the debate graph for a given ticker.
    """
    try:
        graph = create_graph()
        initial_state = {
            "ticker": request.ticker.upper(),
            "api_key": request.api_key,
            "price_data": {},
            "financials": {},
            "news_data": [],
            "bull_argument": "",
            "bear_argument": "",
            "verdict": "",
            "recommendation": ""
        }
        
        # Invoke the graph
        final_state = graph.invoke(initial_state)
        
        return final_state
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
