#!/usr/bin/env bash
set -euo pipefail

# === CONFIG ===
SERVICE_NAME="autotrader-pro"
BASE_URL="http://127.0.0.1:8095"
LOG_LAST="/var/log/autotrader-pro-audit_last.txt"
LOG_SUM="/var/log/autotrader-pro-audit.log"

ts_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ts_brt=$(TZ=America/Sao_Paulo date +"%Y-%m-%d %H:%M:%S")
status="OK"
details=""

# tenta descobrir DATA_DIR do service (se existir)
data_dir=""
envline=$(systemctl show -p Environment "$SERVICE_NAME" 2>/dev/null || true)
if echo "$envline" | grep -q "DATA_DIR="; then
  data_dir=$(echo "$envline" | sed -n 's/.*DATA_DIR=\([^ ]*\).*/\1/p' | tr -d '"')
fi
if [ -z "${data_dir}" ]; then
  data_dir="/home/roteiro_ds/AUTOTRADER-PRO/data"
fi

mkdir -p "$(dirname "$LOG_LAST")" "$(dirname "$LOG_SUM")" "$data_dir" || true

add() { details+="$1"$'\n'; }

add "==== AUDIT $ts_brt ===="

# health
health=$(curl -sS --max-time 3 "$BASE_URL/health" || true)
if echo "$health" | grep -q '"ok":true'; then
  add "health: OK"
else
  status="ERRO"
  add "health: ERRO (sem resposta ou inválido)"
fi

# api/pro
pro=$(curl -sS --max-time 5 "$BASE_URL/api/pro" || true)
pro_itens=$(python3 - <<'PY' <<<"$pro"
import json,sys
try:
  d=json.load(sys.stdin)
  sinais=d.get("lista") or d.get("sinais") or []
  print(len(sinais) if isinstance(sinais,list) else 0)
except Exception:
  print(-1)
PY
)
add "api/pro itens: $pro_itens"
if [ "$pro_itens" -lt 0 ]; then
  status="ERRO"
  add "api/pro: ERRO (json inválido)"
elif [ "$pro_itens" -eq 0 ]; then
  [ "$status" = "OK" ] && status="AVISO"
  add "AVISO: api/pro com 0 itens"
fi

# api/top10
top=$(curl -sS --max-time 5 "$BASE_URL/api/top10" || true)
top10_itens=$(python3 - <<'PY' <<<"$top"
import json,sys
try:
  d=json.load(sys.stdin)
  sinais=d.get("sinais") or d.get("lista") or []
  print(len(sinais) if isinstance(sinais,list) else 0)
except Exception:
  print(-1)
PY
)
add "api/top10 itens: $top10_itens"
if [ "$top10_itens" -lt 0 ]; then
  status="ERRO"
  add "api/top10: ERRO (json inválido)"
elif [ "$top10_itens" -ne 10 ]; then
  [ "$status" = "OK" ] && status="AVISO"
  add "AVISO: api/top10 não tem 10 itens (tem $top10_itens)"
fi

# escreve logs
{
  echo "$details"
  echo "STATUS_FINAL: $status"
} > "$LOG_LAST"

echo "$ts_brt | STATUS=$status | pro=$pro_itens | top10=$top10_itens" >> "$LOG_SUM"

# escreve JSON para o site
python3 - <<PY
import json, os
data = {
  "status": "$status",
  "ts": "$ts_iso",
  "ts_brt": "$ts_brt",
  "pro_itens": int("$pro_itens") if str("$pro_itens").lstrip("-").isdigit() else None,
  "top10_itens": int("$top10_itens") if str("$top10_itens").lstrip("-").isdigit() else None,
  "details": """$details""".strip()
}
out = os.path.join("$data_dir", "audit.json")
with open(out, "w", encoding="utf-8") as f:
  json.dump(data, f, ensure_ascii=False, indent=2)
os.chmod(out, 0o644)
print("OK: escreveu", out)
PY

exit 0
