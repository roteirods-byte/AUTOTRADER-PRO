#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-https://paineljorge.duckdns.org}"
FULL="$BASE_URL/full.html"
TOP10="$BASE_URL/top10.html"

echo "== PRO CHECK PUBLIC =="
echo "BASE_URL: $BASE_URL"
date
echo

echo "== 1) HTML PUBLICO: marcador do patch =="
echo "-- full.html:"
if curl -fsS "$FULL" | grep -q "AUTO_COLORIZE_V1"; then
  echo "OK: full.html tem AUTO_COLORIZE_V1"
else
  echo "ERRO: full.html NAO tem AUTO_COLORIZE_V1"
  echo "=> GitHub != site (deploy nao aconteceu / cache / caminho errado)."
fi
echo
echo "-- top10.html:"
if curl -fsS "$TOP10" | grep -q "AUTO_COLORIZE_V1"; then
  echo "OK: top10.html tem AUTO_COLORIZE_V1"
else
  echo "ERRO: top10.html NAO tem AUTO_COLORIZE_V1"
fi
echo

echo "== 2) API: /api/pro e /api/top10 devem conter PRAZO e updated_brt =="
echo "-- /api/pro (1 item - chaves):"
curl -fsS "$BASE_URL/api/pro" | python3 - <<'PY'
import sys, json
d=json.load(sys.stdin)
rows=d.get("rows") or d.get("data") or d.get("items") or []
print("ok:", d.get("ok", True))
print("updated_brt:", d.get("updated_brt") or d.get("updated_brazil") or d.get("updated"))
print("rows:", len(rows))
if rows:
    r=rows[0]
    keys=["prazo","prazo_dias","prazoDias","data","hora","data_brt","hora_brt"]
    print({k:r.get(k) for k in keys if k in r})
PY
echo

echo "-- /api/top10 (1 item - chaves):"
curl -fsS "$BASE_URL/api/top10" | python3 - <<'PY'
import sys, json
d=json.load(sys.stdin)
rows=d.get("rows") or d.get("data") or d.get("items") or []
print("ok:", d.get("ok", True))
print("updated_brt:", d.get("updated_brt") or d.get("updated_brazil") or d.get("updated"))
print("rows:", len(rows))
if rows:
    r=rows[0]
    keys=["prazo","prazo_dias","prazoDias","data","hora","data_brt","hora_brt"]
    print({k:r.get(k) for k in keys if k in r})
PY
echo

echo "== 3) Conclusao =="
echo "- Se faltar AUTO_COLORIZE_V1 no publico: o servidor nao publicou a versao nova."
echo "- Se faltar PRAZO / DATA / HORA na API: aplicar patches em PATCHES/."
