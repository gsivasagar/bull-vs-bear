"""Reading the Judge's recommendation out of its memo."""
import re
from typing import List, Literal

from pydantic import BaseModel, Field

VALID = ("BUY", "SELL", "HOLD")


def parse_recommendation(text: str) -> str:
    """BUY, SELL or HOLD from the memo's first non-empty line (the prompt demands a single word there).

    Falls back to a "Verdict: X" line. Returns "UNKNOWN" when it cannot tell, rather than guessing HOLD."""
    for line in (text or "").strip().splitlines():
        if not line.strip():
            continue
        found = {w for w in re.findall(r"[A-Za-z]+", line.upper()) if w in VALID}
        if len(found) == 1:
            return found.pop()
        break  # first line is missing or ambiguous: look for an explicit verdict line instead
    match = re.search(r"verdict\W{0,6}(buy|sell|hold)\b", text or "", re.IGNORECASE)
    return match.group(1).upper() if match else "UNKNOWN"


# --- Structured verdict -------------------------------------------------------------------------------------------

class JudgeVerdict(BaseModel):
    """What the Judge returns. The memo shown on the page is built from these fields, so the label can never disagree
    with the text."""
    recommendation: Literal["BUY", "SELL", "HOLD"]
    confidence: Literal["low", "medium", "high"]
    key_reasons: List[str] = Field(min_length=1, max_length=5,
                                   description="The most important factors, one sentence each")
    risks: List[str] = Field(max_length=5, description="What could go wrong, one sentence each")
    cited_figures: List[str] = Field(default_factory=list, max_length=10,
                                     description="Every number from the data you relied on, exactly as given there")
    conclusion: str = Field(description="Two or three sentences")


def render_memo(v: JudgeVerdict) -> str:
    """Markdown memo for display."""
    reasons = "\n".join(f"- {r}" for r in v.key_reasons)
    risks = "\n".join(f"- {r}" for r in v.risks) or "- None stated"
    return (f"**Verdict**: {v.recommendation} (confidence: {v.confidence})\n\n"
            f"**Key rationale**\n{reasons}\n\n**Risk assessment**\n{risks}\n\n**Conclusion**\n{v.conclusion}")
