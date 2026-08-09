"""
charts.py
----------
Plotly chart builders for the premium UI.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import theme

_PLOT_BG = "rgba(0,0,0,0)"
_PAPER_BG = "rgba(0,0,0,0)"
_GRID_COLOR = "rgba(255,255,255,0.06)"
_FONT = dict(family=theme.FONT_STACK, color=theme.TEXT_SECONDARY, size=12)


def _base_layout(height: int = 320, title: str | None = None) -> dict:
    layout = dict(
        height=height, plot_bgcolor=_PLOT_BG, paper_bgcolor=_PAPER_BG, font=_FONT,
        margin=dict(l=10, r=10, t=40 if title else 10, b=10),
        xaxis=dict(gridcolor=_GRID_COLOR, showline=False, zeroline=False),
        yaxis=dict(gridcolor=_GRID_COLOR, showline=False, zeroline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
    )
    if title:
        layout["title"] = dict(text=title, font=dict(size=14, color=theme.TEXT_PRIMARY), x=0.01)
    return layout


def price_chart_with_levels(daily_df: pd.DataFrame, entry: float, stop: float,
                             targets: dict, symbol: str, lookback_days: int = 60) -> go.Figure:
    df = daily_df.tail(lookback_days)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"],
        increasing_line_color=theme.POSITIVE, decreasing_line_color=theme.NEGATIVE,
        increasing_fillcolor=theme.POSITIVE, decreasing_fillcolor=theme.NEGATIVE,
        name=symbol, showlegend=False,
    ))

    def _hline(y, color, label, dash="dot"):
        fig.add_hline(y=y, line=dict(color=color, width=1.5, dash=dash),
                      annotation_text=f"{label} {y:,.2f}", annotation_position="right",
                      annotation_font=dict(color=color, size=11))

    _hline(entry, theme.ACCENT_SOLID, "Entry", dash="solid")
    _hline(stop, theme.NEGATIVE, "Stop")
    for label, level in targets.items():
        _hline(level, theme.POSITIVE, label)

    fig.update_layout(**_base_layout(height=360))
    fig.update_layout(xaxis_rangeslider_visible=False)
    return fig


def monte_carlo_fan_chart(entry: float, price_paths_sample: list, horizon_days: int) -> go.Figure:
    fig = go.Figure()
    paths = np.array(price_paths_sample)
    x = list(range(horizon_days + 1))
    paths_with_entry = np.column_stack([np.full(len(paths), entry), paths])

    p5 = np.percentile(paths_with_entry, 5, axis=0)
    p25 = np.percentile(paths_with_entry, 25, axis=0)
    p50 = np.percentile(paths_with_entry, 50, axis=0)
    p75 = np.percentile(paths_with_entry, 75, axis=0)
    p95 = np.percentile(paths_with_entry, 95, axis=0)

    fig.add_trace(go.Scatter(x=x, y=p95, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=p5, line=dict(width=0), fill="tonexty",
                              fillcolor="rgba(109,93,246,0.08)", name="5th-95th pct", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=p75, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=p25, line=dict(width=0), fill="tonexty",
                              fillcolor="rgba(109,93,246,0.20)", name="25th-75th pct", hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=p50, line=dict(color=theme.ACCENT_END, width=2.5), name="Median path"))

    fig.update_layout(**_base_layout(height=280))
    fig.update_xaxes(title_text="Trading days ahead")
    fig.update_yaxes(title_text="Price")
    return fig


def confidence_gauge(score: float) -> go.Figure:
    if score >= 65:
        color = theme.POSITIVE
    elif score >= 45:
        color = theme.WARNING
    else:
        color = theme.NEGATIVE

    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=score,
        number=dict(suffix="", font=dict(size=32, color=theme.TEXT_PRIMARY)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor=theme.TEXT_MUTED, tickfont=dict(size=9)),
            bar=dict(color=color, thickness=0.3), bgcolor="rgba(255,255,255,0.03)", borderwidth=0,
            steps=[dict(range=[0, 45], color="rgba(244,63,94,0.08)"),
                   dict(range=[45, 65], color="rgba(245,158,11,0.08)"),
                   dict(range=[65, 100], color="rgba(34,197,94,0.08)")],
        ),
    ))
    fig.update_layout(height=160, margin=dict(l=20, r=20, t=10, b=10), paper_bgcolor=_PAPER_BG, font=_FONT)
    return fig


def component_radar(components: dict) -> go.Figure:
    labels = list(components.keys())
    values = list(components.values())
    values_closed = values + [values[0]]
    labels_closed = labels + [labels[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values_closed, theta=[l.replace("_", " ").title() for l in labels_closed],
        fill="toself", fillcolor="rgba(109,93,246,0.25)",
        line=dict(color=theme.ACCENT_END, width=2), marker=dict(size=5, color=theme.ACCENT_START),
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=_GRID_COLOR,
                             tickfont=dict(size=8, color=theme.TEXT_MUTED)),
            angularaxis=dict(gridcolor=_GRID_COLOR, tickfont=dict(size=11, color=theme.TEXT_SECONDARY)),
            bgcolor="rgba(0,0,0,0)",
        ),
        showlegend=False, height=280, margin=dict(l=40, r=40, t=20, b=20),
        paper_bgcolor=_PAPER_BG, font=_FONT,
    )
    return fig


def sentiment_donut(headlines: pd.DataFrame) -> go.Figure:
    if headlines.empty or "sentiment_label" not in headlines.columns:
        counts = {"positive": 0, "neutral": 0, "negative": 0, "unknown": 1}
    else:
        counts = headlines["sentiment_label"].value_counts().to_dict()

    color_map = {"positive": theme.POSITIVE, "neutral": theme.NEUTRAL,
                 "negative": theme.NEGATIVE, "unknown": theme.TEXT_MUTED}
    labels = list(counts.keys())
    values = list(counts.values())
    colors = [color_map.get(l, theme.TEXT_MUTED) for l in labels]

    fig = go.Figure(go.Pie(
        labels=[l.title() for l in labels], values=values, hole=0.65,
        marker=dict(colors=colors, line=dict(color=theme.BG_PRIMARY, width=2)),
        textinfo="label+percent", textfont=dict(size=11, color=theme.TEXT_PRIMARY),
    ))
    fig.update_layout(height=220, showlegend=False, margin=dict(l=10, r=10, t=10, b=10),
                       paper_bgcolor=_PAPER_BG, font=_FONT)
    return fig


def rel_volume_bar(scanned: pd.DataFrame) -> go.Figure:
    df = scanned.sort_values("rel_volume", ascending=True)
    if len(df) > 40:
        df = df.tail(40)  # keep the chart readable when scanning hundreds of symbols
    colors = [theme.POSITIVE if q else theme.TEXT_MUTED for q in df["qualifies"]]

    fig = go.Figure(go.Bar(
        x=df["rel_volume"], y=df["symbol"], orientation="h", marker=dict(color=colors),
        text=[f"{v:.2f}x" for v in df["rel_volume"]], textposition="outside",
        textfont=dict(size=10, color=theme.TEXT_SECONDARY),
    ))
    fig.add_vline(x=1.5, line=dict(color=theme.WARNING, width=1, dash="dash"))
    fig.update_layout(**_base_layout(height=max(280, len(df) * 22)))
    fig.update_xaxes(title_text="Relative volume (vs 20d avg)")
    return fig
