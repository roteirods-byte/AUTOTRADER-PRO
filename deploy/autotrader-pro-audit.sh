#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="autotrader-pro"
BASE_URL="http://127.0.0.1:8095"
LOG_LAST="/var/log/autotrader-pro-audit_last.txt"
LOG_SUM="/var/log/autotrader-pro-audit.log"

EXPECT_PRO=78
EXPECT_TOP10=10
MAX_AGE_SEC=900  # 15 min

ts_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ts_brt=$(TZ=America/Sao_Paulo date +"%Y-%m-%d %H:%M:%S")
now=$(date +%s)

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
    curl -sS --connect-timeout 2 --max-time 15 "$BASE_URL$ep" -o "$tmp" || true

    n=$(python3 - <<'PY' "$tmp"
import json,sys
p=sys.argv[1]
try:
  raw=open(p,'rb').read()
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

check_age () {
  local f="$1" label="$2"
  if [ -f "$f" ]; then
    local mt age
    mt=$(stat -c %Y "$f" 2>/dev/null || echo 0)
    age=$(( now - mt ))
    add "$label idade_seg: $age"
    if [ "$age" -gt "$MAX_AGE_SEC" ]; then
      [ "$status" = "OK" ] && status="AVISO"
      add "AVISO: $label desatualizado (> ${MAX_AGE_SEC}s)"
    fi
  else
    [ "$status" = "OK" ] && status="AVISO"
    add "AVISO: $label não encontrado"
  fi
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
add "api/pro itens: $pro_itens (esperado: $EXPECT_PRO)"
if [ "$pro_itens" -lt 0 ]; then
  status="ERRO"
  add "api/pro: ERRO (json inválido)"
elif [ "$pro_itens" -eq 0 ]; then
  [ "$status" = "OK" ] && status="AVISO"
  add "AVISO: api/pro com 0 itens"
elif [ "$pro_itens" -ne "$EXPECT_PRO" ]; then
  [ "$status" = "OK" ] && status="AVISO"
  add "AVISO: api/pro não tem $EXPECT_PRO itens (tem $pro_itens)"
fi

# api/top10
top10_itens=$(count_list "/api/top10")
add "api/top10 itens: $top10_itens (esperado: $EXPECT_TOP10)"
if [ "$top10_itens" -lt 0 ]; then
  status="ERRO"
  add "api/top10: ERRO (json inválido)"
elif [ "$top10_itens" -ne "$EXPECT_TOP10" ]; then
  [ "$status" = "OK" ] && status="AVISO"
  add "AVISO: api/top10 não tem $EXPECT_TOP10 itens (tem $top10_itens)"
fi

# --- FIX_TOP10_FILE: manter data/top10.json sempre atualizado via endpoint ---
tmp_top10=$(mktemp)
curl -sS --connect-timeout 2 --max-time 15 "$BASE_URL/api/top10" -o "$tmp_top10" || true
ok_top10=$(python3 - <<'PY' "$tmp_top10"
import json,sys
p=sys.argv[1]
try:
  raw=open(p,'rb').read()
  if not raw.strip():
    print(0); raise SystemExit
  d=json.loads(raw.decode('utf-8', errors='strict'))
  s=d.get("lista") or d.get("sinais") or []
  print(1 if isinstance(s,list) and len(s)>0 else 0)
except Exception:
  print(0)
PY
)
if [ "$ok_top10" = "1" ]; then
  mv -f "$tmp_top10" "$data_dir/top10.json"
  chmod 644 "$data_dir/top10.json" || true
else
  rm -f "$tmp_top10" || true
fi

# --- SOURCES: resumo das exchanges usadas (lê src do pro.json/top10.json) ---
src_summary=$(python3 - <<'PY' "$data_dir/pro.json" "$data_dir/top10.json"
import json,sys
from collections import Counter, defaultdict

def load(p):
  try:
    return json.load(open(p,"r",encoding="utf-8"))
  except Exception:
    return {}

def summarize(d):
  lst = d.get("lista") or d.get("sinais") or []
  c1 = Counter()
  c4 = Counter()
  call = Counter()
  for it in lst:
    src = it.get("src")
    if isinstance(src, dict):
      s1 = src.get("1h") or src.get("1H") or ""
      s4 = src.get("4h") or src.get("4H") or ""
      if s1: c1[s1]+=1
      if s4: c4[s4]+=1
      for v in src.values():
        if isinstance(v,str) and v:
          call[v]+=1
    elif isinstance(src,str) and src:
      call[src]+=1
  def fmt(c):
    if not c: return ""
    return " ".join([f"{k}={v}" for k,v in c.most_common(6)])
  return fmt(c1), fmt(c4), fmt(call)

pro = load(sys.argv[1])
top = load(sys.argv[2])

p1,p4,pa = summarize(pro)
t1,t4,ta = summarize(top)

out=[]
if p1: out.append(f"src_pro_1h: {p1}")
if p4: out.append(f"src_pro_4h: {p4}")
if pa: out.append(f"src_pro_all: {pa}")
if t1: out.append(f"src_top10_1h: {t1}")
if t4: out.append(f"src_top10_4h: {t4}")
if ta: out.append(f"src_top10_all: {ta}")

print("\n".join(out).strip())
PY
)
if [ -n "$src_summary" ]; then
  add "$src_summary"
fi

# freshness (arquivos)
check_age "$data_dir/pro.json"   "pro.json"
check_age "$data_dir/top10.json" "top10.json"
check_age "$data_dir/audit.json" "audit.json"

# logs
{
  echo "$details"
  echo "STATUS_FINAL: $status"
} > "$LOG_LAST"

echo "$ts_brt | STATUS=$status | pro=$pro_itens | top10=$top10_itens" >> "$LOG_SUM"

# json para o site
python3 - <<PY
import json, os
def to_int(s):
  try: return int(s)
  except: return None

data = {
  "status": "$status",
  "ts": "$ts_iso",
  "ts_brt": "$ts_brt",
  "pro_itens": to_int("$pro_itens"),
  "top10_itens": to_int("$top10_itens"),
  "details": """$details""".strip()
}
out = os.path.join("$data_dir", "audit.json")
with open(out, "w", encoding="utf-8") as f:
  json.dump(data, f, ensure_ascii=False, indent=2)
os.chmod(out, 0o644)
print("OK: escreveu", out)
PY
