import streamlit as st
import os
from src.graph import create_graph

# Page Config
st.set_page_config(page_title="Bull vs Bear Investment Debate", layout="wide")

# Title and Input
st.title("🐂 Bull vs 🐻 Bear: AI Investment Debate")
st.markdown("### Powered by Multi-Agent AI")

# Sidebar for API Keys (Optional but good practice)
with st.sidebar:
    st.header("Configuration")
    api_key = st.text_input("OpenAI API Key", type="password")
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key

ticker = st.text_input("Enter Stock Ticker (e.g., NVDA, AAPL, TSLA):", "NVDA").upper()

if st.button("Start Debate"):
    if not os.environ.get("OPENAI_API_KEY"):
        st.error("Please set your OpenAI API Key in the sidebar or environment variables.")
    else:
        with st.spinner("Gathering market data and news..."):
            # Initialize Graph
            graph = create_graph()
            
            # Initial State
            initial_state = {
                "ticker": ticker,
                "price_data": {},
                "financials": {},
                "news_data": [],
                "bull_argument": "",
                "bear_argument": "",
                "verdict": ""
            }
            
            # Run the Graph
            # We can stream the updates to show progress
            # For simplicity, we just invoke it, but we could handle intermediate steps
            
            # Placeholder containers
            status_container = st.empty()
            
            try:
                # Running the graph
                
                # Note: LangGraph invoke returns the final state
                status_container.info("Agents are researching and debating...")
                final_state = graph.invoke(initial_state)
                
                status_container.success("Debate Concluded!")
                
                # Display Data Summary
                st.divider()
                st.subheader(f"Market Data for {ticker}")
                col1, col2, col3 = st.columns(3)
                
                price_info = final_state.get('price_data', {})
                financials = final_state.get('financials', {})
                
                with col1:
                    st.metric("Current Price", f"${price_info.get('current_price', 'N/A'):.2f}")
                with col2:
                    st.metric("Market Cap", f"{financials.get('market_cap', 'N/A')}")
                with col3:
                    st.metric("P/E Ratio", f"{financials.get('pe_ratio', 'N/A')}")
                
                # Display Arguments
                st.divider()
                st.subheader("The Debate")
                
                col_bull, col_bear = st.columns(2)
                
                with col_bull:
                    st.markdown("### 🐂 The Bull Case")
                    st.info(final_state.get('bull_argument', 'No argument generated.'))
                    
                with col_bear:
                    st.markdown("### 🐻 The Bear Case")
                    st.error(final_state.get('bear_argument', 'No argument generated.'))
                
                # Display Verdict
                st.divider()
                st.header("⚖️ The Verdict")
                st.markdown(final_state.get('verdict', 'No verdict reached.'))
                
                
                # Display News Sources
                with st.expander("See News Sources"):
                    news = final_state.get('news_data', [])
                    for item in news:
                        st.markdown(f"**[{item.get('title')}]({item.get('url')})** - {item.get('source')}")
                        st.caption(item.get('date'))
                        
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
