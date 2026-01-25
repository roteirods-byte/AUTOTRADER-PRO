#!/usr/bin/env bash
set -euo pipefail

# =========================
# AUTOTRADER-PRO | Deploy VM (GitHub-linked)
# Objetivo: atualizar código + site público + reiniciar serviços + validar
# =========================

APP_DIR="${APP_DIR:-/home/roteiro_ds/AUTOTRADER-PRO}"
BRANCH="${BRANCH:-main}"

# Onde o Nginx serve o HTML público (se existir)
PUBLIC_DIR="${PUBLIC_DIR:-/var/www/paineljorge}"

# URL local do backend (usado na validação)
BASE_URL="${BASE_URL:-http://127.0.0.1:8095}"

TS="$(date +%Y%m%d_%H%M%S)"

echo "== DEPLOY AUTOTRADER-PRO =="
echo "APP_DIR:     ${APP_DIR}"
echo "BRANCH:      ${BRANCH}"
echo "PUBLIC_DIR:  ${PUBLIC_DIR}"
echo "BASE_URL:    ${BASE_URL}"
echo "TS:          ${TS}"
echo

cd "${APP_DIR}"

# 1) Atualizar código da VM para ficar IGUAL ao GitHub
echo "== GIT PULL (ff-only) =="
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "ERRO: ${APP_DIR} nao é um repo git"; exit 1; }

git fetch origin "${BRANCH}" --prune
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"
echo

# 2) Dependências do Node
echo "== NPM INSTALL =="
if [ -f package-lock.json ]; then
  npm ci --omit=dev
else
  npm install --omit=dev
fi
echo

# 3) Backup rápido dos HTML do repo (dist)
echo "== BACKUP dist/*.html (repo) =="
if [ -d "${APP_DIR}/dist" ]; then
  mkdir -p "${APP_DIR}/dist_bkp_${TS}"
  cp -a "${APP_DIR}/dist/"*.html "${APP_DIR}/dist_bkp_${TS}/" 2>/dev/null || true
  cp -a "${APP_DIR}/dist/favicon.ico" "${APP_DIR}/dist_bkp_${TS}/" 2>/dev/null || true
  echo "OK: ${APP_DIR}/dist_bkp_${TS}"
else
  echo "AVISO: dist/ nao existe no repo (ok se seu Nginx aponta para outro local)."
fi
echo

# 4) Atualizar HTML público (se o diretório existir)
echo "== SYNC HTML PUBLICO (Nginx) =="
if [ -d "${PUBLIC_DIR}" ] && [ -d "${APP_DIR}/dist" ]; then
  sudo mkdir -p "${PUBLIC_DIR}/bkp_${TS}"
  sudo cp -a "${PUBLIC_DIR}/"*.html "${PUBLIC_DIR}/bkp_${TS}/" 2>/dev/null || true
  sudo cp -a "${PUBLIC_DIR}/favicon.ico" "${PUBLIC_DIR}/bkp_${TS}/" 2>/dev/null || true
  sudo cp -a "${APP_DIR}/dist/"*.html "${PUBLIC_DIR}/"
  sudo cp -a "${APP_DIR}/dist/favicon.ico" "${PUBLIC_DIR}/" 2>/dev/null || true
  echo "OK: HTML publico atualizado em ${PUBLIC_DIR}"
else
  echo "AVISO: nao consegui sincronizar HTML publico."
  echo " - dist/ existe?  $( [ -d "${APP_DIR}/dist" ] && echo SIM || echo NAO )"
  echo " - PUBLIC_DIR existe? $( [ -d "${PUBLIC_DIR}" ] && echo SIM || echo NAO )"
fi
echo

# 5) Reiniciar serviços (API + WORKER + AUDIT)
echo "== RESTART SERVICES =="
sudo systemctl restart autotrader-pro.service || true
sudo systemctl restart autotrader-pro-worker.service 2>/dev/null || true
sudo systemctl restart autotrader-pro-worker.timer  2>/dev/null || true
sudo systemctl restart autotrader-pro-audit.service 2>/dev/null || true
sudo systemctl restart autotrader-pro-audit.timer   2>/dev/null || true
echo "OK: restart disparado"
echo

# 6) Validação (sem detalhes técnicos)
echo "== VALIDACAO AUTOMATICA (curta) =="
sleep 3

# 6.1) API respondendo?
curl -fsS "${BASE_URL}/api/health" >/dev/null 2>&1 || { echo "ERRO: API nao respondeu /api/health"; exit 1; }
echo "OK: /api/health"

# 6.2) PRO tem PRAZO preenchido?
python3 - <<'PY'
import json, sys, urllib.request
import os
base=os.environ.get("BASE_URL","http://127.0.0.1:8095")
with urllib.request.urlopen(base+"/api/pro") as r:
    d=json.loads(r.read().decode("utf-8","replace"))
rows=d.get("rows") or []
if not rows:
    print("ERRO: /api/pro sem rows"); sys.exit(1)
bad=[x for x in rows if str(x.get("prazo","")).strip() in ("", "-", "—", "None")]
# exigencia: pelo menos 80% com prazo (para nao travar se 1-2 vierem sem)
if len(bad) > max(2, int(len(rows)*0.2)):
    print(f"ERRO: PRAZO vazio em {len(bad)}/{len(rows)} linhas"); sys.exit(1)
print("OK: PRAZO preenchido (>=80%)")
PY

# 6.3) TOP10 tem PRAZO preenchido?
python3 - <<'PY'
import json, sys, urllib.request
import os
base=os.environ.get("BASE_URL","http://127.0.0.1:8095")
with urllib.request.urlopen(base+"/api/top10") as r:
    d=json.loads(r.read().decode("utf-8","replace"))
rows=d.get("rows") or []
if not rows:
    print("ERRO: /api/top10 sem rows"); sys.exit(1)
bad=[x for x in rows if str(x.get("prazo","")).strip() in ("", "-", "—", "None")]
if len(bad) > max(1, int(len(rows)*0.2)):
    print(f"ERRO: PRAZO vazio em {len(bad)}/{len(rows)} linhas"); sys.exit(1)
print("OK: PRAZO preenchido no TOP10 (>=80%)")
PY

echo "OK: VALIDACAO PASSOU"
echo
echo "FIM: deploy concluido."
