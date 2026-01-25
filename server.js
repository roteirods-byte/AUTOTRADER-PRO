/**
 * AUTOTRADER-PRO - server.js (replacement)
 * FIX V1: PRAZO + DATA/HORA corretos (BRT) para PRO e TOP10.
 */

const fs = require("fs");
const path = require("path");
const express = require("express");

const app = express();

const PORT = Number(process.env.PORT || 8095);
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, "data");
const DIST_DIR = process.env.DIST_DIR || path.join(__dirname, "dist");
const GAIN_MIN = Number(process.env.GAIN_MIN || 3);

function readJsonSafe(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback;
    const raw = fs.readFileSync(filePath, "utf8");
    return JSON.parse(raw);
  } catch (e) {
    return fallback;
  }
}

// BRT: "YYYY-MM-DD HH:MM"
function nowBrtString() {
  try {
    const dtf = new Intl.DateTimeFormat("sv-SE", {
      timeZone: "America/Sao_Paulo",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    return dtf.format(new Date());
  } catch (e) {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
  }
}

function splitUpdatedBrt(s) {
  try {
    s = String(s || "").trim();
    const m = s.match(/^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})/);
    if (!m) return null;
    return { data: m[1], hora: m[2] };
  } catch (e) {
    return null;
  }
}

function normalizePrazo(value) {
  try {
    if (value === null || value === undefined) return "—";
    if (typeof value === "number" && Number.isFinite(value)) return `${value.toFixed(1)}d`;

    const s = String(value).trim();
    if (!s || s === "—" || s === "-") return "—";

    const md = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*d/i);
    if (md) return `${Number(md[1]).toFixed(1)}d`;

    const mh = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*h/i);
    if (mh) return `${(Number(mh[1]) / 24).toFixed(1)}d`;

    const mm = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*m/i);
    if (mm) return `${(Number(mm[1]) / 1440).toFixed(1)}d`;

    return s;
  } catch (e) {
    return "—";
  }
}

function prazoFromRow(row) {
  if (!row || typeof row !== "object") return "—";
  const keys = [
    "prazo", "PRAZO",
    "prazo_dias", "prazoDias", "prazo_d",
    "prazo_txt", "prazoTxt",
    "eta", "ETA",
    "eta_horas", "etaHoras",
    "eta_min", "etaMin"
  ];
  for (const k of keys) {
    const v = row[k];
    if (v === undefined || v === null) continue;
    if (String(v).trim() === "") continue;

    if (k === "ETA" || k === "eta" || k === "eta_horas" || k === "etaHoras") {
      const n = Number(v);
      if (Number.isFinite(n)) return normalizePrazo(n / 24);
    }
    if (k === "eta_min" || k === "etaMin") {
      const n = Number(v);
      if (Number.isFinite(n)) return normalizePrazo(n / 1440);
    }
    return normalizePrazo(v);
  }
  return "—";
}

function rowsFromPayload(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && typeof payload === "object") {
    for (const k of ["rows", "data", "items", "result", "pro", "list"]) {
      if (Array.isArray(payload[k])) return payload[k];
    }
    for (const k of Object.keys(payload)) {
      const v = payload[k];
      if (Array.isArray(v) && v.length && typeof v[0] === "object") return v;
    }
  }
  return [];
}

function normalizeRows(rows, updated_brt) {
  const dhr = splitUpdatedBrt(updated_brt);
  if (!Array.isArray(rows)) return rows;

  for (const r of rows) {
    if (!r || typeof r !== "object") continue;

    const p = prazoFromRow(r);
    r.prazo = p;
    r.PRAZO = p;

    if (dhr) {
      r.data = dhr.data; r.DATA = dhr.data;
      r.hora = dhr.hora; r.HORA = dhr.hora;
    }
  }
  return rows;
}

function buildApiPro() {
  const file = path.join(DATA_DIR, "pro.json");
  const payload = readJsonSafe(file, null);

  let updated_brt = nowBrtString();
  let extra = {};

  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    updated_brt = payload.updated_brt || payload.updatedBrt || payload.updated || payload.ts_brt || payload.time_brt || updated_brt;

    for (const k of ["gain_min", "GAIN_MIN", "vol_btc", "volatilidade_btc", "btc_volatility", "btc_vol"]) {
      if (payload[k] !== undefined) extra[k] = payload[k];
    }
  }

  const rows = normalizeRows(rowsFromPayload(payload || []), updated_brt);

  return {
    ok: true,
    updated_brt,
    gain_min: (extra.gain_min ?? extra.GAIN_MIN ?? GAIN_MIN),
    ...extra,
    rows
  };
}

function parsePctNumber(v) {
  if (v === null || v === undefined) return NaN;
  if (typeof v === "number") return v;
  const s = String(v).replace("%", "").trim();
  const n = Number(s);
  return Number.isFinite(n) ? n : NaN;
}
function parseGainNumber(v) { return parsePctNumber(v); }

function buildApiTop10() {
  const file = path.join(DATA_DIR, "top10.json");
  const payload = readJsonSafe(file, null);

  if (payload) {
    let updated_brt = nowBrtString();
    if (payload && typeof payload === "object" && !Array.isArray(payload)) {
      updated_brt = payload.updated_brt || payload.updatedBrt || payload.updated || payload.ts_brt || payload.time_brt || updated_brt;
    }
    const rows = normalizeRows(rowsFromPayload(payload), updated_brt);
    return { ok: true, updated_brt, gain_min: GAIN_MIN, rows };
  }

  const pro = buildApiPro();
  const rows = Array.isArray(pro.rows) ? pro.rows.slice() : [];

  const filtered = rows.filter(r => {
    const g = parseGainNumber(r.ganho ?? r.GANHO ?? r.ganho_pct ?? r.ganhoPct ?? r.ganho_percent ?? r.ganhoPercent);
    if (!Number.isFinite(g)) return true;
    return g >= GAIN_MIN;
  });

  filtered.sort((a,b) => {
    const aa = parsePctNumber(a.assert ?? a.ASSERT ?? a.assert_pct ?? a.assertPct ?? a.assert_percent ?? a.assertPercent);
    const bb = parsePctNumber(b.assert ?? b.ASSERT ?? b.assert_pct ?? b.assertPct ?? b.assert_percent ?? b.assertPercent);
    if (Number.isFinite(bb) && Number.isFinite(aa) && bb !== aa) return bb - aa;

    const ga = parseGainNumber(a.ganho ?? a.GANHO ?? a.ganho_pct ?? a.ganhoPct ?? a.ganho_percent ?? a.ganhoPercent);
    const gb = parseGainNumber(b.ganho ?? b.GANHO ?? b.ganho_pct ?? b.ganhoPct ?? b.ganho_percent ?? b.ganhoPercent);
    if (Number.isFinite(gb) && Number.isFinite(ga) && gb !== ga) return gb - ga;

    return 0;
  });

  const top10 = filtered.slice(0, 10);
  normalizeRows(top10, pro.updated_brt);

  return { ok: true, updated_brt: pro.updated_brt, gain_min: GAIN_MIN, rows: top10 };
}

// STATIC (sem cache)
app.use((req,res,next) => { res.setHeader("Cache-Control", "no-store"); next(); });
app.use(express.static(DIST_DIR, { etag:false, lastModified:false }));

app.get("/health", (req,res) => {
  res.json({ ok:true, service:"autotrader-pro", ts:new Date().toISOString(), version:"github" });
});

app.get("/api/pro", (req,res) => { res.json(buildApiPro()); });
app.get("/api/top10", (req,res) => { res.json(buildApiTop10()); });

app.get("/api/audit", (req,res) => {
  const file = path.join(DATA_DIR, "audit.json");
  const payload = readJsonSafe(file, { ok:true, updated_brt: nowBrtString(), rows: [] });
  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    payload.ok = true;
    payload.updated_brt = payload.updated_brt || nowBrtString();
    const rows = normalizeRows(rowsFromPayload(payload), payload.updated_brt);
    res.json({ ...payload, rows });
    return;
  }
  res.json({ ok:true, updated_brt: nowBrtString(), rows: rowsFromPayload(payload) });
});

app.get("/", (req,res) => {
  const full = path.join(DIST_DIR, "full.html");
  if (fs.existsSync(full)) return res.sendFile(full);
  res.status(200).send("AUTOTRADER-PRO");
});

app.listen(PORT, () => {
  console.log(`[AUTOTRADER-PRO] API on :${PORT} | DATA_DIR=${DATA_DIR} | DIST_DIR=${DIST_DIR} | GAIN_MIN=${GAIN_MIN}`);
});
