import numpy as np
import pandas as pd
from config import SCORE_WEIGHTS, SWING_WEIGHTS, ATR_MULTIPLIER_STOP, ATR_MULTIPLIER_TARGET


# ── Shared sub-scorers ────────────────────────────────────────────────────────

def _rsi_score(rsi_val: float) -> tuple:
    if np.isnan(rsi_val):
        return 50.0, "RSI: N/A"
    score = float(np.interp(rsi_val,
                            [0,  30,  45,  55,  70,  100],
                            [95, 85,  60,  40,  15,   5]))
    if rsi_val < 30:
        label = f"RSI={rsi_val:.1f} (oversold — buy signal)"
    elif rsi_val < 45:
        label = f"RSI={rsi_val:.1f} (approaching oversold)"
    elif rsi_val < 55:
        label = f"RSI={rsi_val:.1f} (neutral)"
    elif rsi_val < 70:
        label = f"RSI={rsi_val:.1f} (approaching overbought)"
    else:
        label = f"RSI={rsi_val:.1f} (overbought — caution)"
    return score, label


def _macd_score(macd: float, macd_sig: float, hist_vals: pd.Series) -> tuple:
    if any(np.isnan(v) for v in [macd, macd_sig]):
        return 50.0, "MACD: N/A"
    score = 0.0
    parts = []
    if macd > macd_sig:
        score += 40
        parts.append("MACD above signal (bullish)")
    else:
        parts.append("MACD below signal (bearish)")
    recent_hist = hist_vals.dropna().tail(3)
    if len(recent_hist) >= 2:
        if recent_hist.iloc[-1] > recent_hist.iloc[-2]:
            score += 30
            parts.append("histogram rising")
        else:
            parts.append("histogram falling")
    if macd > 0:
        score += 30
        parts.append("MACD positive")
    else:
        parts.append("MACD negative")
    label = "MACD: " + ", ".join(parts[:2])
    return score, label


def _bb_score(close: float, bb_lower: float, bb_upper: float) -> tuple:
    if any(np.isnan(v) for v in [close, bb_lower, bb_upper]):
        return 50.0, "BB: N/A"
    band_width = bb_upper - bb_lower
    if band_width == 0:
        return 50.0, "BB: flat band"
    position = (close - bb_lower) / band_width
    score = float(np.clip((1 - position) * 100, 0, 100))
    if position < 0.2:
        label = f"BB: near lower band ({position:.0%}) — oversold zone"
    elif position > 0.8:
        label = f"BB: near upper band ({position:.0%}) — overbought zone"
    else:
        label = f"BB: mid-band ({position:.0%})"
    return score, label


def _ma_score(df: pd.DataFrame) -> tuple:
    last = df.iloc[-1]
    if np.isnan(last.get("ma_short", np.nan)) or np.isnan(last.get("ma_long", np.nan)):
        return 50.0, "MA: N/A"
    tail5 = df.tail(5)
    recent_golden = tail5["golden_cross"].sum() > 0
    recent_death  = tail5["death_cross"].sum() > 0
    ma_above  = last["ma_short"] > last["ma_long"]
    gap_pct   = abs(last["ma_short"] - last["ma_long"]) / last["ma_long"] * 100
    if recent_golden:
        return 90.0, "Golden cross recently (bullish)"
    elif recent_death:
        return 10.0, "Death cross recently (bearish)"
    elif ma_above:
        score = float(np.clip(60 + gap_pct * 2, 60, 80))
        label = f"Fast MA above slow MA by {gap_pct:.1f}% (uptrend)"
    else:
        score = float(np.clip(40 - gap_pct * 2, 20, 40))
        label = f"Fast MA below slow MA by {gap_pct:.1f}% (downtrend)"
    return score, label


def _volume_score(vol_ratio: float, price_change: float) -> tuple:
    if np.isnan(vol_ratio) or np.isnan(price_change):
        return 50.0, "Volume: N/A"
    if price_change > 0 and vol_ratio > 1.5:
        score = float(np.interp(vol_ratio, [1.5, 3.0], [80, 100]))
        label = f"High-volume up-move (×{vol_ratio:.1f}) — conviction buying"
    elif price_change > 0 and vol_ratio > 1.0:
        score = 65.0
        label = f"Above-avg volume with gain (×{vol_ratio:.1f})"
    elif vol_ratio < 0.8:
        score = 50.0
        label = f"Low volume (×{vol_ratio:.1f}) — weak signal"
    elif price_change < 0 and vol_ratio > 1.5:
        score = float(np.interp(vol_ratio, [1.5, 3.0], [20, 0]))
        label = f"High-volume down-move (×{vol_ratio:.1f}) — selling pressure"
    else:
        score = 35.0
        label = f"Volume ×{vol_ratio:.1f} with loss"
    return score, label


def _stoch_score(stoch_k: float, stoch_d: float) -> tuple:
    """Stochastic: below 20 = oversold (buy), above 80 = overbought (sell)."""
    if np.isnan(stoch_k) or np.isnan(stoch_d):
        return 50.0, "Stoch: N/A"
    score = float(np.interp(stoch_k,
                            [0,  20,  40,  60,  80,  100],
                            [90, 80,  55,  45,  20,  10]))
    bullish_cross = stoch_k > stoch_d
    if stoch_k < 20:
        label = f"Stoch={stoch_k:.0f} (oversold{'+ bullish cross' if bullish_cross else ''})"
    elif stoch_k > 80:
        label = f"Stoch={stoch_k:.0f} (overbought{'+ bearish cross' if not bullish_cross else ''})"
    else:
        label = f"Stoch={stoch_k:.0f} ({'bullish' if bullish_cross else 'bearish'} cross)"
    return score, label


# ── Positional scorer (daily candles) ─────────────────────────────────────────

def score_stock(df: pd.DataFrame, weights: dict = None) -> dict:
    if weights is None:
        weights = SCORE_WEIGHTS
    last = df.iloc[-1]

    rsi_s,  rsi_lbl  = _rsi_score(last.get("rsi", np.nan))
    macd_s, macd_lbl = _macd_score(last.get("macd", np.nan),
                                    last.get("macd_signal", np.nan),
                                    df["macd_hist"])
    bb_s,   bb_lbl   = _bb_score(last.get("Close", np.nan),
                                  last.get("bb_lower", np.nan),
                                  last.get("bb_upper", np.nan))
    ma_s,   ma_lbl   = _ma_score(df)
    vol_s,  vol_lbl  = _volume_score(last.get("vol_ratio", np.nan),
                                     last.get("price_change_pct", np.nan))

    sub_scores = {"rsi": rsi_s, "macd": macd_s, "bb": bb_s,
                  "ma": ma_s, "volume": vol_s}
    labels     = {"rsi": rsi_lbl, "macd": macd_lbl, "bb": bb_lbl,
                  "ma": ma_lbl, "volume": vol_lbl}

    composite = sum(sub_scores[k] * weights[k] for k in weights)
    ranked    = sorted(sub_scores.items(), key=lambda x: abs(x[1] - 50), reverse=True)
    reasoning = [labels[k] for k, _ in ranked[:2]]

    return {
        "score":       round(composite, 1),
        "rsi":         round(last.get("rsi", float("nan")), 1),
        "macd_bullish": sub_scores["macd"] >= 50,
        "bb_position": round(
            (last.get("Close", 0) - last.get("bb_lower", 0)) /
            max(last.get("bb_upper", 1) - last.get("bb_lower", 0), 1e-9), 2),
        "ma_cross":  "Golden" if last.get("ma_short", 0) > last.get("ma_long", 0) else "Death",
        "vol_ratio": round(last.get("vol_ratio", float("nan")), 2),
        "sub_scores": sub_scores,
        "reasoning":  reasoning,
        "close":      round(last.get("Close", float("nan")), 2),
    }


# ── Swing scorer (hourly candles) ─────────────────────────────────────────────

def score_stock_swing(df: pd.DataFrame) -> dict:
    """
    Score for swing / short-term trading.
    Returns entry, stop loss, target, and risk:reward in addition to score.
    """
    last = df.iloc[-1]
    weights = SWING_WEIGHTS

    rsi_s,   rsi_lbl   = _rsi_score(last.get("rsi", np.nan))
    macd_s,  macd_lbl  = _macd_score(last.get("macd", np.nan),
                                      last.get("macd_signal", np.nan),
                                      df["macd_hist"])
    bb_s,    bb_lbl    = _bb_score(last.get("Close", np.nan),
                                   last.get("bb_lower", np.nan),
                                   last.get("bb_upper", np.nan))
    ma_s,    ma_lbl    = _ma_score(df)
    vol_s,   vol_lbl   = _volume_score(last.get("vol_ratio", np.nan),
                                       last.get("price_change_pct", np.nan))
    stoch_s, stoch_lbl = _stoch_score(last.get("stoch_k", np.nan),
                                      last.get("stoch_d", np.nan))

    sub_scores = {"rsi": rsi_s, "macd": macd_s, "bb": bb_s,
                  "ma": ma_s, "volume": vol_s, "stoch": stoch_s}
    labels     = {"rsi": rsi_lbl, "macd": macd_lbl, "bb": bb_lbl,
                  "ma": ma_lbl, "volume": vol_lbl, "stoch": stoch_lbl}

    composite = sum(sub_scores[k] * weights[k] for k in weights)
    ranked    = sorted(sub_scores.items(), key=lambda x: abs(x[1] - 50), reverse=True)
    reasoning = [labels[k] for k, _ in ranked[:2]]

    # ── Stop loss & target using ATR ─────────────────────────────────────────
    entry = last.get("Close", float("nan"))
    atr   = last.get("atr",   float("nan"))

    if not np.isnan(atr) and atr > 0:
        stop   = entry - ATR_MULTIPLIER_STOP   * atr
        target = entry + ATR_MULTIPLIER_TARGET * atr
        risk_pct   = (entry - stop)   / entry * 100
        reward_pct = (target - entry) / entry * 100
        rr_ratio   = reward_pct / risk_pct if risk_pct > 0 else float("nan")
    else:
        stop = target = risk_pct = reward_pct = rr_ratio = float("nan")

    # VWAP relationship
    vwap = last.get("vwap", float("nan"))
    above_vwap = (entry > vwap) if not np.isnan(vwap) else None

    return {
        "score":        round(composite, 1),
        "rsi":          round(last.get("rsi", float("nan")), 1),
        "stoch_k":      round(last.get("stoch_k", float("nan")), 1),
        "macd_bullish": sub_scores["macd"] >= 50,
        "ma_cross":     "Golden" if last.get("ma_short", 0) > last.get("ma_long", 0) else "Death",
        "vol_ratio":    round(last.get("vol_ratio", float("nan")), 2),
        "above_vwap":   above_vwap,
        "sub_scores":   sub_scores,
        "reasoning":    reasoning,
        # trade levels
        "entry":      round(entry,      2),
        "stop":       round(stop,       2) if not np.isnan(stop)   else float("nan"),
        "target":     round(target,     2) if not np.isnan(target) else float("nan"),
        "risk_pct":   round(risk_pct,   2) if not np.isnan(risk_pct)   else float("nan"),
        "reward_pct": round(reward_pct, 2) if not np.isnan(reward_pct) else float("nan"),
        "rr_ratio":   round(rr_ratio,   2) if not np.isnan(rr_ratio)   else float("nan"),
        "atr":        round(atr,        2) if not np.isnan(atr)        else float("nan"),
    }


# ── Ranking ───────────────────────────────────────────────────────────────────

def rank_stocks(scored: dict) -> list:
    from scipy.stats import percentileofscore
    rows = [{"ticker": t, **v} for t, v in scored.items()]
    all_scores = [r["score"] for r in rows]
    for r in rows:
        r["percentile"] = round(percentileofscore(all_scores, r["score"]), 0)
    return sorted(rows, key=lambda x: x["score"], reverse=True)
