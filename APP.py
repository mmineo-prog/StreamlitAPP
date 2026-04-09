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
import base64
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
import plotly.io as pio

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
    background:#f8f9fa; border-radius:12px;
    padding:14px 18px; border:1px solid #e9ecef;
  }
  [data-testid="stSidebar"] { background:#fafafa; }
  .filter-tag {
    display:inline-block; background:#e8f4fd; color:#185fa5;
    border-radius:20px; padding:2px 10px; font-size:12px; margin:2px;
  }
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
    offsets = {"1 mese":30,"3 mesi":90,"6 mesi":180,"12 mesi":365}
    return (d - timedelta(days=offsets.get(period, 365))).strftime("%Y-%m-%d")


def fmt_currency(v: float) -> str:
    if v >= 1_000_000: return f"€ {v/1_000_000:.2f}M"
    if v >= 1_000:     return f"€ {v/1_000:.1f}K"
    return f"€ {v:.2f}"


def fig_to_image(fig, width=700, height=320) -> BytesIO:
    """Converte figura Plotly in PNG bytes per ReportLab."""
    img_bytes = pio.to_image(fig, format="png", width=width, height=height, scale=2)
    return BytesIO(img_bytes)


def build_pdf_report(
    sel_kpis: list,
    sel_charts: list,
    kpi_data: dict,
    period: str,
    filters_summary: str,
    chart_figures: dict,   # {"Fatturato mensile": fig_object, ...}
    store_table: pd.DataFrame | None = None,
    top_prod_table: pd.DataFrame | None = None,
    top_cust_table: pd.DataFrame | None = None,
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    W = A4[0] - 4*cm   # larghezza utile

    # ── Stili ────────────────────────────────────────────────────────────────
    base = getSampleStyleSheet()
    title_style = ParagraphStyle("title", parent=base["Normal"],
        fontSize=22, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1c1c1a"), spaceAfter=4)
    subtitle_style = ParagraphStyle("subtitle", parent=base["Normal"],
        fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#6b6b63"), spaceAfter=2)
    section_style = ParagraphStyle("section", parent=base["Normal"],
        fontSize=13, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1c1c1a"),
        spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle("body", parent=base["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#3d3d3a"), spaceAfter=3)
    kpi_label_style = ParagraphStyle("kpi_label", parent=base["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=colors.HexColor("#888780"))
    kpi_value_style = ParagraphStyle("kpi_value", parent=base["Normal"],
        fontSize=18, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1c1c1a"))

    BLUE   = colors.HexColor("#378ADD")
    GRAY   = colors.HexColor("#f5f5f4")
    BORDER = colors.HexColor("#e0e0dc")

    story = []

    # ── Cover ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph("Retail Analytics Report", title_style))
    story.append(Paragraph(
        f"Periodo: <b>{period}</b> &nbsp;·&nbsp; "
        f"Generato il {datetime.now().strftime('%d %B %Y, %H:%M')} &nbsp;·&nbsp; "
        f"Supabase",
        subtitle_style
    ))
    if filters_summary != "Nessuno":
        story.append(Paragraph(f"Filtri attivi: {filters_summary}", subtitle_style))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width=W, thickness=2, color=BLUE, spaceAfter=16))

    # ── KPI ──────────────────────────────────────────────────────────────────
    if sel_kpis:
        story.append(Paragraph("KPI selezionati", section_style))

        kpi_cells = []
        row = []
        for i, k in enumerate(sel_kpis):
            if k not in kpi_data:
                continue
            cell = [
                Paragraph(kpi_data[k]["label"], kpi_label_style),
                Paragraph(kpi_data[k]["value"], kpi_value_style),
            ]
            row.append(cell)
            if len(row) == 3 or i == len(sel_kpis)-1:
                # padding celle mancanti
                while len(row) < 3:
                    row.append([""])
                kpi_cells.append(row)
                row = []

        col_w = W / 3
        for kpi_row in kpi_cells:
            t = Table(kpi_row, colWidths=[col_w]*3)
            t.setStyle(TableStyle([
                ("BACKGROUND",  (0,0), (-1,-1), GRAY),
                ("GRID",        (0,0), (-1,-1), 0.5, BORDER),
                ("ROUNDEDCORNERS", [6]),
                ("TOPPADDING",  (0,0), (-1,-1), 10),
                ("BOTTOMPADDING",(0,0),(-1,-1), 10),
                ("LEFTPADDING", (0,0), (-1,-1), 12),
                ("RIGHTPADDING",(0,0), (-1,-1), 12),
                ("VALIGN",      (0,0), (-1,-1), "TOP"),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.2*cm))

    # ── Grafici ───────────────────────────────────────────────────────────────
    if sel_charts and chart_figures:
        story.append(Paragraph("Grafici", section_style))
        story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=8))

        for chart_name in sel_charts:
            if chart_name not in chart_figures:
                continue
            story.append(Paragraph(chart_name, ParagraphStyle(
                "chart_title", parent=base["Normal"],
                fontSize=11, fontName="Helvetica-Bold",
                textColor=colors.HexColor("#1c1c1a"),
                spaceBefore=10, spaceAfter=4
            )))
            try:
                img_buf = fig_to_image(chart_figures[chart_name])
                img = RLImage(img_buf, width=W, height=W*0.42)
                story.append(img)
            except Exception as e:
                story.append(Paragraph(f"[Grafico non disponibile: {e}]", body_style))
            story.append(Spacer(1, 0.4*cm))

    # ── Tabelle dati ──────────────────────────────────────────────────────────
    def df_to_table(df: pd.DataFrame, title: str):
        if df is None or df.empty:
            return
        story.append(Paragraph(title, section_style))
        story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=6))

        col_w = W / len(df.columns)
        header = [[Paragraph(f"<b>{c}</b>", ParagraphStyle(
            "th", parent=base["Normal"], fontSize=8,
            fontName="Helvetica-Bold", textColor=colors.HexColor("#3d3d3a")
        )) for c in df.columns]]
        rows = [[Paragraph(str(v), ParagraphStyle(
            "td", parent=base["Normal"], fontSize=8,
            fontName="Helvetica", textColor=colors.HexColor("#1c1c1a")
        )) for v in row] for _, row in df.iterrows()]

        t = Table(header + rows, colWidths=[col_w]*len(df.columns), repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0),  colors.HexColor("#378ADD")),
            ("TEXTCOLOR",    (0,0), (-1,0),  colors.white),
            ("BACKGROUND",   (0,1), (-1,-1), GRAY),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, GRAY]),
            ("GRID",         (0,0), (-1,-1), 0.3, BORDER),
            ("TOPPADDING",   (0,0), (-1,-1), 5),
            ("BOTTOMPADDING",(0,0), (-1,-1), 5),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.4*cm))

    if "Performance store" in sel_charts and store_table is not None:
        df_to_table(store_table, "Dettaglio performance store")

    if "Top clienti" in sel_charts and top_cust_table is not None:
        df_to_table(top_cust_table, "Top clienti per spesa")

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=6))
    story.append(Paragraph(
        f"Report generato da Retail Analytics Dashboard · Supabase · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        ParagraphStyle("footer", parent=base["Normal"], fontSize=7,
                       fontName="Helvetica", textColor=colors.HexColor("#aaaaaa"),
                       alignment=TA_CENTER)
    ))

    doc.build(story)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════════
# CARICAMENTO BASE (solo periodo — i filtri dimensionali vengono dopo)
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📊 Retail Analytics")
    st.caption(f"Supabase · {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    st.divider()
    st.markdown("### ⏱ Periodo")
    period = st.selectbox("Periodo di analisi",
                          ["1 mese","3 mesi","6 mesi","12 mesi"], index=3,
                          label_visibility="collapsed")

date_from = get_date_from(period)

with st.spinner(f"Caricamento dati (periodo: {period})..."):
    sales_raw, stores, products, customers, load_errors = load_data(date_from)

for err in load_errors:
    st.error(f"⚠ {err}")

if sales_raw.empty:
    st.warning(
        f"Nessuna vendita con `sale_date >= {date_from}`.\n\n"
        "Cause: tabelle vuote · RLS attiva · date fuori range"
    )
    st.stop()

# ── Pulizia e join ─────────────────────────────────────────────────────────────
sales_raw["total_amount"] = pd.to_numeric(sales_raw["total_amount"], errors="coerce").fillna(0)
sales_raw["unit_price"]   = pd.to_numeric(sales_raw["unit_price"],   errors="coerce").fillna(0)
sales_raw["quantity"]     = pd.to_numeric(sales_raw["quantity"],     errors="coerce").fillna(0)
sales_raw["sale_date"]    = pd.to_datetime(sales_raw["sale_date"], utc=True)
sales_raw["month"]        = sales_raw["sale_date"].dt.to_period("M").astype(str)
sales_raw["month_label"]  = sales_raw["sale_date"].dt.strftime("%b %y")
sales_raw["week"]         = sales_raw["sale_date"].dt.to_period("W").astype(str)
sales_raw["day_of_week"]  = sales_raw["sale_date"].dt.day_name()

if not stores.empty:
    sales_raw = sales_raw.merge(
        stores[["store_id","store_name","region","city"]], on="store_id", how="left")
    sales_raw["store_name"] = sales_raw["store_name"].fillna(sales_raw["store_id"])
    sales_raw["region"]     = sales_raw["region"].fillna("N/D")
    sales_raw["city"]       = sales_raw["city"].fillna("N/D")
else:
    sales_raw["store_name"] = sales_raw["store_id"]
    sales_raw["region"]     = "N/D"
    sales_raw["city"]       = "N/D"

if not products.empty:
    sales_raw = sales_raw.merge(
        products[["product_id","category"]], on="product_id", how="left")
    sales_raw["category"] = sales_raw["category"].fillna("N/D")
else:
    sales_raw["category"] = "N/D"


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR — FILTRI DIMENSIONALI (dopo il caricamento)
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.divider()
    st.markdown("### 🔍 Filtri dimensionali")

    # Store
    all_stores = sorted(sales_raw["store_name"].dropna().unique().tolist())
    sel_stores = st.multiselect(
        "Store", all_stores,
        placeholder="Tutti gli store",
        help="Filtra per uno o più punti vendita"
    )

    # Regione
    all_regions = sorted(sales_raw["region"].dropna().unique().tolist())
    sel_regions = st.multiselect(
        "Regione", all_regions,
        placeholder="Tutte le regioni",
        help="Filtra per area geografica"
    )

    # Categoria prodotto
    all_cats = sorted(sales_raw["category"].dropna().unique().tolist())
    sel_cats = st.multiselect(
        "Categoria prodotto", all_cats,
        placeholder="Tutte le categorie",
        help="Filtra per categoria merceologica"
    )

    # Canale
    all_channels = sorted(sales_raw["channel"].dropna().unique().tolist())
    sel_channels = st.multiselect(
        "Canale di vendita", all_channels,
        placeholder="Tutti i canali",
        help="POS · eCommerce · Marketplace"
    )

    # Loyalty tier
    all_tiers = []
    if not customers.empty and "loyalty_tier" in customers.columns:
        all_tiers = sorted(customers["loyalty_tier"].dropna().unique().tolist())
    sel_tiers = st.multiselect(
        "Loyalty tier", all_tiers,
        placeholder="Tutti i tier",
        help="Filtra per tier fidelizzazione cliente"
    )

    # Fascia di prezzo
    min_price = float(sales_raw["unit_price"].min())
    max_price = float(sales_raw["unit_price"].max())
    if max_price > min_price:
        price_range = st.slider(
            "Fascia prezzo unitario (€)",
            min_value=min_price, max_value=max_price,
            value=(min_price, max_price),
            format="€%.0f"
        )
    else:
        price_range = (min_price, max_price)

    st.divider()
    st.markdown("### 📋 Composizione report")
    kpi_options   = ["Fatturato netto","Scontrino medio","Transazioni","Unità vendute"]
    chart_options = ["Fatturato mensile","Mix canali","Mix categorie",
                     "Performance store","Trend scontrino medio","Top clienti"]
    sel_kpis   = st.multiselect("KPI",     kpi_options,   default=[])
    sel_charts = st.multiselect("Grafici", chart_options, default=[])

    st.divider()
    generate_btn = st.button("📄 Genera report PDF", use_container_width=True,
                             type="primary", disabled=not(sel_kpis or sel_charts))
    if st.button("🔄 Svuota cache", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ════════════════════════════════════════════════════════════════════════════
# APPLICA FILTRI
# ════════════════════════════════════════════════════════════════════════════
sales = sales_raw.copy()

if sel_stores:   sales = sales[sales["store_name"].isin(sel_stores)]
if sel_regions:  sales = sales[sales["region"].isin(sel_regions)]
if sel_cats:     sales = sales[sales["category"].isin(sel_cats)]
if sel_channels: sales = sales[sales["channel"].isin(sel_channels)]
sales = sales[
    (sales["unit_price"] >= price_range[0]) &
    (sales["unit_price"] <= price_range[1])
]

# Filtro loyalty tier — tramite customer_id
if sel_tiers and not customers.empty:
    cust_filtered = customers[customers["loyalty_tier"].isin(sel_tiers)]["customer_id"].tolist()
    sales = sales[sales["customer_id"].isin(cust_filtered)]

# Riepilogo filtri attivi
active_filters = []
if sel_stores:   active_filters.append(f"Store: {', '.join(sel_stores)}")
if sel_regions:  active_filters.append(f"Regione: {', '.join(sel_regions)}")
if sel_cats:     active_filters.append(f"Categoria: {', '.join(sel_cats)}")
if sel_channels: active_filters.append(f"Canale: {', '.join(sel_channels)}")
if sel_tiers:    active_filters.append(f"Tier: {', '.join(sel_tiers)}")
if price_range != (min_price, max_price):
    active_filters.append(f"Prezzo: €{price_range[0]:.0f}–€{price_range[1]:.0f}")
filters_summary = " · ".join(active_filters) if active_filters else "Nessuno"

if sales.empty:
    st.warning("Nessun dato corrisponde ai filtri selezionati. Prova ad allargare la selezione.")
    st.stop()


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

# Header
st.markdown(f"## Retail analytics — {period}")

# Badge filtri attivi
if active_filters:
    badges = " ".join([f'<span class="filter-tag">{f}</span>' for f in active_filters])
    st.markdown(f"Filtri attivi: {badges}", unsafe_allow_html=True)
else:
    st.caption(f"{transactions:,} transazioni · {unique_cust:,} clienti unici · tutti gli store e canali")

# Confronto con totale non filtrato
if active_filters:
    tot_rev = sales_raw["total_amount"].sum()
    pct = revenue / tot_rev * 100 if tot_rev else 0
    st.caption(f"Selezione: {pct:.1f}% del fatturato totale del periodo · {transactions:,} transazioni · {unique_cust:,} clienti")

st.markdown("")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Fatturato netto", fmt_currency(revenue),
          delta=f"{revenue/sales_raw['total_amount'].sum()*100:.0f}% del totale" if active_filters else None)
c2.metric("Scontrino medio", f"€ {avg_basket:.2f}")
c3.metric("Transazioni",     f"{transactions:,}")
c4.metric("Unità vendute",   f"{units:,}")
c5.metric("Clienti unici",   f"{unique_cust:,}")


# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab_ov, tab_st, tab_pr, tab_cu = st.tabs([
    "📈 Overview","🏪 Store","📦 Prodotti","👥 Clienti"
])

PLOT_LAYOUT = dict(
    margin=dict(l=0,r=0,t=28,b=0),
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
                     labels={"month_label":"","total_amount":"Revenue (€)"})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PLOT_LAYOUT, height=300,
                          yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
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
    cats["pct"] = (cats["total_amount"]/cats["total_amount"].sum()*100).round(1)
    cats = cats.sort_values("pct", ascending=True)
    fig = px.bar(cats, x="pct", y="category", orientation="h",
                 color="category", color_discrete_sequence=COLORS,
                 labels={"pct":"% revenue","category":""}, text="pct")
    fig.update_traces(marker_cornerradius=4,
                      texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(**PLOT_LAYOUT, height=max(220,len(cats)*38),
                      showlegend=False, xaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

    col_l2, col_r2 = st.columns(2)

    with col_l2:
        st.markdown("#### Trend scontrino medio settimanale")
        weekly = (sales.groupby("week")
                  .agg(rev=("total_amount","sum"), txn=("sale_id","count"))
                  .reset_index())
        weekly["basket"] = (weekly["rev"]/weekly["txn"]).round(2)
        fig = px.line(weekly, x="week", y="basket", markers=True,
                      color_discrete_sequence=["#7F77DD"],
                      labels={"week":"Settimana","basket":"Scontrino (€)"})
        fig.update_layout(**PLOT_LAYOUT, height=260,
                          yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    with col_r2:
        st.markdown("#### Vendite per giorno della settimana")
        dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dow_labels = {"Monday":"Lun","Tuesday":"Mar","Wednesday":"Mer",
                      "Thursday":"Gio","Friday":"Ven","Saturday":"Sab","Sunday":"Dom"}
        dow = sales.groupby("day_of_week")["total_amount"].sum().reset_index()
        dow["order"] = dow["day_of_week"].map({d:i for i,d in enumerate(dow_order)})
        dow["label"] = dow["day_of_week"].map(dow_labels)
        dow = dow.sort_values("order")
        fig = px.bar(dow, x="label", y="total_amount",
                     color_discrete_sequence=["#1D9E75"],
                     labels={"label":"","total_amount":"Revenue (€)"})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PLOT_LAYOUT, height=260,
                          yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
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
                     labels={"total_amount":"Revenue (€)","store_name":""})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PLOT_LAYOUT, height=340, showlegend=False,
                          xaxis=dict(gridcolor="#f0f0f0"), yaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        st.markdown("#### Riepilogo per store")
        by_store_t = sales.groupby("store_name").agg(
            transazioni=("sale_id","count"),
            revenue=("total_amount","sum"),
            clienti=("customer_id","nunique"),
            unita=("quantity","sum")
        ).reset_index()
        by_store_t["scontrino"] = (by_store_t["revenue"]/by_store_t["transazioni"]).round(2)
        by_store_t["revenue_fmt"] = by_store_t["revenue"].apply(fmt_currency)
        by_store_t = by_store_t.sort_values("revenue", ascending=False)
        st.dataframe(
            by_store_t[["store_name","transazioni","scontrino","clienti","revenue_fmt"]].rename(columns={
                "store_name":"Store","transazioni":"Transaz.",
                "scontrino":"Scontrino €","clienti":"Clienti","revenue_fmt":"Revenue"
            }),
            use_container_width=True, hide_index=True
        )

    col_l2, col_r2 = st.columns(2)

    with col_l2:
        if "region" in sales.columns and sales["region"].notna().any():
            st.markdown("#### Revenue per regione")
            by_region = sales.groupby("region")["total_amount"].sum().reset_index()
            fig = px.pie(by_region, names="region", values="total_amount",
                         hole=0.4, color_discrete_sequence=COLORS)
            fig.update_layout(**PLOT_LAYOUT, height=280)
            st.plotly_chart(fig, use_container_width=True)

    with col_r2:
        if "city" in sales.columns and sales["city"].notna().any():
            st.markdown("#### Top città per revenue")
            by_city = (sales.groupby("city")["total_amount"]
                       .sum().reset_index()
                       .sort_values("total_amount", ascending=False).head(8))
            fig = px.bar(by_city, x="city", y="total_amount",
                         color="city", color_discrete_sequence=COLORS,
                         labels={"city":"","total_amount":"Revenue (€)"})
            fig.update_traces(marker_cornerradius=4)
            fig.update_layout(**PLOT_LAYOUT, height=280, showlegend=False,
                              yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
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
                  .sum().reset_index().sort_values("quantity", ascending=False))
        fig = px.bar(cats_q, x="category", y="quantity",
                     color="category", color_discrete_sequence=COLORS,
                     labels={"quantity":"Unità","category":""})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PLOT_LAYOUT, height=300, showlegend=False,
                          yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
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
        top_prod["quota_%"] = (top_prod["total_amount"]/top_prod["total_amount"].sum()*100).round(1)
        st.dataframe(
            top_prod[["product_name","category","revenue_fmt","quota_%"]].rename(columns={
                "product_name":"Prodotto","category":"Categoria",
                "revenue_fmt":"Revenue","quota_%":"Quota %"
            }),
            use_container_width=True, hide_index=True
        )
    else:
        st.info("Dati prodotti non disponibili — verifica dim_products")

    st.markdown("#### Prezzo medio per categoria")
    avg_price = (sales.groupby("category")["unit_price"]
                 .mean().reset_index()
                 .sort_values("unit_price", ascending=False))
    avg_price["unit_price"] = avg_price["unit_price"].round(2)
    fig = px.bar(avg_price, x="category", y="unit_price",
                 color="category", color_discrete_sequence=COLORS,
                 labels={"unit_price":"Prezzo medio (€)","category":""},
                 text="unit_price")
    fig.update_traces(marker_cornerradius=4, texttemplate="€%{text:.2f}", textposition="outside")
    fig.update_layout(**PLOT_LAYOUT, height=280, showlegend=False,
                      yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

# ── Clienti ───────────────────────────────────────────────────────────────────
with tab_cu:
    col_l, col_r = st.columns(2)

    with col_l:
        st.markdown("#### Top 10 clienti per spesa")
        if not customers.empty:
            customers["total_spend"] = pd.to_numeric(
                customers["total_spend"], errors="coerce").fillna(0)
            # se filtro tier attivo, filtra anche qui
            cust_view = customers.copy()
            if sel_tiers:
                cust_view = cust_view[cust_view["loyalty_tier"].isin(sel_tiers)]
            top_cust = cust_view.head(10).copy()
            top_cust["spesa_fmt"] = top_cust["total_spend"].apply(fmt_currency)
            st.dataframe(
                top_cust[["name","loyalty_tier","spesa_fmt"]].rename(columns={
                    "name":"Cliente","loyalty_tier":"Tier","spesa_fmt":"Spesa totale"
                }),
                use_container_width=True, hide_index=True
            )
        else:
            st.info("Nessun dato clienti disponibile")

    with col_r:
        st.markdown("#### Mix loyalty tier")
        if not customers.empty and "loyalty_tier" in customers.columns:
            cust_view2 = customers.copy()
            if sel_tiers:
                cust_view2 = cust_view2[cust_view2["loyalty_tier"].isin(sel_tiers)]
            tier = (cust_view2.groupby("loyalty_tier")["total_spend"]
                    .agg(["count","sum"]).reset_index())
            tier.columns = ["tier","clienti","spesa"]
            fig = px.pie(tier, names="tier", values="spesa",
                         hole=0.4, color_discrete_sequence=COLORS)
            fig.update_layout(**PLOT_LAYOUT, height=280)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Spesa clienti per canale di acquisto")
    if not sales[sales["customer_id"].notna()].empty:
        cust_ch = (sales[sales["customer_id"].notna()]
                   .groupby("channel")
                   .agg(clienti=("customer_id","nunique"),
                        spesa_media=("total_amount","mean"))
                   .reset_index())
        cust_ch["spesa_media"] = cust_ch["spesa_media"].round(2)
        fig = px.bar(cust_ch, x="channel", y="spesa_media",
                     color="channel", color_discrete_sequence=COLORS,
                     labels={"channel":"Canale","spesa_media":"Spesa media per transazione (€)"},
                     text="spesa_media")
        fig.update_traces(marker_cornerradius=4,
                          texttemplate="€%{text:.2f}", textposition="outside")
        fig.update_layout(**PLOT_LAYOUT, height=260, showlegend=False,
                          yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# REPORT PDF
# ════════════════════════════════════════════════════════════════════════════
if generate_btn and (sel_kpis or sel_charts):
    with st.spinner("Generazione PDF in corso..."):

        # ── Costruisci i grafici selezionati ──────────────────────────────
        chart_figures = {}

        if "Fatturato mensile" in sel_charts:
            monthly = (sales.groupby(["month","month_label"])["total_amount"]
                       .sum().reset_index().sort_values("month"))
            chart_figures["Fatturato mensile"] = px.bar(
                monthly, x="month_label", y="total_amount",
                color_discrete_sequence=["#378ADD"],
                labels={"month_label":"Mese","total_amount":"Revenue (€)"},
                title="Fatturato mensile"
            )

        if "Mix canali" in sel_charts:
            ch = sales.groupby("channel")["total_amount"].sum().reset_index()
            chart_figures["Mix canali"] = px.pie(
                ch, names="channel", values="total_amount",
                hole=0.45, color_discrete_sequence=COLORS,
                title="Mix canali di vendita"
            )

        if "Mix categorie" in sel_charts:
            cats = sales.groupby("category")["total_amount"].sum().reset_index()
            cats["pct"] = (cats["total_amount"]/cats["total_amount"].sum()*100).round(1)
            cats = cats.sort_values("pct", ascending=True)
            chart_figures["Mix categorie"] = px.bar(
                cats, x="pct", y="category", orientation="h",
                color="category", color_discrete_sequence=COLORS,
                labels={"pct":"% revenue","category":""},
                title="Mix categorie merceologiche"
            )

        if "Performance store" in sel_charts:
            by_store = (sales.groupby("store_name")["total_amount"]
                        .sum().reset_index()
                        .sort_values("total_amount", ascending=True).tail(10))
            chart_figures["Performance store"] = px.bar(
                by_store, x="total_amount", y="store_name", orientation="h",
                color="store_name", color_discrete_sequence=COLORS,
                labels={"total_amount":"Revenue (€)","store_name":""},
                title="Revenue per store"
            )

        if "Trend scontrino medio" in sel_charts:
            weekly = (sales.groupby("week")
                      .agg(rev=("total_amount","sum"), txn=("sale_id","count"))
                      .reset_index())
            weekly["basket"] = (weekly["rev"]/weekly["txn"]).round(2)
            chart_figures["Trend scontrino medio"] = px.line(
                weekly, x="week", y="basket", markers=True,
                color_discrete_sequence=["#7F77DD"],
                labels={"week":"Settimana","basket":"Scontrino medio (€)"},
                title="Trend scontrino medio settimanale"
            )

        if "Top clienti" in sel_charts and not customers.empty:
            cust_chart = customers.head(10).copy()
            cust_chart["total_spend"] = pd.to_numeric(
                cust_chart["total_spend"], errors="coerce").fillna(0)
            chart_figures["Top clienti"] = px.bar(
                cust_chart.sort_values("total_spend"),
                x="total_spend", y="name", orientation="h",
                color="loyalty_tier", color_discrete_sequence=COLORS,
                labels={"total_spend":"Spesa totale (€)","name":""},
                title="Top clienti per spesa"
            )

        # Applica layout pulito a tutti i grafici
        for fig in chart_figures.values():
            fig.update_layout(
                plot_bgcolor="rgba(255,255,255,1)",
                paper_bgcolor="rgba(255,255,255,1)",
                font=dict(family="Helvetica, Arial, sans-serif", size=12),
                margin=dict(l=20,r=20,t=40,b=20),
                showlegend=True,
            )

        # ── Tabelle per il PDF ─────────────────────────────────────────────
        store_table = None
        if "Performance store" in sel_charts:
            st_df = sales.groupby("store_name").agg(
                Transazioni=("sale_id","count"),
                Revenue=("total_amount","sum"),
                Clienti=("customer_id","nunique")
            ).reset_index().sort_values("Revenue", ascending=False)
            st_df["Scontrino €"] = (st_df["Revenue"]/st_df["Transazioni"]).round(2)
            st_df["Revenue"] = st_df["Revenue"].apply(fmt_currency)
            store_table = st_df.rename(columns={"store_name":"Store"})

        top_cust_table = None
        if "Top clienti" in sel_charts and not customers.empty:
            tc = customers.head(10).copy()
            tc["total_spend"] = pd.to_numeric(tc["total_spend"], errors="coerce").fillna(0)
            tc["Spesa totale"] = tc["total_spend"].apply(fmt_currency)
            top_cust_table = tc[["name","loyalty_tier","Spesa totale"]].rename(columns={
                "name":"Cliente","loyalty_tier":"Tier"
            })

        # ── Genera PDF ─────────────────────────────────────────────────────
        try:
            pdf_bytes = build_pdf_report(
                sel_kpis=sel_kpis,
                sel_charts=sel_charts,
                kpi_data=kpi_data,
                period=period,
                filters_summary=filters_summary,
                chart_figures=chart_figures,
                store_table=store_table,
                top_cust_table=top_cust_table,
            )
            st.sidebar.success("✅ PDF pronto!")
            st.sidebar.download_button(
                label="📥 Scarica report PDF",
                data=pdf_bytes,
                file_name=f"retail_report_{datetime.now().strftime('%Y-%m-%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as e:
            st.sidebar.error(f"Errore generazione PDF: {e}")
