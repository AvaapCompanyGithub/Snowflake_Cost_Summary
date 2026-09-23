"""
Snowflake Cost Summary

Requires the app owner role to hold IMPORTED PRIVILEGES on database SNOWFLAKE.
Uses only packages bundled with Streamlit in Snowflake — no extra packages needed.
"""

import calendar
import json
import decimal

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import math
from snowflake.snowpark.context import get_active_session

# -------------------------------------------------
# Session
# -------------------------------------------------

try:
    session = get_active_session()
except Exception:
    conn = st.connection("snowflake")
    session = conn.session()
else:
    class _SessConn:
        def query(self, sql, ttl=300):
            return session.sql(sql).to_pandas()
    conn = _SessConn()

# -------------------------------------------------
# Page config
# -------------------------------------------------

st.set_page_config(
    page_title="Cost Summary",
    page_icon="📊",
    layout="wide",
)

# ----------------------------------------------------------------------
# Page settings
# Cache Snowflake queries for 1h; cast NUMBER/Decimal to float for charts.
# ----------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner="Querying ACCOUNT_USAGE...")

def _query(sql: str, start: str, end: str) -> pd.DataFrame:
    df = session.sql(sql, params=[start, end]).to_pandas()
    # Snowflake NUMBER(p,s) arrives as decimal.Decimal -> object dtype.
    # Cast to float so .round(), .clip() and the charts work.
    for c in df.columns:
        if df[c].map(lambda v: isinstance(v, decimal.Decimal)).any():
            df[c] = df[c].astype(float)
    return df


def run(sql: str, start: str, end: str) -> pd.DataFrame:
    """A missing view or column degrades one section, not the whole app."""
    try:
        return _query(sql, start, end)
    except Exception as e:
        st.warning(f"Query failed, section will be empty: {e}")
        return pd.DataFrame()


def run_optional(sql: str, start: str, end: str) -> pd.DataFrame:
    """Silent variant: these views are legitimately absent on many accounts."""
    try:
        return _query(sql, start, end)
    except Exception:
        return pd.DataFrame()

# ------------------------------------------------------------------
# Config from config.json (same folder as this app)
# ------------------------------------------------------------------

def _load_config():
    candidates = []
    try:
        candidates.append(Path(__file__).resolve().parent / "config.json")
    except Exception:
        pass
    candidates.append(Path("config.json"))
    for path in candidates:
        if path.is_file():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("config.json must contain a JSON object")
            return data, path
    raise FileNotFoundError(
        "config.json not found next to cost_summary.py. "
        "Add config.json with contract_start, annual_capacity, credit_rate, credit_rate_label."
    )

_cfg, _cfg_path = _load_config()
contract_start = datetime.strptime(str(_cfg["contract_start"])[:10], "%Y-%m-%d").date()
annual_budget = float(_cfg["annual_capacity"])
credit_price = float(_cfg["credit_rate"])
rate_choice = str(_cfg.get("credit_rate_label", "") or "Configured rate")
if credit_price <= 0:
    rate_choice = "Credits only"

# ----------------------------------------------------------------------
# Colors
# ----------------------------------------------------------------------

NAVY = "#16324F"
NAVY_LIGHT = "#2A5F8F"  # slightly lighter blue for Total spend card
NAVY_DEEP = "#0F2438"
SNOW_BLUE = "#29B5E8"
BLUE_MID = "#5FC5EC"
BLUE_LIGHT = "#A7D8EF"
BLUE_PALE = "#CFE8F5"
PANEL = "#E9EEF2"
CARD_BG = "#EEF2F6"
INK = "#0F2438"
MUTED = "#6B7F92"
GREEN = "#1F9D6B"
RED = "#C23B3B"
WHITE = "#FFFFFF"

SERIES_COLORS = {
    "Warehouse Compute": "#C44E52",  # red
    "Serverless": "#55A868",         # teal/green
    "AI Services": "#4C72B0",        # blue
    "Cloud Services": "#CCB974",     # gold/yellow
}
DONUT_COLORS = [NAVY, SNOW_BLUE, BLUE_LIGHT, BLUE_PALE, "#7BA3C9", "#4A7BA7"]

# ----------------------------------------------------------------------
# Style
# ----------------------------------------------------------------------

st.markdown(
    f"""
    <style>
      .stApp {{ background: #F4F6F8; }}
      .block-container {{ padding-top: 1.4rem; max-width: 1600px; }}
      #MainMenu, footer {{ visibility: hidden; }}

      .masthead {{ display: flex; align-items: baseline; gap: .55rem; margin-bottom: .1rem; }}
      .masthead h1 {{
        font-size: 1.65rem; font-weight: 800; color: {INK};
        margin: 0; letter-spacing: -.02em;
      }}
      .masthead .logo {{
        height: 28px; width: auto; object-fit: contain;
        display: block;
      }}
      .masthead .logo-fallback {{
        width: 28px; height: 28px; border-radius: 6px;
        background: linear-gradient(135deg, {SNOW_BLUE}, {NAVY_LIGHT});
        flex-shrink: 0;
      }}
      .subhead {{ color: {MUTED}; font-size: .75rem; margin: .1rem 0 .8rem 0; }}

      .card {{
        border-radius: 12px; padding: .75rem .9rem 0.85rem .9rem; height: 100%;
        text-align: center; background: {CARD_BG};
        border: 1px solid #E2E8EE;
      }}
      .card.primary {{
        background: {NAVY_LIGHT}; color: #FFFFFF; text-align: left;
        padding: .85rem 1rem; border: none;
      }}
      .card .label {{
        font-size: .62rem; font-weight: 600; letter-spacing: .01em;
        opacity: .85; margin-bottom: .2rem; line-height: 1.2;
      }}
      .card .value {{
        font-size: 1.25rem; font-weight: 800; letter-spacing: -.03em;
        line-height: 1.15; font-variant-numeric: tabular-nums;
        color: {INK};
      }}
      .card.primary .value {{ color: #FFFFFF; font-size: 1.42rem; }}
      .card .delta-pill {{
        display: inline-block; margin-top: .35rem; margin-bottom: .25rem;
        padding: .12rem .5rem; border-radius: 999px;
        font-size: .62rem; font-weight: 600;
      }}
      .card .delta-pill.up {{ background: #D8F3E7; color: {GREEN}; }}
      .card .delta-pill.down {{ background: #FDE8E8; color: {RED}; }}
      .card.primary .delta-pill.up {{ background: rgba(125,255,179,.22); color: #7DFFB3; }}
      .card.primary .delta-pill.down {{ background: rgba(255,180,180,.22); color: #FFB4B4; }}
      .card .foot {{
        font-size: .78rem; color: {MUTED}; margin-top: .15rem;
        line-height: 1.35;
      }}
      .card.primary .foot {{ color: rgba(255,255,255,.78); }}
      .budget-bar {{
        height: 5px; border-radius: 3px; background: rgba(255,255,255,.18);
        margin: .45rem 0 .35rem 0; overflow: hidden;
      }}
      .budget-bar span {{ display: block; height: 100%; background: {SNOW_BLUE}; border-radius: 3px; }}

      .tray {{
        background: {PANEL}; border-radius: 10px;
        padding: .45rem .5rem;
      }}

      .note {{
        text-align: left; color: {MUTED}; font-size: .66rem;
        margin: .55rem 0 1rem 0; line-height: 1.4;
      }}
      .panel-title {{
        font-size: .82rem; font-weight: 700; color: {INK};
        margin: 0 0 .4rem .05rem;
      }}
      div[data-testid="stSelectbox"] label,
      div[data-testid="stDateInput"] label {{
        color: {MUTED}; font-size: .72rem;
      }}
      .range-label {{
        font-size: .78rem; color: {INK}; margin: .35rem 0 .5rem 0;
      }}
      .range-label b {{ color: {RED}; }}

      /* Smaller Warehouse Detail dataframe text */
      div[data-testid="stDataFrame"] {{
        font-size: 0.72rem;
      }}
      div[data-testid="stDataFrame"] table {{
        font-size: 0.72rem;
      }}
      div[data-testid="stDataFrame"] th {{
        font-size: 0.68rem !important;
        padding-top: 0.25rem !important;
        padding-bottom: 0.25rem !important;
      }}
      div[data-testid="stDataFrame"] td {{
        font-size: 0.72rem !important;
        padding-top: 0.2rem !important;
        padding-bottom: 0.2rem !important;
      }}

      /* Denser stacked bars (Vega / native chart) */
      .stVegaLiteChart svg g.mark-rect > path,
      .stVegaLiteChart svg rect {{ }}
      div[data-testid="stVegaLiteChart"] svg .mark-bar rect,
      div[data-testid="stArrowVegaLiteChart"] svg .mark-bar rect {{
        /* browser may ignore; height increase is primary lever */
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------
# Logo
# ----------------------------------------------------------------------

_logo_html = '<div class="logo-fallback" title="Add logo.png or logo.jpg"></div>'
try:
    from pathlib import Path as _Path
    import base64 as _b64
    _logo_dir = _Path(__file__).resolve().parent
    _logo_path = None
    _mime = None
    for _name, _m in (
        ("logo.png", "image/png"),
        ("logo.jpg", "image/jpeg"),
        ("logo.jpeg", "image/jpeg"),
    ):
        _candidate = _logo_dir / _name
        if _candidate.is_file():
            _logo_path, _mime = _candidate, _m
            break
    if _logo_path is not None:
        _b64data = _b64.b64encode(_logo_path.read_bytes()).decode("ascii")
        _logo_html = (
            f'<img class="logo" alt="Logo" '
            f'src="data:{_mime};base64,{_b64data}"/>'
        )
except Exception:
    pass

# ----------------------------------------------------------------------
# Page Header
# ----------------------------------------------------------------------

# Dropdown label -> short code used on the Total card
DATE_PRESET_MAP = {
    "Today": "TODAY",
    "Week to Date": "WTD",
    "Month to Date": "MTD",
    "Quarter to Date": "QTD",
    "Year to Date": "YTD",
}
DATE_PRESETS = list(DATE_PRESET_MAP.keys())

if "last_refreshed" not in st.session_state:
    st.session_state.last_refreshed = datetime.now()

title_col, range_col = st.columns([3.2, 1.3])
with title_col:
    st.markdown(
        f'<div class="masthead">{_logo_html}<h1>Cost Summary</h1></div>'
        '<div class="subhead">High-level financial overview of compute, storage, '
        "and serverless consumption.</div>"
        f'<div style="color:{MUTED};font-size:.72rem;margin:-0.35rem 0 0.15rem 0;">'
        f"Last refreshed: {st.session_state.last_refreshed.strftime('%Y-%m-%d %H:%M:%S')}</div>",
        unsafe_allow_html=True,
    )
with range_col:
    preset_label = st.selectbox(
        "Date Range",
        DATE_PRESETS,
        index=DATE_PRESETS.index("Year to Date"),
    )
    preset = DATE_PRESET_MAP[preset_label]

today = datetime.now().date()
if preset == "TODAY":
    start_date = today
    end_date = today
elif preset == "WTD":
    start_date = today - timedelta(days=today.weekday())  # Monday
    end_date = today
elif preset == "MTD":
    start_date = today.replace(day=1)
    end_date = today
elif preset == "QTD":
    quarter_start_month = ((today.month - 1) // 3) * 3 + 1
    start_date = today.replace(month=quarter_start_month, day=1)
    end_date = today
else:  # YTD
    start_date = today.replace(month=1, day=1)
    end_date = today

with range_col:
    st.markdown(
        f'<div style="color:{MUTED};font-size:0.72rem;margin-top:-0.35rem;">'
        f'{start_date.strftime("%b %d, %Y")} → {end_date.strftime("%b %d, %Y")}'
        f'</div>',
        unsafe_allow_html=True,
    )

st.markdown("---")

start_ts = start_date.strftime("%Y-%m-%d")
end_ts = end_date.strftime("%Y-%m-%d")

# ACCOUNT_USAGE ranges are half-open; end bound is exclusive.
p_start = start_ts
p_end = (end_date + timedelta(days=1)).isoformat()


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

Q_WAREHOUSE = """
SELECT warehouse_name                                AS "Warehouse"
     , SUM(credits_used_compute)                     AS "Compute"
     , SUM(credits_used_cloud_services)              AS "Cloud Services"
     , SUM(COALESCE(credits_attributed_compute_queries, 0)) AS "Query Attributed"
     , GREATEST(SUM(credits_used_compute)
       - SUM(COALESCE(credits_attributed_compute_queries, 0)), 0) AS "Idle"
     , SUM(credits_used)                             AS "Total Credits"
FROM snowflake.account_usage.warehouse_metering_history
WHERE start_time >= ? AND start_time < ?
GROUP BY 1
ORDER BY "Total Credits" DESC
"""

Q_WAREHOUSE_DAILY = """
SELECT TO_CHAR(start_time, 'YYYY-MM-DD') AS "Date"
     , warehouse_name       AS "Warehouse"
     , SUM(credits_used)    AS "Credits"
FROM snowflake.account_usage.warehouse_metering_history
WHERE start_time >= ? AND start_time < ?
GROUP BY 1, 2
ORDER BY 1
"""

Q_QUERY = """
SELECT warehouse_name                       AS "Warehouse"
     , COUNT(*)                             AS "Queries"
     , SUM(credits_attributed_compute)      AS "Query Credits"
     , SUM(credits_used_query_acceleration) AS "Query Acceleration"
     , AVG(credits_attributed_compute)      AS "Avg Credits / Query"
FROM snowflake.account_usage.query_attribution_history
WHERE start_time >= ? AND start_time < ?
GROUP BY 1
ORDER BY "Query Credits" DESC
"""

# One predicate defines AI. Q_SERVERLESS negates it, so the two sections
# can never overlap or leave a gap. Add new AI service types here only.
AI_PREDICATE = """(
       service_type LIKE 'AI%'
    OR service_type LIKE 'CORTEX%'
    OR service_type LIKE 'SNOWFLAKE_COCO%'
    OR service_type IN ('SNOWFLAKE_COWORK', 'SNOWFLAKE_INTELLIGENCE')
  )"""

Q_SERVERLESS = f"""
SELECT service_type        AS "Service"
     , SUM(credits_used)   AS "Credits"
FROM snowflake.account_usage.metering_daily_history
WHERE usage_date >= ? AND usage_date < ?
  AND service_type NOT IN ('WAREHOUSE_METERING', 'WAREHOUSE_METERING_READER')
  AND NOT {AI_PREDICATE}
GROUP BY 1
HAVING SUM(credits_used) > 0
ORDER BY "Credits" DESC
"""

Q_SERVERLESS_DAILY = f"""
SELECT TO_CHAR(usage_date, 'YYYY-MM-DD') AS "Date"
     , SUM(credits_used)                 AS "Credits"
FROM snowflake.account_usage.metering_daily_history
WHERE usage_date >= ? AND usage_date < ?
  AND service_type NOT IN ('WAREHOUSE_METERING', 'WAREHOUSE_METERING_READER')
  AND NOT {AI_PREDICATE}
GROUP BY 1
ORDER BY 1
"""

Q_CLOUD = """
SELECT TO_CHAR(usage_date, 'YYYY-MM-DD')          AS "Date"
     , SUM(credits_used_compute)                  AS "Warehouse Compute"
     , SUM(credits_used_cloud_services)           AS "Cloud Services Used"
     , -SUM(credits_adjustment_cloud_services)    AS "Covered by allowance"
     , SUM(credits_used_cloud_services)
       + SUM(credits_adjustment_cloud_services)   AS "Billed"
FROM snowflake.account_usage.metering_daily_history
WHERE usage_date >= ? AND usage_date < ?
GROUP BY 1
ORDER BY 1
"""

Q_TRANSFER = """
SELECT transfer_type AS "Type"
     , source_cloud || ' ' || source_region || '  ->  '
       || target_cloud || ' ' || target_region      AS "Route"
     , SUM(bytes_transferred) / POWER(1024, 4)      AS "TB"
FROM snowflake.account_usage.data_transfer_history
WHERE start_time >= ? AND start_time < ?
GROUP BY 1, 2
HAVING SUM(bytes_transferred) > 0
ORDER BY "TB" DESC
"""

Q_STORAGE = """
SELECT usage_date                    AS "Date"
     , storage_bytes  / POWER(1024, 4) AS "Database"
     , stage_bytes    / POWER(1024, 4) AS "Stage"
     , failsafe_bytes / POWER(1024, 4) AS "Fail-safe"
FROM snowflake.account_usage.storage_usage
WHERE usage_date >= ? AND usage_date < ?
ORDER BY 1
"""

Q_AI = f"""
SELECT service_type        AS "Service"
     , SUM(credits_used)   AS "Credits"
FROM snowflake.account_usage.metering_daily_history
WHERE usage_date >= ? AND usage_date < ?
  AND {AI_PREDICATE}
GROUP BY 1
HAVING SUM(credits_used) > 0
ORDER BY "Credits" DESC
"""

Q_AI_DAILY = f"""
SELECT TO_CHAR(usage_date, 'YYYY-MM-DD') AS "Date"
     , SUM(credits_used)                 AS "Credits"
FROM snowflake.account_usage.metering_daily_history
WHERE usage_date >= ? AND usage_date < ?
  AND {AI_PREDICATE}
GROUP BY 1
ORDER BY 1
"""

Q_AI_DETAIL = """
SELECT COALESCE(model_name, '(none)') AS "Model"
     , function_name                  AS "Function"
     , SUM(tokens)                    AS "Tokens"
     , SUM(token_credits)             AS "Credits"
FROM snowflake.account_usage.cortex_functions_usage_history
WHERE start_time >= ? AND start_time < ?
GROUP BY 1, 2
ORDER BY "Credits" DESC
"""


wh = run(Q_WAREHOUSE, p_start, p_end)
wh_daily = run(Q_WAREHOUSE_DAILY, p_start, p_end)
qry = run(Q_QUERY, p_start, p_end)
srv = run(Q_SERVERLESS, p_start, p_end)
srv_daily = run(Q_SERVERLESS_DAILY, p_start, p_end)
cld = run(Q_CLOUD, p_start, p_end)
stg = run(Q_STORAGE, p_start, p_end)
xfer = run(Q_TRANSFER, p_start, p_end)
ai = run_optional(Q_AI, p_start, p_end)
ai_daily = run_optional(Q_AI_DAILY, p_start, p_end)
ai_detail = run_optional(Q_AI_DETAIL, p_start, p_end)


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------

# Comparison window. Named calendar presets shift by a whole period so the
# same portion of the prior week/month/quarter/year is compared; rolling
# "Last N Days" presets shift by their own length.
PERIOD_SHIFT = {
    "TODAY": ("days", 1),
    "WTD": ("days", 7),
    "MTD": ("months", 1),
    "QTD": ("months", 3),
    "YTD": ("months", 12),
}


def shift_months(d, n):
    m = d.month - 1 - n
    y = d.year + m // 12
    m = m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


span = (end_date - start_date).days + 1
kind, n = PERIOD_SHIFT.get(preset, ("days", span))

if kind == "days":
    pp_start_date = start_date - timedelta(days=n)
    pp_end_date = end_date - timedelta(days=n)
else:
    pp_start_date = shift_months(start_date, n)
    pp_end_date = shift_months(end_date, n)

pp_start = pp_start_date.isoformat()
pp_end = (pp_end_date + timedelta(days=1)).isoformat()

pp_wh = run(Q_WAREHOUSE, pp_start, pp_end)
pp_srv = run(Q_SERVERLESS, pp_start, pp_end)
pp_cld = run(Q_CLOUD, pp_start, pp_end)
pp_stg = run(Q_STORAGE, pp_start, pp_end)
pp_ai = run_optional(Q_AI, pp_start, pp_end)
pp_xfer = run(Q_TRANSFER, pp_start, pp_end)


def total(df: pd.DataFrame, col: str) -> float:
    return float(df[col].sum()) if not df.empty else 0.0


def avg_storage(df: pd.DataFrame) -> float:
    cols = ["Database", "Stage", "Fail-safe"]
    return float(df[cols].sum(axis=1).mean()) if not df.empty else 0.0


wh_credits = total(wh, "Total Credits")
srv_credits = total(srv, "Credits")
cs_billed = total(cld, "Billed")
idle_credits = total(wh, "Idle")
ai_credits = total(ai, "Credits")
avg_tb = avg_storage(stg)
xfer_tb = total(xfer, "TB")
total_credits = wh_credits + srv_credits + ai_credits + cs_billed

pp_wh_credits = total(pp_wh, "Total Credits")
pp_srv_credits = total(pp_srv, "Credits")
pp_cs_billed = total(pp_cld, "Billed")
pp_ai_credits = total(pp_ai, "Credits")
pp_avg_tb = avg_storage(pp_stg)
pp_xfer_tb = total(pp_xfer, "TB")
pp_total = pp_wh_credits + pp_srv_credits + pp_ai_credits + pp_cs_billed


def delta(current: float, prior: float):
    """Percent change vs the prior period.

    Returns a float percent, or the string 'new' when prior is zero/missing
    but current has spend, or None when both are empty.
    """
    if prior is None or prior == 0:
        if current and current != 0:
            return "new"
        return None
    return (current - prior) / prior * 100


def fmt_delta_pill(d):
    """Always render a prior-period change pill when possible."""
    if d is None:
        return ""
    if d == "new":
        return '<span class="delta-pill up">new</span>'
    arrow = "↑" if d >= 0 else "↓"
    cls = "up" if d >= 0 else "down"
    return f'<span class="delta-pill {cls}">{arrow} {d:+.1f}%</span>'


def money(v: float) -> str:
    return f"${v:,.2f}"


def money_short(v: float) -> str:
    return f"${v:,.0f}" if abs(v) >= 100 else f"${v:,.2f}"


def card_html(
    label: str,
    value: str,
    delta_html: str,
    foot_lines: list,
    primary: bool = False,
) -> str:
    cls = "card primary" if primary else "card"
    foot = "".join(f'<div class="foot">{line}</div>' for line in foot_lines if line)
    return (
        f'<div class="{cls}">'
        f'<div class="label">{label}</div>'
        f'<div class="value">{value}</div>'
        f'{delta_html}'
        f'{foot}'
        f'</div>'
    )

# Build the 7 KPI cards

d_total = delta(total_credits, pp_total)
d_wh = delta(wh_credits, pp_wh_credits)
d_srv = delta(srv_credits, pp_srv_credits)
d_ai = delta(ai_credits, pp_ai_credits)
d_cs = delta(cs_billed, pp_cs_billed)
d_stg = delta(avg_tb, pp_avg_tb)
d_xfer = delta(xfer_tb, pp_xfer_tb)

# Contract-to-date spend for remaining budget
ct_start = contract_start.isoformat()
ct_end = (datetime.now().date() + timedelta(days=1)).isoformat()
ct_wh = run(Q_WAREHOUSE, ct_start, ct_end)
ct_srv = run(Q_SERVERLESS, ct_start, ct_end)
ct_cld = run(Q_CLOUD, ct_start, ct_end)
ct_ai = run_optional(Q_AI, ct_start, ct_end)
ct_credits = (
    total(ct_wh, "Total Credits")
    + total(ct_srv, "Credits")
    + total(ct_ai, "Credits")
    + total(ct_cld, "Billed")
)
ct_spend = ct_credits * credit_price if credit_price else 0.0
remaining = max(annual_budget - ct_spend, 0.0) if credit_price else None
budget_pct = (ct_spend / annual_budget) if (credit_price and annual_budget) else 0.0

range_label = preset
contract_label = contract_start.strftime("%b %d, %Y")

# Peak storage & transfer routes for richer footers
peak_tb = 0.0
if not stg.empty:
    peak_tb = float(stg[["Database", "Stage", "Fail-safe"]].sum(axis=1).max())
xfer_routes = int(len(xfer)) if not xfer.empty else 0

if credit_price > 0:
    total_spend_val = total_credits * credit_price
    share = lambda c: (c / total_credits * 100) if total_credits else 0.0
    cards = [
        {
            "label": f"Total spend · {range_label}",
            "value": money(total_spend_val),
            "delta": fmt_delta_pill(d_total),
            "foot": [f"{total_credits:,.1f} credits"],
            "primary": True,
        },
        {
            "label": "Warehouse",
            "value": money(wh_credits * credit_price),
            "delta": fmt_delta_pill(d_wh),
            "foot": [f"{wh_credits:,.1f} credits · {share(wh_credits):.0f}% of credits"],
            "primary": False,
        },
        {
            "label": "Serverless",
            "value": money(srv_credits * credit_price),
            "delta": fmt_delta_pill(d_srv),
            "foot": [f"{srv_credits:,.1f} credits · {share(srv_credits):.0f}% of credits"],
            "primary": False,
        },
        {
            "label": "AI services",
            "value": money(ai_credits * credit_price),
            "delta": fmt_delta_pill(d_ai),
            "foot": [f"{ai_credits:,.1f} credits · {share(ai_credits):.0f}% of credits"],
            "primary": False,
        },
        {
            "label": "Cloud services billed",
            "value": money(cs_billed * credit_price),
            "delta": fmt_delta_pill(d_cs),
            "foot": [f"{cs_billed:,.1f} credits · {share(cs_billed):.0f}% of credits"],
            "primary": False,
        },
        {
            "label": "Avg storage",
            "value": f"{avg_tb:,.2f} TB",
            "delta": fmt_delta_pill(d_stg),
            "foot": [f"peak {peak_tb:,.2f} TB"],
            "primary": False,
        },
        {
            "label": "Data transfer",
            "value": f"{xfer_tb:,.3f} TB",
            "delta": fmt_delta_pill(d_xfer),
            "foot": [f"{xfer_routes} route(s)"],
            "primary": False,
        },
    ]
else:
    cards = [
        {
            "label": f"Total credits · {range_label}",
            "value": f"{total_credits:,.1f}",
            "delta": fmt_delta_pill(d_total),
            "foot": [],
            "primary": True,
        },
        {"label": "Warehouse", "value": f"{wh_credits:,.1f}", "delta": fmt_delta_pill(d_wh),
         "foot": ["credits"], "primary": False},
        {"label": "Serverless", "value": f"{srv_credits:,.1f}", "delta": fmt_delta_pill(d_srv),
         "foot": ["credits"], "primary": False},
        {"label": "AI services", "value": f"{ai_credits:,.1f}", "delta": fmt_delta_pill(d_ai),
         "foot": ["credits"], "primary": False},
        {"label": "Cloud services billed", "value": f"{cs_billed:,.1f}", "delta": fmt_delta_pill(d_cs),
         "foot": ["credits"], "primary": False},
        {"label": "Avg storage", "value": f"{avg_tb:,.2f} TB", "delta": fmt_delta_pill(d_stg),
         "foot": [f"peak {peak_tb:,.2f} TB"], "primary": False},
        {"label": "Data transfer", "value": f"{xfer_tb:,.3f} TB", "delta": fmt_delta_pill(d_xfer),
         "foot": [f"{xfer_routes} route(s)"], "primary": False},
    ]

k = st.columns(7)
for col, c in zip(k, cards):
    with col:
        st.markdown(
            card_html(
                c["label"],
                c["value"],
                c["delta"],
                c["foot"],
                c.get("primary", False),
            ),
            unsafe_allow_html=True,
        )

# Capacity remaining + equation on one line under the KPI cards
_cap = ""
if credit_price > 0 and remaining is not None:
    _cap = (
        f'{money(remaining)} left of {money(annual_budget)}'
        f' · {budget_pct * 100:.1f}% used since {contract_label}'
    )
_eq = "Warehouse + Serverless + AI services + Cloud services billed = Total credits"
st.markdown(
    f'<div style="display:flex;align-items:center;justify-content:space-between;'
    f'gap:1rem;margin:0.4rem 0.15rem 0.3rem 0.15rem;flex-wrap:wrap;">'
    f'<div style="color:{MUTED};font-size:0.72rem;flex:1 1 auto;">{_cap}</div>'
    f'<div style="color:{MUTED};font-size:0.72rem;flex:1 1 auto;text-align:center;">'
    f'{_eq}</div>'
    f'<div style="flex:1 1 auto;"></div>'
    f'</div>',
    unsafe_allow_html=True,
)

st.divider()



# ----------------------------------------------------------------------
# Charts: stacked credits, warehouse table, spend mix
# (Streamlit native charts only — no plotly/matplotlib)
# ----------------------------------------------------------------------

# Build daily series for stacked bar
daily_frames = []

if not cld.empty:
    wh_comp = cld[["Date", "Warehouse Compute"]].copy()
    daily_frames.append(wh_comp.set_index("Date"))

if not srv_daily.empty:
    s = srv_daily.copy()
    s = s.rename(columns={"Credits": "Serverless"}).set_index("Date")
    daily_frames.append(s)

if not ai_daily.empty:
    a = ai_daily.copy()
    a = a.rename(columns={"Credits": "AI Services"}).set_index("Date")
    daily_frames.append(a)

if not cld.empty:
    cs = cld[["Date", "Billed"]].copy()
    cs = cs.rename(columns={"Billed": "Cloud Services"}).set_index("Date")
    daily_frames.append(cs)

if daily_frames:
    daily = pd.concat(daily_frames, axis=1).fillna(0.0)
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()
else:
    daily = pd.DataFrame()

# Warehouse detail for table + mix
if not wh.empty:
    detail = (
        wh[["Warehouse", "Total Credits"]]
        .rename(columns={"Warehouse": "Warehouse Name", "Total Credits": "Credits"})
        .copy()
    )
    detail["Cost ($)"] = detail["Credits"] * credit_price if credit_price else detail["Credits"]
    detail = detail.sort_values("Credits", ascending=False).reset_index(drop=True)
else:
    detail = pd.DataFrame(columns=["Warehouse Name", "Credits", "Cost ($)"])

# Charts: full-width bar, then table + donut
st.markdown('<div class="panel-title">Credits Used</div>', unsafe_allow_html=True)
if daily.empty:
    st.info("No daily metering data for the selected range.")
else:
    plot_df = daily.copy()
    if len(plot_df) > 62:
        plot_df = plot_df.resample("W-SUN").sum()
    series_order = [
        c for c in ["Warehouse Compute", "Serverless", "AI Services", "Cloud Services"]
        if c in plot_df.columns
    ]
    series_order += [c for c in plot_df.columns if c not in series_order]
    plot_df = plot_df[series_order]

    try:
        import altair as alt

        long = plot_df.reset_index()
        long = long.rename(columns={long.columns[0]: "Date"})
        long = long.melt(id_vars=["Date"], var_name="Service", value_name="Credits")
        long["Date"] = pd.to_datetime(long["Date"])

        color_scale = alt.Scale(
            domain=series_order,
            range=[SERIES_COLORS.get(s, "#4C72B0") for s in series_order],
        )
        n_dates = int(long["Date"].nunique())
        tick_count = n_dates if n_dates <= 20 else max(10, n_dates // 2)
        chart = (
            alt.Chart(long)
            .mark_bar()
            .encode(
                x=alt.X(
                    "Date:T",
                    axis=alt.Axis(
                        title=None,
                        labelAngle=-90,
                        labelAlign="right",
                        labelBaseline="middle",
                        format="%b %d",
                        labelFontSize=10,
                        tickCount=tick_count,
                    ),
                ),
                y=alt.Y(
                    "Credits:Q",
                    stack="zero",
                    axis=alt.Axis(title="Credits", labelFontSize=10),
                ),
                color=alt.Color(
                    "Service:N",
                    scale=color_scale,
                    legend=alt.Legend(
                        title=None,
                        orient="bottom",
                        direction="horizontal",
                        labelFontSize=11,
                        symbolSize=80,
                        columns=4,
                    ),
                ),
                tooltip=[
                    "Date:T",
                    "Service:N",
                    alt.Tooltip("Credits:Q", format=",.1f"),
                ],
            )
            .properties(height=300)
            .configure_view(strokeWidth=0)
            .configure_axis(grid=True, gridOpacity=0.3)
            .configure_legend(orient="bottom")
        )
        st.altair_chart(chart, use_container_width=True)
    except Exception:
        st.bar_chart(plot_df, height=320, use_container_width=True)

table_col, mix_col = st.columns([1.4, 1.0], gap="medium")

with table_col:
    st.markdown('<div class="panel-title">Warehouse Detail</div>', unsafe_allow_html=True)
    if detail.empty:
        st.info("No warehouse metering data.")
    else:
        display = detail.copy()
        total_val = float(display["Cost ($)"].sum()) if credit_price > 0 else float(display["Credits"].sum())
        value_col = "Cost ($)" if credit_price > 0 else "Credits"
        display["Share %"] = (display[value_col] / total_val * 100).round(1) if total_val else 0.0
        if credit_price <= 0:
            display = display.drop(columns=["Cost ($)"], errors="ignore")

        if credit_price > 0:
            col_cfg = {
                "Warehouse Name": st.column_config.TextColumn("Warehouse", width="large"),
                "Credits": st.column_config.NumberColumn("Credits", format="%.1f", width="small"),
                "Cost ($)": st.column_config.NumberColumn("Cost", format="$%.2f", width="small"),
                "Share %": st.column_config.NumberColumn("Share", format="%.1f%%", width="small"),
            }
        else:
            col_cfg = {
                "Warehouse Name": st.column_config.TextColumn("Warehouse", width="large"),
                "Credits": st.column_config.NumberColumn("Credits", format="%.1f", width="small"),
                "Share %": st.column_config.NumberColumn("Share", format="%.1f%%", width="small"),
            }
        row_h = 35
        tbl_h = min(360, 48 + max(len(display), 1) * row_h)
        st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            height=tbl_h,
            column_config=col_cfg,
        )

with mix_col:
    st.markdown('<div class="panel-title">Spend by Warehouse</div>', unsafe_allow_html=True)
    if detail.empty or detail["Credits"].sum() == 0:
        st.info("No warehouse spend to chart.")
    else:
        mix = detail.copy()
        total_val = float(mix["Cost ($)"].sum()) if credit_price > 0 else float(mix["Credits"].sum())
        value_col = "Cost ($)" if credit_price > 0 else "Credits"
        center = money(total_val) if credit_price > 0 else f"{total_val:,.1f}"
        center_sub = "spend" if credit_price > 0 else "credits"

        # Pure SVG donut — no extra packages
        colors = DONUT_COLORS
        values = mix[value_col].tolist()
        labels = mix["Warehouse Name"].tolist()
        n = len(values)
        # SVG arc path helper
        def arc_path(cx, cy, r_outer, r_inner, start_deg, end_deg):
            # degrees clockwise from top (-90)
            def pt(r, deg):
                rad = math.radians(deg - 90)
                return cx + r * math.cos(rad), cy + r * math.sin(rad)
            large = 1 if (end_deg - start_deg) % 360 > 180 else 0
            x1, y1 = pt(r_outer, start_deg)
            x2, y2 = pt(r_outer, end_deg)
            x3, y3 = pt(r_inner, end_deg)
            x4, y4 = pt(r_inner, start_deg)
            return (
                f"M {x1:.2f} {y1:.2f} "
                f"A {r_outer} {r_outer} 0 {large} 1 {x2:.2f} {y2:.2f} "
                f"L {x3:.2f} {y3:.2f} "
                f"A {r_inner} {r_inner} 0 {large} 0 {x4:.2f} {y4:.2f} Z"
            )

        cx = cy = 110
        r_outer, r_inner = 100, 58
        angle = 0.0
        paths = []
        legend_items = []
        for i, (lab, val) in enumerate(zip(labels, values)):
            frac = (val / total_val) if total_val else 0
            sweep = frac * 360
            # avoid zero-length arcs
            if sweep < 0.3:
                angle += sweep
                continue
            color = colors[i % len(colors)]
            end = angle + sweep
            # full circle special case
            if sweep >= 359.9:
                path = (
                    f"M {cx} {cy - r_outer} "
                    f"A {r_outer} {r_outer} 0 1 1 {cx} {cy + r_outer} "
                    f"A {r_outer} {r_outer} 0 1 1 {cx} {cy - r_outer} "
                    f"M {cx} {cy - r_inner} "
                    f"A {r_inner} {r_inner} 0 1 0 {cx} {cy + r_inner} "
                    f"A {r_inner} {r_inner} 0 1 0 {cx} {cy - r_inner} Z"
                )
            else:
                path = arc_path(cx, cy, r_outer, r_inner, angle, end)
            paths.append(f'<path d="{path}" fill="{color}" stroke="#fff" stroke-width="2"/>')
            pct = frac * 100
            legend_items.append(
                f'<div style="display:flex;align-items:center;gap:6px;margin:2px 0;">'
                f'<span style="width:10px;height:10px;border-radius:2px;background:{color};display:inline-block;"></span>'
                f'<span style="font-size:10px;color:{INK};">{lab} ({pct:.0f}%)</span></div>'
            )
            angle = end

        svg = (
            f'<div style="text-align:center;">'
            f'<svg viewBox="0 0 220 220" width="100%" style="max-width:240px;">'
            + "".join(paths)
            + f'<text x="{cx}" y="{cy - 6}" text-anchor="middle" '
            f'font-size="14" font-weight="700" fill="{INK}">{center}</text>'
            + f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" '
            f'font-size="10" fill="{MUTED}">{center_sub}</text>'
            + "</svg>"
            + '<div style="text-align:left;margin-top:4px;">'
            + "".join(legend_items)
            + "</div></div>"
        )
        st.markdown(svg, unsafe_allow_html=True)

st.markdown("---")

# Rate / capacity note (matches selected credit rate)
if credit_price <= 0 or rate_choice == "Credits only":
    rate_note = "Dollar figures suppressed. All values reported in credits."
else:
    rate_note = (
        f"${credit_price:,.2f} per credit — configured rate for {rate_choice}. "
        "Actual rates vary by cloud and region, and contracted rates may differ. "
        "Treat dollar figures as indicative. Capacity remaining is measured from the "
        "current contract anniversary through today, independent of the date range above."
    )

# -------------------------------------------------
# Notes
# -------------------------------------------------

st.markdown("---")

st.markdown(
    f"""
    <div class="note">
    {rate_note}<br><br>
    Change vs prior period ({preset}).
    ACCOUNT_USAGE views are not real time. Metering and storage lag by roughly
    2 to 3 hours, query attribution by up to 8 hours, and Cortex function usage
    by about 5 minutes. Ranges that include today or yesterday will therefore
    understate actual consumption, and the most recent day is always partial.<br><br>
    Storage and data transfer bill in dollars per terabyte, not credits, so
    neither is included in Total credits / Total Spend.
    Figures are drawn from ACCOUNT_USAGE and are for internal analysis only —
    they will not tie exactly to your Snowflake invoice. Use ORGANIZATION_USAGE
    or the billing statement for figures of record.
    </div>
    """,
    unsafe_allow_html=True,
)
