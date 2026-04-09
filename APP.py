"""
Retail Analytics Dashboard — Streamlit + Supabase
─────────────────────────────────────────────────
secrets.toml:
  SUPABASE_URL = "https://ttnvaxeqbxtvulofeuqs.supabase.co"
  SUPABASE_KEY = "eyJhbGci..."

Avvio locale:
  pip install -r requirements.txt
  streamlit run app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime, timedelta

# ── CONFIG ────────────────────────────────────────────────────────────────────
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

COLORS = ["#378ADD","#1D9E75","#D85A30","#7F77DD","#BA7517","#D4537E"]

st.set_page_config(
    page_title="Retail Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  [data-testid="metric-container"] {
    background: #f8f9fa; border-radius: 12px;
    padding: 14px 18px; border: 1px solid #e9ecef;
  }
  [data-testid="stSidebar"] { background: #fafafa; }
</style>
""", unsafe_allow_html=True)

# ── SUPABASE ──────────────────────────────────────────────────────────────────
@st.cache_resource
def get_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

@st.cache_data(ttl=300, show_spinner=False)
def load_data(date_from: str):
    sb = get_supabase()
    errors = []

    def safe_load(query_fn, label):
        try:
            return pd.DataFrame(query_fn().execute().data)
        except Exception as e:
            errors.append(f"{label}: {e}")
            return pd.DataFrame()

    sales = safe_load(
        lambda: sb.table("fact_sales")
            .select("sale_id,store_id,product_id,customer_id,quantity,unit_price,total_amount,sale_date,channel,payment_type")
            .gte("sale_date", date_from)
            .limit(5000),
        "fact_sales"
    )
    stores = safe_load(
        lambda: sb.table("dim_stores").select("store_id,store_name,region,city,sqm"),
        "dim_stores"
    )
    products = safe_load(
        lambda: sb.table("dim_products").select("product_id,product_name,category"),
        "dim_products"
    )
    customers = safe_load(
        lambda: sb.table("dim_customers")
            .select("customer_id,name,loyalty_tier,total_spend,last_purchase")
            .order("total_spend", desc=True)
            .limit(50),
        "dim_customers"
    )
    return sales, stores, products, customers, errors


def get_date_from(period: str) -> str:
    d = datetime.now()
    offsets = {"1 mese": 30, "3 mesi": 90, "6 mesi": 180, "12 mesi": 365}
    return (d - timedelta(days=offsets.get(period, 365))).strftime("%Y-%m-%d")


def fmt_currency(v: float) -> str:
    if v >= 1_000_000: return f"€ {v/1_000_000:.2f}M"
    if v >= 1_000:     return f"€ {v/1_000:.1f}K"
    return f"€ {v:.2f}"


def build_report(sel_kpis, sel_charts, kpi_data, period) -> str:
    chart_labels = {
        "Fatturato mensile":     "Andamento fatturato mensile",
        "Mix canali":            "Mix canali di vendita",
        "Mix categorie":         "Mix categorie merceologiche",
        "Performance store":     "Revenue per punto vendita",
        "Trend scontrino medio": "Evoluzione scontrino medio",
        "Top clienti":           "Top clienti per spesa totale",
    }
    lines = [
        "RETAIL ANALYTICS REPORT",
        f"Periodo: {period}  —  Generato il {datetime.now().strftime('%d %B %Y, %H:%M')}",
        f"Sorgente: Supabase — {SUPABASE_URL}",
        "═" * 54, "",
    ]
    if sel_kpis:
        lines += ["KPI SELEZIONATI", "─" * 36]
        for k in sel_kpis:
            if k in kpi_data:
                lines.append(f"  {kpi_data[k]['label']:<24} {kpi_data[k]['value']}")
        lines.append("")
    if sel_charts:
        lines += ["GRAFICI INCLUSI", "─" * 36]
        for c in sel_charts:
            lines.append(f"  • {chart_labels.get(c, c)}")
        lines.append("")
    lines += ["═" * 54]
    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📊 Retail Analytics")
    st.caption(f"Supabase · {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    st.divider()

    period = st.selectbox("Periodo di analisi",
                          ["1 mese","3 mesi","6 mesi","12 mesi"], index=3)

    st.divider()
    st.markdown("### Composizione report")
    st.caption("Seleziona cosa includere")

    kpi_options   = ["Fatturato netto","Scontrino medio","Transazioni","Unità vendute"]
    chart_options = ["Fatturato mensile","Mix canali","Mix categorie",
                     "Performance store","Trend scontrino medio","Top clienti"]

    sel_kpis   = st.multiselect("KPI",    kpi_options,   default=[])
    sel_charts = st.multiselect("Grafici", chart_options, default=[])

    st.divider()
    generate_btn = st.button("📥 Genera report", use_container_width=True,
                             type="primary", disabled=not(sel_kpis or sel_charts))

    st.divider()
    if st.button("🔄 Svuota cache", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# LOAD DATA
# ════════════════════════════════════════════════════════════════════════════
date_from = get_date_from(period)

with st.spinner(f"Caricamento dati (periodo: {period})..."):
    sales, stores, products, customers, load_errors = load_data(date_from)

for err in load_errors:
    st.error(f"⚠ {err}")

if sales.empty:
    st.warning(
        f"Nessuna vendita trovata con `sale_date >= {date_from}`.\n\n"
        "Cause possibili:\n"
        "- Tabelle vuote\n"
        "- RLS attiva senza policy `anon_read`\n"
        "- Date fuori dal range selezionato"
    )
    st.stop()

# ── Pulizia ───────────────────────────────────────────────────────────────────
sales["total_amount"] = pd.to_numeric(sales["total_amount"], errors="coerce").fillna(0)
sales["unit_price"]   = pd.to_numeric(sales["unit_price"],   errors="coerce").fillna(0)
sales["quantity"]     = pd.to_numeric(sales["quantity"],     errors="coerce").fillna(0)
sales["sale_date"]    = pd.to_datetime(sales["sale_date"], utc=True)
sales["month"]        = sales["sale_date"].dt.to_period("M").astype(str)
sales["month_label"]  = sales["sale_date"].dt.strftime("%b %y")
sales["week"]         = sales["sale_date"].dt.to_period("W").astype(str)

if not stores.empty:
    sales = sales.merge(stores[["store_id","store_name","region"]], on="store_id", how="left")
    sales["store_name"] = sales["store_name"].fillna(sales["store_id"])
else:
    sales["store_name"] = sales["store_id"]
    sales["region"]     = "N/D"

if not products.empty:
    sales = sales.merge(products[["product_id","category"]], on="product_id", how="left")
    sales["category"] = sales["category"].fillna("N/D")
else:
    sales["category"] = "N/D"


# ════════════════════════════════════════════════════════════════════════════
# KPI
# ════════════════════════════════════════════════════════════════════════════
revenue      = sales["total_amount"].sum()
transactions = len(sales)
avg_basket   = revenue / transactions if transactions else 0
units        = int(sales["quantity"].sum())
unique_cust  = sales["customer_id"].nunique()

kpi_data = {
    "Fatturato netto": {"label":"Fatturato netto", "value":fmt_currency(revenue)},
    "Scontrino medio": {"label":"Scontrino medio", "value":f"€ {avg_basket:.2f}"},
    "Transazioni":     {"label":"Transazioni",      "value":f"{transactions:,}"},
    "Unità vendute":   {"label":"Unità vendute",    "value":f"{units:,}"},
}

st.markdown(f"## Retail analytics — {period}")
st.caption(
    f"{transactions:,} transazioni · {unique_cust:,} clienti unici · "
    f"aggiornato {datetime.now().strftime('%d/%m/%Y %H:%M')}"
)

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Fatturato netto", fmt_currency(revenue))
c2.metric("Scontrino medio", f"€ {avg_basket:.2f}")
c3.metric("Transazioni",     f"{transactions:,}")
c4.metric("Unità vendute",   f"{units:,}")
c5.metric("Clienti unici",   f"{unique_cust:,}")


# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab_ov, tab_st, tab_pr, tab_cu = st.tabs([
    "📈 Overview", "🏪 Store", "📦 Prodotti", "👥 Clienti"
])

PLOT_LAYOUT = dict(
    margin=dict(l=0, r=0, t=28, b=0),
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(size=12),
    legend=dict(orientation="h", y=-0.2),
)

# ── Overview ──────────────────────────────────────────────────────────────────
with tab_ov:
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Fatturato mensile")
        monthly = (sales.groupby(["month","month_label"])["total_amount"]
                   .sum().reset_index().sort_values("month"))
        fig = px.bar(monthly, x="month_label", y="total_amount",
                     color_discrete_sequence=["#378ADD"],
                     labels={"month_label":"", "total_amount":"Revenue (€)"})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PLOT_LAYOUT, height=300,
                          yaxis=dict(gridcolor="#f0f0f0"),
                          xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("#### Mix canali")
        ch = sales.groupby("channel")["total_amount"].sum().reset_index()
        fig = px.pie(ch, names="channel", values="total_amount",
                     hole=0.45, color_discrete_sequence=COLORS)
        fig.update_layout(**PLOT_LAYOUT, height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Mix categorie merceologiche")
    cats = sales.groupby("category")["total_amount"].sum().reset_index()
    cats["pct"] = (cats["total_amount"] / cats["total_amount"].sum() * 100).round(1)
    cats = cats.sort_values("pct", ascending=True)
    fig = px.bar(cats, x="pct", y="category", orientation="h",
                 color="category", color_discrete_sequence=COLORS,
                 labels={"pct":"% revenue", "category":""}, text="pct")
    fig.update_traces(marker_cornerradius=4,
                      texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(**PLOT_LAYOUT, height=max(220, len(cats)*38),
                      showlegend=False, xaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Trend scontrino medio settimanale")
    weekly = (sales.groupby("week")
              .agg(rev=("total_amount","sum"), txn=("sale_id","count"))
              .reset_index())
    weekly["basket"] = (weekly["rev"] / weekly["txn"]).round(2)
    fig = px.line(weekly, x="week", y="basket", markers=True,
                  color_discrete_sequence=["#7F77DD"],
                  labels={"week":"Settimana", "basket":"Scontrino medio (€)"})
    fig.update_layout(**PLOT_LAYOUT, height=250,
                      yaxis=dict(gridcolor="#f0f0f0"),
                      xaxis=dict(showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

# ── Store ─────────────────────────────────────────────────────────────────────
with tab_st:
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Revenue per store")
        by_store = (sales.groupby("store_name")["total_amount"]
                    .sum().reset_index()
                    .sort_values("total_amount", ascending=True).tail(10))
        fig = px.bar(by_store, x="total_amount", y="store_name", orientation="h",
                     color="store_name", color_discrete_sequence=COLORS,
                     labels={"total_amount":"Revenue (€)", "store_name":""})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PLOT_LAYOUT, height=340, showlegend=False,
                          xaxis=dict(gridcolor="#f0f0f0"),
                          yaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("#### Riepilogo per store")
        by_store_t = sales.groupby("store_name").agg(
            transazioni=("sale_id","count"),
            revenue=("total_amount","sum"),
            clienti=("customer_id","nunique")
        ).reset_index()
        by_store_t["scontrino"] = (
            by_store_t["revenue"] / by_store_t["transazioni"]
        ).round(2)
        by_store_t["revenue_fmt"] = by_store_t["revenue"].apply(fmt_currency)
        by_store_t = by_store_t.sort_values("revenue", ascending=False)
        st.dataframe(
            by_store_t[["store_name","transazioni","scontrino",
                        "clienti","revenue_fmt"]].rename(columns={
                "store_name":"Store", "transazioni":"Transaz.",
                "scontrino":"Scontrino €", "clienti":"Clienti",
                "revenue_fmt":"Revenue"
            }),
            use_container_width=True, hide_index=True
        )

    if "region" in sales.columns and sales["region"].notna().any():
        st.markdown("#### Revenue per regione")
        by_region = sales.groupby("region")["total_amount"].sum().reset_index()
        fig = px.pie(by_region, names="region", values="total_amount",
                     hole=0.4, color_discrete_sequence=COLORS)
        fig.update_layout(**PLOT_LAYOUT, height=280)
        st.plotly_chart(fig, use_container_width=True)

# ── Prodotti ──────────────────────────────────────────────────────────────────
with tab_pr:
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Venduto per categoria (revenue)")
        cats2 = sales.groupby("category")["total_amount"].sum().reset_index()
        fig = px.pie(cats2, names="category", values="total_amount",
                     hole=0.45, color_discrete_sequence=COLORS)
        fig.update_layout(**PLOT_LAYOUT, height=300)
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("#### Unità vendute per categoria")
        cats_q = (sales.groupby("category")["quantity"]
                  .sum().reset_index()
                  .sort_values("quantity", ascending=False))
        fig = px.bar(cats_q, x="category", y="quantity",
                     color="category", color_discrete_sequence=COLORS,
                     labels={"quantity":"Unità", "category":""})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PLOT_LAYOUT, height=300, showlegend=False,
                          yaxis=dict(gridcolor="#f0f0f0"),
                          xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Top 10 prodotti per revenue")
    if not products.empty:
        top_prod = (sales.groupby("product_id")["total_amount"]
                    .sum().reset_index()
                    .merge(products[["product_id","product_name","category"]],
                           on="product_id", how="left")
                    .sort_values("total_amount", ascending=False)
                    .head(10))
        top_prod["revenue_fmt"] = top_prod["total_amount"].apply(fmt_currency)
        top_prod["quota_%"] = (
            top_prod["total_amount"] / top_prod["total_amount"].sum() * 100
        ).round(1)
        st.dataframe(
            top_prod[["product_name","category","revenue_fmt","quota_%"]].rename(columns={
                "product_name":"Prodotto", "category":"Categoria",
                "revenue_fmt":"Revenue",   "quota_%":"Quota %"
            }),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("Dati prodotti non disponibili — verifica dim_products")

# ── Clienti ───────────────────────────────────────────────────────────────────
with tab_cu:
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Top 10 clienti per spesa")
        if not customers.empty:
            customers["total_spend"] = pd.to_numeric(
                customers["total_spend"], errors="coerce").fillna(0)
            top_cust = customers.head(10).copy()
            top_cust["spesa_fmt"] = top_cust["total_spend"].apply(fmt_currency)
            st.dataframe(
                top_cust[["name","loyalty_tier","spesa_fmt"]].rename(columns={
                    "name":"Cliente", "loyalty_tier":"Tier",
                    "spesa_fmt":"Spesa totale"
                }),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("Nessun dato clienti disponibile")

    with col_r:
        st.markdown("#### Mix loyalty tier")
        if not customers.empty and "loyalty_tier" in customers.columns:
            tier = (customers.groupby("loyalty_tier")["total_spend"]
                    .agg(["count","sum"]).reset_index())
            tier.columns = ["tier","clienti","spesa"]
            fig = px.pie(tier, names="tier", values="spesa",
                         hole=0.4, color_discrete_sequence=COLORS)
            fig.update_layout(**PLOT_LAYOUT, height=280)
            st.plotly_chart(fig, use_container_width=True)

    if not customers.empty:
        st.markdown("#### Distribuzione spesa clienti")
        customers["total_spend"] = pd.to_numeric(
            customers["total_spend"], errors="coerce").fillna(0)
        fig = px.histogram(customers, x="total_spend", nbins=20,
                           color_discrete_sequence=["#378ADD"],
                           labels={"total_spend":"Spesa totale (€)",
                                   "count":"Clienti"})
        fig.update_layout(**PLOT_LAYOUT, height=240,
                          yaxis=dict(gridcolor="#f0f0f0"), bargap=0.06)
        st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# REPORT DOWNLOAD
# ════════════════════════════════════════════════════════════════════════════
if generate_btn and (sel_kpis or sel_charts):
    report_txt = build_report(sel_kpis, sel_charts, kpi_data, period)
    st.sidebar.success("✅ Report pronto!")
    st.sidebar.download_button(
        label="📥 Scarica report .txt",
        data=report_txt,
        file_name=f"retail_report_{datetime.now().strftime('%Y-%m-%d')}.txt",
        mime="text/plain",
        use_container_width=True
    )
