import os
import time
import pickle
import random
import yfinance as yf
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import MIN_ROWS

CACHE_DIR = os.path.expanduser("~/.stocks_cache/data")
DATA_CACHE_TTL_HOURS = 4   # refresh intraday data every 4 hours


def _cache_path(ticker: str, period: str) -> str:
    safe = ticker.replace(".", "_").replace("/", "_")
    return os.path.join(CACHE_DIR, f"{safe}_{period}.pkl")


def _load_cache(ticker: str, period: str):
    path = _cache_path(ticker, period)
    if not os.path.exists(path):
        return None
    age_hours = (time.time() - os.path.getmtime(path)) / 3600
    if age_hours > DATA_CACHE_TTL_HOURS:
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _save_cache(ticker: str, period: str, df: pd.DataFrame):
    os.makedirs(CACHE_DIR, exist_ok=True)
    try:
        with open(_cache_path(ticker, period), "wb") as f:
            pickle.dump(df, f)
    except Exception:
        pass


def fetch_ticker_data(ticker: str, period: str, interval: str,
                      use_cache: bool = True) -> pd.DataFrame:
    """Fetch OHLCV for one NSE ticker. Uses disk cache, falls back to yfinance."""
    if use_cache:
        cached = _load_cache(ticker, period)
        if cached is not None:
            return cached

    # Small random jitter to avoid thundering-herd on Yahoo Finance
    time.sleep(random.uniform(0.1, 0.4))
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval, auto_adjust=True)
        if df is None or df.empty:
            return pd.DataFrame()

        # Normalise column names
        df.columns = [c.title() for c in df.columns]
        keep = [c for c in df.columns if c in {"Open", "High", "Low", "Close", "Volume"}]
        df = df[keep]

        if not {"Open", "High", "Low", "Close", "Volume"}.issubset(df.columns):
            return pd.DataFrame()

        df = df.dropna(subset=["Close", "Volume"])
        df = df.ffill()

        if len(df) < MIN_ROWS:
            return pd.DataFrame()

        if use_cache:
            _save_cache(ticker, period, df)
        return df

    except Exception:
        return pd.DataFrame()


def fetch_all(tickers: list, period: str, interval: str,
              max_workers: int = 10, use_cache: bool = True,
              progress_callback=None) -> tuple:
    """
    Fetch all tickers in parallel.
    progress_callback(ticker, success) called after each completes.
    Returns (results_dict, error_list).
    """
    results = {}
    errors = []

    def _fetch(ticker):
        return ticker, fetch_ticker_data(ticker, period, interval, use_cache)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, df = future.result()
            if df.empty:
                errors.append(ticker)
                if progress_callback:
                    progress_callback(ticker, False)
            else:
                results[ticker] = df
                if progress_callback:
                    progress_callback(ticker, True)

    return results, errors
