#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/home/roteiro_ds/AUTOTRADER-PRO}"
SERVICE_APP="${SERVICE_APP:-autotrader-pro.service}"
SERVICE_WORKER="${SERVICE_WORKER:-autotrader-pro-worker.service}"
TIMER_WORKER="${TIMER_WORKER:-autotrader-pro-worker.timer}"

echo "== DEPLOY: ${APP_DIR} =="
cd "${APP_DIR}"

ts="$(date +%Y%m%d_%H%M%S)"
mkdir -p "_bkp/${ts}"
cp -a "server.js" "_bkp/${ts}/server.js" || true
cp -a "dist/full.html" "_bkp/${ts}/full.html" || true
cp -a "dist/top10.html" "_bkp/${ts}/top10.html" || true
cp -a "dist/audit.html" "_bkp/${ts}/audit.html" || true
echo "Backup OK: _bkp/${ts}"

echo "Restart services..."
sudo systemctl restart "${SERVICE_APP}"
sudo systemctl restart "${SERVICE_WORKER}" || true
sudo systemctl restart "${TIMER_WORKER}" || true

echo "== SELF-AUDIT (falha se PRAZO continuar vazio) =="
node - <<'NODE'
const http = require("http");
function get(p){return new Promise((res,rej)=>{http.get({host:"127.0.0.1",port:8095,path:p},r=>{let d="";r.on("data",c=>d+=c);r.on("end",()=>{try{res(JSON.parse(d))}catch(e){rej(e)}})}).on("error",rej);});}
(async()=>{
  const pro = await get("/api/pro?ts="+Date.now());
  const top = await get("/api/top10?ts="+Date.now());
  const okPro = !!(pro && pro.ok && pro.meta && pro.meta.updated_brt);
  const okTop = !!(top && top.ok && top.meta && top.meta.updated_brt);
  const hasPrazo = (pro.items||[]).some(x => x && x.prazo && x.prazo !== "—");
  console.log("PRO:", okPro ? pro.meta.updated_brt : "FAIL", "PRAZO:", hasPrazo);
  console.log("TOP10:", okTop ? top.meta.updated_brt : "FAIL");
  if (!okPro || !okTop) process.exit(2);
  if (!hasPrazo) process.exit(3);
  process.exit(0);
})().catch(e=>{console.error("AUDIT FAIL:", e && e.message ? e.message : e); process.exit(4);});
NODE
echo "DEPLOY OK"
