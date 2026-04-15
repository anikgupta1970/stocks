#!/usr/bin/env python3
"""
NSE Stock Trend Analyser
Two modes:
  positional  — daily candles, 6-month lookback, multi-week view
  swing       — hourly candles, 1-month lookback, entry/stop/target for 1-5 day trades
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.progress import (Progress, SpinnerColumn, TextColumn,
                           BarColumn, MofNCompleteColumn, TimeElapsedColumn)

from config import (NIFTY_50_TICKERS, SECTOR_MAP,
                    DEFAULT_PERIOD, DEFAULT_INTERVAL, SCORE_WEIGHTS,
                    SWING_PERIOD, SWING_INTERVAL, SWING_MIN_ROWS)
from data_fetcher import fetch_ticker_data
from indicators import add_all_indicators, add_all_indicators_swing
from scorer import score_stock, score_stock_swing, rank_stocks
from display import (render_table, render_summary,
                     render_swing_table, render_swing_summary, console)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyse NSE stocks and rank by buy probability.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  general   (default) — daily candles, long-term trend view
  intraday            — hourly candles, gives entry/stop/target for 1-5 day trades

Examples:
  python3 main.py                              # All NSE stocks, general mode
  python3 main.py --mode intraday              # All NSE stocks, intraday/swing mode
  python3 main.py --mode intraday --top 20     # Top 20 intraday picks
  python3 main.py --mode intraday --index nifty50  # NIFTY 50 intraday picks
  python3 main.py --index nifty50 --top 10    # NIFTY 50 general top 10
  python3 main.py --sector Banking            # Filter to Banking sector
  python3 main.py --no-cache                  # Force fresh download
        """,
    )
    parser.add_argument("--mode", choices=["general", "intraday"], default="general",
                        help="general=daily candles, long-term | intraday=hourly+stop/target for 1-5 day trades (default: general)")
    parser.add_argument("--index", choices=["all", "nifty50"], default="all",
                        help="Stock universe (default: all NSE equities)")
    parser.add_argument("--top", type=int, default=None,
                        help="Limit output to top N stocks (default: show all)")
    parser.add_argument("--sector", type=str, default=None,
                        help="Filter output by sector")
    parser.add_argument("--period", type=str, default=None,
                        help="Override lookback period (e.g. 3mo, 1y)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore cached data and re-download everything")
    parser.add_argument("--workers", type=int, default=10,
                        help="Parallel download threads (default: 10)")
    return parser.parse_args()


def get_tickers(index: str) -> list:
    if index == "nifty50":
        return NIFTY_50_TICKERS.copy()
    try:
        from universe import get_all_tickers
        tickers = get_all_tickers()
        console.print(f"[dim]NSE universe: {len(tickers):,} listed equities[/dim]")
        return tickers
    except Exception as e:
        console.print(f"[yellow]Warning: could not fetch full NSE list ({e}). "
                      "Falling back to NIFTY 50.[/yellow]")
        return NIFTY_50_TICKERS.copy()


def main():
    args = parse_args()
    use_cache = not args.no_cache

    is_swing = args.mode == "intraday"
    period   = args.period or (SWING_PERIOD if is_swing else DEFAULT_PERIOD)
    interval = SWING_INTERVAL if is_swing else DEFAULT_INTERVAL
    min_rows = SWING_MIN_ROWS if is_swing else 60

    tickers = get_tickers(args.index)

    mode_label = "[yellow]INTRADAY/SWING[/yellow]" if is_swing else "[blue]GENERAL[/blue]"
    console.print(
        f"\n[bold cyan]NSE Stock Analyser[/bold cyan] · {mode_label} mode · "
        f"[white]{len(tickers):,} stocks · {period} · {interval} candles[/white]\n"
    )

    if is_swing:
        console.print(
            "[dim]Swing mode uses 1-hour candles. Provides entry price, stop loss, "
            "target, and R:R ratio for each stock.[/dim]\n"
        )

    if len(tickers) > 200:
        console.print(
            f"[dim]Large universe. First run caches data (~{len(tickers) // args.workers // 2}s). "
            "Subsequent runs are fast.[/dim]\n"
        )

    # ── Fetch ────────────────────────────────────────────────────────────────
    raw_data = {}
    errors   = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
                  console=console) as progress:
        task_id = progress.add_task("Fetching market data...", total=len(tickers))

        def _fetch(ticker):
            return ticker, fetch_ticker_data(ticker, period, interval, use_cache)

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_fetch, t): t for t in tickers}
            for future in as_completed(futures):
                ticker, df = future.result()
                if df.empty or len(df) < min_rows:
                    errors.append(ticker)
                else:
                    raw_data[ticker] = df
                progress.advance(task_id)

    if not raw_data:
        console.print("[red]No data fetched. Check your internet connection.[/red]")
        sys.exit(1)

    console.print(f"[dim]Fetched {len(raw_data):,} stocks "
                  f"({len(errors):,} skipped — no data/delisted/insufficient history)[/dim]")

    # ── Indicators ───────────────────────────────────────────────────────────
    console.print("[dim]Computing indicators...[/dim]")
    enriched = {}
    indicator_fn = add_all_indicators_swing if is_swing else add_all_indicators
    for ticker, df in raw_data.items():
        try:
            enriched[ticker] = indicator_fn(df)
        except Exception:
            errors.append(ticker)

    # ── Score ────────────────────────────────────────────────────────────────
    scored  = {}
    score_fn = score_stock_swing if is_swing else score_stock
    for ticker, df in enriched.items():
        try:
            result = score_fn(df) if is_swing else score_fn(df, SCORE_WEIGHTS)
            scored[ticker] = result
        except Exception:
            errors.append(ticker)

    if not scored:
        console.print("[red]Scoring failed for all stocks.[/red]")
        sys.exit(1)

    # ── Rank & sector filter ─────────────────────────────────────────────────
    ranked = rank_stocks(scored)

    if args.sector:
        sector_lower = args.sector.strip().lower()
        ranked = [r for r in ranked
                  if SECTOR_MAP.get(r["ticker"], "").lower() == sector_lower]
        if not ranked:
            console.print(
                f"[red]No results for sector '{args.sector}'.[/red]\n"
                f"Known sectors: {', '.join(sorted(set(SECTOR_MAP.values())))}"
            )
            sys.exit(1)

    top_n = min(args.top, len(ranked)) if args.top else len(ranked)

    # ── Display ──────────────────────────────────────────────────────────────
    if is_swing:
        render_swing_table(ranked, top_n, SECTOR_MAP)
        render_swing_summary(ranked, SECTOR_MAP, errors)
    else:
        render_table(ranked, top_n, SECTOR_MAP)
        render_summary(ranked, SECTOR_MAP, errors)


if __name__ == "__main__":
    main()
