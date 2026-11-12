from src.tools import faithfulness as f

DATA = {"price_data": {"current_price": 123.45, "company_name": "NVIDIA"},
        "financials": {"market_cap": 3_000_000_000_000, "pe_ratio": 60.1, "profit_margins": 0.255, "revenue_growth": 0.62},
        "quant": {"volatility": {"forecast_annualized_pct": 31.2, "one_sigma_move_over_horizon_pct": 9.0},
                  "recent": {"max_drawdown_1y_pct": -18.2}}}
NEWS = [{"title": "NVDA ships 2,000 racks", "summary": "Demand up 40% on the quarter"}]


def share(text):
    return f.check(text, DATA, NEWS)


def test_numbers_in_the_data_are_supported_in_their_usual_forms():
    out = share("Price is $123.45, market cap $3.0T, P/E 60.1, margin 25.5%, growth 62%, vol 31.2%, a 18.2% fall.")
    assert out["checked"] >= 7 and out["unsupported"] == [] and out["share"] == 1.0


def test_rounding_to_the_stated_precision_is_allowed():
    assert share("P/E about 60 and price near $123")["unsupported"] == []
    assert share("Vol of 31%")["unsupported"] == []


def test_invented_numbers_are_flagged():
    out = share("Price is $150.00 and P/E 45.3 while volatility is 55%.")
    assert set(out["unsupported"]) == {"$150.00", "45.3", "55%"} and out["share"] == 0.0


def test_news_numbers_count_as_data():
    assert share("It ships 2,000 racks and demand rose 40%")["unsupported"] == []


def test_years_and_small_counts_are_ignored():
    out = share("In 2024 there are 3 reasons and 5 risks")
    assert out["checked"] == 0 and out["share"] is None


def test_mixed_text_gives_a_partial_share():
    out = share("P/E 60.1 but market cap 9T")
    assert out["checked"] == 2 and out["supported"] == 1 and out["share"] == 0.5


def test_period_labels_like_52_week_are_not_data_claims():
    out = share("Trading near its 52-week high, a 30 day average, 12-month view, 5 years")
    assert out["checked"] == 0


def test_long_period_labels_are_skipped_whole():
    assert share("A 123-day trend and a 250 day mean")["checked"] == 0


def test_numbers_written_inside_the_summary_sentence_count_as_data():
    data = {"quant": {"summary": "it had 34% lower error than the naive guess; real moves fell inside the range in 60% of months"}}
    out = f.check('The summary says "34% lower error" and "60% of months" (about 68% expected)', data)
    assert out["unsupported"] == ["68%"]
