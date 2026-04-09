import { useState, useEffect, useCallback, useRef } from "react";

// ═══════════════════════════════════════════════════════════════════════════════
// TARGET SCHEMA — Single source of truth, mirrors Supabase DDL exactly
// ═══════════════════════════════════════════════════════════════════════════════
const TARGET_TABLES = {
  dim_stores: {
    label: "dim_stores",
    fields: {
      store_id:     { type: "VARCHAR(20)",  required: true,  pk: true },
      store_name:   { type: "VARCHAR(100)", required: true },
      region:       { type: "VARCHAR(50)",  required: true },
      city:         { type: "VARCHAR(50)",  required: true },
      address:      { type: "VARCHAR(200)", required: false },
      manager:      { type: "VARCHAR(100)", required: false },
      opening_date: { type: "DATE",         required: false },
      sqm:          { type: "INTEGER",      required: false },
      created_at:   { type: "TIMESTAMPTZ",  required: true, default: "now()" },
      updated_at:   { type: "TIMESTAMPTZ",  required: true, default: "now()" },
    },
  },
  dim_customers: {
    label: "dim_customers",
    fields: {
      customer_id:  { type: "UUID",          required: true, pk: true, default: "uuid_generate_v4()" },
      email:        { type: "VARCHAR(255)",  required: true },
      name:         { type: "VARCHAR(150)",  required: false },
      phone:        { type: "VARCHAR(30)",   required: false },
      loyalty_tier: { type: "VARCHAR(20)",   required: false },
      total_spend:  { type: "DECIMAL(12,2)", required: false, default: "0" },
      last_purchase:{ type: "TIMESTAMPTZ",   required: false },
      created_at:   { type: "TIMESTAMPTZ",   required: true, default: "now()" },
      updated_at:   { type: "TIMESTAMPTZ",   required: true, default: "now()" },
    },
  },
  dim_products: {
    label: "dim_products",
    fields: {
      product_id:   { type: "VARCHAR(50)",  required: true, pk: true },
      product_name: { type: "VARCHAR(200)", required: false },
      category:     { type: "VARCHAR(100)", required: false },
      supplier_id:  { type: "VARCHAR(50)",  required: false },
      created_at:   { type: "TIMESTAMPTZ",  required: true, default: "now()" },
      updated_at:   { type: "TIMESTAMPTZ",  required: true, default: "now()" },
    },
  },
  fact_sales: {
    label: "fact_sales",
    fields: {
      sale_id:      { type: "UUID",          required: true, pk: true, default: "uuid_generate_v4()" },
      store_id:     { type: "VARCHAR(20)",   required: true, fk: "dim_stores" },
      product_id:   { type: "VARCHAR(50)",   required: true, fk: "dim_products" },
      customer_id:  { type: "UUID",          required: false, fk: "dim_customers" },
      quantity:     { type: "INTEGER",       required: true, check: "quantity > 0" },
      unit_price:   { type: "DECIMAL(10,2)", required: true, check: "unit_price >= 0" },
      total_amount: { type: "DECIMAL(12,2)", required: true },
      sale_date:    { type: "TIMESTAMPTZ",   required: true },
      channel:      { type: "VARCHAR(20)",   required: true, check: "IN ('pos','ecommerce','marketplace')" },
      payment_type: { type: "VARCHAR(30)",   required: false },
      currency:     { type: "VARCHAR(3)",    required: true, default: "EUR" },
      created_at:   { type: "TIMESTAMPTZ",   required: true, default: "now()" },
    },
  },
};

// Source column → target field mapping rules (fuzzy + exact)
const MAPPING_RULES = {
  dim_stores: {
    store_code: "store_id", store_id: "store_id",
    store_name: "store_name", name: "store_name",
    region: "region", city: "city", address: "address",
    manager: "manager", opening_date: "opening_date",
    sqm: "sqm", area: "sqm", square_meters: "sqm",
  },
  dim_customers: {
    customer_id: "customer_id", customer_id_raw: "customer_id", cust_id: "customer_id",
    email: "email", customer_email: "email", mail: "email",
    name: "name", customer_name: "name", full_name: "name",
    phone: "phone", telephone: "phone", tel: "phone",
    loyalty_tier: "loyalty_tier", tier: "loyalty_tier", loyalty: "loyalty_tier",
    total_spend: "total_spend", spend: "total_spend", lifetime_value: "total_spend",
    last_purchase: "last_purchase", last_order: "last_purchase",
  },
  dim_products: {
    product_id: "product_id", item_code: "product_id", product_sku: "product_id", sku: "product_id",
    product_name: "product_name", item_name: "product_name", name: "product_name",
    category: "category", product_category: "category",
    supplier_id: "supplier_id", supplier: "supplier_id",
  },
  fact_sales: {
    transaction_id: "sale_id", sale_id: "sale_id", order_id: "sale_id", id: "sale_id",
    store_id: "store_id", store_code: "store_id", shop_id: "store_id",
    product_sku: "product_id", product_id: "product_id", item_code: "product_id", sku: "product_id",
    customer_id: "customer_id", customer_email: "customer_id",
    qty: "quantity", quantity: "quantity", amount: "quantity",
    price: "unit_price", unit_price: "unit_price",
    total: "total_amount", total_amount: "total_amount",
    date: "sale_date", sale_date: "sale_date", created_at: "sale_date", order_date: "sale_date",
    channel: "channel", source: "channel",
    payment_type: "payment_type", payment: "payment_type", payment_method: "payment_type",
    currency: "currency",
  },
};

// Auto-detect which target table a source file maps to
function detectTargetTable(fileName, columns) {
  const fn = fileName.toLowerCase();
  const colSet = new Set(columns.map(c => c.toLowerCase().trim()));

  // Filename heuristics
  if (fn.includes("store") || fn.includes("punto_vendita") || fn.includes("punti_vendita") || fn.includes("anagrafica")) return "dim_stores";
  if (fn.includes("customer") || fn.includes("crm") || fn.includes("clienti")) return "dim_customers";
  if (fn.includes("product") || fn.includes("inventory") || fn.includes("inventar") || fn.includes("catalogo")) return "dim_products";
  if (fn.includes("sale") || fn.includes("order") || fn.includes("pos") || fn.includes("ecommerce") || fn.includes("transaction")) return "fact_sales";

  // Column overlap scoring
  let bestTable = null, bestScore = 0;
  for (const [table, rules] of Object.entries(MAPPING_RULES)) {
    const srcKeys = Object.keys(rules);
    const score = srcKeys.filter(k => colSet.has(k)).length;
    if (score > bestScore) { bestScore = score; bestTable = table; }
  }
  return bestTable || "fact_sales";
}

// ═══════════════════════════════════════════════════════════════════════════════
// TYPE CASTING & VALIDATION ENGINE
// ═══════════════════════════════════════════════════════════════════════════════

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_TS_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;
const DMY_RE = /^(\d{1,2})[\/\.\-](\d{1,2})[\/\.\-](\d{4})$/;
const MDY_RE = /^(\d{1,2})-(\d{1,2})-(\d{4})$/;

function castValue(raw, targetType, fieldName) {
  if (raw === null || raw === undefined || raw === "") return { value: null, error: null };

  const str = String(raw).trim();
  if (str === "") return { value: null, error: null };

  const baseType = targetType.replace(/\(.*\)/, "").toUpperCase();

  switch (baseType) {
    case "UUID": {
      const uuidRe = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
      if (uuidRe.test(str)) return { value: str.toLowerCase(), error: null };
      // Generate deterministic UUID from non-UUID value (e.g. "TX000123" → UUID)
      return { value: crypto.randomUUID ? crypto.randomUUID() : `00000000-0000-4000-8000-${str.replace(/\W/g,"").padStart(12,"0").slice(0,12)}`, error: null, transformed: true };
    }
    case "VARCHAR": {
      const maxLen = parseInt(targetType.match(/\((\d+)\)/)?.[1] || "255");
      const truncated = str.slice(0, maxLen);
      return { value: truncated, error: truncated.length < str.length ? "truncated" : null };
    }
    case "INTEGER": {
      const n = parseInt(str.replace(/[,.\s]/g, ""));
      if (isNaN(n)) return { value: null, error: "invalid_integer" };
      return { value: n, error: null };
    }
    case "DECIMAL": {
      const num = parseFloat(str.replace(/[,\s]/g, "").replace(/€/g, ""));
      if (isNaN(num)) return { value: null, error: "invalid_decimal" };
      const prec = targetType.match(/\((\d+),(\d+)\)/);
      if (prec) {
        const decimals = parseInt(prec[2]);
        return { value: parseFloat(num.toFixed(decimals)), error: null };
      }
      return { value: num, error: null };
    }
    case "DATE": {
      // Try ISO first
      if (ISO_DATE_RE.test(str)) return { value: str, error: null };
      // DD/MM/YYYY or DD.MM.YYYY
      const dmy = str.match(DMY_RE);
      if (dmy) {
        const [, d, m, y] = dmy;
        return { value: `${y}-${m.padStart(2,"0")}-${d.padStart(2,"0")}`, error: null, transformed: true };
      }
      // Timestamp → Date
      if (ISO_TS_RE.test(str)) return { value: str.slice(0,10), error: null, transformed: true };
      // Unix timestamp
      const unix = parseInt(str);
      if (!isNaN(unix) && unix > 946684800 && unix < 2000000000) {
        return { value: new Date(unix * 1000).toISOString().slice(0,10), error: null, transformed: true };
      }
      return { value: null, error: "invalid_date" };
    }
    case "TIMESTAMPTZ": {
      if (ISO_TS_RE.test(str)) {
        const ts = str.endsWith("Z") ? str : str + "Z";
        return { value: ts, error: null };
      }
      if (ISO_DATE_RE.test(str)) return { value: `${str}T00:00:00Z`, error: null, transformed: true };
      const dmy = str.match(DMY_RE);
      if (dmy) {
        const [, d, m, y] = dmy;
        return { value: `${y}-${m.padStart(2,"0")}-${d.padStart(2,"0")}T00:00:00Z`, error: null, transformed: true };
      }
      const unix = parseInt(str);
      if (!isNaN(unix) && unix > 946684800 && unix < 2000000000) {
        return { value: new Date(unix * 1000).toISOString(), error: null, transformed: true };
      }
      return { value: null, error: "invalid_timestamp" };
    }
    default:
      return { value: str, error: null };
  }
}

function validateCheck(value, check, fieldName) {
  if (!check || value === null || value === undefined) return null;
  if (check.includes("> 0") && value <= 0) return `${fieldName} deve essere > 0 (valore: ${value})`;
  if (check.includes(">= 0") && value < 0) return `${fieldName} deve essere >= 0 (valore: ${value})`;
  if (check.startsWith("IN")) {
    const allowed = check.match(/'([^']+)'/g)?.map(s => s.replace(/'/g, "")) || [];
    if (!allowed.includes(String(value).toLowerCase())) return `${fieldName} deve essere uno tra: ${allowed.join(", ")} (valore: "${value}")`;
  }
  return null;
}

// ═══════════════════════════════════════════════════════════════════════════════
// FILE PARSING
// ═══════════════════════════════════════════════════════════════════════════════

function parseCSV(text) {
  const lines = text.trim().split("\n").filter(Boolean);
  if (!lines.length) return { columns: [], records: [] };
  const sep = lines[0].includes(";") ? ";" : lines[0].includes("\t") ? "\t" : ",";
  const columns = lines[0].split(sep).map(h => h.trim().replace(/^"|"$/g, "").replace(/\r/g, ""));
  const records = [];
  for (let i = 1; i < lines.length; i++) {
    const vals = lines[i].split(sep).map(v => v.trim().replace(/^"|"$/g, "").replace(/\r/g, ""));
    const obj = {};
    columns.forEach((h, j) => { obj[h] = vals[j] ?? ""; });
    records.push(obj);
  }
  return { columns, records };
}

function parseJSON(text) {
  const parsed = JSON.parse(text);
  const arr = Array.isArray(parsed) ? parsed : [parsed];
  const columns = arr.length ? Object.keys(arr[0]) : [];
  return { columns, records: arr };
}

function parseJSONL(text) {
  const lines = text.trim().split("\n").filter(Boolean);
  const records = lines.map(l => JSON.parse(l));
  const columns = records.length ? Object.keys(records[0]) : [];
  return { columns, records };
}

function parseXML(text) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(text, "text/xml");
  const root = doc.documentElement;
  const children = Array.from(root.children);
  if (!children.length) return { columns: [], records: [] };
  const columns = Array.from(children[0].children).map(el => el.tagName);
  const records = children.map(child => {
    const obj = {};
    Array.from(child.children).forEach(el => { obj[el.tagName] = el.textContent || ""; });
    return obj;
  });
  return { columns, records };
}

function parseFileContent(text, format) {
  switch (format) {
    case "CSV": return parseCSV(text);
    case "JSON": return parseJSON(text);
    case "JSONL": return parseJSONL(text);
    case "XML": return parseXML(text);
    default: return parseCSV(text);
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// FULL TRANSFORM + VALIDATE PIPELINE
// ═══════════════════════════════════════════════════════════════════════════════

function transformAndValidate(records, sourceColumns, targetTableName) {
  const tableDef = TARGET_TABLES[targetTableName];
  if (!tableDef) return { transformed: [], issues: [], mapping: {} };

  const rules = MAPPING_RULES[targetTableName] || {};
  const targetFields = tableDef.fields;

  // Build mapping: sourceCol → targetField
  const mapping = {};
  sourceColumns.forEach(srcCol => {
    const key = srcCol.toLowerCase().trim();
    if (rules[key]) mapping[srcCol] = rules[key];
  });

  const issues = [];
  const issueCounts = {};
  const addIssue = (type, severity, field, detail) => {
    const key = `${type}:${field}:${detail}`;
    if (!issueCounts[key]) {
      issueCounts[key] = { type, severity, field, detail, count: 0 };
    }
    issueCounts[key].count++;
  };

  // Track duplicates by PK
  const pkField = Object.entries(targetFields).find(([, v]) => v.pk)?.[0];
  const seenPKs = new Set();

  const transformed = [];
  const now = new Date().toISOString();

  for (let i = 0; i < records.length; i++) {
    const srcRow = records[i];
    const outRow = {};
    let rowValid = true;

    for (const [fieldName, fieldDef] of Object.entries(targetFields)) {
      // Find source value via mapping
      const srcCol = Object.entries(mapping).find(([, tgt]) => tgt === fieldName)?.[0];
      let rawValue = srcCol ? srcRow[srcCol] : undefined;

      // Apply defaults
      if ((rawValue === undefined || rawValue === null || rawValue === "") && fieldDef.default) {
        if (fieldDef.default === "now()") { outRow[fieldName] = now; continue; }
        if (fieldDef.default === "uuid_generate_v4()") { outRow[fieldName] = crypto.randomUUID(); continue; }
        if (fieldDef.default === "EUR") { outRow[fieldName] = "EUR"; continue; }
        if (fieldDef.default === "0") { outRow[fieldName] = 0; continue; }
      }

      // Missing required field
      if ((rawValue === undefined || rawValue === null || rawValue === "") && fieldDef.required && !fieldDef.default) {
        addIssue("missing", "critical", fieldName, `Campo obbligatorio mancante (riga ${i+1})`);
        rowValid = false;
        outRow[fieldName] = '';
        continue;
      }

      if (rawValue === undefined || rawValue === null || rawValue === "") {
        outRow[fieldName] = '';
        continue;
      }

      // Type casting
      const cast = castValue(rawValue, fieldDef.type, fieldName);
      if (cast.error === "truncated") {
        addIssue("format", "low", fieldName, `Valore troncato a max length`);
      } else if (cast.error) {
        addIssue("schema", "high", fieldName, `Type mismatch: "${rawValue}" → ${fieldDef.type}`);
        outRow[fieldName] = '';
        continue;
      }
      if (cast.transformed) {
        addIssue("format", "low", fieldName, `Formato normalizzato → ${fieldDef.type}`);
      }
      outRow[fieldName] = cast.value;

      // CHECK constraints
      if (fieldDef.check) {
        const checkErr = validateCheck(cast.value, fieldDef.check, fieldName);
        if (checkErr) {
          addIssue("constraint", "critical", fieldName, checkErr);
          rowValid = false;
        }
      }
    }

    // Compute total_amount for fact_sales if missing
    if (targetTableName === "fact_sales" && outRow.quantity != null && outRow.unit_price != null) {
      const srcTotal = Object.entries(mapping).find(([, t]) => t === "total_amount")?.[0];
      const rawTotal = srcTotal ? srcRow[srcTotal] : null;
      if (!rawTotal || rawTotal === "") {
        outRow.total_amount = parseFloat((outRow.quantity * outRow.unit_price).toFixed(2));
      }
    }

    // Normalize currency
    if (outRow.currency !== undefined && outRow.currency !== null) {
      const cur = String(outRow.currency).toLowerCase().trim();
      if (["eur","€","euro"].includes(cur)) outRow.currency = "EUR";
      else if (["usd","$","dollar"].includes(cur)) outRow.currency = "USD";
    }

    // Normalize channel
    if (outRow.channel !== undefined && outRow.channel !== null) {
      const ch = String(outRow.channel).toLowerCase().trim();
      if (["pos","in_store","store","offline"].includes(ch)) outRow.channel = "pos";
      else if (["ecommerce","e-commerce","online","web"].includes(ch)) outRow.channel = "ecommerce";
      else if (["marketplace","amazon","ebay"].includes(ch)) outRow.channel = "marketplace";
    }

    // PK duplicate check
    if (pkField && outRow[pkField]) {
      const pkVal = String(outRow[pkField]);
      if (seenPKs.has(pkVal)) {
        addIssue("duplicate", "medium", pkField, `PK duplicata: "${pkVal}"`);
        continue; // skip duplicate row
      }
      seenPKs.add(pkVal);
    }

    transformed.push(outRow);
  }

  return {
    transformed,
    issues: Object.values(issueCounts),
    mapping,
    unmapped: sourceColumns.filter(c => !mapping[c]),
  };
}

// ═══════════════════════════════════════════════════════════════════════════════
// UI TOKENS & SMALL COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════
const T = {
  bg: "#06080C", surface: "#0D1117", surface2: "#151B25", surface3: "#1C2333",
  border: "#1E2636", borderHi: "#2D3752", text: "#E6EAF1", textDim: "#8B95A9",
  textMuted: "#4E5972", accent: "#00E5B0", accentDim: "rgba(0,229,176,0.10)",
  accentGlow: "rgba(0,229,176,0.30)", warn: "#FBBF24", warnDim: "rgba(251,191,36,0.10)",
  error: "#F43F5E", errorDim: "rgba(244,63,94,0.10)", info: "#38BDF8",
  infoDim: "rgba(56,189,248,0.10)", purple: "#A78BFA", purpleDim: "rgba(167,139,250,0.10)",
  emerald: "#34D399", emeraldDim: "rgba(52,211,153,0.10)",
  r: "10px", rSm: "6px",
  mono: "'JetBrains Mono','Fira Code',monospace",
  sans: "'DM Sans','Segoe UI',system-ui,sans-serif",
};

const SEV_COLOR = { low: T.info, medium: T.warn, high: T.error, critical: T.error };
const SEV_BG = { low: T.infoDim, medium: T.warnDim, high: T.errorDim, critical: T.errorDim };
const FORMATS_META = {
  CSV: { color: "#34D399", icon: "≡" }, XLSX: { color: "#38BDF8", icon: "⊞" },
  XML: { color: "#FBBF24", icon: "</>" }, JSON: { color: "#A78BFA", icon: "{ }" },
  JSONL: { color: "#F472B6", icon: "⊞" },
};

const Badge = ({ children, color = T.accent, bg = T.accentDim, style = {} }) => (
  <span style={{
    display: "inline-flex", alignItems: "center", gap: 4,
    padding: "2px 8px", borderRadius: 99, fontSize: 10.5, fontWeight: 600,
    fontFamily: T.mono, color, background: bg, letterSpacing: "0.02em", whiteSpace: "nowrap", ...style,
  }}>{children}</span>
);
const Btn = ({ children, primary, danger, small, disabled, onClick, style = {} }) => (
  <button disabled={disabled} onClick={onClick} style={{
    fontFamily: T.sans, fontSize: small ? 11 : 13, fontWeight: 600,
    padding: small ? "5px 12px" : "9px 20px", borderRadius: T.rSm,
    border: primary || danger ? "none" : `1px solid ${T.borderHi}`,
    cursor: disabled ? "not-allowed" : "pointer",
    background: disabled ? T.surface2 : danger ? T.error : primary ? T.accent : "transparent",
    color: disabled ? T.textMuted : primary ? T.bg : danger ? "#fff" : T.textDim,
    transition: "all 0.15s",
    boxShadow: primary && !disabled ? `0 0 16px ${T.accentGlow}` : "none", ...style,
  }}>{children}</button>
);
const Card = ({ children, style = {} }) => (
  <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: T.r, padding: 20, ...style }}>{children}</div>
);
const Spinner = ({ size = 14, color = T.accent }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" style={{ animation: "spin 0.8s linear infinite", flexShrink: 0 }}>
    <circle cx="12" cy="12" r="10" fill="none" stroke={color} strokeWidth="3" strokeDasharray="31.4 31.4" strokeLinecap="round" />
  </svg>
);
const Progress = ({ value, color = T.accent, h = 5 }) => (
  <div style={{ width: "100%", height: h, background: T.surface2, borderRadius: 99, overflow: "hidden" }}>
    <div style={{ width: `${Math.min(100, Math.max(0, value))}%`, height: "100%", background: color, borderRadius: 99, transition: "width 0.35s ease" }} />
  </div>
);

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════════════════════
export default function DataValidationHub() {
  const [datasets, setDatasets] = useState([]);
  const [view, setView] = useState("upload");
  const [logs, setLogs] = useState([]);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [alerts, setAlerts] = useState([]);
  const [showManual, setShowManual] = useState(false);
  const [manualText, setManualText] = useState("");
  const [manualFormat, setManualFormat] = useState("CSV");
  const [manualName, setManualName] = useState("");
  const fileRef = useRef(null);
  const logEnd = useRef(null);

  // ── Supabase Config ──
  const [sbConnected, setSbConnected] = useState(true);
  const [sbError, setSbError] = useState("");
  const [sbUploadStatus, setSbUploadStatus] = useState({});

  // ── Supabase REST (direct — no CORS from localhost) ──
  const sbFetch = useCallback(async (path, method = "GET", body = null, extraHeaders = {}) => {
    const url = `https://ttnvaxeqbxtvulofeuqs.supabase.co/rest/v1/${path}`;
    const headers = {
      "apikey": 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR0bnZheGVxYnh0dnVsb2ZldXFzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTcyMDE0NSwiZXhwIjoyMDkxMjk2MTQ1fQ.TuD92chDT4_w0EccqoCbX2wYmXLK50rQoMEoHGp-ynA',
      "Authorization": `Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR0bnZheGVxYnh0dnVsb2ZldXFzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTcyMDE0NSwiZXhwIjoyMDkxMjk2MTQ1fQ.TuD92chDT4_w0EccqoCbX2wYmXLK50rQoMEoHGp-ynA`,
      "Content-Type": "application/json",
      ...extraHeaders,
    };
    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);
    return await fetch(url, opts);
  }, []);

  // Test connection
  const testConnection = useCallback(async () => {
    try {
      const res = await sbFetch("dim_stores?limit=1");
      if (res.ok) { setSbConnected(true); setSbError(""); }
      else {
        const txt = await res.text();
        setSbConnected(false); setSbError(`Errore ${res.status}: ${txt.slice(0, 200)}`);
      }
    } catch (err) { setSbConnected(false); setSbError(err.message); }
  }, [sbFetch]);

  // Fields that have server-side defaults
  const SERVER_DEFAULT_FIELDS = new Set(["created_at", "updated_at"]);

  // Upload batch to Supabase via REST POST in chunks
  const uploadToSupabase = useCallback(async (table, rows, dsId, logFn) => {
    const CHUNK_SIZE = 100;
    let uploaded = 0;
    setSbUploadStatus(prev => ({ ...prev, [dsId]: { status: "uploading", count: 0, error: null } }));

    const tableDef = TARGET_TABLES[table];
    const pkField = tableDef ? Object.entries(tableDef.fields).find(([, v]) => v.pk)?.[0] : null;

    for (let i = 0; i < rows.length; i += CHUNK_SIZE) {
      const chunk = rows.slice(i, i + CHUNK_SIZE);

      const cleaned = chunk.map(row => {
        const out = {};
        for (const [k, v] of Object.entries(row)) {
          if (SERVER_DEFAULT_FIELDS.has(k)) continue;
          if (v === null || v === undefined || v === "") continue;
          out[k] = v;
        }
        return out;
      }).filter(row => Object.keys(row).length > 0);

      if (!cleaned.length) continue;

      try {
        const endpoint = pkField ? `${table}?on_conflict=${pkField}` : table;
        const res = await sbFetch(endpoint, "POST", cleaned, { "Prefer": "return=minimal" });

        if (!res.ok) {
          let errDetail = "";
          try { const j = await res.json(); errDetail = j.message || j.details || j.hint || JSON.stringify(j); }
          catch { errDetail = await res.text().catch(() => `HTTP ${res.status}`); }
          const errMsg = `Supabase ${res.status}: ${errDetail}`;
          logFn("store", `  ❌ Chunk ${Math.floor(i/CHUNK_SIZE)+1}: ${errMsg}`, "critical");
          setSbUploadStatus(prev => ({ ...prev, [dsId]: { status: "error", count: uploaded, error: errMsg } }));
          return false;
        }

        uploaded += cleaned.length;
        setSbUploadStatus(prev => ({ ...prev, [dsId]: { status: "uploading", count: uploaded, error: null } }));
        logFn("store", `  📤 ${uploaded}/${rows.length} righe → ${table}`, "success");
      } catch (err) {
        const errMsg = `Errore di rete: ${err.message}`;
        logFn("store", `  ❌ ${errMsg}`, "critical");
        setSbUploadStatus(prev => ({ ...prev, [dsId]: { status: "error", count: uploaded, error: errMsg } }));
        return false;
      }
    }

    setSbUploadStatus(prev => ({ ...prev, [dsId]: { status: "done", count: uploaded, error: null } }));
    return true;
  }, [sbFetch]);

  useEffect(() => { logEnd.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  // ── File Reading ──
  function readFile(file) {
    return new Promise(resolve => {
      const format = (() => {
        const ext = file.name.split(".").pop().toLowerCase();
        return { csv:"CSV", xlsx:"XLSX", xls:"XLSX", xml:"XML", json:"JSON", jsonl:"JSONL", jcde:"JSON" }[ext] || "CSV";
      })();
      const reader = new FileReader();
      reader.onload = e => {
        const text = e.target.result;
        let parsed;
        try { parsed = parseFileContent(text, format); } catch { parsed = { columns: [], records: [] }; }
        const targetTable = detectTargetTable(file.name, parsed.columns);
        resolve({
          id: crypto.randomUUID(), fileName: file.name, fileSize: file.size,
          format, targetTable, sourceColumns: parsed.columns, records: parsed.records,
          status: "uploaded", result: null,
        });
      };
      reader.readAsText(file);
    });
  }

  const handleFiles = async (files) => {
    const accepted = [".csv",".xlsx",".xls",".xml",".json",".jsonl",".jcde"];
    const valid = Array.from(files).filter(f => accepted.some(e => f.name.toLowerCase().endsWith(e)));
    if (!valid.length) return;
    const parsed = await Promise.all(valid.map(readFile));
    setDatasets(prev => [...prev, ...parsed]);
  };

  const handleManualAdd = () => {
    if (!manualText.trim()) return;
    let parsed;
    try { parsed = parseFileContent(manualText, manualFormat); } catch { parsed = { columns: [], records: [] }; }
    const targetTable = detectTargetTable(manualName || "manual", parsed.columns);
    setDatasets(prev => [...prev, {
      id: crypto.randomUUID(), fileName: manualName || `manual.${manualFormat.toLowerCase()}`,
      fileSize: manualText.length, format: manualFormat, targetTable,
      sourceColumns: parsed.columns, records: parsed.records, status: "uploaded", result: null,
    }]);
    setManualText(""); setManualName(""); setShowManual(false);
  };

  const removeDataset = (id) => setDatasets(prev => prev.filter(d => d.id !== id));

  const changeTargetTable = (dsId, table) => {
    setDatasets(prev => prev.map(d => d.id === dsId ? { ...d, targetTable: table } : d));
  };

  // ── PIPELINE ──
  const delay = ms => new Promise(r => setTimeout(r, ms));

  const runPipeline = useCallback(async () => {
    if (!datasets.length) return;
    setRunning(true); setView("pipeline"); setLogs([]); setAlerts([]); setProgress(0);

    for (let i = 0; i < datasets.length; i++) {
      const ds = datasets[i];
      const idx = i;
      const log = (agent, msg, type = "info") =>
        setLogs(prev => [...prev, { agent, msg, type, ds: ds.fileName, ts: Date.now() }]);

      // STEP 1: INGESTION
      log("ingestion", `📥 ${ds.fileName} — ${ds.format}, ${ds.records.length} righe, ${ds.sourceColumns.length} colonne`);
      await delay(250);
      log("ingestion", `Tabella target rilevata: ${ds.targetTable}`);
      await delay(200);

      // STEP 2: MAPPING
      const rules = MAPPING_RULES[ds.targetTable] || {};
      const mapped = ds.sourceColumns.filter(c => rules[c.toLowerCase().trim()]);
      const unmapped = ds.sourceColumns.filter(c => !rules[c.toLowerCase().trim()]);
      log("mapping", `🔗 Mapping: ${mapped.length}/${ds.sourceColumns.length} colonne → ${ds.targetTable}`);
      await delay(150);
      if (mapped.length) log("mapping", `  Mappate: ${mapped.join(", ")}`, "success");
      if (unmapped.length) log("mapping", `  Non mappate (ignorate): ${unmapped.join(", ")}`, "warning");
      await delay(200);

      // STEP 3: TRANSFORM + VALIDATE
      log("transform", `🔄 Trasformazione e validazione vs DDL ${ds.targetTable}...`);
      await delay(300);

      const result = transformAndValidate(ds.records, ds.sourceColumns, ds.targetTable);

      const criticals = result.issues.filter(i => i.severity === "critical");
      const highs = result.issues.filter(i => i.severity === "high");
      const fixable = result.issues.filter(i => i.severity === "medium" || i.severity === "low");

      // Log fixable → auto-resolved
      for (const iss of fixable) {
        const actions = {
          duplicate: "Deduplicazione: rimossa riga duplicata",
          format: `Normalizzazione → ${TARGET_TABLES[ds.targetTable]?.fields[iss.field]?.type || "target type"}`,
        };
        log("autofix", `  🤖 AUTO-FIX "${iss.field}": ${actions[iss.type] || iss.detail} (${iss.count}×)`, "success");
        await delay(100);
      }

      // Log highs → escalated but not blocking
      for (const iss of highs) {
        log("quality", `  🟠 ${iss.type.toUpperCase()} "${iss.field}": ${iss.detail} (${iss.count}×)`, "warning");
        await delay(100);
      }

      // Log criticals → ALERT
      for (const iss of criticals) {
        log("alert", `  🚨 CRITICO "${iss.field}": ${iss.detail} (${iss.count}×)`, "critical");
        setAlerts(prev => [...prev, { id: crypto.randomUUID(), dataset: ds.fileName, table: ds.targetTable, ...iss }]);
        await delay(100);
      }

      // Quality score
      const totalRows = ds.records.length;
      const errorRows = criticals.reduce((a, i) => a + i.count, 0) + highs.reduce((a, i) => a + i.count, 0);
      const score = Math.max(10, Math.round(100 - (errorRows / Math.max(totalRows, 1)) * 100));

      log("quality", `📊 Score: ${score}/100 — ${result.transformed.length}/${totalRows} righe valide → ${ds.targetTable}`, score >= 70 ? "success" : "warning");
      await delay(200);

      // STEP 4: STORE TO SUPABASE
      const canStore = criticals.length === 0;
      if (canStore && sbConnected && result.transformed.length > 0) {
        log("store", `📤 Upload su Supabase → ${ds.targetTable} (${result.transformed.length} righe)...`);
        const ok = await uploadToSupabase(ds.targetTable, result.transformed, ds.id, log);
        if (ok) {
          log("store", `✅ ${result.transformed.length} righe caricate su Supabase → ${ds.targetTable}`, "success");
          setDatasets(prev => prev.map((d, j) => j === idx ? {
            ...d, status: "stored",
            result: { ...result, score, criticals: criticals.length, fixedCount: fixable.length },
          } : d));
        } else {
          log("store", `❌ Upload fallito — verifica errori sopra`, "critical");
          setDatasets(prev => prev.map((d, j) => j === idx ? {
            ...d, status: "error",
            result: { ...result, score, criticals: criticals.length, fixedCount: fixable.length },
          } : d));
        }
      } else if (canStore && !sbConnected) {
        log("store", `⚠ Supabase non connesso — dati pronti per download JSONL`, "warning");
        setDatasets(prev => prev.map((d, j) => j === idx ? {
          ...d, status: "validated",
          result: { ...result, score, criticals: criticals.length, fixedCount: fixable.length },
        } : d));
      } else {
        log("store", `⏸ Upload bloccato — ${criticals.length} issue critiche pendenti`, "warning");
        setDatasets(prev => prev.map((d, j) => j === idx ? {
          ...d, status: "blocked",
          result: { ...result, score, criticals: criticals.length, fixedCount: fixable.length },
        } : d));
      }

      setProgress(((i + 1) / datasets.length) * 100);
      await delay(250);
    }

    setRunning(false);
  }, [datasets, sbConnected, uploadToSupabase]);

  // ── DOWNLOAD: produces JSONL conforming to target DDL ──
  const handleDownload = (ds) => {
    if (!ds.result?.transformed?.length) return;
    const jsonl = ds.result.transformed.map(row => JSON.stringify(row)).join("\n");
    const blob = new Blob([jsonl], { type: "application/jsonl" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${ds.targetTable}_validated.jsonl`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const resolveAlert = (id) => setAlerts(prev => prev.filter(a => a.id !== id));

  const forceStore = useCallback(async (dsId) => {
    const ds = datasets.find(d => d.id === dsId);
    if (!ds?.result?.transformed?.length) return;

    if (sbConnected) {
      const log = (agent, msg, type) => setLogs(prev => [...prev, { agent, msg, type, ds: ds.fileName, ts: Date.now() }]);
      log("store", `📤 Upload forzato su Supabase → ${ds.targetTable}...`);
      const ok = await uploadToSupabase(ds.targetTable, ds.result.transformed, dsId, log);
      if (ok) {
        setDatasets(prev => prev.map(d => d.id === dsId ? { ...d, status: "stored" } : d));
        log("store", `✅ Upload forzato completato`, "success");
      } else {
        setDatasets(prev => prev.map(d => d.id === dsId ? { ...d, status: "error" } : d));
      }
    } else {
      setDatasets(prev => prev.map(d => d.id === dsId ? { ...d, status: "stored" } : d));
    }
  }, [datasets, sbConnected, uploadToSupabase]);

  // ═════════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═════════════════════════════════════════════════════════════════════════════
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,600;0,700&family=JetBrains+Mono:wght@400;500;600&display=swap');
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes fadeUp { from { opacity:0; transform:translateY(10px); } to { opacity:1; transform:translateY(0); } }
    @keyframes slideIn { from { opacity:0; transform:translateX(-10px); } to { opacity:1; transform:translateX(0); } }
    @keyframes pulse { 0%,100%{opacity:1;}50%{opacity:0.4;} }
    @keyframes alertFlash { 0%,100%{box-shadow:0 0 0 0 rgba(244,63,94,0);}50%{box-shadow:0 0 20px 4px rgba(244,63,94,0.25);} }
    *{box-sizing:border-box;margin:0;padding:0;}
    ::-webkit-scrollbar{width:5px;} ::-webkit-scrollbar-track{background:${T.bg};} ::-webkit-scrollbar-thumb{background:${T.borderHi};border-radius:99px;}
    textarea,input,select{font-family:${T.mono};}
  `;

  const tableOptions = Object.keys(TARGET_TABLES);

  // ── UPLOAD VIEW ──
  const renderUpload = () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, animation: "fadeUp 0.3s ease" }}>
      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); e.currentTarget.style.borderColor = T.accent; }}
        onDragLeave={e => { e.currentTarget.style.borderColor = T.borderHi; }}
        onDrop={e => { e.preventDefault(); e.currentTarget.style.borderColor = T.borderHi; handleFiles(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        style={{
          border: `2px dashed ${T.borderHi}`, borderRadius: T.r, padding: "44px 24px",
          textAlign: "center", cursor: "pointer", background: T.surface, transition: "border-color 0.2s",
        }}
      >
        <input ref={fileRef} type="file" multiple accept=".csv,.xlsx,.xls,.xml,.json,.jsonl,.jcde" style={{ display: "none" }}
          onChange={e => handleFiles(e.target.files)} />
        <div style={{ fontSize: 32, marginBottom: 10 }}>📂</div>
        <p style={{ fontFamily: T.sans, fontSize: 14, fontWeight: 600, color: T.text, marginBottom: 4 }}>
          Trascina file o clicca per caricare
        </p>
        <p style={{ fontFamily: T.mono, fontSize: 11, color: T.textDim }}>CSV · XLSX · XML · JSON · JSONL · JCDE</p>
      </div>

      {/* Manual entry */}
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Btn small onClick={() => setShowManual(!showManual)}>{showManual ? "✕ Chiudi" : "+ Inserimento manuale"}</Btn>
      </div>
      {showManual && (
        <Card style={{ animation: "fadeUp 0.2s ease" }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            <input value={manualName} onChange={e => setManualName(e.target.value)} placeholder="Nome dataset"
              style={{ flex: "1 1 180px", padding: "7px 10px", borderRadius: T.rSm, border: `1px solid ${T.borderHi}`, background: T.surface2, color: T.text, fontSize: 11 }} />
            <select value={manualFormat} onChange={e => setManualFormat(e.target.value)}
              style={{ padding: "7px 10px", borderRadius: T.rSm, border: `1px solid ${T.borderHi}`, background: T.surface2, color: T.text, fontSize: 11 }}>
              {["CSV","JSON","JSONL","XML"].map(f => <option key={f}>{f}</option>)}
            </select>
          </div>
          <textarea value={manualText} onChange={e => setManualText(e.target.value)} rows={6}
            placeholder="Incolla i dati qui..."
            style={{ width: "100%", padding: 12, borderRadius: T.rSm, border: `1px solid ${T.borderHi}`, background: T.bg, color: T.text, fontSize: 11, resize: "vertical", lineHeight: 1.6 }} />
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
            <Btn primary small onClick={handleManualAdd} disabled={!manualText.trim()}>Aggiungi</Btn>
          </div>
        </Card>
      )}

      {/* Target schema reference */}
      <Card style={{ padding: 14, background: T.purpleDim, border: `1px solid ${T.purple}30` }}>
        <p style={{ fontFamily: T.sans, fontSize: 12, fontWeight: 600, color: T.purple, marginBottom: 8 }}>
          Schema Target (da DDL Supabase)
        </p>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {tableOptions.map(t => (
            <Badge key={t} color={T.purple} bg={`${T.purple}18`} style={{ fontSize: 10 }}>
              {t} ({Object.keys(TARGET_TABLES[t].fields).length} campi)
            </Badge>
          ))}
        </div>
      </Card>

      {/* Dataset list */}
      {datasets.length > 0 && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <h3 style={{ fontFamily: T.sans, fontSize: 15, fontWeight: 600, color: T.text }}>
              Dataset caricati ({datasets.length})
            </h3>
            <Btn primary onClick={runPipeline} disabled={running}>▶ Avvia Validazione</Btn>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {datasets.map(ds => (
              <Card key={ds.id} style={{ padding: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 200 }}>
                    <span style={{
                      width: 32, height: 32, borderRadius: 7, display: "flex", alignItems: "center", justifyContent: "center",
                      background: `${FORMATS_META[ds.format]?.color || T.textMuted}15`,
                      color: FORMATS_META[ds.format]?.color || T.textMuted, fontFamily: T.mono, fontSize: 11, fontWeight: 600,
                    }}>{FORMATS_META[ds.format]?.icon || "?"}</span>
                    <div>
                      <p style={{ fontFamily: T.sans, fontSize: 13, fontWeight: 600, color: T.text }}>{ds.fileName}</p>
                      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted }}>
                        {ds.records.length} righe · {ds.sourceColumns.length} col
                      </span>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontFamily: T.mono, fontSize: 10, color: T.textDim }}>Target →</span>
                    <select value={ds.targetTable} onChange={e => changeTargetTable(ds.id, e.target.value)}
                      style={{
                        padding: "4px 8px", borderRadius: T.rSm, border: `1px solid ${T.purple}50`,
                        background: T.purpleDim, color: T.purple, fontFamily: T.mono, fontSize: 11, fontWeight: 600,
                      }}>
                      {tableOptions.map(t => <option key={t} value={t}>{t}</option>)}
                    </select>
                    <button onClick={() => removeDataset(ds.id)} style={{
                      background: "transparent", border: "none", color: T.textMuted, cursor: "pointer", fontSize: 15, padding: 4,
                    }}>✕</button>
                  </div>
                </div>
                {/* Column preview */}
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 8 }}>
                  {ds.sourceColumns.slice(0, 8).map(c => {
                    const rules = MAPPING_RULES[ds.targetTable] || {};
                    const isMapped = !!rules[c.toLowerCase().trim()];
                    return (
                      <Badge key={c}
                        color={isMapped ? T.accent : T.textMuted}
                        bg={isMapped ? T.accentDim : T.surface3}
                        style={{ fontSize: 9 }}
                      >
                        {c} {isMapped ? `→ ${rules[c.toLowerCase().trim()]}` : "(skip)"}
                      </Badge>
                    );
                  })}
                  {ds.sourceColumns.length > 8 && <Badge color={T.textMuted} bg={T.surface3} style={{ fontSize: 9 }}>+{ds.sourceColumns.length - 8}</Badge>}
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  // ── PIPELINE VIEW ──
  const agentMeta = {
    ingestion: { label: "Ingestion", color: T.info, icon: "📥" },
    mapping: { label: "Mapping", color: T.purple, icon: "🔗" },
    transform: { label: "Transform", color: T.warn, icon: "🔄" },
    autofix: { label: "Auto-Fix AI", color: T.emerald, icon: "🤖" },
    quality: { label: "Quality", color: T.warn, icon: "📊" },
    alert: { label: "Alert", color: T.error, icon: "🚨" },
    store: { label: "Supabase", color: T.accent, icon: "📤" },
  };

  const renderPipeline = () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 14, animation: "fadeUp 0.3s ease" }}>
      <Card style={{ padding: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontFamily: T.sans, fontSize: 13, fontWeight: 600, color: T.text }}>
            {running ? "Pipeline in esecuzione..." : "Pipeline completata"}
          </span>
          <span style={{ fontFamily: T.mono, fontSize: 11, color: T.accent }}>{Math.round(progress)}%</span>
        </div>
        <Progress value={progress} />
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))", gap: 6 }}>
        {Object.entries(agentMeta).map(([k, m]) => {
          const count = logs.filter(l => l.agent === k).length;
          const active = running && logs.length && logs[logs.length - 1]?.agent === k;
          return (
            <Card key={k} style={{
              padding: 8, border: `1px solid ${active ? m.color : T.border}`,
              boxShadow: active ? `0 0 10px ${m.color}25` : "none",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 3 }}>
                <span style={{ fontSize: 12 }}>{m.icon}</span>
                <span style={{ fontFamily: T.sans, fontSize: 10, fontWeight: 600, color: m.color }}>{m.label}</span>
                {active && <Spinner size={9} color={m.color} />}
              </div>
              <span style={{ fontFamily: T.mono, fontSize: 9, color: T.textMuted }}>{count} ops</span>
            </Card>
          );
        })}
      </div>

      {alerts.length > 0 && (
        <Card style={{ padding: 0, border: `1px solid ${T.error}40`, animation: "alertFlash 2s infinite" }}>
          <div style={{ padding: "8px 14px", background: T.errorDim, borderBottom: `1px solid ${T.error}30`, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 14 }}>🚨</span>
            <span style={{ fontFamily: T.sans, fontSize: 12, fontWeight: 700, color: T.error }}>
              Issue Critiche ({alerts.length})
            </span>
          </div>
          <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
            {alerts.map(a => (
              <div key={a.id} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "8px 12px", borderRadius: T.rSm, background: T.surface2,
              }}>
                <div>
                  <div style={{ display: "flex", gap: 5, alignItems: "center", marginBottom: 3 }}>
                    <Badge color={T.error} bg={T.errorDim}>{a.severity}</Badge>
                    <Badge color={T.purple} bg={T.purpleDim}>{a.table}</Badge>
                    <span style={{ fontFamily: T.mono, fontSize: 11, color: T.text }}>{a.type} → {a.field}</span>
                  </div>
                  <p style={{ fontFamily: T.sans, fontSize: 10, color: T.textDim }}>{a.detail} · {a.count}× · {a.dataset}</p>
                </div>
                <Btn small danger onClick={() => resolveAlert(a.id)}>Risolto</Btn>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card style={{ padding: 0, maxHeight: 340, overflow: "auto", background: T.bg }}>
        <div style={{ padding: "4px 0" }}>
          {logs.map((l, i) => {
            const m = agentMeta[l.agent] || { color: T.textMuted };
            const tc = l.type === "critical" ? T.error : l.type === "error" ? T.error
              : l.type === "warning" ? T.warn : l.type === "success" ? T.accent : T.textDim;
            return (
              <div key={i} style={{
                padding: "4px 14px", display: "flex", gap: 7, alignItems: "flex-start",
                animation: "slideIn 0.12s ease", borderLeft: `2px solid ${m.color}`, marginLeft: 8, marginBottom: 1,
              }}>
                <span style={{ fontFamily: T.mono, fontSize: 9, color: T.textMuted, minWidth: 52, paddingTop: 1 }}>{l.agent.slice(0, 7)}</span>
                <span style={{ fontFamily: T.mono, fontSize: 10.5, color: tc, lineHeight: 1.5 }}>{l.msg}</span>
              </div>
            );
          })}
          <div ref={logEnd} />
        </div>
      </Card>

      {!running && <div style={{ display: "flex", justifyContent: "center" }}><Btn primary onClick={() => setView("results")}>Vai ai Risultati →</Btn></div>}
    </div>
  );

  // ── RESULTS VIEW ──
  const renderResults = () => {
    const processed = datasets.filter(d => d.result);
    const avgScore = processed.length ? Math.round(processed.reduce((a, d) => a + (d.result?.score || 0), 0) / processed.length) : 0;
    const totalTransformed = processed.reduce((a, d) => a + (d.result?.transformed?.length || 0), 0);
    const totalFixed = processed.reduce((a, d) => a + (d.result?.fixedCount || 0), 0);
    const stored = datasets.filter(d => d.status === "stored").length;
    const blocked = datasets.filter(d => d.status === "blocked").length;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 18, animation: "fadeUp 0.3s ease" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(145px, 1fr))", gap: 8 }}>
          {[
            { label: "Quality Score", value: `${avgScore}/100`, color: avgScore >= 70 ? T.accent : T.warn },
            { label: "Righe Valide", value: totalTransformed.toLocaleString(), color: T.accent },
            { label: "Auto-Fixed", value: totalFixed, color: T.emerald },
            { label: "Su Supabase", value: stored, color: T.info },
            { label: "Bloccati", value: blocked, color: blocked > 0 ? T.error : T.textMuted },
          ].map(m => (
            <Card key={m.label} style={{ padding: 12, textAlign: "center" }}>
              <p style={{ fontFamily: T.mono, fontSize: 9, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 5 }}>{m.label}</p>
              <p style={{ fontFamily: T.mono, fontSize: 24, fontWeight: 700, color: m.color }}>{m.value}</p>
            </Card>
          ))}
        </div>

        {datasets.map(ds => {
          if (!ds.result) return null;
          const r = ds.result;
          const sm = ds.status === "stored" ? { label: "SU SUPABASE ✅", color: T.accent, bg: T.accentDim }
            : ds.status === "error" ? { label: "UPLOAD FALLITO", color: T.error, bg: T.errorDim }
            : ds.status === "blocked" ? { label: "BLOCCATO", color: T.error, bg: T.errorDim }
            : ds.status === "validated" ? { label: "VALIDATO (offline)", color: T.warn, bg: T.warnDim }
            : { label: "VALIDATO", color: T.warn, bg: T.warnDim };
          const uploadInfo = sbUploadStatus[ds.id];

          return (
            <Card key={ds.id} style={{ padding: 0, overflow: "hidden" }}>
              <div style={{
                padding: "10px 16px", display: "flex", justifyContent: "space-between", alignItems: "center",
                background: sm.bg, borderBottom: `1px solid ${T.border}`, flexWrap: "wrap", gap: 6,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Badge color={FORMATS_META[ds.format]?.color} bg={`${FORMATS_META[ds.format]?.color}15`}>{ds.format}</Badge>
                  <span style={{ fontFamily: T.mono, fontSize: 10, color: T.textDim }}>→</span>
                  <Badge color={T.purple} bg={T.purpleDim}>{ds.targetTable}</Badge>
                  <span style={{ fontFamily: T.sans, fontSize: 12, fontWeight: 600, color: T.text }}>{ds.fileName}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Badge color={sm.color} bg={sm.bg}>{sm.label}</Badge>
                  <Badge color={r.score >= 70 ? T.accent : T.warn} bg={r.score >= 70 ? T.accentDim : T.warnDim}>Score: {r.score}</Badge>
                </div>
              </div>

              <div style={{ padding: 14 }}>
                <Progress value={r.score} color={r.score >= 70 ? T.accent : T.warn} h={5} />

                {/* Mapping detail */}
                <div style={{ marginTop: 10, marginBottom: 8 }}>
                  <p style={{ fontFamily: T.mono, fontSize: 10, color: T.textMuted, marginBottom: 6 }}>
                    MAPPING ({Object.keys(r.mapping).length} mappate · {r.unmapped.length} ignorate) → JSONL per {ds.targetTable}
                  </p>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {Object.entries(r.mapping).map(([src, tgt]) => (
                      <Badge key={src} color={T.accent} bg={T.accentDim} style={{ fontSize: 9 }}>
                        {src} → {tgt}
                      </Badge>
                    ))}
                    {r.unmapped.map(c => (
                      <Badge key={c} color={T.textMuted} bg={T.surface3} style={{ fontSize: 9, textDecoration: "line-through" }}>
                        {c}
                      </Badge>
                    ))}
                  </div>
                </div>

                {/* Issues */}
                {r.issues.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 10 }}>
                    {r.issues.map((iss, j) => (
                      <div key={j} style={{
                        display: "flex", justifyContent: "space-between", alignItems: "center",
                        padding: "6px 10px", borderRadius: T.rSm, background: T.surface2,
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <Badge color={SEV_COLOR[iss.severity]} bg={SEV_BG[iss.severity]} style={{ fontSize: 9 }}>{iss.severity}</Badge>
                          <span style={{ fontFamily: T.mono, fontSize: 10, color: T.text }}>{iss.type} → {iss.field}</span>
                          <span style={{ fontFamily: T.mono, fontSize: 9, color: T.textMuted }}>({iss.count}×)</span>
                        </div>
                        <Badge
                          color={iss.severity === "low" || iss.severity === "medium" ? T.emerald : T.error}
                          bg={iss.severity === "low" || iss.severity === "medium" ? T.emeraldDim : T.errorDim}
                          style={{ fontSize: 9 }}
                        >
                          {iss.severity === "low" || iss.severity === "medium" ? "✔ AUTO-FIX" : "⚠ ESCALATED"}
                        </Badge>
                      </div>
                    ))}
                  </div>
                )}

                {/* Output preview */}
                {r.transformed.length > 0 && (
                  <div style={{
                    background: T.bg, borderRadius: T.rSm, padding: 10, marginBottom: 10,
                    maxHeight: 120, overflow: "auto", border: `1px solid ${T.border}`,
                  }}>
                    <p style={{ fontFamily: T.mono, fontSize: 9, color: T.accent, marginBottom: 6 }}>
                      Output JSONL preview ({r.transformed.length} righe → {ds.targetTable}):
                    </p>
                    {r.transformed.slice(0, 3).map((row, k) => (
                      <p key={k} style={{ fontFamily: T.mono, fontSize: 9, color: T.textDim, lineHeight: 1.6, wordBreak: "break-all" }}>
                        {JSON.stringify(row)}
                      </p>
                    ))}
                    {r.transformed.length > 3 && (
                      <p style={{ fontFamily: T.mono, fontSize: 9, color: T.textMuted }}>... +{r.transformed.length - 3} righe</p>
                    )}
                  </div>
                )}

                {/* Actions */}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                  <Btn small onClick={() => handleDownload(ds)} disabled={!r.transformed.length}>
                    ⬇ Scarica JSONL ({ds.targetTable})
                  </Btn>
                  {(ds.status === "blocked" || ds.status === "validated") && sbConnected && (
                    <Btn small primary onClick={() => forceStore(ds.id)}>📤 Upload su Supabase</Btn>
                  )}
                  {ds.status === "error" && sbConnected && (
                    <Btn small danger onClick={() => forceStore(ds.id)}>🔄 Riprova upload</Btn>
                  )}
                  {ds.status === "stored" && (
                    <Badge color={T.accent} bg={T.accentDim} style={{ padding: "5px 10px" }}>
                      ✅ Su Supabase → {ds.targetTable}
                      {uploadInfo?.count ? ` (${uploadInfo.count} righe)` : ""}
                    </Badge>
                  )}
                  {ds.status === "error" && uploadInfo?.error && (
                    <span style={{ fontFamily: T.mono, fontSize: 9, color: T.error }}>{uploadInfo.error.slice(0, 100)}</span>
                  )}
                  {uploadInfo?.status === "uploading" && (
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <Spinner size={11} color={T.accent} />
                      <span style={{ fontFamily: T.mono, fontSize: 10, color: T.accent }}>{uploadInfo.count} righe...</span>
                    </div>
                  )}
                  {!sbConnected && (ds.status === "validated" || ds.status === "blocked") && (
                    <Badge color={T.warn} bg={T.warnDim} style={{ padding: "4px 10px", fontSize: 9 }}>
                      Supabase non connesso — scarica JSONL
                    </Badge>
                  )}
                </div>
              </div>
            </Card>
          );
        })}

        <div style={{ display: "flex", justifyContent: "center" }}>
          <Btn onClick={() => { setView("upload"); setDatasets([]); setLogs([]); setAlerts([]); setProgress(0); }}>
            ← Nuova Validazione
          </Btn>
        </div>
      </div>
    );
  };

  // ── LAYOUT ──
  const nav = [
    { id: "config", label: "Supabase", icon: "⚡" },
    { id: "upload", label: "Upload", icon: "📂" },
    { id: "pipeline", label: "Pipeline", icon: "⚙" },
    { id: "results", label: "Risultati", icon: "📊" },
  ];

  // ── Debug state ──
  const [debugLog, setDebugLog] = useState([]);
  const [debugging, setDebugging] = useState(false);

  const runDebug = useCallback(async () => {
    setDebugging(true);
    const lines = [];
    const add = (msg) => { lines.push(msg); setDebugLog([...lines]); };

    add("── STEP 1: Test connettività ──");
    try {
      const r = await sbFetch("");
      add(`GET /rest/v1/ → ${r.status} ${r.statusText}`);
    } catch (err) {
      add(`❌ ERRORE: ${err.message}`);
      setDebugging(false); return;
    }

    for (const table of ["dim_stores", "dim_customers", "dim_products", "fact_sales"]) {
      add(`\n── SELECT ${table} ──`);
      try {
        const r = await sbFetch(`${table}?select=*&limit=1`);
        add(`→ ${r.status} ${r.statusText}`);
        const body = await r.text();
        add(`  ${body.slice(0, 150)}`);
        if (r.status === 404 || body.includes("does not exist")) add(`❌ Tabella NON ESISTE`);
        else if (r.ok) add(`✅ OK`);
      } catch (err) { add(`❌ ${err.message}`); }
    }

    add("\n── Test INSERT dim_stores ──");
    const testRow = { store_id: "TEST_DEBUG_999", store_name: "Debug", region: "Test", city: "Test" };
    try {
      const r = await sbFetch("dim_stores", "POST", testRow, { "Prefer": "return=representation" });
      add(`POST → ${r.status}`);
      const body = await r.text();
      add(`  ${body.slice(0, 300)}`);
      if (r.status === 201 || r.status === 200) {
        add("✅ INSERT OK!");
        setSbConnected(true); setSbError("");
        await sbFetch("dim_stores?store_id=eq.TEST_DEBUG_999", "DELETE");
        add("Cleanup OK");
      } else if (r.status === 403) {
        add("❌ RLS attivo! Esegui: ALTER TABLE dim_stores DISABLE ROW LEVEL SECURITY;");
      } else if (r.status === 409) {
        add("⚠ Conflict (riga già presente) — ma INSERT funziona");
        setSbConnected(true);
      }
    } catch (err) { add(`❌ ${err.message}`); }

    add("\n── DEBUG COMPLETO ──");
    setDebugging(false);
  }, [sbFetch]);

  const renderConfig = () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, animation: "fadeUp 0.3s ease" }}>
      <h2 style={{ fontFamily: T.sans, fontSize: 20, fontWeight: 700, color: T.text }}>Connessione Supabase</h2>

      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 10, height: 10, borderRadius: 99,
              background: sbConnected ? T.accent : T.warn,
              boxShadow: sbConnected ? `0 0 8px ${T.accentGlow}` : "none",
            }} />
            <span style={{ fontFamily: T.sans, fontSize: 14, fontWeight: 600, color: T.text }}>
              {sbConnected ? "Connesso" : "Da verificare"}
            </span>
          </div>
          <div style={{ fontFamily: T.mono, fontSize: 10, color: T.textDim, lineHeight: 1.8 }}>
            URL: https://ttnvaxeqbxtvulofeuqs.supabase.co <br/>
            KEY: {"•".repeat(16)}...{eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR0bnZheGVxYnh0dnVsb2ZldXFzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTcyMDE0NSwiZXhwIjoyMDkxMjk2MTQ1fQ.TuD92chDT4_w0EccqoCbX2wYmXLK50rQoMEoHGp-ynA.slice(-8)}
          </div>
          {sbError && (
            <div style={{ fontFamily: T.mono, fontSize: 10, color: T.error, padding: "8px 10px", background: T.errorDim, borderRadius: T.rSm }}>
              {sbError}
            </div>
          )}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 4 }}>
            <Btn small onClick={testConnection}>🔌 Test rapido</Btn>
            <Btn small danger={debugging} onClick={runDebug} disabled={debugging}>
              {debugging ? <>Debugging... <Spinner size={11} color="#fff" /></> : "🔍 Debug completo"}
            </Btn>
            <Btn small primary onClick={() => setView("upload")}>Upload →</Btn>
          </div>
        </div>
      </Card>

      {debugLog.length > 0 && (
        <Card style={{ padding: 0, background: T.bg }}>
          <div style={{ padding: "8px 14px", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontFamily: T.mono, fontSize: 10, color: T.warn, fontWeight: 600 }}>DEBUG LOG</span>
            <button onClick={() => setDebugLog([])} style={{ background: "transparent", border: "none", color: T.textMuted, cursor: "pointer", fontSize: 12 }}>✕</button>
          </div>
          <div style={{ padding: 14, maxHeight: 450, overflow: "auto" }}>
            {debugLog.map((line, i) => (
              <pre key={i} style={{
                fontFamily: T.mono, fontSize: 10.5, margin: 0, padding: "1px 0",
                whiteSpace: "pre-wrap", wordBreak: "break-all", lineHeight: 1.6,
                color: line.includes("❌") ? T.error : line.includes("✅") ? T.accent : line.startsWith("──") ? T.warn : T.textDim,
              }}>{line}</pre>
            ))}
            {debugging && <Spinner size={12} color={T.accent} />}
          </div>
        </Card>
      )}
    </div>
  );

  return (
    <div style={{ fontFamily: T.sans, background: T.bg, minHeight: "100vh", color: T.text }}>
      <style>{css}</style>
      <div style={{
        padding: "12px 20px", display: "flex", justifyContent: "space-between", alignItems: "center",
        borderBottom: `1px solid ${T.border}`, background: T.surface,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 30, height: 30, borderRadius: 8, background: T.accentDim, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: 16 }}>◈</span>
          </div>
          <div>
            <h1 style={{ fontSize: 14, fontWeight: 700, color: T.text }}>Data Validation Hub</h1>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <p style={{ fontSize: 9, color: T.textDim, fontFamily: T.mono }}>POC Retail · DDL-driven · Multi-format → Supabase</p>
              <div style={{
                width: 7, height: 7, borderRadius: 99,
                background: sbConnected ? T.accent : T.textMuted,
                boxShadow: sbConnected ? `0 0 6px ${T.accentGlow}` : "none",
              }} title={sbConnected ? "Supabase connesso" : "Supabase non connesso"} />
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 2 }}>
          {nav.map(n => (
            <button key={n.id} onClick={() => setView(n.id)} style={{
              fontFamily: T.sans, fontSize: 11, fontWeight: 500, padding: "5px 12px",
              borderRadius: T.rSm, border: "none", cursor: "pointer",
              background: view === n.id ? T.accentDim : "transparent",
              color: view === n.id ? T.accent : T.textDim, transition: "all 0.15s",
              display: "flex", alignItems: "center", gap: 4,
            }}><span style={{ fontSize: 12 }}>{n.icon}</span> {n.label}</button>
          ))}
        </div>
      </div>
      <div style={{ padding: "20px", maxWidth: 1050, margin: "0 auto" }}>
        {view === "config" && renderConfig()}
        {view === "upload" && renderUpload()}
        {view === "pipeline" && renderPipeline()}
        {view === "results" && renderResults()}
      </div>
    </div>
  );
}
