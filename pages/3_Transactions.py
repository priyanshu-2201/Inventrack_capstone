"""
Inventrack - 3. Transaction Management & Sales Ledger
Sales logging, inventory depletion, procurement inflows, and audit trail ledger.
Strictly scoped to authenticated user_id.
"""

import os
from datetime import date, datetime
import streamlit as st
import pandas as pd
from database.db_manager import (
    get_all_products,
    get_all_raw_materials,
    get_all_transactions,
    log_transaction
)
from components.nav import render_sidebar_navigation, render_top_header, ensure_authenticated_session

# Page configuration
st.set_page_config(
    page_title="Transactions | Inventrack",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Inject modern pastel CSS
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

# Transaction Completion Feedback & Animation Check (Top of rendering cycle)
if st.session_state.get('transaction_success_msg'):
    success_msg = st.session_state.pop('transaction_success_msg')
    is_sale_completed = st.session_state.pop('sale_success', False)
    if is_sale_completed:
        st.balloons()
        st.toast("Sale recorded and stock dispatched!", icon="🎉")
    else:
        st.toast("Purchase recorded and stock received!", icon="📦")
    st.success(f"✅ {success_msg}")

# Render Global Top Header & Sidebar Navigation
render_top_header()
render_sidebar_navigation(current_page="Transactions")

# Page Header
st.markdown("""
    <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 1.5rem; border-bottom: 1px solid #e2e8f0; padding-bottom: 1rem;">
        <div>
            <h1 style="margin: 0; color: #1e293b; font-size: 2rem; letter-spacing: -0.025em;">Transactions &amp; Sales Ledger</h1>
            <p style="margin: 0.3rem 0 0 0; color: #64748b; font-size: 0.95rem;">
                Process customer sales orders, inbound procurement shipments, and maintain audit trails in Indian Rupees (₹).
            </p>
        </div>
        <div>
            <span class="badge badge-blue">Real-time Stock Depletion</span>
        </div>
    </div>
""", unsafe_allow_html=True)

tab_log, tab_ledger = st.tabs([
    "Log New Transaction",
    "Transaction Ledger & History"
])


# =============================================================
# TAB 1: LOG NEW TRANSACTION (Scoped to user_id)
# =============================================================
with tab_log:
    st.markdown("""
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 14px; padding: 1.25rem 1.5rem; margin-bottom: 1.2rem;">
            <h3 style="margin-top: 0; color: #1e293b;">Create New Transaction Record</h3>
            <p style="color: #64748b; font-size: 0.95rem; margin-bottom: 0;">
                Recording a <strong>Sale</strong> automatically checks current inventory and deducts quantity upon confirmation.<br>
                Recording a <strong>Purchase</strong> increments warehouse stock and logs procurement expenditure.
            </p>
        </div>
    """, unsafe_allow_html=True)

    products_df = get_all_products(user_id=user_id)
    materials_df = get_all_raw_materials(user_id=user_id)

    c1, c2 = st.columns(2)

    with c1:
        txn_category = st.radio(
            "Transaction Flow *",
            ["Customer Sale (Reduces Stock)", "Inbound Procurement (Adds Stock)"],
            horizontal=True,
            key="radio_txn_flow"
        )
        is_sale = "Sale" in txn_category
        txn_type = "SALE" if is_sale else "PURCHASE"

        # Determine Target Type
        target_item_type = st.radio(
            "Item Type *",
            ["Finished Product", "Raw Material"],
            horizontal=True,
            key=f"radio_item_type_{'sale' if is_sale else 'purch'}"
        )

        is_product = target_item_type == "Finished Product"
        item_type_db = "PRODUCT" if is_product else "RAW_MATERIAL"

        # Dynamic item selector with live stock information
        if is_product:
            if not products_df.empty:
                item_options = {
                    f"{r['name']} ({r['sku']}) | In Stock: {r['stock_quantity']} units": (
                        r['id'], float(r['unit_price']), float(r['cost_price']), float(r['stock_quantity'])
                    )
                    for _, r in products_df.iterrows()
                }
                selected_label = st.selectbox("Select Finished Product *", list(item_options.keys()), key="sel_prod_item")
                selected_item_id, prod_sell_price, prod_cost_price, curr_stock = item_options[selected_label]
                # Default price: if sale, use unit_price; if purchase, use cost_price
                suggested_price = prod_sell_price if is_sale else (prod_cost_price if prod_cost_price > 0 else prod_sell_price)
            else:
                st.error("No finished products found in your catalog.")
                selected_item_id, suggested_price, curr_stock = None, 0.0, 0.0
        else:
            if not materials_df.empty:
                item_options = {
                    f"{r['name']} ({r['code']}) | In Stock: {r['stock_quantity']} {r['unit']}": (
                        r['id'], float(r['unit_cost']), float(r['stock_quantity'])
                    )
                    for _, r in materials_df.iterrows()
                }
                selected_label = st.selectbox("Select Raw Material *", list(item_options.keys()), key="sel_mat_item")
                selected_item_id, suggested_price, curr_stock = item_options[selected_label]
            else:
                st.error("No raw materials found in your inventory.")
                selected_item_id, suggested_price, curr_stock = None, 0.0, 0.0

    with c2:
        st.markdown("##### Commercial Terms")
        q_col, p_col = st.columns(2)
        with q_col:
            txn_qty = st.number_input("Quantity *", min_value=1.0, value=1.0, step=1.0, key="input_txn_qty")
        with p_col:
            init_price = float(suggested_price) if suggested_price and suggested_price > 0 else 0.0
            txn_price = st.number_input(
                "Unit Price / Cost (₹) *",
                min_value=0.0,
                value=init_price,
                step=10.0,
                key=f"input_txn_price_{selected_item_id}_{'sale' if is_sale else 'purch'}"
            )

        total_calc = round(txn_qty * txn_price, 2)
        st.markdown(f"""
            <div style="background: #f0fdf4; border: 1px dashed #22c55e; border-radius: 8px; padding: 0.6rem 1rem; margin: 0.5rem 0 1rem 0;">
                <span style="font-size: 0.85rem; color: #166534;">Calculated Line Total:</span>
                <strong style="color: #15803d; font-size: 1.25rem; margin-left: 0.5rem;">₹{total_calc:,.2f}</strong>
            </div>
        """, unsafe_allow_html=True)

        party_label = "Customer / Client Name *" if is_sale else "Supplier / Vendor Name *"
        party_placeholder = "e.g. Aura Wellness Boutique" if is_sale else "e.g. Provence Organics Co."
        txn_party = st.text_input(party_label, placeholder=party_placeholder, key="input_txn_party")

        d_col, n_col = st.columns([1, 1])
        with d_col:
            txn_date = st.date_input("Transaction Date", value=date.today(), key="input_txn_date")
        with n_col:
            txn_notes = st.text_input("Invoice / Memo Ref", placeholder="e.g. INV-9042, Net 30, Paid via Wire", key="input_txn_notes")

    # Submit Button (Active reactive trigger)
    btn_label = "Confirm Sale & Dispatch Stock" if is_sale else "Confirm PO & Receive Stock"
    submit_btn = st.button(btn_label, use_container_width=True, type="primary", key="btn_submit_txn")

    if submit_btn:
        if not selected_item_id:
            st.error("Please select a valid inventory item.")
        elif not txn_party.strip():
            st.error(f"Please provide the {'Customer' if is_sale else 'Supplier'} party name.")
        elif is_sale and txn_qty > curr_stock:
            st.error(f"Cannot complete sale: requested {txn_qty:g} units, but only {curr_stock:g} available in stock!")
        else:
            success, msg = log_transaction(
                user_id=user_id,
                transaction_type=txn_type,
                item_type=item_type_db,
                item_id=selected_item_id,
                quantity=txn_qty,
                unit_price=txn_price,
                party_name=txn_party.strip(),
                transaction_date=txn_date.strftime("%Y-%m-%d"),
                notes=txn_notes.strip()
            )
            if success:
                st.session_state['transaction_success_msg'] = msg
                st.session_state['sale_success'] = is_sale
                st.rerun()
            else:
                st.error(msg)


# =============================================================
# TAB 2: TRANSACTION LEDGER & HISTORY (Scoped to user_id)
# =============================================================
with tab_ledger:
    transactions_df = get_all_transactions(user_id=user_id)

    # Ledger Summary KPI Row
    if not transactions_df.empty:
        total_inflow = transactions_df[transactions_df["transaction_type"] == "SALE"]["total_amount"].sum()
        total_outflow = transactions_df[transactions_df["transaction_type"] == "PURCHASE"]["total_amount"].sum()
        total_txns = len(transactions_df)
        avg_sale = transactions_df[transactions_df["transaction_type"] == "SALE"]["total_amount"].mean()

        tl1, tl2, tl3, tl4 = st.columns(4)
        with tl1:
            st.metric("Total Sales Revenue", f"₹{total_inflow:,.2f}")
        with tl2:
            st.metric("Total Procurement Outflow", f"₹{total_outflow:,.2f}")
        with tl3:
            st.metric("Ledger Records", f"{total_txns:,} Transactions")
        with tl4:
            st.metric("Avg Sale Ticket", f"₹{avg_sale:,.2f}" if not pd.isna(avg_sale) else "₹0.00")

    st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)

    # Filter Bar
    l_c1, l_c2, l_c3 = st.columns([1.5, 2, 1.5])
    with l_c1:
        txn_types = ["All Types", "SALE", "PURCHASE", "ADJUSTMENT"]
        sel_type = st.selectbox("Filter Transaction Type", txn_types, key="ledger_filter_type")
    with l_c2:
        search_txn = st.text_input("Search Code, Item or Counter Party", "", key="ledger_search")
    with l_c3:
        sort_order = st.selectbox("Sort Order", ["Newest First", "Oldest First", "Highest Amount", "Lowest Amount"])

    # Apply Filters
    d_tx = transactions_df.copy()
    if sel_type != "All Types":
        d_tx = d_tx[d_tx["transaction_type"] == sel_type]

    if search_txn:
        q_t = search_txn.lower()
        d_tx = d_tx[
            d_tx["transaction_code"].str.lower().str.contains(q_t, na=False) |
            d_tx["item_name"].str.lower().str.contains(q_t, na=False) |
            d_tx["party_name"].str.lower().str.contains(q_t, na=False) |
            d_tx["notes"].str.lower().str.contains(q_t, na=False)
        ]

    # Sort
    if sort_order == "Newest First":
        d_tx = d_tx.sort_values(by=["transaction_date", "id"], ascending=[False, False])
    elif sort_order == "Oldest First":
        d_tx = d_tx.sort_values(by=["transaction_date", "id"], ascending=[True, True])
    elif sort_order == "Highest Amount":
        d_tx = d_tx.sort_values(by="total_amount", ascending=False)
    elif sort_order == "Lowest Amount":
        d_tx = d_tx.sort_values(by="total_amount", ascending=True)

    st.markdown(f"**Showing {len(d_tx)} transactions**")

    # Render Ledger
    if not d_tx.empty:
        display_cols = [
            "transaction_code", "transaction_date", "transaction_type",
            "item_name", "quantity", "unit_price", "total_amount",
            "party_name", "notes"
        ]
        render_table = d_tx[display_cols].copy()
        render_table.columns = [
            "Reference Code", "Date", "Type", "Item Name",
            "Qty", "Unit Price (₹)", "Total Amount (₹)",
            "Counter Party", "Notes"
        ]

        st.dataframe(render_table, use_container_width=True, hide_index=True)

        col_exp, _ = st.columns([1, 4])
        with col_exp:
            csv_txns = d_tx.to_csv(index=False).encode('utf-8')
            st.download_button(
                "Export Full Ledger (CSV)",
                data=csv_txns,
                file_name="inventrack_transactions_ledger.csv",
                mime="text/csv",
                key="btn_dl_txns"
            )
    else:
        st.info("No transaction records match the specified filters.")
