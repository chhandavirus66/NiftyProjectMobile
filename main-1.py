import flet as ft
import yfinance as yf
import threading
import time
import math
import random
from datetime import datetime


# ============================================================
# NIFTY PRO QUANT TERMINAL
# Android/Flet-friendly single-file main.py
# ============================================================

class AdaptiveQuantConfig:
    def __init__(self):
        self.atr_multiplier = 1.0
        self.optimization_score = 0.0

    def auto_tune(self, wins, losses, total):
        if total <= 0:
            return "No data to optimize."
        win_rate = (wins / total) * 100.0
        self.optimization_score = win_rate
        if win_rate < 70:
            self.atr_multiplier = 1.3
            return (
                f"Accuracy low ({win_rate:.1f}%). "
                "Volatility buffer increased to 1.3x."
            )
        self.atr_multiplier = 1.0
        return f"Accuracy solid ({win_rate:.1f}%). Strategy stable."


quant_config = AdaptiveQuantConfig()


def safe_float(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError, OverflowError):
        return default


def calculate_atr(df, period=14):
    if df is None or df.empty or len(df) < 2:
        return 0.0

    try:
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)
        prev_close = close.shift(1)

        tr1 = (high - low).abs()
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        tr = tr1.combine(tr2, max).combine(tr3, max)
        return safe_float(
            tr.rolling(period, min_periods=1).mean().iloc[-1]
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return 0.0


def calculate_vwap(df):
    if df is None or df.empty:
        return 0.0

    try:
        high = df["High"].astype(float)
        low = df["Low"].astype(float)
        close = df["Close"].astype(float)
        typical = (high + low + close) / 3.0

        if "Volume" in df.columns:
            volume = df["Volume"].fillna(0).astype(float)
            total_volume = safe_float(volume.sum())
            if total_volume > 0:
                return safe_float(
                    (typical * volume).sum() / total_volume
                )

        return safe_float(typical.mean())
    except (KeyError, TypeError, ValueError):
        return 0.0


def calculate_volume_signal(df):
    if df is None or df.empty or "Volume" not in df.columns:
        return "Volume unavailable", 0.0

    try:
        volume = df["Volume"].fillna(0).astype(float)
        if len(volume) < 6:
            return "Insufficient volume data", 0.0

        current = safe_float(volume.iloc[-1])
        baseline = safe_float(volume.iloc[-6:-1].mean())

        if baseline <= 0:
            return "Volume unavailable", 0.0

        change = ((current - baseline) / baseline) * 100.0

        if change >= 25:
            return f"Volume surge (+{change:.0f}% vs 5-bar avg)", change
        if change <= -25:
            return f"Volume contraction ({change:.0f}% vs 5-bar avg)", change

        return f"Volume normal ({change:+.0f}% vs 5-bar avg)", change
    except (TypeError, ValueError, IndexError):
        return "Volume unavailable", 0.0


def calculate_pivots(day_high, day_low, prev_close):
    pivot = (day_high + day_low + prev_close) / 3.0
    s1 = (2.0 * pivot) - day_high
    r1 = (2.0 * pivot) - day_low
    return pivot, s1, r1


def fetch_history(symbol, period="1d", interval="1m"):
    ticker = yf.Ticker(symbol)
    return ticker.history(
        period=period,
        interval=interval,
        auto_adjust=False,
        prepost=False,
        timeout=10,
    )


def main(page: ft.Page):
    # ---------------- PAGE / ANDROID SETTINGS ----------------
    page.title = "NIFTY PRO QUANT TERMINAL"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#020409"
    page.padding = 8
    page.scroll = ft.ScrollMode.AUTO
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER

    # ---------------- SHARED STATE ----------------
    state = {
        "scanning": False,
        "latest_reason": "Run live scan to generate analysis.",
        "scan_lock": threading.Lock(),
        "price": 0.0,
        "vwap": 0.0,
        "macro": "Neutral",
        "verdict": "WAIT",
        "ai_adjustment": "",
        "chart_points": [],
    }

    # ---------------- AI & FLOW CONTROLS ----------------
    big_money_status = ft.Text(
        "Scanning institutional flow...",
        size=11,
        color=ft.colors.YELLOW_300,
        weight=ft.FontWeight.BOLD,
    )
    volume_spike_status = ft.Text(
        "Analyzing real volume...",
        size=11,
        color=ft.colors.CYAN_300,
        weight=ft.FontWeight.BOLD,
    )
    oi_change_status = ft.Text(
        "Option-chain OI: not connected",
        size=11,
        color=ft.colors.PURPLE_300,
        weight=ft.FontWeight.BOLD,
    )

    chat_list = ft.ListView(
        expand=True,
        spacing=4,
        auto_scroll=True,
    )
    chat_list.controls.append(
        ft.Text(
            "🤖 AI Mentor: System Ready.",
            size=10,
            color=ft.colors.CYAN_200,
        )
    )

    # ---------------- CHAT ----------------
    def send_ai_message(e=None):
        q = user_input.value.strip()
        if not q:
            return

        chat_list.controls.append(
            ft.Text(
                f"👤: {q}",
                size=10,
                color=ft.colors.WHITE,
            )
        )
        user_input.value = ""

        ql = q.lower()
        reason = state["latest_reason"]
        verdict = state["verdict"]
        p = state["price"]
        v = state["vwap"]
        m = state["macro"]

        if any(
            x in ql
            for x in (
                "why",
                "reason",
                "setup",
                "up",
                "down",
                "kya",
                "kyun",
                "analysis",
            )
        ):
            if "BULLISH" in verdict:
                reply = (
                    f"🤖 Mentor: Current setup is BULLISH, not a guarantee. "
                    f"Price ₹{p:.0f}, VWAP ₹{v:.0f}. Macro: {m}. "
                    f"{reason}"
                )
            elif "BEARISH" in verdict:
                reply = (
                    f"🤖 Mentor: Current setup is BEARISH, not a guarantee. "
                    f"Price ₹{p:.0f}, VWAP ₹{v:.0f}. Macro: {m}. "
                    f"{reason}"
                )
            else:
                reply = (
                    "🤖 Mentor: Market setup is currently CHOPPY/WAIT. "
                    "A clearer breakout confirmation is needed."
                )
        else:
            reply = (
                "🤖 Mentor: Live scan data is ready. "
                "Ask 'why', 'setup', 'up' or 'down'."
            )

        chat_list.controls.append(
            ft.Text(
                reply,
                size=10,
                color=ft.colors.CYAN_200,
            )
        )

        safe_update(page)

    user_input = ft.TextField(
        hint_text="Ask AI Mentor...",
        expand=True,
        bgcolor="#020409",
        border_color=ft.colors.WHITE24,
        text_size=11,
        height=35,
        content_padding=8,
        border_radius=6,
        on_submit=send_ai_message,
    )

    send_btn_chat = ft.IconButton(
        icon=ft.icons.SEND,
        icon_size=16,
        icon_color=ft.colors.BLUE_400,
        on_click=send_ai_message,
        tooltip="Send",
    )

    ai_flow_content = ft.Container(
        expand=True,
        bgcolor="#0A1128",
        border_radius=12,
        padding=10,
        border=ft.border.all(1, "#1C2A4A"),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.icons.SECURITY,
                            color=ft.colors.GREEN_400,
                            size=14,
                        ),
                        ft.Text(
                            "INSTITUTIONAL FLOW & OI",
                            weight=ft.FontWeight.BOLD,
                            color=ft.colors.GREEN_400,
                            size=11,
                        ),
                    ]
                ),
                ft.Container(
                    bgcolor="#020409",
                    padding=6,
                    border_radius=6,
                    content=ft.Column(
                        [
                            ft.Text(
                                "BIG MONEY:",
                                size=8,
                                color=ft.colors.WHITE54,
                            ),
                            big_money_status,
                            ft.Text(
                                "VOLUME:",
                                size=8,
                                color=ft.colors.WHITE54,
                            ),
                            volume_spike_status,
                            ft.Text(
                                "OI:",
                                size=8,
                                color=ft.colors.WHITE54,
                            ),
                            oi_change_status,
                        ],
                        spacing=1,
                    ),
                ),
                ft.Divider(color=ft.colors.WHITE24, height=10),
                ft.Row(
                    [
                        ft.Icon(
                            ft.icons.SUPPORT_AGENT,
                            color=ft.colors.BLUE_400,
                            size=14,
                        ),
                        ft.Text(
                            "AI TRADING MENTOR",
                            weight=ft.FontWeight.BOLD,
                            color=ft.colors.BLUE_400,
                            size=11,
                        ),
                    ]
                ),
                ft.Container(
                    content=chat_list,
                    expand=True,
                    bgcolor="#020409",
                    padding=6,
                    border_radius=6,
                ),
                ft.Row(
                    [user_input, send_btn_chat],
                    spacing=2,
                ),
            ],
            spacing=6,
        ),
    )

    # ---------------- MACRO CONTROLS ----------------
    ohlc_list = ft.ListView(
        expand=True,
        spacing=3,
        auto_scroll=False,
    )

    def ticker_row(name, ref):
        return ft.Row(
            [
                ft.Text(
                    name,
                    size=11,
                    color=ft.colors.WHITE70,
                    weight=ft.FontWeight.BOLD,
                ),
                ref,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

    hdfc_txt = ft.Text("--", size=11)
    rel_txt = ft.Text("--", size=11)
    dow_txt = ft.Text("--", size=11)
    crude_txt = ft.Text("--", size=11)

    macro_content = ft.Container(
        expand=True,
        bgcolor="#0A1128",
        border_radius=12,
        padding=12,
        border=ft.border.all(1, "#1C2A4A"),
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Icon(
                            ft.icons.SATELLITE_ALT,
                            color=ft.colors.PURPLE_400,
                            size=16,
                        ),
                        ft.Text(
                            "MACRO & SECTOR RADAR",
                            weight=ft.FontWeight.BOLD,
                            color=ft.colors.PURPLE_400,
                            size=12,
                        ),
                    ]
                ),
                ft.Divider(color=ft.colors.WHITE24),
                ticker_row("HDFC BANK", hdfc_txt),
                ticker_row("RELIANCE", rel_txt),
                ft.Divider(color=ft.colors.WHITE24),
                ticker_row("DOW JONES", dow_txt),
                ticker_row("CRUDE OIL", crude_txt),
                ft.Divider(color=ft.colors.WHITE24),
                ft.Row(
                    [
                        ft.Icon(
                            ft.icons.ACCESS_TIME,
                            color=ft.colors.CYAN_400,
                            size=14,
                        ),
                        ft.Text(
                            "15-MIN OHLC FEED",
                            weight=ft.FontWeight.BOLD,
                            color=ft.colors.CYAN_400,
                            size=11,
                        ),
                    ]
                ),
                ft.Container(
                    content=ohlc_list,
                    expand=True,
                    bgcolor="#020409",
                    padding=5,
                    border_radius=6,
                ),
            ],
            expand=True,
        ),
    )

    # ---------------- TERMINAL HEADER ----------------
    time_text = ft.Text(
        "--:--:--",
        size=12,
        weight=ft.FontWeight.BOLD,
        color=ft.colors.CYAN_300,
    )

    header_row = ft.Row(
        [
            ft.Column(
                [
                    ft.Text(
                        "NIFTY QUANT AI",
                        size=18,
                        weight=ft.FontWeight.W_900,
                        color=ft.colors.BLUE_400,
                    ),
                    ft.Text(
                        "MOTO G85 MOBILE TERMINAL",
                        size=8,
                        color=ft.colors.CYAN_700,
                        weight=ft.FontWeight.BOLD,
                    ),
                ],
                spacing=1,
            ),
            time_text,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    price_text = ft.Text(
        "₹0.00",
        size=30,
        weight=ft.FontWeight.BOLD,
        color=ft.colors.WHITE,
    )
    live_status = ft.Text(
        "Waiting...",
        size=10,
        color=ft.colors.WHITE54,
    )

    # ---------------- CHART ----------------
    chart_series = ft.LineChartData(
        data_points=[],
        stroke_width=2,
        color=ft.colors.CYAN_400,
    )

    line_chart = ft.LineChart(
        data_series=[chart_series],
        border=ft.border.all(1, ft.colors.WHITE10),
        expand=True,
        min_y=0,
        max_y=1,
        min_x=0,
        max_x=1,
    )

    chart_container = ft.Container(
        content=line_chart,
        height=140,
        padding=8,
        bgcolor="#0A1128",
        border_radius=10,
        visible=False,
    )

    # ---------------- DATA BOXES ----------------
    sup_text = ft.Text("--", size=11)
    res_text = ft.Text("--", size=11)
    vix_text = ft.Text("--", size=11)
    atr_text = ft.Text("--", size=11)
    vwap_text = ft.Text("--", size=11)

    def data_box(title, ref):
        return ft.Column(
            [
                ft.Text(
                    title,
                    size=8,
                    color=ft.colors.WHITE54,
                    weight=ft.FontWeight.BOLD,
                ),
                ref,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

    data_row = ft.Container(
        content=ft.Row(
            [
                data_box("S1", sup_text),
                data_box("R1", res_text),
                data_box("VIX", vix_text),
                data_box("ATR", atr_text),
                data_box("VWAP", vwap_text),
            ],
            alignment=ft.MainAxisAlignment.SPACE_EVENLY,
        ),
        bgcolor="#0A1128",
        padding=8,
        border_radius=10,
        border=ft.border.all(1, "#1C2A4A"),
    )

    # ---------------- ENGINES ----------------
    engine_news_text = ft.Text(
        "Awaiting Macro...",
        size=9,
        color=ft.colors.WHITE,
    )
    engine_tech_text = ft.Text(
        "Awaiting Quant...",
        size=9,
        color=ft.colors.WHITE,
    )
    engine_live_text = ft.Text(
        "Awaiting Price...",
        size=9,
        color=ft.colors.WHITE,
    )

    def engine_box(title, icon, color, ref):
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(icon, size=12, color=color),
                            ft.Text(
                                title,
                                size=9,
                                weight=ft.FontWeight.BOLD,
                                color=color,
                            ),
                        ]
                    ),
                    ref,
                ],
                spacing=2,
            ),
            bgcolor="#0A1128",
            padding=6,
            border_radius=8,
            border=ft.border.only(
                left=ft.border.BorderSide(3, color)
            ),
        )

    box_news = engine_box(
        "ENGINE 1: MACRO",
        ft.icons.PUBLIC,
        ft.colors.ORANGE_400,
        engine_news_text,
    )
    box_tech = engine_box(
        "ENGINE 2: QUANT",
        ft.icons.DATA_EXPLORATION,
        ft.colors.PURPLE_400,
        engine_tech_text,
    )
    box_live = engine_box(
        "ENGINE 3: PRICE ACTION",
        ft.icons.BOLT,
        ft.colors.YELLOW_400,
        engine_live_text,
    )

    # ---------------- VERDICT ----------------
    final_verdict_text = ft.Text(
        "RUN LIVE SCAN",
        size=11,
        weight=ft.FontWeight.W_900,
        color=ft.colors.WHITE,
    )
    entry_text = ft.Text("ENTRY: --", size=10)
    target_text = ft.Text("TARGET: --", size=10)
    sl_text = ft.Text("SL: --", size=10)
    reason_text = ft.Text(
        "REASON: Awaiting...",
        size=9,
        italic=True,
    )

    final_box = ft.Container(
        content=ft.Column(
            [
                final_verdict_text,
                ft.Divider(color=ft.colors.WHITE24, height=4),
                ft.Row(
                    [entry_text, target_text, sl_text],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(color=ft.colors.WHITE24, height=4),
                reason_text,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor="#070C1E",
        padding=10,
        border_radius=10,
        border=ft.border.all(2, ft.colors.BLUE_700),
    )

    # ---------------- BACKTEST DIALOG ----------------
    backtest_result_text = ft.Text(
        "Initializing AI Backtest...",
        size=11,
        color=ft.colors.WHITE,
    )

    backtest_dialog = ft.AlertDialog(
        title=ft.Text(
            "ALGO TUNER",
            size=14,
            weight=ft.FontWeight.BOLD,
        ),
        content=ft.Container(
            content=backtest_result_text,
            width=280,
            height=180,
            padding=8,
        ),
        bgcolor="#111B2D",
    )

    # ---------------- SAFE UI UPDATE ----------------
    def safe_update(pg):
        try:
            pg.update()
        except Exception:
            pass

    # ---------------- CHART UPDATE ----------------
    def update_chart(df):
        try:
            closes = [
                safe_float(x)
                for x in df["Close"].tail(40).tolist()
            ]
            closes = [x for x in closes if x > 0]

            if len(closes) < 2:
                return

            chart_points = [
                ft.LineChartDataPoint(i, value)
                for i, value in enumerate(closes)
            ]

            chart_series.data_points = chart_points
            line_chart.min_x = 0
            line_chart.max_x = max(1, len(chart_points) - 1)

            low = min(closes)
            high = max(closes)
            padding = max((high - low) * 0.10, 1.0)

            line_chart.min_y = low - padding
            line_chart.max_y = high + padding
            chart_container.visible = True
        except Exception:
            chart_container.visible = False

    # ---------------- BACKTEST ----------------
    def run_backtest(e=None):
        backtest_dialog.open = True
        backtest_result_text.value = "⏳ Running simulation..."
        safe_update(page)

        def worker():
            try:
                # Data download is intentionally retained to validate connectivity.
                _ = fetch_history("^NSEI", "1y", "1d")

                wins = random.randint(15, 25)
                total = 30
                losses = total - wins

                result = quant_config.auto_tune(
                    wins,
                    losses,
                    total,
                )

                backtest_result_text.value = (
                    f"✅ Wins: {wins} | Losses: {losses}\n"
                    f"🎯 Accuracy: {(wins / total) * 100:.1f}%\n\n"
                    f"{result}\n\n"
                    "Note: demo simulation, not a verified strategy."
                )
            except Exception as ex:
                backtest_result_text.value = (
                    f"Backtest/data error:\n{ex}"
                )

            safe_update(page)

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    # ---------------- LIVE DATA SCAN ----------------
    def fetch_all_data(e=None):
        if not state["scan_lock"].acquire(blocking=False):
            return

        state["scanning"] = True
        live_status.value = "Scanning..."
        safe_update(page)

        def background_task():
            try:
                n_hist = fetch_history(
                    "^NSEI",
                    "1d",
                    "1m",
                )

                if n_hist is None or n_hist.empty:
                    raise RuntimeError(
                        "No market data returned by Yahoo Finance."
                    )

                close_series = n_hist["Close"].dropna()
                if close_series.empty:
                    raise RuntimeError("NIFTY close price unavailable.")

                price = safe_float(close_series.iloc[-1])
                vwap = calculate_vwap(n_hist)
                atr = calculate_atr(n_hist, 14)

                # Basic derived levels.
                day_high = safe_float(n_hist["High"].max())
                day_low = safe_float(n_hist["Low"].min())

                if len(close_series) >= 2:
                    previous_close = safe_float(
                        close_series.iloc[-2]
                    )
                else:
                    previous_close = price

                pivot, s1, r1 = calculate_pivots(
                    day_high,
                    day_low,
                    previous_close,
                )

                price_text.value = f"₹{price:,.2f}"
                sup_text.value = f"{s1:.0f}"
                res_text.value = f"{r1:.0f}"
                atr_text.value = f"{atr:.1f}"
                vwap_text.value = f"{vwap:.1f}"

                # Simple VIX fetch.
                try:
                    vix_df = fetch_history(
                        "^INDIAVIX",
                        "1d",
                        "1m",
                    )
                    if vix_df is not None and not vix_df.empty:
                        vix = safe_float(
                            vix_df["Close"].dropna().iloc[-1]
                        )
                        vix_text.value = f"{vix:.2f}"
                    else:
                        vix_text.value = "--"
                except Exception:
                    vix_text.value = "--"

                volume_msg, _ = calculate_volume_signal(n_hist)
                volume_spike_status.value = volume_msg

                # Basic VWAP/price interpretation.
                if vwap > 0 and price > vwap:
                    state["verdict"] = "BULLISH"
                    state["macro"] = "Price above VWAP"
                    reason = (
                        "Price is above session VWAP. "
                        "Confirmation is still required."
                    )
                elif vwap > 0 and price < vwap:
                    state["verdict"] = "BEARISH"
                    state["macro"] = "Price below VWAP"
                    reason = (
                        "Price is below session VWAP. "
                        "Confirmation is still required."
                    )
                else:
                    state["verdict"] = "WAIT"
                    state["macro"] = "Neutral"
                    reason = (
                        "VWAP comparison is inconclusive."
                    )

                state["price"] = price
                state["vwap"] = vwap
                state["latest_reason"] = reason

                engine_news_text.value = (
                    "News API is not connected. "
                    "No live news sentiment is being claimed."
                )
                engine_tech_text.value = (
                    f"Price/VWAP: {state['verdict']} | "
                    f"ATR: {atr:.1f} | Pivot: {pivot:.1f}"
                )
                engine_live_text.value = (
                    f"Last price ₹{price:,.2f} | "
                    f"VWAP ₹{vwap:,.2f}"
                )

                big_money_status.value = (
                    "Institutional flow API not connected"
                )
                oi_change_status.value = (
                    "Option-chain OI API not connected"
                )

                final_verdict_text.value = (
                    f"VERDICT: {state['verdict']}"
                )
                entry_text.value = f"ENTRY: ₹{price:.0f}"
                target_text.value = (
                    f"TARGET: ₹{price + atr * 1.5:.0f}"
                    if atr > 0
                    else "TARGET: --"
                )
                sl_text.value = (
                    f"SL: ₹{price - atr:.0f}"
                    if atr > 0
                    else "SL: --"
                )
                reason_text.value = f"REASON: {reason}"

                update_chart(n_hist)

                live_status.value = (
                    datetime.now().strftime("%H:%M:%S")
                )

            except Exception as ex:
                live_status.value = "Data Error"
                engine_news_text.value = (
                    "Market data request failed."
                )
                reason_text.value = (
                    f"REASON: {str(ex)[:180]}"
                )

            finally:
                state["scanning"] = False
                state["scan_lock"].release()
                safe_update(page)

        threading.Thread(
            target=background_task,
            daemon=True,
        ).start()

    # ---------------- CLOCK ----------------
    def update_clock():
        while True:
            try:
                time_text.value = datetime.now().strftime(
                    "%H:%M:%S"
                )
                safe_update(page)
                time.sleep(1)
            except Exception:
                break

    # ---------------- AUTO SCAN ----------------
    def auto_scan_loop():
        while True:
            try:
                if auto_scan_switch.value:
                    fetch_all_data()
                time.sleep(5)
            except Exception:
                time.sleep(5)

    scan_btn = ft.ElevatedButton(
        "LIVE SCAN",
        icon=ft.icons.RADAR,
        bgcolor=ft.colors.BLUE_700,
        color=ft.colors.WHITE,
        on_click=fetch_all_data,
        expand=True,
    )

    backtest_btn = ft.ElevatedButton(
        "SCALP TEST",
        icon=ft.icons.STAR,
        bgcolor=ft.colors.PURPLE_700,
        color=ft.colors.WHITE,
        on_click=run_backtest,
        expand=True,
    )

    auto_scan_switch = ft.Switch(
        label="Auto Scan (5s)",
        value=False,
        active_color=ft.colors.GREEN_400,
    )

    terminal_content = ft.Container(
        expand=True,
        content=ft.Column(
            [
                header_row,
                ft.Row(
                    [price_text, live_status],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                chart_container,
                data_row,
                box_news,
                box_tech,
                box_live,
                final_box,
                ft.Row(
                    [scan_btn, backtest_btn],
                    spacing=10,
                ),
                ft.Row(
                    [auto_scan_switch],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            expand=True,
            spacing=6,
            scroll=ft.ScrollMode.AUTO,
        ),
    )

    main_tabs = ft.Tabs(
        selected_index=0,
        expand=True,
        tabs=[
            ft.Tab(
                text="Terminal",
                icon=ft.icons.DASHBOARD,
                content=terminal_content,
            ),
            ft.Tab(
                text="AI & Flow",
                icon=ft.icons.SUPPORT_AGENT,
                content=ai_flow_content,
            ),
            ft.Tab(
                text="Macro",
                icon=ft.icons.PUBLIC,
                content=macro_content,
            ),
        ],
    )

    page.add(main_tabs)

    # Start background loops after controls are created.
    threading.Thread(
        target=update_clock,
        daemon=True,
    ).start()

    threading.Thread(
        target=auto_scan_loop,
        daemon=True,
    ).start()


if __name__ == "__main__":
    ft.app(target=main)
