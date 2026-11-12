"""Do the numbers an agent cites exist in the data it was given?

This checks numbers only. It cannot tell whether a number is used sensibly, only whether it appears (allowing for
rounding, percent versus fraction, and K/M/B/T suffixes). Years and small whole numbers ("3 reasons") are skipped."""
import re
from typing import Any, Dict, Iterable, List

_NUMBER = re.compile(r"(?<![\w.])[-+]?\$?\d[\d,]*(?:\.\d+)?\s?(?:%|[KMBT]\b|trillion|billion|million)?", re.IGNORECASE)
_PERIOD = re.compile(r"\s?-?\s?(?:week|day|month|year)s?\b", re.IGNORECASE)   # "52-week", "30 day": labels, not data
_SUFFIX = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12, "million": 1e6, "billion": 1e9, "trillion": 1e12}


def _decimals(text: str) -> int:
    return len(text.split(".")[1]) if "." in text else 0


def extract_numbers(text: str) -> List[Dict[str, Any]]:
    """Numbers in the text as {"raw", "value", "decimals", "percent"}; years and tiny whole numbers are left out."""
    found = []
    for match in _NUMBER.finditer(text or ""):
        raw = match.group(0).strip()
        if _PERIOD.match(text, match.end()):
            continue
        body = re.sub(r"[^\d.]", "", re.sub(r"(%|[KMBT]\b|trillion|billion|million)\s*$", "", raw, flags=re.I))
        if not body or body == ".":
            continue
        try:
            value = float(body)
        except ValueError:
            continue
        tail = re.search(r"(%|[KMBT]\b|trillion|billion|million)\s*$", raw, flags=re.I)
        unit = tail.group(1).lower() if tail else ""
        decimals = _decimals(body)
        if unit in _SUFFIX:
            value *= _SUFFIX[unit]
        is_percent = unit == "%"
        if not is_percent and not unit and decimals == 0 and (value <= 10 or 1900 <= value <= 2100):
            continue                                   # years, counts and ordinals are not data claims
        found.append({"raw": raw, "value": -value if raw.startswith("-") else value, "decimals": decimals,
                      "percent": is_percent})
    return found


def _leaves(node: Any) -> Iterable[float]:
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        yield float(node)
    elif isinstance(node, dict):
        for v in node.values():
            yield from _leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from _leaves(v)


def _strings(node: Any) -> Iterable[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


def _candidates(data: Dict[str, Any]) -> List[float]:
    """Every number in the data (including numbers written inside text such as the track-record sentence), plus the
    forms an agent may quote it in (percent of a fraction, abs of a loss)."""
    out: set[float] = set(_text_numbers(_strings(data)))
    for v in _leaves(data):
        out.update({v, abs(v)})
        if abs(v) <= 1.5:
            out.update({v * 100, abs(v) * 100})        # 0.25 may be quoted as 25%
    return list(out)


def _text_numbers(items: Iterable[str]) -> List[float]:
    values = []
    for text in items:
        values.extend(n["value"] for n in extract_numbers(text))
        values.extend(float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", text or "")
                      if x.replace(",", "").replace(".", "", 1).isdigit())
    return values


def _matches(cited: Dict[str, Any], candidates: Iterable[float]) -> bool:
    x, d = cited["value"], cited["decimals"]
    tolerance = 0.51 * 10 ** (-d)                       # half a unit in the last place the agent wrote
    for c in candidates:
        if abs(x - c) <= tolerance or (c and abs(x - c) / abs(c) <= 0.005):
            return True
        if abs(c) >= 1e6 and abs(x) < 1e6:              # a big figure quoted in billions without a suffix
            for scale in (1e6, 1e9, 1e12):
                if abs(x * scale - c) / abs(c) <= 0.005:
                    return True
    return False


def check(text: str, data: Dict[str, Any], news: Iterable[Dict[str, str]] = ()) -> Dict[str, Any]:
    """{"checked", "supported", "unsupported": [raw...], "share"} for the numbers cited in `text`."""
    candidates = _candidates(data) + _text_numbers(f"{n.get('title', '')} {n.get('summary', '')}" for n in news)
    cited = extract_numbers(text)
    unsupported = [c["raw"] for c in cited if not _matches(c, candidates)]
    checked = len(cited)
    return {"checked": checked, "supported": checked - len(unsupported), "unsupported": unsupported,
            "share": None if checked == 0 else round((checked - len(unsupported)) / checked, 4)}
