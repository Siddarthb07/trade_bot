"""Ticker and entity normalization."""

import re
import unicodedata


def normalize_entity(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.strip().upper())
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_ticker(ticker: str, market: str) -> str:
    symbol = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    if market == "IN":
        return f"{symbol}.NS"
    return symbol


def display_ticker(ticker: str, market: str) -> str:
    symbol = ticker.strip().upper().replace(".NS", "").replace(".BO", "")
    return symbol if market == "IN" else symbol
