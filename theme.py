"""
theme.py
---------
Central design system for the AlphaQuant premium UI.
"""
BG_PRIMARY = "#0B0F1A"
BG_SECONDARY = "#111827"
BG_CARD = "rgba(255, 255, 255, 0.035)"
BORDER_CARD = "rgba(255, 255, 255, 0.08)"

ACCENT_START = "#6D5DF6"
ACCENT_END = "#2EC5FF"
ACCENT_SOLID = "#7C6CFA"

POSITIVE = "#22C55E"
POSITIVE_BG = "rgba(34, 197, 94, 0.12)"
NEGATIVE = "#F43F5E"
NEGATIVE_BG = "rgba(244, 63, 94, 0.12)"
WARNING = "#F59E0B"
WARNING_BG = "rgba(245, 158, 11, 0.12)"
NEUTRAL = "#94A3B8"

TEXT_PRIMARY = "#F1F5F9"
TEXT_SECONDARY = "#94A3B8"
TEXT_MUTED = "#64748B"

FONT_STACK = "'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif"
MONO_STACK = "'JetBrains Mono', 'SF Mono', Consolas, monospace"


def inject_css() -> str:
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] {{
        font-family: {FONT_STACK} !important;
    }}

    .stApp {{
        background:
            radial-gradient(circle at 15% 0%, rgba(109, 93, 246, 0.10) 0%, transparent 45%),
            radial-gradient(circle at 85% 15%, rgba(46, 197, 255, 0.08) 0%, transparent 40%),
            {BG_PRIMARY};
    }}

    section[data-testid="stSidebar"] {{
        background: linear-gradient(180deg, {BG_SECONDARY} 0%, {BG_PRIMARY} 100%);
        border-right: 1px solid {BORDER_CARD};
    }}
    section[data-testid="stSidebar"] .stButton button {{
        border-radius: 10px;
        font-weight: 600;
        transition: all 0.2s ease;
    }}
    section[data-testid="stSidebar"] .stButton button[kind="primary"] {{
        background: linear-gradient(135deg, {ACCENT_START} 0%, {ACCENT_END} 100%);
        border: none;
        box-shadow: 0 4px 16px rgba(109, 93, 246, 0.35);
    }}
    section[data-testid="stSidebar"] .stButton button[kind="primary"]:hover {{
        box-shadow: 0 6px 24px rgba(109, 93, 246, 0.5);
        transform: translateY(-1px);
    }}

    .aq-brand-wrap {{
        display: flex; align-items: center; gap: 12px; margin-bottom: 4px;
    }}
    .aq-logo-mark {{
        width: 40px; height: 40px; border-radius: 12px;
        background: linear-gradient(135deg, {ACCENT_START} 0%, {ACCENT_END} 100%);
        display: flex; align-items: center; justify-content: center;
        font-size: 20px; box-shadow: 0 4px 14px rgba(109, 93, 246, 0.4); flex-shrink: 0;
    }}
    .aq-brand-title {{
        font-size: 22px; font-weight: 800; letter-spacing: -0.02em;
        background: linear-gradient(135deg, #FFFFFF 0%, #C7D2FE 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent; line-height: 1.1;
    }}
    .aq-brand-tagline {{ font-size: 12px; color: {TEXT_SECONDARY}; font-weight: 500; margin-top: 2px; }}

    .aq-card {{
        background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 16px;
        padding: 20px 22px; backdrop-filter: blur(12px);
        box-shadow: 0 4px 24px rgba(0,0,0,0.25); margin-bottom: 14px;
    }}
    .aq-card-tight {{ padding: 14px 16px; }}

    .aq-kpi {{
        background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 14px;
        padding: 16px 18px; text-align: left;
    }}
    .aq-kpi-label {{
        font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
        color: {TEXT_MUTED}; font-weight: 600; margin-bottom: 6px;
    }}
    .aq-kpi-value {{
        font-size: 26px; font-weight: 800; color: {TEXT_PRIMARY};
        font-family: {MONO_STACK}; letter-spacing: -0.01em;
    }}
    .aq-kpi-delta {{ font-size: 13px; font-weight: 600; margin-top: 4px; }}
    .aq-kpi-delta.pos {{ color: {POSITIVE}; }}
    .aq-kpi-delta.neg {{ color: {NEGATIVE}; }}
    .aq-kpi-delta.neu {{ color: {TEXT_MUTED}; }}

    .aq-pill {{
        display: inline-flex; align-items: center; gap: 6px;
        padding: 4px 12px; border-radius: 999px; font-size: 12px; font-weight: 700; letter-spacing: 0.02em;
    }}
    .aq-pill.approved {{ background: {POSITIVE_BG}; color: {POSITIVE}; border: 1px solid rgba(34,197,94,0.3); }}
    .aq-pill.rejected {{ background: {NEGATIVE_BG}; color: {NEGATIVE}; border: 1px solid rgba(244,63,94,0.3); }}
    .aq-pill.warning  {{ background: {WARNING_BG}; color: {WARNING}; border: 1px solid rgba(245,158,11,0.3); }}
    .aq-pill.new      {{ background: linear-gradient(135deg, {ACCENT_START}, {ACCENT_END}); color: white; }}
    .aq-pill.neutral  {{ background: rgba(148,163,184,0.1); color: {NEUTRAL}; border: 1px solid rgba(148,163,184,0.2); }}

    .aq-meter-track {{
        width: 100%; height: 8px; border-radius: 999px;
        background: rgba(255,255,255,0.06); overflow: hidden; margin: 8px 0 2px 0;
    }}
    .aq-meter-fill {{ height: 100%; border-radius: 999px; background: linear-gradient(90deg, {ACCENT_START}, {ACCENT_END}); }}

    .aq-section-title {{
        display: flex; align-items: center; gap: 10px;
        font-size: 18px; font-weight: 700; color: {TEXT_PRIMARY}; margin: 6px 0 14px 0;
    }}
    .aq-section-title .bar {{
        width: 4px; height: 20px; border-radius: 4px;
        background: linear-gradient(180deg, {ACCENT_START}, {ACCENT_END});
    }}

    .aq-symbol-chip {{
        font-family: {MONO_STACK}; font-weight: 700; font-size: 15px;
        color: {TEXT_PRIMARY}; letter-spacing: -0.01em;
    }}

    div[data-testid="stMetric"] {{
        background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 14px; padding: 14px 16px;
    }}
    div[data-testid="stMetricValue"] {{ font-family: {MONO_STACK}; }}

    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px; background: {BG_CARD}; padding: 6px; border-radius: 12px; border: 1px solid {BORDER_CARD};
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px; font-weight: 600; color: {TEXT_SECONDARY}; padding: 8px 16px;
    }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(135deg, {ACCENT_START}, {ACCENT_END}) !important; color: white !important;
    }}

    div[data-testid="stExpander"] {{
        background: {BG_CARD}; border: 1px solid {BORDER_CARD}; border-radius: 14px !important; overflow: hidden;
    }}

    .stDataFrame {{ border-radius: 12px; overflow: hidden; }}

    div[data-testid="stProgress"] > div > div {{
        background: linear-gradient(90deg, {ACCENT_START}, {ACCENT_END}) !important;
    }}

    hr {{ border-color: {BORDER_CARD} !important; }}

    .aq-footer {{ text-align: center; color: {TEXT_MUTED}; font-size: 12px; padding: 18px 0 6px 0; line-height: 1.6; }}
    </style>
    """


def kpi_html(label: str, value: str, delta: str | None = None, delta_type: str = "neu") -> str:
    delta_html = f'<div class="aq-kpi-delta {delta_type}">{delta}</div>' if delta else ""
    return f"""
    <div class="aq-kpi">
        <div class="aq-kpi-label">{label}</div>
        <div class="aq-kpi-value">{value}</div>
        {delta_html}
    </div>
    """


def pill_html(text: str, kind: str = "neutral") -> str:
    return f'<span class="aq-pill {kind}">{text}</span>'


def section_title_html(icon: str, text: str) -> str:
    return f'<div class="aq-section-title"><span class="bar"></span>{icon} {text}</div>'


def confidence_meter_html(score: float) -> str:
    score = max(0, min(100, score))
    if score >= 65:
        color = POSITIVE
    elif score >= 45:
        color = WARNING
    else:
        color = NEGATIVE
    return f"""
    <div class="aq-meter-track">
        <div class="aq-meter-fill" style="width:{score}%; background:{color};"></div>
    </div>
    """
