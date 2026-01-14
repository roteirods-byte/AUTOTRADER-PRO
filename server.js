/**
 * AUTOTRADER-PRO — API/Servidor
 * Rotas obrigatórias:
 *  GET /health
 *  GET /api/pro
 *  GET /api/top10
 *  GET /
 *  GET /top10
 */
const express = require("express");
const path = require("path");
const fs = require("fs");
const morgan = require("morgan");

const app = express();

const PORT = process.env.PORT || 3000;
const DATA_DIR = process.env.DATA_DIR || path.join(__dirname, "data");
const DIST_DIR = path.join(__dirname, "dist");

app.disable("x-powered-by");
app.use(morgan("combined"));
app.use(express.static(DIST_DIR, { maxAge: "60s", etag: true }));

function safeReadJson(filePath, fallback) {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    return JSON.parse(raw);
  } catch (e) {
    return fallback;
  }
}

app.get("/health", (req, res) => {
  res.json({ ok: true, service: "autotrader-pro", ts: new Date().toISOString() });
});

app.get("/api/pro", (req, res) => {
  const p = path.join(DATA_DIR, "pro.json");
  const data = safeReadJson(p, { ultima_atualizacao: null, regra_gain_min: 3, status_volatilidade: "desconhecido", sinais: [] });
  res.setHeader("Cache-Control", "no-store");
  res.json(data);
});

app.get("/api/top10", (req, res) => {
  const p = path.join(DATA_DIR, "top10.json");
  const data = safeReadJson(p, { ultima_atualizacao: null, regra_gain_min: 3, status_volatilidade: "desconhecido", sinais: [] });
  res.setHeader("Cache-Control", "no-store");
  res.json(data);
});

// HTMLs (rotas obrigatórias)
app.get("/", (req, res) => res.sendFile(path.join(DIST_DIR, "index.html")));
app.get("/top10", (req, res) => res.sendFile(path.join(DIST_DIR, "top10.html")));

app.listen(PORT, "0.0.0.0", () => {
  console.log(`[AUTOTRADER-PRO] API on :${PORT} | DATA_DIR=${DATA_DIR}`);
});
