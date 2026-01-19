#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="autotrader-pro"
BASE_URL="http://127.0.0.1:8095"
LOG_LAST="/var/log/autotrader-pro-audit_last.txt"
LOG_SUM="/var/log/autotrader-pro-audit.log"

ts_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ts_brt=$(TZ=America/Sao_Paulo date +"%Y-%m-%d %H:%M:%S")
status="OK"
details=""

data_dir=""
envline=$(systemctl show -p Environment "$SERVICE_NAME" 2>/dev/null || true)
if echo "$envline" | grep -q "DATA_DIR="; then
  data_dir=$(echo "$envline" | sed -n 's/.*DATA_DIR=\([^ ]*\).*/\1/p' | tr -d '"')
fi
[ -z "${data_dir}" ] && data_dir="/home/roteiro_ds/AUTOTRADER-PRO/data"

mkdir -p "$(dirname "$LOG_LAST")" "$(dirname "$LOG_SUM")" "$data_dir" || true
add(){ details+="$1"$'\n'; }

count_list () {
  # $1 = endpoint (/api/pro ou /api/top10)
  # tenta 3x para evitar pegar JSON “no meio da escrita”
  local ep="$1" raw="" n=-1 i=1
  for i in 1 2 3; do
    raw=$(curl -sS --max-time 5 "$BASE_URL$ep" || true)
    n=$(python3 - <<'PY' <<<"$raw"
import json,sys
try:
  d=json.load(sys.stdin)
  s=d.get("lista") or d.get("sinais") or []
  print(len(s) if isinstance(s,list) else 0)
except Exception:
  print(-1)
PY
)
    [[ "$n" =~ ^-?[0-9]+$ ]] || n=-1
    if [ "$n" -ge 0 ]; then
      echo "$n"
      return 0
    fi
    sleep 0.4
  done
  echo "-1"
  return 0
}

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
pro_itens=$(count_list "/api/pro")
add "api/pro itens: $pro_itens"
if [ "$pro_itens" -lt 0 ]; then
  status="ERRO"
  add "api/pro: ERRO (json inválido)"
elif [ "$pro_itens" -eq 0 ]; then
  [ "$status" = "OK" ] && status="AVISO"
  add "AVISO: api/pro com 0 itens"
fi

# api/top10
top10_itens=$(count_list "/api/top10")
add "api/top10 itens: $top10_itens"
if [ "$top10_itens" -lt 0 ]; then
  status="ERRO"
  add "api/top10: ERRO (json inválido)"
elif [ "$top10_itens" -ne 10 ]; then
  [ "$status" = "OK" ] && status="AVISO"
  add "AVISO: api/top10 não tem 10 itens (tem $top10_itens)"
fi

{
  echo "$details"
  echo "STATUS_FINAL: $status"
} > "$LOG_LAST"

echo "$ts_brt | STATUS=$status | pro=$pro_itens | top10=$top10_itens" >> "$LOG_SUM"

python3 - <<PY
import json, os
data = {
  "status": "$status",
  "ts": "$ts_iso",
  "ts_brt": "$ts_brt",
  "pro_itens": int("$pro_itens"),
  "top10_itens": int("$top10_itens"),
  "details": """$details""".strip()
}
out = os.path.join("$data_dir", "audit.json")
with open(out, "w", encoding="utf-8") as f:
  json.dump(data, f, ensure_ascii=False, indent=2)
os.chmod(out, 0o644)
print("OK: escreveu", out)
PY
