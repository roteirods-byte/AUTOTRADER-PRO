#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="autotrader-pro"
BASE_URL="http://127.0.0.1:8095"
LOG_LAST="/var/log/autotrader-pro-audit_last.txt"
LOG_SUM="/var/log/autotrader-pro-audit.log"

EXPECT_PRO=78

ts_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ts_brt=$(TZ=America/Sao_Paulo date +"%Y-%m-%d %H:%M:%S")
status="OK"
details=""

# DATA_DIR do service (se existir), senão fallback
data_dir=""
envline=$(systemctl show -p Environment "$SERVICE_NAME" 2>/dev/null || true)
if echo "$envline" | grep -q "DATA_DIR="; then
  data_dir=$(echo "$envline" | sed -n 's/.*DATA_DIR=\([^ ]*\).*/\1/p' | tr -d '"')
fi
[ -z "${data_dir}" ] && data_dir="/home/roteiro_ds/AUTOTRADER-PRO/data"

mkdir -p "$(dirname "$LOG_LAST")" "$(dirname "$LOG_SUM")" "$data_dir" || true
add(){ details+="$1"$'\n'; }

count_list () {
  local ep="$1" tmp="" n=-1 i=1
  for i in 1 2 3; do
    tmp="$(mktemp)"
    # timeout maior (evita JSON cortado)
    curl -sS --connect-timeout 2 --max-time 15 "$BASE_URL$ep" -o "$tmp" || true

    n=$(python3 - <<'PY' "$tmp"
import json,sys,os
p=sys.argv[1]
try:
  raw=open(p,'rb').read()
  # se veio vazio, falha
  if not raw.strip():
    print(-1); raise SystemExit
  d=json.loads(raw.decode('utf-8', errors='strict'))
  s=d.get("lista") or d.get("sinais") or []
  print(len(s) if isinstance(s,list) else 0)
except Exception:
  print(-1)
PY
)
    rm -f "$tmp" || true

    [[ "$n" =~ ^-?[0-9]+$ ]] || n=-1
    if [ "$n" -ge 0 ]; then
      echo "$n"
      return 0
    fi
    sleep 0.6
  done
  echo "-1"
  return 0
}

add "==== AUDIT $ts_brt ===="

# health
health=$(curl -sS --connect-timeout 2 --max-time 5 "$BASE_URL/health" || true)
if echo "$health" | grep -q '"ok":true'; then
  add "health: OK"
else
  status="ERRO"
  add "health: ERRO (sem resposta ou inválido)"
fi

# api/pro
pro_itens=$(count_list "/api/pro")
add "api/pro itens: $pro_itens"
  if [ "$pro_itens" -ge 0 ] && [ "$pro_itens" -ne "$EXPECT_PRO" ]; then
    [ "$status" = "OK" ] && status="AVISO"
    add "AVISO: api/pro não tem $EXPECT_PRO itens (tem $pro_itens)"
  fi
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

# logs
{
  echo "$details"
  echo "STATUS_FINAL: $status"
} > "$LOG_LAST"

echo "$ts_brt | STATUS=$status | pro=$pro_itens | top10=$top10_itens" >> "$LOG_SUM"

# json para o site
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
