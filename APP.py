import { useState, useEffect } from "react";

const URL  = "https://ttnvaxeqbxtvulofeuqs.supabase.co";
const KEY  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR0bnZheGVxYnh0dnVsb2ZldXFzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU3MjAxNDUsImV4cCI6MjA5MTI5NjE0NX0.egdVHwUPY1xhVpeLks6ttyHKusDn94GOi31gPPgt0QQ";
const HDR  = { apikey: KEY, Authorization: `Bearer ${KEY}`, Accept: "application/json" };

async function get(table, params = {}) {
  const u = new URL(`${URL}/rest/v1/${table}`);
  Object.entries(params).forEach(([k,v]) => u.searchParams.set(k,v));
  const r = await fetch(u, { headers: HDR });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

const TABLES = ["fact_sales","dim_stores","dim_products","dim_customers"];

export default function App() {
  const [results, setResults] = useState({});
  const [done, setDone]       = useState(false);

  useEffect(() => {
    async function probe() {
      const out = {};
      for (const t of TABLES) {
        try {
          const rows = await get(t, { limit: 3, select: "*" });
          const count_r = await fetch(`${URL}/rest/v1/${t}?select=*`, {
            headers: { ...HDR, Prefer: "count=exact", "Range-Unit": "items", Range: "0-0" }
          });
          const range = count_r.headers.get("content-range") || "";
          const total = range.split("/")[1] || "?";
          out[t] = { ok: true, total, sample: rows, cols: rows[0] ? Object.keys(rows[0]) : [] };
        } catch(e) {
          out[t] = { ok: false, error: e.message };
        }
      }
      setResults(out);
      setDone(true);
    }
    probe();
  }, []);

  const copyAll = () => {
    const txt = JSON.stringify(results, null, 2);
    navigator.clipboard?.writeText(txt);
  };

  return (
    <div style={{ padding: 20, fontFamily: "var(--font-mono)", fontSize: 12 }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
        <strong style={{ fontSize:14, fontFamily:"var(--font-sans)" }}>Ricognizione tabelle Supabase</strong>
        {done && (
          <button onClick={copyAll} style={{ fontSize:11, padding:"4px 12px", borderRadius:8, border:"1px solid var(--color-border-secondary)", background:"transparent", color:"var(--color-text-secondary)", cursor:"pointer" }}>
            Copia JSON
          </button>
        )}
      </div>

      {TABLES.map(t => {
        const r = results[t];
        if (!r) return (
          <div key={t} style={{ marginBottom:12, padding:"10px 14px", borderRadius:8, background:"var(--color-background-secondary)", border:"1px solid var(--color-border-tertiary)", color:"var(--color-text-tertiary)" }}>
            ○ {t} — in attesa...
          </div>
        );
        return (
          <div key={t} style={{ marginBottom:12, padding:"12px 14px", borderRadius:8, background:"var(--color-background-secondary)", border:`1px solid ${r.ok?"var(--color-border-secondary)":"var(--color-border-danger)"}` }}>
            <div style={{ display:"flex", gap:10, alignItems:"center", marginBottom: r.ok ? 8 : 0 }}>
              <span style={{ color: r.ok ? "var(--color-text-success)" : "var(--color-text-danger)" }}>
                {r.ok ? "✓" : "✗"}
              </span>
              <strong style={{ fontFamily:"var(--font-sans)" }}>{t}</strong>
              {r.ok && <span style={{ color:"var(--color-text-secondary)" }}>{r.total} righe</span>}
              {!r.ok && <span style={{ color:"var(--color-text-danger)" }}>{r.error}</span>}
            </div>
            {r.ok && r.cols.length > 0 && (
              <div style={{ color:"var(--color-text-secondary)", marginBottom:6 }}>
                <span style={{ color:"var(--color-text-tertiary)" }}>colonne: </span>
                {r.cols.join(", ")}
              </div>
            )}
            {r.ok && r.sample?.length > 0 && (
              <details>
                <summary style={{ cursor:"pointer", color:"var(--color-text-tertiary)", fontSize:11 }}>
                  mostra {r.sample.length} righe campione
                </summary>
                <pre style={{ marginTop:8, fontSize:10, overflowX:"auto", color:"var(--color-text-primary)", lineHeight:1.5 }}>
                  {JSON.stringify(r.sample, null, 2)}
                </pre>
              </details>
            )}
          </div>
        );
      })}

      {done && (
        <div style={{ marginTop:8, padding:"10px 14px", borderRadius:8, background:"var(--color-background-info)", border:"1px solid var(--color-border-info)", fontFamily:"var(--font-sans)", fontSize:12, color:"var(--color-text-info)" }}>
          Ricognizione completata — incolla il risultato nella chat per generare il frontend
        </div>
      )}
    </div>
  );
}
