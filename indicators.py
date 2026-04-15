import pandas as pd
import ta


# ── Shared helpers ────────────────────────────────────────────────────────────

def add_rsi(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = ta.momentum.RSIIndicator(close=df["Close"], window=window).rsi()
    return df


def add_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26,
             signal: int = 9) -> pd.DataFrame:
    df = df.copy()
    macd = ta.trend.MACD(close=df["Close"], window_fast=fast,
                         window_slow=slow, window_sign=signal)
    df["macd"]        = macd.macd()
    df["macd_signal"] = macd.macd_signal()
    df["macd_hist"]   = macd.macd_diff()
    return df


def add_bollinger_bands(df: pd.DataFrame, window: int = 20,
                        std: float = 2.0) -> pd.DataFrame:
    df = df.copy()
    bb = ta.volatility.BollingerBands(close=df["Close"], window=window,
                                      window_dev=std)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_mid"]   = bb.bollinger_mavg()
    return df


def add_moving_averages(df: pd.DataFrame, short: int = 20,
                        long: int = 50) -> pd.DataFrame:
    df = df.copy()
    df["ma_short"]  = df["Close"].rolling(short).mean()
    df["ma_long"]   = df["Close"].rolling(long).mean()
    df["ma_cross"]  = (df["ma_short"] > df["ma_long"]).astype(int)
    prev            = df["ma_cross"].shift(1)
    df["golden_cross"] = ((df["ma_cross"] == 1) & (prev == 0)).astype(int)
    df["death_cross"]  = ((df["ma_cross"] == 0) & (prev == 1)).astype(int)
    return df


def add_volume_trend(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    df = df.copy()
    df["vol_avg"]         = df["Volume"].rolling(window).mean()
    df["vol_ratio"]       = df["Volume"] / df["vol_avg"]
    df["price_change_pct"] = df["Close"].pct_change()
    return df


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Standard daily indicators for positional analysis."""
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_moving_averages(df)
    df = add_volume_trend(df)
    return df


# ── Swing-specific additions ──────────────────────────────────────────────────

def add_atr(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Average True Range — measures volatility for stop/target sizing."""
    df = df.copy()
    atr = ta.volatility.AverageTrueRange(
        high=df["High"], low=df["Low"], close=df["Close"], window=window
    )
    df["atr"] = atr.average_true_range()
    return df


def add_stochastic(df: pd.DataFrame, window: int = 14,
                   smooth: int = 3) -> pd.DataFrame:
    """Stochastic oscillator — good for spotting short-term reversals."""
    df = df.copy()
    stoch = ta.momentum.StochasticOscillator(
        high=df["High"], low=df["Low"], close=df["Close"],
        window=window, smooth_window=smooth
    )
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()
    return df


def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """
    Approximate VWAP using cumulative volume-weighted price.
    On hourly data this gives a meaningful intraday reference level.
    """
    df = df.copy()
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    df["vwap"] = (typical_price * df["Volume"]).cumsum() / df["Volume"].cumsum()
    return df


def add_all_indicators_swing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Faster indicator parameters suited for 1h candles / swing trading.
    RSI(9), MACD(5,13,4), BB(10), MA(9,21), ATR(14), Stoch(14,3), VWAP.
    """
    df = add_rsi(df, window=9)
    df = add_macd(df, fast=5, slow=13, signal=4)
    df = add_bollinger_bands(df, window=10, std=2.0)
    df = add_moving_averages(df, short=9, long=21)
    df = add_volume_trend(df, window=20)
    df = add_atr(df, window=14)
    df = add_stochastic(df, window=14, smooth=3)
    df = add_vwap(df)
    return df
