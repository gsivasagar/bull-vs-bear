"""Reading the Judge's recommendation out of its memo."""
import re

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
