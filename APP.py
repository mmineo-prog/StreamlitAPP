"""
Retail Analytics Dashboard — Streamlit + Supabase
─────────────────────────────────────────────────
secrets.toml:
  SUPABASE_URL = "https://ttnvaxeqbxtvulofeuqs.supabase.co"
  SUPABASE_KEY = "eyJhbGci..."

Avvio locale:
  pip install -r requirements.txt
  streamlit run APP.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image as RLImage, KeepTogether
)
from reportlab.lib.enums import TA_CENTER
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# ── CONFIG ────────────────────────────────────────────────────────────────────
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
COLORS  = ["#378ADD","#1D9E75","#D85A30","#7F77DD","#BA7517","#D4537E"]
MCOLORS = COLORS

st.set_page_config(page_title="Retail Analytics", page_icon="📊",
                   layout="wide", initial_sidebar_state="expanded")

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
            .gte("sale_date", date_from).limit(5000),
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
            .order("total_spend", desc=True).limit(50),
        "dim_customers"
    )
    return sales, stores, products, customers, errors


def get_date_from(period: str) -> str:
    d = datetime.now()
    offsets = {"1 mese":30,"3 mesi":90,"6 mesi":180,"12 mesi":365}
    return (d - timedelta(days=offsets.get(period, 365))).strftime("%Y-%m-%d")


def fmt_currency(v: float) -> str:
    if v >= 1_000_000: return f"€ {v/1_000_000:,.2f}M"
    if v >= 1_000:     return f"€ {v:,.0f}"
    return f"€ {v:.2f}"


# ── MATPLOTLIB HELPERS ────────────────────────────────────────────────────────
def mpl_to_bytes(fig) -> BytesIO:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf

def chart_bar_v(df, x_col, y_col, title) -> BytesIO:
    fig, ax = plt.subplots(figsize=(8, 3.5))
    clrs = [MCOLORS[i % len(MCOLORS)] for i in range(len(df))]
    bars = ax.bar(df[x_col].astype(str), df[y_col], color=clrs, width=0.6)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"€{v:,.0f}" if v < 1000 else f"€{v/1000:.0f}K"))
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(axis="x", labelsize=8, rotation=30)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    # valori sulle barre solo se abbastanza larghe
    max_v = df[y_col].max()
    for bar in bars:
        h = bar.get_height()
        if h > max_v * 0.15:   # mostra solo se barra > 15% del max
            ax.text(bar.get_x() + bar.get_width()/2, h * 0.97,
                    f"€{h:,.0f}", ha="center", va="top",
                    fontsize=7, color="white", fontweight="bold")
    fig.tight_layout()
    return mpl_to_bytes(fig)

def chart_bar_h(df, x_col, y_col, title) -> BytesIO:
    fig, ax = plt.subplots(figsize=(8, max(2.5, len(df)*0.45)))
    clrs = [MCOLORS[i % len(MCOLORS)] for i in range(len(df))]
    bars = ax.barh(df[y_col].astype(str), df[x_col], color=clrs, height=0.6)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"€{v:,.0f}" if v < 1000 else f"€{v/1000:.0f}K"))
    ax.spines[["top","right","left"]].set_visible(False)
    ax.tick_params(axis="y", labelsize=9)
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    # valori nelle barre solo se abbastanza lunghe
    max_v = df[x_col].max()
    for bar in bars:
        w = bar.get_width()
        if w > max_v * 0.25:   # mostra solo se barra > 25% del max
            ax.text(w * 0.97, bar.get_y() + bar.get_height()/2,
                    f"€{w:,.0f}", ha="right", va="center",
                    fontsize=7, color="white", fontweight="bold")
    fig.tight_layout()
    return mpl_to_bytes(fig)

def chart_pie(labels, values, title) -> BytesIO:
    fig, ax = plt.subplots(figsize=(5, 3.8))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%",
        colors=MCOLORS[:len(labels)], startangle=90,
        wedgeprops=dict(width=0.55), pctdistance=0.75,
        labeldistance=1.1
    )
    for t in texts:     t.set_fontsize(8)
    for t in autotexts: t.set_fontsize(7.5)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.set_aspect("equal")
    fig.subplots_adjust(left=0.08, right=0.92, top=0.88, bottom=0.05)
    return mpl_to_bytes(fig)

def chart_line(df, x_col, y_col, title) -> BytesIO:
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(df[x_col].astype(str), df[y_col],
            color="#7F77DD", linewidth=2, marker="o", markersize=4)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"€{v:,.0f}"))
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(axis="x", labelsize=7, rotation=45)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    return mpl_to_bytes(fig)

def chart_bar_v_days(df, x_col, y_col, title) -> BytesIO:
    """Grafico a barre verticali per vendite per giorno della settimana."""
    fig, ax = plt.subplots(figsize=(7, 3.2))
    clrs = [MCOLORS[i % len(MCOLORS)] for i in range(len(df))]
    bars = ax.bar(df[x_col].astype(str), df[y_col], color=clrs, width=0.6)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(
        lambda v, _: f"€{v:,.0f}" if v < 1000 else f"€{v/1000:.0f}K"))
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(axis="x", labelsize=9)
    ax.tick_params(axis="y", labelsize=8)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    max_v = df[y_col].max()
    for bar in bars:
        h = bar.get_height()
        if h > max_v * 0.15:
            ax.text(bar.get_x() + bar.get_width()/2, h * 0.97,
                    f"€{h:,.0f}", ha="center", va="top",
                    fontsize=7, color="white", fontweight="bold")
    fig.tight_layout()
    return mpl_to_bytes(fig)


# ── PDF BUILDER ───────────────────────────────────────────────────────────────
def build_pdf_report(
    sel_kpis: list,
    sel_charts: list,
    kpi_data: dict,
    period: str,
    filters_summary: str,
    chart_imgs: dict,          # ← unico nome usato ovunque
    store_table=None,
    top_cust_table=None,
) -> bytes:

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    W = A4[0] - 4*cm

    base   = getSampleStyleSheet()
    BLUE   = colors.HexColor("#378ADD")
    GRAY   = colors.HexColor("#f5f5f4")
    BORDER = colors.HexColor("#e0e0dc")

    def sty(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    title_sty    = sty("t",  fontSize=22, fontName="Helvetica-Bold",
                        textColor=colors.HexColor("#1c1c1a"), spaceAfter=10, spaceBefore=6)
    sub_sty      = sty("s",  fontSize=10, fontName="Helvetica",
                        textColor=colors.HexColor("#6b6b63"), spaceAfter=6, leading=16)
    section_sty  = sty("se", fontSize=13, fontName="Helvetica-Bold",
                        textColor=colors.HexColor("#1c1c1a"),
                        spaceBefore=14, spaceAfter=6)
    body_sty     = sty("b",  fontSize=9,  fontName="Helvetica",
                        textColor=colors.HexColor("#3d3d3a"), spaceAfter=3)
    kpi_lbl_sty  = sty("kl", fontSize=9,  fontName="Helvetica",
                        textColor=colors.HexColor("#888780"))
    kpi_val_sty  = sty("kv", fontSize=18, fontName="Helvetica-Bold",
                        textColor=colors.HexColor("#1c1c1a"))
    footer_sty   = sty("f",  fontSize=7,  fontName="Helvetica",
                        textColor=colors.HexColor("#aaaaaa"),
                        alignment=TA_CENTER)
    chart_tit_sty = sty("ct", fontSize=11, fontName="Helvetica-Bold",
                         textColor=colors.HexColor("#1c1c1a"),
                         spaceBefore=10, spaceAfter=4)
    th_sty = sty("th", fontSize=8, fontName="Helvetica-Bold",
                 textColor=colors.HexColor("#3d3d3a"))
    td_sty = sty("td", fontSize=8, fontName="Helvetica",
                 textColor=colors.HexColor("#1c1c1a"))

    story = []

    # Cover
    story += [
        Spacer(1, 0.5*cm),
        Paragraph("Retail Analytics Report", title_sty),
        Spacer(1, 0.15*cm),
        Paragraph(
            f"Periodo: <b>{period}</b> &nbsp;·&nbsp; "
            f"Generato il {datetime.now().strftime('%d %B %Y, %H:%M')}",
            sub_sty),
    ]
    if filters_summary != "Nessuno":
        story.append(Spacer(1, 0.1*cm))
        story.append(Paragraph(f"Filtri attivi: {filters_summary}", sub_sty))
    story += [Spacer(1, 0.4*cm),
              HRFlowable(width=W, thickness=2, color=BLUE, spaceAfter=16)]

    # KPI — layout adattivo senza celle vuote
    if sel_kpis:
        story.append(Paragraph("KPI selezionati", section_sty))
        valid_kpis = [k for k in sel_kpis if k in kpi_data]
        n = len(valid_kpis)
        # scegli numero colonne: multiplo di 3 → 3, pari → 2, altrimenti 3
        if n == 0:
            ncols = 1
        elif n % 3 == 0:
            ncols = 3
        elif n % 2 == 0:
            ncols = 2
        else:
            ncols = 3   # ultima riga avrà resto, gestito sotto

        for i in range(0, n, ncols):
            chunk = valid_kpis[i:i+ncols]
            actual_cols = len(chunk)   # ultima riga può avere meno celle
            row = [[Paragraph(kpi_data[k]["label"], kpi_lbl_sty),
                    Paragraph(kpi_data[k]["value"], kpi_val_sty)]
                   for k in chunk]
            t = Table(row, colWidths=[W/actual_cols]*actual_cols)
            t.setStyle(TableStyle([
                ("BACKGROUND",   (0,0),(-1,-1), GRAY),
                ("GRID",         (0,0),(-1,-1), 0.5, BORDER),
                ("TOPPADDING",   (0,0),(-1,-1), 10),
                ("BOTTOMPADDING",(0,0),(-1,-1), 10),
                ("LEFTPADDING",  (0,0),(-1,-1), 12),
                ("RIGHTPADDING", (0,0),(-1,-1), 12),
                ("VALIGN",       (0,0),(-1,-1), "TOP"),
            ]))
            story += [t, Spacer(1, 0.2*cm)]

    # Grafici — usa SOLO chart_imgs
    if sel_charts and chart_imgs:
        story += [Paragraph("Grafici", section_sty),
                  HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=8)]

        # Altezze native per tipo di grafico
        chart_heights = {
            "Fatturato mensile":     W * 0.40,
            "Mix canali":            W * 0.42,   # torta 5x5 — mantieni proporzione quadrata
            "Mix categorie":         W * 0.38,
            "Performance store":     W * 0.50,
            "Trend scontrino medio": W * 0.35,
            "Top clienti":           W * 0.45,
        }

        for name in sel_charts:
            if name not in chart_imgs:
                continue
            try:
                buf_img = chart_imgs[name]
                buf_img.seek(0)
                h = chart_heights.get(name, W * 0.40)
                # KeepTogether impedisce lo split titolo/grafico tra pagine
                block = KeepTogether([
                    Paragraph(name, chart_tit_sty),
                    Spacer(1, 0.15*cm),
                    RLImage(buf_img, width=W, height=h),
                    Spacer(1, 0.5*cm),
                ])
                story.append(block)
            except Exception as ex:
                story.append(Paragraph(f"[{name} — errore: {ex}]", body_sty))

    # Tabelle
    def df_to_table(s, df, title):
        if df is None or df.empty:
            return
        s += [Paragraph(title, section_sty),
              HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=6)]
        col_w = W / len(df.columns)
        header = [[Paragraph(f"<b>{c}</b>", th_sty) for c in df.columns]]
        rows   = [[Paragraph(str(v), td_sty) for v in r]
                  for _, r in df.iterrows()]
        t = Table(header + rows, colWidths=[col_w]*len(df.columns), repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  BLUE),
            ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, GRAY]),
            ("GRID",          (0,0),(-1,-1), 0.3, BORDER),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 8),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        s += [t, Spacer(1, 0.4*cm)]

    if "Performance store" in sel_charts:
        df_to_table(story, store_table, "Dettaglio performance store")
    if "Top clienti" in sel_charts:
        df_to_table(story, top_cust_table, "Top clienti per spesa")

    # Footer
    story += [
        Spacer(1, 0.5*cm),
        HRFlowable(width=W, thickness=0.5, color=BORDER, spaceAfter=6),
        Paragraph(
            f"Report generato da Retail Analytics Dashboard · "
            f"{datetime.now().strftime('%d/%m/%Y %H:%M')}",
            footer_sty)
    ]

    doc.build(story)
    return buf.getvalue()


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR — PERIODO
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📊 Retail Analytics")
    st.caption(f"Supabase · {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    st.divider()
    st.markdown("### ⏱ Periodo")
    period = st.selectbox("Periodo", ["1 mese","3 mesi","6 mesi","12 mesi"],
                          index=3, label_visibility="collapsed")

date_from = get_date_from(period)

with st.spinner(f"Caricamento dati (periodo: {period})..."):
    sales_raw, stores, products, customers, load_errors = load_data(date_from)

for err in load_errors:
    st.error(f"⚠ {err}")

if sales_raw.empty:
    st.warning("Nessuna vendita trovata. Verifica RLS policies o il range di date.")
    st.stop()

# ── Pulizia ────────────────────────────────────────────────────────────────────
for col in ["total_amount","unit_price","quantity"]:
    sales_raw[col] = pd.to_numeric(sales_raw[col], errors="coerce").fillna(0)
sales_raw["sale_date"]   = pd.to_datetime(sales_raw["sale_date"], utc=True)
sales_raw["month"]       = sales_raw["sale_date"].dt.to_period("M").astype(str)
sales_raw["month_label"] = sales_raw["sale_date"].dt.strftime("%b %y")
sales_raw["week"]        = sales_raw["sale_date"].dt.to_period("W").astype(str)
sales_raw["day_of_week"] = sales_raw["sale_date"].dt.day_name()

if not stores.empty:
    sales_raw = sales_raw.merge(
        stores[["store_id","store_name","region","city"]], on="store_id", how="left")
    for c in ["store_name","region","city"]:
        sales_raw[c] = sales_raw[c].fillna(sales_raw.get("store_id","N/D"))
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
# SIDEBAR — FILTRI DIMENSIONALI
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.divider()
    st.markdown("### 🔍 Filtri")

    sel_stores   = st.multiselect("Store",
        sorted(sales_raw["store_name"].dropna().unique()),
        placeholder="Tutti gli store")
    sel_regions  = st.multiselect("Regione",
        sorted(sales_raw["region"].dropna().unique()),
        placeholder="Tutte le regioni")
    sel_cats     = st.multiselect("Categoria",
        sorted(sales_raw["category"].dropna().unique()),
        placeholder="Tutte le categorie")
    sel_channels = st.multiselect("Canale",
        sorted(sales_raw["channel"].dropna().unique()),
        placeholder="Tutti i canali")

    all_tiers = sorted(customers["loyalty_tier"].dropna().unique()) \
        if not customers.empty and "loyalty_tier" in customers.columns else []
    sel_tiers = st.multiselect("Loyalty tier", all_tiers,
                               placeholder="Tutti i tier")

    min_p = float(sales_raw["unit_price"].min())
    max_p = float(sales_raw["unit_price"].max())
    price_range = st.slider("Prezzo unitario (€)", min_p, max_p,
                            (min_p, max_p), format="€%.0f") \
        if max_p > min_p else (min_p, max_p)

    st.divider()
    st.markdown("### 📋 Report")
    sel_kpis   = st.multiselect("KPI",
        ["Fatturato netto","Scontrino medio","Transazioni","Unità vendute"],
        default=[])
    sel_charts = st.multiselect("Grafici",
        ["Fatturato mensile","Mix canali","Mix categorie",
         "Performance store","Trend scontrino medio",
         "Vendite per giorno","% venduto per categoria"],
        default=[])

    st.divider()
    if st.button("📄 Genera report PDF", use_container_width=True,
                 type="primary", disabled=not(sel_kpis or sel_charts)):
        st.session_state["generate_pdf"] = True
        st.session_state["pdf_bytes"]    = None  # reset pdf precedente
    if st.button("🔄 Svuota cache", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # Bottone download — persiste tra rerun
    if st.session_state.get("pdf_bytes"):
        st.success("✅ PDF pronto!")
        st.download_button(
            label="📥 Scarica report PDF",
            data=st.session_state["pdf_bytes"],
            file_name=f"retail_report_{datetime.now().strftime('%Y-%m-%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ════════════════════════════════════════════════════════════════════════════
# APPLICA FILTRI
# ════════════════════════════════════════════════════════════════════════════
sales = sales_raw.copy()
if sel_stores:   sales = sales[sales["store_name"].isin(sel_stores)]
if sel_regions:  sales = sales[sales["region"].isin(sel_regions)]
if sel_cats:     sales = sales[sales["category"].isin(sel_cats)]
if sel_channels: sales = sales[sales["channel"].isin(sel_channels)]
sales = sales[(sales["unit_price"] >= price_range[0]) &
              (sales["unit_price"] <= price_range[1])]
if sel_tiers and not customers.empty:
    cids = customers[customers["loyalty_tier"].isin(sel_tiers)]["customer_id"].tolist()
    sales = sales[sales["customer_id"].isin(cids)]

active_filters = []
if sel_stores:   active_filters.append(f"Store: {', '.join(sel_stores)}")
if sel_regions:  active_filters.append(f"Regione: {', '.join(sel_regions)}")
if sel_cats:     active_filters.append(f"Categoria: {', '.join(sel_cats)}")
if sel_channels: active_filters.append(f"Canale: {', '.join(sel_channels)}")
if sel_tiers:    active_filters.append(f"Tier: {', '.join(sel_tiers)}")
if price_range != (min_p, max_p):
    active_filters.append(f"Prezzo: €{price_range[0]:.0f}–€{price_range[1]:.0f}")
filters_summary = " · ".join(active_filters) if active_filters else "Nessuno"

if sales.empty:
    st.warning("Nessun dato con i filtri selezionati.")
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

st.markdown(f"## Retail analytics — {period}")
if active_filters:
    badges = " ".join([f'<span class="filter-tag">{f}</span>' for f in active_filters])
    st.markdown(f"Filtri attivi: {badges}", unsafe_allow_html=True)
    tot = sales_raw["total_amount"].sum()
    st.caption(f"Selezione: {revenue/tot*100:.1f}% del totale · {transactions:,} transazioni")
else:
    st.caption(f"{transactions:,} transazioni · {unique_cust:,} clienti unici")

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Fatturato netto", fmt_currency(revenue))
c2.metric("Scontrino medio", f"€ {avg_basket:.2f}")
c3.metric("Transazioni",     f"{transactions:,}")
c4.metric("Unità vendute",   f"{units:,}")
c5.metric("Clienti unici",   f"{unique_cust:,}")


# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab_ov, tab_st, tab_pr, tab_cu = st.tabs(["📈 Overview","🏪 Store","📦 Prodotti","👥 Clienti"])

PL = dict(margin=dict(l=0,r=0,t=28,b=0),
          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
          font=dict(size=12), legend=dict(orientation="h", y=-0.2))

# Overview
with tab_ov:
    cl, cr = st.columns(2)
    with cl:
        st.markdown("#### Fatturato mensile")
        m = sales.groupby(["month","month_label"])["total_amount"].sum().reset_index().sort_values("month")
        fig = px.bar(m, x="month_label", y="total_amount", color_discrete_sequence=["#378ADD"],
                     labels={"month_label":"","total_amount":"Revenue (€)"})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PL, height=300, yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)
    with cr:
        st.markdown("#### Mix canali")
        ch = sales.groupby("channel")["total_amount"].sum().reset_index()
        fig = px.pie(ch, names="channel", values="total_amount", hole=0.45, color_discrete_sequence=COLORS)
        fig.update_layout(**PL, height=300)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Mix categorie")
    cats = sales.groupby("category")["total_amount"].sum().reset_index()
    cats["pct"] = (cats["total_amount"]/cats["total_amount"].sum()*100).round(1)
    cats = cats.sort_values("pct", ascending=True)
    fig = px.bar(cats, x="pct", y="category", orientation="h",
                 color="category", color_discrete_sequence=COLORS,
                 labels={"pct":"% revenue","category":""}, text="pct")
    fig.update_traces(marker_cornerradius=4, texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(**PL, height=max(220,len(cats)*38), showlegend=False, xaxis=dict(gridcolor="#f0f0f0"))
    st.plotly_chart(fig, use_container_width=True)

    cl2, cr2 = st.columns(2)
    with cl2:
        st.markdown("#### Trend scontrino medio")
        w = sales.groupby("week").agg(rev=("total_amount","sum"),txn=("sale_id","count")).reset_index()
        w["basket"] = (w["rev"]/w["txn"]).round(2)
        fig = px.line(w, x="week", y="basket", markers=True, color_discrete_sequence=["#7F77DD"],
                      labels={"week":"Settimana","basket":"Scontrino (€)"})
        fig.update_layout(**PL, height=260, yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)
    with cr2:
        st.markdown("#### Vendite per giorno")
        dow_ord = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        dow_lbl = {"Monday":"Lun","Tuesday":"Mar","Wednesday":"Mer","Thursday":"Gio",
                   "Friday":"Ven","Saturday":"Sab","Sunday":"Dom"}
        dw = sales.groupby("day_of_week")["total_amount"].sum().reset_index()
        dw["ord"] = dw["day_of_week"].map({d:i for i,d in enumerate(dow_ord)})
        dw["lbl"] = dw["day_of_week"].map(dow_lbl)
        dw = dw.sort_values("ord")
        fig = px.bar(dw, x="lbl", y="total_amount", color_discrete_sequence=["#1D9E75"],
                     labels={"lbl":"","total_amount":"Revenue (€)"})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PL, height=260, yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

# Store
with tab_st:
    cl, cr = st.columns(2)
    with cl:
        st.markdown("#### Revenue per store")
        bs = sales.groupby("store_name")["total_amount"].sum().reset_index().sort_values("total_amount", ascending=True).tail(10)
        fig = px.bar(bs, x="total_amount", y="store_name", orientation="h",
                     color="store_name", color_discrete_sequence=COLORS,
                     labels={"total_amount":"Revenue (€)","store_name":""})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PL, height=340, showlegend=False,
                          xaxis=dict(gridcolor="#f0f0f0"), yaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)
    with cr:
        st.markdown("#### Riepilogo store")
        bst = sales.groupby("store_name").agg(
            transazioni=("sale_id","count"), revenue=("total_amount","sum"),
            clienti=("customer_id","nunique")).reset_index()
        bst["scontrino"] = (bst["revenue"]/bst["transazioni"]).round(2)
        bst["revenue_fmt"] = bst["revenue"].apply(fmt_currency)
        st.dataframe(bst[["store_name","transazioni","scontrino","clienti","revenue_fmt"]]
                     .sort_values("revenue_fmt", ascending=False)
                     .rename(columns={"store_name":"Store","transazioni":"Transaz.",
                                      "scontrino":"Scontrino €","clienti":"Clienti","revenue_fmt":"Revenue"}),
                     use_container_width=True, hide_index=True)

    cl2, cr2 = st.columns(2)
    with cl2:
        if sales["region"].notna().any():
            st.markdown("#### Per regione")
            br = sales.groupby("region")["total_amount"].sum().reset_index()
            fig = px.pie(br, names="region", values="total_amount", hole=0.4, color_discrete_sequence=COLORS)
            fig.update_layout(**PL, height=280)
            st.plotly_chart(fig, use_container_width=True)
    with cr2:
        if sales["city"].notna().any():
            st.markdown("#### Top città")
            bc = sales.groupby("city")["total_amount"].sum().reset_index().sort_values("total_amount", ascending=False).head(8)
            fig = px.bar(bc, x="city", y="total_amount", color="city", color_discrete_sequence=COLORS,
                         labels={"city":"","total_amount":"Revenue (€)"})
            fig.update_traces(marker_cornerradius=4)
            fig.update_layout(**PL, height=280, showlegend=False,
                              yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
            st.plotly_chart(fig, use_container_width=True)

# Prodotti
with tab_pr:
    cl, cr = st.columns(2)
    with cl:
        st.markdown("#### Venduto per categoria")
        c2 = sales.groupby("category")["total_amount"].sum().reset_index()
        fig = px.pie(c2, names="category", values="total_amount", hole=0.45, color_discrete_sequence=COLORS)
        fig.update_layout(**PL, height=300)
        st.plotly_chart(fig, use_container_width=True)
    with cr:
        st.markdown("#### Unità per categoria")
        cq = sales.groupby("category")["quantity"].sum().reset_index().sort_values("quantity", ascending=False)
        fig = px.bar(cq, x="category", y="quantity", color="category", color_discrete_sequence=COLORS,
                     labels={"quantity":"Unità","category":""})
        fig.update_traces(marker_cornerradius=4)
        fig.update_layout(**PL, height=300, showlegend=False,
                          yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    if not products.empty:
        st.markdown("#### Top 10 prodotti")
        tp = (sales.groupby("product_id")["total_amount"].sum().reset_index()
              .merge(products[["product_id","product_name","category"]], on="product_id", how="left")
              .sort_values("total_amount", ascending=False).head(10))
        tp["revenue_fmt"] = tp["total_amount"].apply(fmt_currency)
        tp["quota_%"] = (tp["total_amount"]/tp["total_amount"].sum()*100).round(1)
        st.dataframe(tp[["product_name","category","revenue_fmt","quota_%"]].rename(columns={
            "product_name":"Prodotto","category":"Categoria","revenue_fmt":"Revenue","quota_%":"Quota %"}),
            use_container_width=True, hide_index=True)

# Clienti
with tab_cu:
    cl, cr = st.columns(2)
    with cl:
        st.markdown("#### Top 10 clienti")
        if not customers.empty:
            customers["total_spend"] = pd.to_numeric(customers["total_spend"], errors="coerce").fillna(0)
            cv = customers[customers["loyalty_tier"].isin(sel_tiers)] if sel_tiers else customers
            tc = cv.head(10).copy()
            tc["spesa_fmt"] = tc["total_spend"].apply(fmt_currency)
            st.dataframe(tc[["name","loyalty_tier","spesa_fmt"]].rename(columns={
                "name":"Cliente","loyalty_tier":"Tier","spesa_fmt":"Spesa totale"}),
                use_container_width=True, hide_index=True)
        else:
            st.info("Nessun dato clienti")
    with cr:
        st.markdown("#### Mix loyalty tier")
        if not customers.empty and "loyalty_tier" in customers.columns:
            cv2 = customers[customers["loyalty_tier"].isin(sel_tiers)] if sel_tiers else customers
            tr = cv2.groupby("loyalty_tier")["total_spend"].agg(["count","sum"]).reset_index()
            tr.columns = ["tier","clienti","spesa"]
            fig = px.pie(tr, names="tier", values="spesa", hole=0.4, color_discrete_sequence=COLORS)
            fig.update_layout(**PL, height=280)
            st.plotly_chart(fig, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# GENERA PDF
# ════════════════════════════════════════════════════════════════════════════
if st.session_state.get("generate_pdf") and (sel_kpis or sel_charts):
    st.session_state["generate_pdf"] = False
    with st.spinner("Generazione PDF in corso..."):

        # Costruisci immagini matplotlib
        chart_imgs = {}

        if "Fatturato mensile" in sel_charts:
            m = sales.groupby(["month","month_label"])["total_amount"].sum().reset_index().sort_values("month")
            chart_imgs["Fatturato mensile"] = chart_bar_v(m, "month_label", "total_amount", "Fatturato mensile")

        if "Mix canali" in sel_charts:
            ch = sales.groupby("channel")["total_amount"].sum().reset_index()
            chart_imgs["Mix canali"] = chart_pie(ch["channel"].tolist(), ch["total_amount"].tolist(), "Mix canali")

        if "Mix categorie" in sel_charts:
            cats = sales.groupby("category")["total_amount"].sum().reset_index().sort_values("total_amount")
            chart_imgs["Mix categorie"] = chart_bar_h(cats, "total_amount", "category", "Mix categorie")

        if "% venduto per categoria" in sel_charts:
            cats_p = sales.groupby("category")["total_amount"].sum().reset_index()
            total_c = cats_p["total_amount"].sum()
            chart_imgs["% venduto per categoria"] = chart_pie(
                cats_p["category"].tolist(),
                cats_p["total_amount"].tolist(),
                "% venduto per categoria"
            )

        if "Performance store" in sel_charts:
            bs = sales.groupby("store_name")["total_amount"].sum().reset_index().sort_values("total_amount").tail(10)
            chart_imgs["Performance store"] = chart_bar_h(bs, "total_amount", "store_name", "Revenue per store")

        if "Trend scontrino medio" in sel_charts:
            w = sales.groupby("week").agg(rev=("total_amount","sum"),txn=("sale_id","count")).reset_index()
            w["basket"] = (w["rev"]/w["txn"]).round(2)
            chart_imgs["Trend scontrino medio"] = chart_line(w, "week", "basket", "Trend scontrino medio")

        if "Vendite per giorno" in sel_charts:
            dow_ord = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            dow_lbl = {"Monday":"Lun","Tuesday":"Mar","Wednesday":"Mer","Thursday":"Gio",
                       "Friday":"Ven","Saturday":"Sab","Sunday":"Dom"}
            dw = sales.groupby("day_of_week")["total_amount"].sum().reset_index()
            dw["ord"] = dw["day_of_week"].map({d:i for i,d in enumerate(dow_ord)})
            dw["lbl"] = dw["day_of_week"].map(dow_lbl)
            dw = dw.sort_values("ord")
            chart_imgs["Vendite per giorno"] = chart_bar_v_days(
                dw, "lbl", "total_amount", "Vendite per giorno della settimana")

        # Tabelle
        store_table = None
        if "Performance store" in sel_charts:
            sd = sales.groupby("store_name").agg(
                Transazioni=("sale_id","count"), Revenue=("total_amount","sum"),
                Clienti=("customer_id","nunique")).reset_index().sort_values("Revenue", ascending=False).head(15)
            sd["Scontrino €"] = (sd["Revenue"]/sd["Transazioni"]).apply(lambda x: f"€ {x:,.2f}")
            sd["Revenue"] = sd["Revenue"].apply(fmt_currency)
            store_table = sd.rename(columns={"store_name":"Store"})

        if "Performance store" in sel_charts and store_table is not None:
            df_to_table(story, store_table,
                        "Dettaglio performance store (top 15 per revenue)")

        top_cust_table = None
        if "Top clienti" in sel_charts and not customers.empty:
            tc2 = customers.head(10).copy()
            tc2["total_spend"] = pd.to_numeric(tc2["total_spend"], errors="coerce").fillna(0)
            tc2["Spesa totale"] = tc2["total_spend"].apply(fmt_currency)
            top_cust_table = tc2[["name","loyalty_tier","Spesa totale"]].rename(
                columns={"name":"Cliente","loyalty_tier":"Tier"})

        # Genera PDF
        try:
            pdf_bytes = build_pdf_report(
                sel_kpis=sel_kpis,
                sel_charts=sel_charts,
                kpi_data=kpi_data,
                period=period,
                filters_summary=filters_summary,
                chart_imgs=chart_imgs,       # ← unico nome, nessuna ambiguità
                store_table=store_table,
                top_cust_table=top_cust_table,
            )
            st.sidebar.success("✅ PDF pronto!")
            st.sidebar.download_button(
                label="📥 Scarica report PDF",
                data=pdf_bytes,
                file_name=f"retail_report_{datetime.now().strftime('%Y-%m-%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.sidebar.error(f"Errore generazione PDF: {e}")
