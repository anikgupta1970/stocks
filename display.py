from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from collections import Counter

console = Console(width=160)


def _score_color(score: float) -> str:
    if score >= 70:
        return "bold green"
    elif score >= 55:
        return "yellow"
    else:
        return "red"


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}" + {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _score_bar(score: float) -> str:
    filled = int(score / 10)
    return "█" * filled + "░" * (10 - filled)


def render_table(results: list, top_n: int, sector_map: dict) -> None:
    shown = results[:top_n]

    table = Table(
        title=f"[bold cyan]NSE Stock Analysis — {top_n} Stocks by Buy Probability[/bold cyan]",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        header_style="bold white on dark_blue",
        expand=False,
    )

    table.add_column("#",       justify="center", style="dim",    width=3)
    table.add_column("Ticker",  justify="left",   style="bold",   width=12, no_wrap=True)
    table.add_column("Sector",  justify="left",                   width=16, no_wrap=True)
    table.add_column("Price ₹", justify="right",                  width=10, no_wrap=True)
    table.add_column("Score",   justify="left",                   width=16, no_wrap=True)
    table.add_column("Pctl",    justify="center",                 width=5,  no_wrap=True)
    table.add_column("RSI",     justify="center",                 width=6,  no_wrap=True)
    table.add_column("MACD",    justify="center",                 width=7,  no_wrap=True)
    table.add_column("MA Trend",justify="center",                 width=9,  no_wrap=True)
    table.add_column("Vol×",    justify="center",                 width=5,  no_wrap=True)
    table.add_column("Key Signals")

    for i, row in enumerate(shown, 1):
        ticker = row["ticker"]
        sector = sector_map.get(ticker, "—")
        score = row["score"]
        color = _score_color(score)
        bar = _score_bar(score)

        score_text = Text()
        score_text.append(bar, style=color)
        score_text.append(f" {score:.0f}", style=f"bold {color}")

        macd_str = "[green]Bull ▲[/green]" if row["macd_bullish"] else "[red]Bear ▼[/red]"
        ma_str   = "[green]Golden[/green]" if row["ma_cross"] == "Golden" else "[red]Death[/red]"

        rsi_val = row["rsi"]
        if rsi_val < 30:
            rsi_cell = f"[bold green]{rsi_val:.1f}[/bold green]"
        elif rsi_val > 70:
            rsi_cell = f"[bold red]{rsi_val:.1f}[/bold red]"
        else:
            rsi_cell = f"{rsi_val:.1f}"

        vol = row["vol_ratio"]
        vol_str = f"{vol:.1f}" if vol == vol else "N/A"   # nan-safe

        signals = " | ".join(row["reasoning"])

        table.add_row(
            str(i),
            ticker.replace(".NS", ""),
            sector,
            f"₹{row['close']:,.1f}",
            score_text,
            _ordinal(int(row["percentile"])),
            rsi_cell,
            macd_str,
            ma_str,
            vol_str,
            signals,
        )

    console.print()
    console.print(table)


def render_summary(results: list, sector_map: dict, errors: list) -> None:
    top10 = results[:10]
    sector_counts = Counter(sector_map.get(r["ticker"], "Other") for r in top10)
    avg_score = sum(r["score"] for r in results) / max(len(results), 1)
    top_score = results[0]["score"] if results else 0

    lines = [
        f"[bold]Stocks analysed:[/bold]  {len(results)}",
        f"[bold]Average score:[/bold]    {avg_score:.1f} / 100",
        f"[bold]Top pick:[/bold]         {results[0]['ticker'].replace('.NS','') if results else '—'} "
        f"(score {top_score:.1f})",
        "",
        "[bold]Sector distribution in top 10:[/bold]",
    ]
    for sector, count in sector_counts.most_common():
        lines.append(f"  {'█' * count}  {sector} ({count})")

    if errors:
        lines.append("")
        skipped = ", ".join(e.replace(".NS", "") for e in errors)
        lines.append(f"[yellow]Skipped (no/insufficient data):[/yellow] {skipped}")

    lines += [
        "",
        "[dim]Score guide:  [bold green]≥70[/bold green] Strong buy · "
        "[yellow]55-69[/yellow] Watch · [red]<55[/red] Neutral/Avoid[/dim]",
        "[dim italic]Disclaimer: Algorithmic analysis only — not financial advice.[/dim italic]",
    ]

    console.print(Panel("\n".join(lines), title="[bold cyan]Summary[/bold cyan]",
                        border_style="cyan", width=100))


def render_swing_table(results: list, top_n: int, sector_map: dict) -> None:
    """Swing-mode table: includes entry, stop loss, target, R:R, VWAP position."""
    shown = results[:top_n]

    table = Table(
        title=f"[bold cyan]NSE Swing Analysis — Top {top_n} Short-Term Picks (1h candles)[/bold cyan]",
        box=box.SIMPLE_HEAVY,
        show_lines=False,
        header_style="bold white on dark_blue",
        expand=False,
    )

    table.add_column("#",         justify="center", style="dim",  width=3)
    table.add_column("Ticker",    justify="left",   style="bold", width=12, no_wrap=True)
    table.add_column("Sector",    justify="left",                 width=14, no_wrap=True)
    table.add_column("Score",     justify="left",                 width=14, no_wrap=True)
    table.add_column("Entry ₹",   justify="right",                width=9,  no_wrap=True)
    table.add_column("Stop ₹",    justify="right",                width=9,  no_wrap=True)
    table.add_column("Target ₹",  justify="right",                width=10, no_wrap=True)
    table.add_column("Risk %",    justify="center",               width=7,  no_wrap=True)
    table.add_column("R:R",       justify="center",               width=5,  no_wrap=True)
    table.add_column("RSI",       justify="center",               width=6,  no_wrap=True)
    table.add_column("Stoch",     justify="center",               width=6,  no_wrap=True)
    table.add_column("VWAP",      justify="center",               width=6,  no_wrap=True)
    table.add_column("Vol×",      justify="center",               width=5,  no_wrap=True)
    table.add_column("Signals")

    for i, row in enumerate(shown, 1):
        ticker = row["ticker"]
        sector = sector_map.get(ticker, "—")
        score  = row["score"]
        color  = _score_color(score)
        bar    = _score_bar(score)

        score_text = Text()
        score_text.append(bar, style=color)
        score_text.append(f" {score:.0f}", style=f"bold {color}")

        entry  = row.get("entry",  float("nan"))
        stop   = row.get("stop",   float("nan"))
        target = row.get("target", float("nan"))
        risk   = row.get("risk_pct",   float("nan"))
        rr     = row.get("rr_ratio",   float("nan"))

        def fmt(v, prefix="₹"):
            return f"{prefix}{v:,.1f}" if v == v else "—"

        rsi_v   = row["rsi"]
        stoch_v = row.get("stoch_k", float("nan"))

        if rsi_v < 30:
            rsi_cell = f"[bold green]{rsi_v:.0f}[/bold green]"
        elif rsi_v > 70:
            rsi_cell = f"[bold red]{rsi_v:.0f}[/bold red]"
        else:
            rsi_cell = f"{rsi_v:.0f}"

        if stoch_v == stoch_v:
            if stoch_v < 20:
                stoch_cell = f"[bold green]{stoch_v:.0f}[/bold green]"
            elif stoch_v > 80:
                stoch_cell = f"[bold red]{stoch_v:.0f}[/bold red]"
            else:
                stoch_cell = f"{stoch_v:.0f}"
        else:
            stoch_cell = "—"

        above_vwap = row.get("above_vwap")
        vwap_cell  = ("[green]Above[/green]" if above_vwap
                      else "[red]Below[/red]" if above_vwap is not None
                      else "—")

        vol     = row.get("vol_ratio", float("nan"))
        vol_str = f"{vol:.1f}" if vol == vol else "—"

        rr_str  = f"{rr:.1f}" if rr == rr else "—"
        risk_str = f"{risk:.1f}%" if risk == risk else "—"
        stop_color = "red" if stop == stop else "white"
        tgt_color  = "green" if target == target else "white"

        signals = " | ".join(row.get("reasoning", []))

        table.add_row(
            str(i),
            ticker.replace(".NS", ""),
            sector,
            score_text,
            fmt(entry),
            f"[{stop_color}]{fmt(stop)}[/{stop_color}]",
            f"[{tgt_color}]{fmt(target)}[/{tgt_color}]",
            risk_str,
            rr_str,
            rsi_cell,
            stoch_cell,
            vwap_cell,
            vol_str,
            signals,
        )

    console.print()
    console.print(table)


def render_swing_summary(results: list, sector_map: dict, errors: list) -> None:
    avg_score  = sum(r["score"] for r in results) / max(len(results), 1)
    top        = results[0] if results else {}
    top_ticker = top.get("ticker", "—").replace(".NS", "")

    # Average R:R of top picks
    top10_rr = [r["rr_ratio"] for r in results[:10]
                if r.get("rr_ratio") == r.get("rr_ratio")]
    avg_rr = sum(top10_rr) / len(top10_rr) if top10_rr else float("nan")

    above_vwap_count = sum(1 for r in results[:10] if r.get("above_vwap"))

    lines = [
        f"[bold]Stocks analysed:[/bold]  {len(results)}",
        f"[bold]Timeframe:[/bold]         1-hour candles (1-month lookback)",
        f"[bold]Avg score:[/bold]         {avg_score:.1f} / 100",
        f"[bold]Top pick:[/bold]          {top_ticker} (score {top.get('score', 0):.1f})",
        f"[bold]Avg R:R (top 10):[/bold]  {avg_rr:.1f}  (target is {avg_rr:.1f}× the risk)"
            if avg_rr == avg_rr else "",
        f"[bold]Above VWAP (top 10):[/bold] {above_vwap_count}/10",
        "",
        "[bold]How to use these levels:[/bold]",
        "  [green]Entry[/green]  → current market price, buy near this",
        "  [red]Stop[/red]   → exit immediately if price falls here (limits loss)",
        "  [green]Target[/green] → take profit at this price",
        "  R:R    → reward ÷ risk. Prefer R:R ≥ 1.5",
        "",
        "[dim]Stop & Target are based on ATR (Average True Range) — "
        "a measure of recent volatility.[/dim]",
        "[dim]Score guide:  [bold green]≥70[/bold green] Strong · "
        "[yellow]55-69[/yellow] Watch · [red]<55[/red] Skip[/dim]",
        "[dim italic]Disclaimer: Algorithmic signals only — not financial advice.[/dim italic]",
    ]

    console.print(Panel("\n".join(l for l in lines if l is not None),
                        title="[bold cyan]Swing Trading Summary[/bold cyan]",
                        border_style="cyan", width=110))
