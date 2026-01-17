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

// anti-cache (garante que HTML/JSON nao fica “velho”)
app.disable("etag");
app.use((req, res, next) => {
  res.setHeader("Cache-Control", "no-store");
  next();
});


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
  const GAIN_MIN = 3;
  const ASSERT_MIN = 65;

  // 1) tenta ler top10.json
  const pTop = path.join(DATA_DIR, "top10.json");
  let data = safeReadJson(pTop, null);

  // 2) se top10.json estiver ausente/vazio, monta TOP10 a partir do pro.json (fallback)
  const precisaFallback = (!data || !Array.isArray(data.sinais) || data.sinais.length === 0);
  if (precisaFallback) {
    const pPro = path.join(DATA_DIR, "pro.json");
    const pro = safeReadJson(pPro, { updated_brt: null, meta: {}, sinais: [] });
    const sinais = Array.isArray(pro.sinais) ? pro.sinais : [];

    const num = (v) => {
      const n = Number(v);
      return Number.isFinite(n) ? n : 0;
    };
    const up = (v) => String(v || "").trim().toUpperCase();

    const top = sinais
      .map((x) => {
        const gain = num(x.ganho_pct ?? x.ganho ?? x.gain ?? x.ganho_perc);
        const asrt = num(x.assert_pct ?? x.assert ?? x.assert_perc);
        const side = up(x.side ?? x.sinal ?? x.side_src);
        return { x, gain, asrt, side };
      })
      .filter((r) => (r.side === "LONG" || r.side === "SHORT") && r.asrt >= ASSERT_MIN && r.gain >= GAIN_MIN)
      .sort((a, b) => (b.asrt - a.asrt) || (b.gain - a.gain))
      .slice(0, 10)
      .map((r) => r.x);

    data = {
      ultima_atualizacao: pro.updated_brt || pro.updated || null,
      regra_gain_min: GAIN_MIN,
      status_volatilidade: pro.status_volatilidade || "desconhecido",
      sinais: top
    };
  }

  res.setHeader("Cache-Control", "no-store");
  res.json(data);
});

// HTMLs (rotas obrigatórias)
app.get("/", (req, res) => res.sendFile(path.join(DIST_DIR, "index.html")));
app.get("/top10", (req, res) => res.sendFile(path.join(DIST_DIR, "top10.html")));

app.listen(PORT, "0.0.0.0", () => {
  console.log(`[AUTOTRADER-PRO] API on :${PORT} | DATA_DIR=${DATA_DIR}`);
});
