/**
 * AUTOTRADER-PRO - server.js (FIX DEFINITIVO V2)
 * - Corrige DATA/HORA (BRT) e PRAZO (quando existir em qualquer chave conhecida)
 * - /api/top10 pode ser derivado do PRO se top10.json estiver ausente/inválido
 */
"use strict";

const fs = require("fs");
const path = require("path");
const express = require("express");
app.get("/health", (req, res) => {
  res.json({ ok: true, service: "AUTOTRADER-PRO", ts: Date.now() });
});

const app = express();
// === STATIC_SITE_V1 ===
const path = require("path");

// health (para monitorar se está vivo)
app.get("/health", (req, res) => {
  res.json({ ok: true, service: "autotrader-pro", ts: Date.now() });
});

// servir arquivos do /dist (top10.html, full.html, index.html etc)
app.use(express.static(path.join(__dirname, "dist")));

// compatibilidade (links diretos)
app.get("/top10", (req, res) => res.sendFile(path.join(__dirname, "dist", "top10.html")));
app.get("/top10.html", (req, res) => res.sendFile(path.join(__dirname, "dist", "top10.html")));
app.get("/full", (req, res) => res.sendFile(path.join(__dirname, "dist", "full.html")));
app.get("/full.html", (req, res) => res.sendFile(path.join(__dirname, "dist", "full.html")));
// === /STATIC_SITE_V1 ===

const PORT = Number(process.env.PORT || 8095);
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, "data");
const TZ = "America/Sao_Paulo";

function readJsonSafe(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    const raw = fs.readFileSync(filePath, "utf8");
    if (!raw || !raw.trim()) return null;
    return JSON.parse(raw);
  } catch (e) {
    return { __error: String(e && e.message ? e.message : e) };
  }
}

function formatBRTFromDate(d) {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  }).formatToParts(d);
  const get = (t) => (parts.find(p => p.type === t) || {}).value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

function parseUpdatedBrt(v) {
  if (typeof v !== "string") return null;
  const s = v.trim();
  const m = s.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?$/);
  if (!m) return null;
  return { date: m[1], time: m[2] };
}

function coerceNumber(x) {
  if (x === null || x === undefined) return null;
  if (typeof x === "number" && Number.isFinite(x)) return x;
  if (typeof x === "string") {
    const s = x.trim().replace(",", ".");
    if (!s) return null;
    const n = Number(s);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function formatPrazoDays(days) {
  const d = coerceNumber(days);
  if (d === null) return null;
  return `${d.toFixed(1)}d`;
}

function pickFirst(obj, keys) {
  for (const k of keys) {
    if (obj && Object.prototype.hasOwnProperty.call(obj, k) && obj[k] !== null && obj[k] !== undefined && obj[k] !== "") {
      return obj[k];
    }
  }
  return null;
}

function normalizeRow(r) {
  const row = Object.assign({}, r || {});

  // DATA/HORA
  const updatedRaw = pickFirst(row, [
    "updated_brt","updatedBrt","updated_brt_str","updated_at_brt",
    "updated_at","updatedAt","ts_brt","timestamp_brt","time_brt"
  ]);
  let parsed = parseUpdatedBrt(updatedRaw);

  if (!parsed && typeof updatedRaw === "string") {
    const d = new Date(updatedRaw.trim());
    if (!Number.isNaN(d.getTime())) {
      const brt = formatBRTFromDate(d);
      parsed = parseUpdatedBrt(brt);
      row.updated_brt = brt.slice(0, 16);
    }
  }

  if (!parsed) {
    const d = pickFirst(row, ["data","date","dt"]);
    const h = pickFirst(row, ["hora","time","hm"]);
    if (typeof d === "string" && typeof h === "string") {
      parsed = { date: d.trim(), time: h.trim().slice(0,5) };
      row.updated_brt = `${parsed.date} ${parsed.time}`;
    }
  }

  if (!parsed) {
    const brt = formatBRTFromDate(new Date());
    parsed = parseUpdatedBrt(brt);
    row.updated_brt = brt.slice(0, 16);
  }

  row.data = parsed.date;
  row.hora = parsed.time;

  // PRAZO
  const prazoTxt = pickFirst(row, ["prazo_txt","prazoTxt","prazo","prazo_str","prazoStr"]);
  if (typeof prazoTxt === "string" && prazoTxt.trim() && prazoTxt.trim() !== "—" && prazoTxt.trim() !== "-") {
    row.prazo = prazoTxt.trim();
  } else {
    const prazoDias = pickFirst(row, ["prazo_dias","prazoDias","prazo_d","eta_dias","etaDias"]);
    const p1 = formatPrazoDays(prazoDias);
    if (p1) row.prazo = p1;
    else {
      const prazoHoras = pickFirst(row, ["prazo_horas","prazoHoras","eta_horas","etaHoras","eta_hours","etaHours"]);
      const h = coerceNumber(prazoHoras);
      if (h !== null) row.prazo = formatPrazoDays(h / 24);
    }
  }
  if (!row.prazo) row.prazo = "—";

  // SIDE
  if (row.side) {
    const s = String(row.side).toUpperCase().trim();
    row.side = (s === "LONG" || s === "SHORT" || s === "NÃO ENTRAR" || s === "NAO ENTRAR") ? s.replace("NAO","NÃO") : s;
  }

  return row;
}

function normalizePayload(payload) {
  let items = null;
  if (Array.isArray(payload)) items = payload;
  else if (payload && typeof payload === "object") items = payload.items || payload.rows || payload.data || payload.result || null;
  if (!Array.isArray(items)) items = [];

  const norm = items.map(normalizeRow);

  let max = null;
  for (const r of norm) {
    const u = typeof r.updated_brt === "string" ? r.updated_brt.slice(0,16) : null;
    if (!u) continue;
    if (!max || u > max) max = u;
  }
  if (!max) max = formatBRTFromDate(new Date()).slice(0,16);

  return { items: norm, meta: { updated_brt: max, count: norm.length } };
}

function chooseFile(candidates) {
  for (const f of candidates) {
    const fp = path.join(DATA_DIR, f);
    if (fs.existsSync(fp)) return fp;
  }
  return null;
}

app.get("/api/pro", (req, res) => {
  const fp = chooseFile(["pro.json","pro_latest.json","pro_data.json","pro_snapshot.json"]);
  const raw = fp ? readJsonSafe(fp) : null;
  if (raw && raw.__error) return res.status(500).json({ ok:false, error: raw.__error, file: fp || null });
  const out = normalizePayload(raw);
  return res.json({ ok:true, source_file: fp ? path.basename(fp) : null, ...out });
});

app.get("/api/top10", (req, res) => {
  const fp = chooseFile(["top10.json","top10_latest.json","top10_data.json","top10_snapshot.json"]);
  const raw = fp ? readJsonSafe(fp) : null;

  let out;
  if (raw && !raw.__error) {
    out = normalizePayload(raw);
  } else {
    const proFp = chooseFile(["pro.json","pro_latest.json","pro_data.json","pro_snapshot.json"]);
    const proRaw = proFp ? readJsonSafe(proFp) : null;
    const proOut = normalizePayload(proRaw);

    const scored = proOut.items.slice().sort((a,b)=>{
      const aa = coerceNumber(a.assert || a.assert_pct || a.assert_percent) ?? 0;
      const bb = coerceNumber(b.assert || b.assert_pct || b.assert_percent) ?? 0;
      if (bb !== aa) return bb - aa;
      const ag = coerceNumber(a.ganho || a.ganho_pct || a.ganho_percent) ?? 0;
      const bg = coerceNumber(b.ganho || b.ganho_pct || b.ganho_percent) ?? 0;
      return bg - ag;
    });

    out = { items: scored.slice(0,10), meta: { updated_brt: proOut.meta.updated_brt, count: Math.min(10, scored.length) } };
  }

  return res.json({ ok:true, source_file: fp ? path.basename(fp) : null, ...out });
});

app.get("/api/audit", (req, res) => {
  const fp = chooseFile(["audit.json","audit_latest.json","audit_data.json"]);
  const raw = fp ? readJsonSafe(fp) : null;
  if (raw && raw.__error) return res.status(500).json({ ok:false, error: raw.__error, file: fp || null });
  if (!raw) return res.json({ ok:true, meta:{ updated_brt: formatBRTFromDate(new Date()).slice(0,16) }, items: [] });
  return res.json(raw);
});
const path = require("path");

// HEALTH (pra auditoria e deploy)
app.get("/health", (req, res) => {
  res.json({ ok: true, service: "autotrader-pro" });
});

// SERVIR HTML DO /dist
const DIST = path.join(__dirname, "dist");
app.use(express.static(DIST, { index: false }));

// URLs oficiais do painel
app.get("/", (req, res) => res.sendFile(path.join(DIST, "full.html")));
app.get("/full.html", (req, res) => res.sendFile(path.join(DIST, "full.html")));
app.get("/top10.html", (req, res) => res.sendFile(path.join(DIST, "top10.html")));

app.listen(PORT, () => {
  console.log(`[AUTOTRADER-PRO] API on :${PORT} | DATA_DIR=${DATA_DIR}`);
});
