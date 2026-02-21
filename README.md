# Bull vs Bear: AI Investment Debate 🐂🐻⚖️

An AI-powered investment analysis tool that orchestrates a debate between a "Bull" agent (optimist) and a "Bear" agent (skeptic), presided over by a "Judge" who renders a final verdict and investment recommendation.

![Demo Screenshot](frontend/public/vite.svg) <!-- Replace with actual screenshot if available -->

## 🚀 Features

-   **Multi-Agent Debate**: Orchestrates three LLM agents (Bull, Bear, Judge) using **LangGraph**.
-   **Live Data**: Fetches real-time stock prices and financials via `yfinance`.
-   **Market News**: Scrapes latest news headlines using `duckduckgo-search`.
-   **Dual LLM Support**:
    -   **Gemini 2.0 Flash**: Fast, high-quality inference (requires API Key).
    -   **Ollama (Local)**: Runs locally with `gemma3:latest` (or other models) for privacy/free usage.
-   **Interactive UI**: Modern React frontend with glassmorphism design, real-time status updates, and ticker search suggestions.
-   **Robust Error Handling**: Handles API rate limits with automatic retries and exponential backoff.

## 🛠️ Tech Stack

-   **Backend**: Python, FastAPI, LangGraph, LangChain
-   **Frontend**: React, Vite, Axios, Vanilla CSS
-   **AI Serving**: Google Gemini API, Ollama (Local)

## 📦 Installation

### Prerequisites

-   Python 3.10+
-   Node.js 18+
-   (Optional) [Ollama](https://ollama.com/) for local inference.

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/bull-vs-bear.git
cd bull-vs-bear
```

### 2. Backend Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
python src/api.py
```
*Server runs on http://localhost:8000*

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```
*UI runs on http://localhost:5173*

### 🐳 Docker Setup (Recommended)

Run the entire application with a single command:

```bash
docker compose up --build
```

-   **Frontend**: http://localhost:5173
-   **Backend**: http://localhost:8000
-   **Streamlit**: http://localhost:8501

## 💡 Usage

1.  Open **http://localhost:5173** in your browser.
2.  **Enter Stock Ticker**: e.g., `NVDA`, `AAPL`, `TSLA`. Use the search dropdown for suggestions.
3.  **API Key (Optional)**:
    -   Enter your **Gemini API Key** for best results.
    -   **Leave blank** to use **Ollama** running locally on your machine.
    -   *Note: Ensure you have `gemma3` model pulled: `ollama pull gemma3`*
4.  Click **Start Debate**.
5.  Watch the agents research, argue, and decide!

## 🤖 Agents

| Agent | Role | Goal |
| :--- | :--- | :--- |
| **🐂 Bull** | Optimist | Finds growth drivers, competitive advantages, and positive catalysts. |
| **🐻 Bear** | Skeptic | Highlights risks, valuation concerns, and competitive threats. |
| **⚖️ Judge** | Arbiter | Weighs both sides to provide a "BUY", "SELL", or "HOLD" verdict. |

## ⚠️ Troubleshooting

-   **429 Quota Exceeded**: The system has built-in 60s retry logic. If the debate pauses, check the backend terminal; it's likely sleeping to respect rate limits.
-   **404 Model Not Found**: The code defaults to `gemini-2.0-flash`. Ensure your API key supports this model.
-   **Ollama Errors**: Make sure Ollama is running (`ollama serve`) and you have pulled the model (`ollama pull gemma3`).

## 📄 License

MIT License.
