"""
Inventrack - 4. Statistical Stock Depletion Forecasting
Predicts when each product will run out of stock using:
  - Pandas groupby / rolling for daily sales velocity (7-day & 30-day)
  - NumPy polyfit (linear regression) for trend detection
  - Weighted average consumption rate for stockout date estimation
All queries are strictly scoped to the authenticated user_id.
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from database.db_manager import get_stock_depletion_forecast, get_all_transactions
from components.nav import render_sidebar_navigation, render_top_header, ensure_authenticated_session

# Page configuration
st.set_page_config(
    page_title="Forecasting | Inventrack",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inject CSS
css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "style.css")
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Authentication Guard
is_auth, user_id, username = ensure_authenticated_session()
if not is_auth or not user_id:
    st.warning("Access restricted. Please authenticate via the main portal.")
    if st.button("Go to Login Gateway"):
        st.switch_page("app.py")
    st.stop()

# Render Global Top Header & Tab Navigation
render_top_header()
render_sidebar_navigation(current_page="Forecasting")

# Page Header
st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 1.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 1rem;">
        <div>
            <h1 style="margin: 0; color: #1e293b; font-size: 2rem; letter-spacing: -0.025em;">Stock Depletion Forecast</h1>
            <p style="margin: 0.3rem 0 0 0; color: #64748b; font-size: 0.95rem;">
                Statistical prediction of stockout dates using NumPy linear regression &amp; Pandas sales velocity analysis.
            </p>
        </div>
        <div>
            <span style="background-color: #dbeafe; color: #1d4ed8; padding: 4px 14px; border-radius: 9999px; font-size: 0.82rem; font-weight: 600;">
                Powered by NumPy &amp; Pandas
            </span>
        </div>
    </div>
""", unsafe_allow_html=True)

# Fetch forecast data
forecast_df = get_stock_depletion_forecast(user_id=user_id)

if forecast_df.empty:
    st.info("No products found in your catalog. Add products or import data to see forecasts.")
    st.stop()

# ---------------------------------------------------------------
# SECTION 1: RISK SUMMARY CARDS
# ---------------------------------------------------------------
critical_count = len(forecast_df[forecast_df["risk_level"] == "Critical"])
warning_count = len(forecast_df[forecast_df["risk_level"] == "Warning"])
monitor_count = len(forecast_df[forecast_df["risk_level"] == "Monitor"])
safe_count = len(forecast_df[forecast_df["risk_level"] == "Safe"])
total_count = len(forecast_df)

def risk_card(title, count, bg_color, border_color, icon, subtitle):
    return f"""
    <div style="
        background-color: {bg_color};
        border-radius: 16px;
        padding: 1.25rem 1.4rem;
        border: 1px solid {border_color};
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        min-height: 110px;
    ">
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
            <span style="font-size: 1.15rem;">{icon}</span>
            <span style="font-size: 0.88rem; font-weight: 700; color: #000000; letter-spacing: -0.01em;">{title}</span>
        </div>
        <div style="font-size: 2.2rem; font-weight: 800; color: #000000; letter-spacing: -0.03em; line-height: 1.15; margin: 0.2rem 0;">
            {count}
        </div>
        <div style="font-size: 0.78rem; color: #333333; font-weight: 500;">{subtitle}</div>
    </div>
    """

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(risk_card("Critical", critical_count, "#fff1f2", "#ffe4e6", "🔴", "Stock = 0 (Out of stock)"), unsafe_allow_html=True)
with c2:
    st.markdown(risk_card("Warning", warning_count, "#fefce8", "#fef9c3", "🟡", "Stockout within 7 days"), unsafe_allow_html=True)
with c3:
    st.markdown(risk_card("Monitor", monitor_count, "#fff7ed", "#ffedd5", "🟠", "Stockout within 8–21 days"), unsafe_allow_html=True)
with c4:
    st.markdown(risk_card("Safe", safe_count, "#f0fdf4", "#dcfce7", "🟢", "Stockout beyond 21 days"), unsafe_allow_html=True)

st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------
# SECTION 2: DEPLETION CHART — Days Until Stockout per Product
# ---------------------------------------------------------------
col_ds_head, col_ds_ctrl = st.columns([3, 1.5], vertical_alignment="center")
with col_ds_head:
    st.markdown("### Days Until Stockout")
    st.markdown("""
        <div style="font-size: 0.88rem; color: #64748b; margin-bottom: 0.5rem; line-height: 1.5;">
            <strong>How to read:</strong> Each bar shows the estimated number of days before a product
            runs out of stock, calculated from the weighted average daily sales velocity
            (<strong>V<sub>w</sub> = 0.6 × V<sub>7d</sub> + 0.4 × V<sub>30d</sub></strong>).
            Shorter bars mean the product needs attention sooner.
        </div>
    """, unsafe_allow_html=True)

with col_ds_ctrl:
    stockout_sort = st.selectbox(
        "Sort Order",
        options=["Urgent First (Fewest Days)", "Most Days Left", "Alphabetical (A-Z)"],
        index=0,
        key="stockout_sort_order",
        help="Order products by days left until stockout."
    )

# Risk Level Segmented Tab Pills
risk_tab_options = [
    f"All Items ({total_count})",
    f"🔴 Critical ({critical_count})",
    f"🟡 Warning ({warning_count})",
    f"🟠 Monitor ({monitor_count})",
    f"🟢 Safe ({safe_count})"
]

selected_risk_tab = st.pills(
    "Filter by Risk Level",
    options=risk_tab_options,
    default=f"All Items ({total_count})",
    label_visibility="collapsed",
    key="stockout_risk_tab"
)

# Apply risk tab filter
if selected_risk_tab and "Critical" in selected_risk_tab:
    stage_filtered = forecast_df[forecast_df["risk_level"] == "Critical"].copy()
elif selected_risk_tab and "Warning" in selected_risk_tab:
    stage_filtered = forecast_df[forecast_df["risk_level"] == "Warning"].copy()
elif selected_risk_tab and "Monitor" in selected_risk_tab:
    stage_filtered = forecast_df[forecast_df["risk_level"] == "Monitor"].copy()
elif selected_risk_tab and "Safe" in selected_risk_tab:
    stage_filtered = forecast_df[forecast_df["risk_level"] == "Safe"].copy()
else:
    stage_filtered = forecast_df.copy()

# Product Multi-Select Pill System (matching Product Sales Trends)
available_stockout_prods = sorted(stage_filtered["name"].dropna().unique().tolist())
default_stockout_prods = available_stockout_prods  # Select all items by default so none are omitted

selected_stockout_prods = st.multiselect(
    "Filter products to display:",
    options=available_stockout_prods,
    default=default_stockout_prods,
    key="stockout_prod_filter",
    help="Select which products to display on the stockout bar chart."
)

# Filter items by user selection
chart_df = stage_filtered[stage_filtered["name"].isin(selected_stockout_prods)].copy()

if not chart_df.empty:
    chart_df["display_days"] = chart_df["days_until_stockout"].fillna(180.0)

    if stockout_sort == "Urgent First (Fewest Days)":
        chart_df = chart_df.sort_values("display_days", ascending=True)
    elif stockout_sort == "Most Days Left":
        chart_df = chart_df.sort_values("display_days", ascending=False)
    else:
        chart_df = chart_df.sort_values("name", ascending=True)

    # Assign bar colors based on risk level (soft pastel palette)
    color_map = {
        "Critical": "#f87171",
        "Warning": "#facc15",
        "Monitor": "#fb923c",
        "Safe": "#4ade80"
    }
    chart_df["bar_color"] = chart_df["risk_level"].map(color_map).fillna("#4ade80")

    chart_df["bar_label"] = chart_df.apply(
        lambda r: "0 days (Out of Stock)" if r["display_days"] <= 0 else (
            f"{r['display_days']:.0f} days" if r["display_days"] < 180 else "180+ days (Safe)"
        ), axis=1
    )

    fig_depletion = go.Figure()
    fig_depletion.add_trace(go.Bar(
        y=chart_df["name"].str[:25],
        x=chart_df["display_days"],
        orientation="h",
        marker_color=chart_df["bar_color"],
        text=chart_df["bar_label"],
        textposition="outside",
        textfont=dict(color="#1e293b", size=12),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Days left: %{x:.1f}<br>"
            "<extra></extra>"
        )
    ))

    # Add threshold lines
    fig_depletion.add_vline(x=7, line_dash="dash", line_color="#facc15", line_width=1.5,
                            annotation_text="7-day Warning", annotation_position="top")
    fig_depletion.add_vline(x=21, line_dash="dash", line_color="#fb923c", line_width=1.5,
                            annotation_text="21-day Monitor", annotation_position="top")

    fig_depletion.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Plus Jakarta Sans", color="#1e293b"),
        height=max(260, len(chart_df) * 44),
        margin=dict(l=10, r=80, t=30, b=20),
        xaxis=dict(
            title="Days Until Stockout",
            title_font=dict(color="#475569"),
            gridcolor="#f1f5f9",
            linecolor="#cbd5e1",
            tickfont=dict(color="#475569")
        ),
        yaxis=dict(
            tickfont=dict(color="#1e293b"),
            linecolor="#cbd5e1",
            autorange="reversed"
        ),
        showlegend=False,
    )
    st.plotly_chart(fig_depletion, use_container_width=True,
                    config={"responsive": True, "displayModeBar": True, "displaylogo": False})
else:
    st.info("No products match the selected risk category and filter. Adjust the filters above to view predictions.")

st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------
# SECTION 3: PRODUCT SALES TREND LINES (Separate line per product)
# ---------------------------------------------------------------
col_tr_head, col_tr_ctrl = st.columns([3, 1.5], vertical_alignment="center")
with col_tr_head:
    st.markdown("### Product Sales Trends")
    st.markdown("""
        <div style="font-size: 0.88rem; color: #64748b; margin-bottom: 0.5rem; line-height: 1.5;">
            <strong>How to read:</strong> Each colored line tracks a specific product's sales volume over time.
            Rising curves indicate increasing demand (faster stock depletion), while declining curves indicate slowing sales.
        </div>
    """, unsafe_allow_html=True)

# Fetch transaction data and build timeline
tx_df = get_all_transactions(user_id=user_id)
sales_only = tx_df[tx_df["transaction_type"] == "SALE"].copy() if not tx_df.empty else pd.DataFrame()

if not sales_only.empty and "transaction_date" in sales_only.columns:
    sales_only["transaction_date"] = pd.to_datetime(sales_only["transaction_date"], errors="coerce")
    sales_only = sales_only.dropna(subset=["transaction_date"])
    
    # Calculate date span to choose optimal default view
    min_dt = sales_only["transaction_date"].min()
    max_dt = sales_only["transaction_date"].max()
    day_span = (max_dt - min_dt).days if pd.notna(min_dt) and pd.notna(max_dt) else 0
    default_view_idx = 0 if day_span <= 45 else 1

    with col_tr_ctrl:
        time_view = st.selectbox(
            "Trend Aggregation",
            options=["Daily Trend", "Monthly Trend"],
            index=default_view_idx,
            help="Switch between daily sales points and monthly totals."
        )

    if time_view == "Daily Trend":
        sales_only["period_key"] = sales_only["transaction_date"].dt.strftime("%Y-%m-%d")
        sales_only["period_label"] = sales_only["transaction_date"].dt.strftime("%d %b")
    else:
        sales_only["period_key"] = sales_only["transaction_date"].dt.to_period("M").astype(str)
        sales_only["period_label"] = sales_only["transaction_date"].dt.strftime("%b %Y")

    # Aggregate total quantity sold per product per time period
    period_df = (
        sales_only.groupby(["period_key", "period_label", "item_name"])["quantity"]
        .sum()
        .reset_index()
    )
    period_df = period_df.sort_values("period_key")

    periods_ordered = period_df.drop_duplicates("period_key").sort_values("period_key")["period_label"].tolist()
    all_products = sorted(period_df["item_name"].unique().tolist())

    # Product selector filter (default to first 6 or all if <= 6)
    default_selected = all_products[:6] if len(all_products) > 6 else all_products
    selected_products = st.multiselect(
        "Filter products to display:",
        options=all_products,
        default=default_selected,
        help="Select which products to display on the trend graph."
    )

    if selected_products:
        TREND_COLORS = [
            "#2563eb", "#ea580c", "#0f766e", "#dc2626", "#7c3aed",
            "#0284c7", "#16a34a", "#be185d", "#ca8a04", "#475569"
        ]

        fig_trends = go.Figure()
        for i, product in enumerate(selected_products):
            prod_data = period_df[period_df["item_name"] == product].copy()
            if prod_data.empty:
                continue

            # Ensure all periods are represented so lines connect smoothly across timeline
            prod_data = prod_data.set_index("period_label").reindex(periods_ordered).reset_index()
            prod_data["quantity"] = prod_data["quantity"].fillna(0)

            color = TREND_COLORS[i % len(TREND_COLORS)]

            fig_trends.add_trace(go.Scatter(
                x=prod_data["period_label"],
                y=prod_data["quantity"],
                mode="lines+markers+text",
                name=product[:25],
                line=dict(color=color, width=2.5),
                marker=dict(size=7, color=color),
                text=prod_data["quantity"].apply(lambda q: f"{q:.0f}" if q > 0 else ""),
                textposition="top center",
                textfont=dict(size=10, color=color),
                hovertemplate=(
                    f"<b>{product}</b><br>"
                    "Timeline: %{x}<br>"
                    "Units sold: %{y:.0f}<br>"
                    "<extra></extra>"
                )
            ))

        fig_trends.update_layout(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Plus Jakarta Sans", color="#1e293b"),
            height=420,
            margin=dict(l=20, r=20, t=20, b=30),
            xaxis=dict(
                categoryorder="array",
                categoryarray=periods_ordered,
                tickfont=dict(color="#475569", size=11),
                linecolor="#cbd5e1",
                gridcolor="#f1f5f9"
            ),
            yaxis=dict(
                title="Units Sold",
                title_font=dict(color="#475569"),
                gridcolor="#f1f5f9",
                linecolor="#cbd5e1",
                tickfont=dict(color="#475569")
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.28,
                xanchor="center",
                x=0.5,
                font=dict(color="#475569", size=11)
            ),
            hovermode="x unified",
        )
        st.plotly_chart(fig_trends, use_container_width=True,
                        config={"responsive": True, "displayModeBar": True, "displaylogo": False})
    else:
        st.info("Please select at least one product to display on the trend chart.")
else:
    st.info("Not enough sales data to plot product trend lines.")

st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------
# SECTION 4: DETAILED FORECAST TABLE
# ---------------------------------------------------------------
st.markdown("### Detailed Product Forecast Table")
st.markdown("""
    <div style="font-size: 0.88rem; color: #64748b; margin-bottom: 1rem; line-height: 1.5;">
        Complete stockout predictions for every product.
        <strong>V<sub>7d</sub></strong> = average daily sales over last 7 days,
        <strong>V<sub>30d</sub></strong> = over last 30 days,
        <strong>V<sub>w</sub></strong> = weighted blend (60% recent + 40% monthly).
    </div>
""", unsafe_allow_html=True)

# Risk level filter
risk_filter = st.selectbox(
    "Filter by Risk Level",
    ["All", "Critical", "Warning", "Monitor", "Safe"],
    index=0
)

display_df = forecast_df.copy()
if risk_filter != "All":
    display_df = display_df[display_df["risk_level"] == risk_filter]

if not display_df.empty:
    # Format for display
    table_df = pd.DataFrame({
        "Product": display_df["name"],
        "SKU": display_df["sku"],
        "Category": display_df["category"],
        "Stock": display_df["current_stock"].apply(lambda s: f"{s:,}"),
        "V₇ (units/day)": display_df["avg_daily_7d"],
        "V₃₀ (units/day)": display_df["avg_daily_30d"],
        "Vw (weighted)": display_df["avg_daily_weighted"],
        "Trend": display_df["trend_label"],
        "Days Left": display_df["days_until_stockout"].apply(
            lambda d: f"{d:.0f}" if pd.notna(d) else "∞"
        ),
        "Stockout Date": display_df["stockout_date"],
        "Reorder By": display_df["reorder_by"],
        "Risk": display_df["risk_level"],
    })

    # Color-code risk column
    def color_risk(val):
        colors = {
            "Critical": "background-color: #fee2e2; color: #dc2626; font-weight: 700;",
            "Warning": "background-color: #fef9c3; color: #ca8a04; font-weight: 700;",
            "Monitor": "background-color: #ffedd5; color: #ea580c; font-weight: 700;",
            "Safe": "background-color: #dcfce7; color: #16a34a; font-weight: 700;",
        }
        return colors.get(val, "")

    styled_table = table_df.style.map(color_risk, subset=["Risk"])

    st.dataframe(
        styled_table,
        use_container_width=True,
        hide_index=True,
        height=min(600, 45 + len(table_df) * 38)
    )
else:
    st.info(f"No products found with risk level: {risk_filter}")

st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------
# SECTION 5: METHODOLOGY NOTE
# ---------------------------------------------------------------
with st.expander("📐 Forecasting Methodology & Formulas", expanded=False):
    st.markdown(r"""
**1. Average Daily Sales Velocity**

$$V_7 = \frac{\text{Total units sold in last 7 days}}{7}$$

$$V_{30} = \frac{\text{Total units sold in last 30 days}}{30}$$

$$V_w = 0.6 \times V_7 + 0.4 \times V_{30}$$

The weighted formula gives 60% importance to recent (7-day) data and 40% to the monthly baseline,
so it reacts to sudden demand changes while staying stable.

**2. Days Until Stockout**

$$D_{out} = \frac{\text{Current Stock}}{V_w}$$

**Stockout Date** = Today + $D_{out}$ days

**3. Linear Regression (Trend Detection)**

Uses `numpy.polyfit(x, y, 1)` which fits the line $y = mx + b$ using least squares:

$$m = \frac{n \sum x_i y_i - \sum x_i \sum y_i}{n \sum x_i^2 - (\sum x_i)^2}$$

- $m > 0$ → sales **rising** (stock runs out faster)
- $m < 0$ → sales **falling** (stock lasts longer)
- $m \approx 0$ → sales **stable**

**4. Reorder Date** = Stockout Date − 3 days (lead time buffer)

**5. Risk Classification**

| Condition | Level | Color |
|---|---|---|
| Stock = 0 | Critical | 🔴 Red |
| Days ≤ 7 | Warning | 🟡 Yellow |
| 7 < Days ≤ 21 | Monitor | 🟠 Orange |
| Days > 21 | Safe | 🟢 Green |
    """)

