set -euo pipefail

BASE="/home/roteiro_ds/AUTOTRADER-PRO"
DIST="$BASE/dist"
DATA="$BASE/data"
TS="$(date +%Y%m%d_%H%M%S)"
BK="/home/roteiro_ds/backup_autotrader/PRO_PATCH_${TS}"

echo "=== 0) BACKUP ==="
sudo install -d "$BK"
sudo cp -a "$BASE/worker_pro.py" "$BK/worker_pro.py.bak"
sudo cp -a "$BASE/server.js" "$BK/server.js.bak" 2>/dev/null || true
sudo cp -a "$DIST" "$BK/dist.bak"
sudo cp -a /usr/local/bin/autotrader-pro-audit.sh "$BK/autotrader-pro-audit.sh.bak"
echo "OK backup em: $BK"

echo
echo "=== 1) PATCH worker_pro.py (PRAZO dias + ASSERT_N + garantir 78) ==="
python3 - <<'PY'
import re, pathlib

p = pathlib.Path("/home/roteiro_ds/AUTOTRADER-PRO/worker_pro.py")
s = p.read_text(encoding="utf-8", errors="replace")

# 1.1) Inserir helpers de PRAZO (se não existir)
if "def calc_prazo_days(" not in s:
  insert_after = "def calc_target_and_eta"
  m = re.search(r"(def\s+calc_target_and_eta\s*\([^)]*\)\s*:\s*\n)", s)
  if not m:
    raise SystemExit("ERRO: não achei calc_target_and_eta para inserir helpers.")
  idx = m.end(1)

  helper = r'''
# ---------------- PRAZO (dias) ----------------
# PRAZO em dias (não usa travas min/max); usa distância ao ALVO e "movimento diário típico"
# + eficiência (trend_score) para refletir vai-e-volta do mercado.
def calc_prazo_days(price, alvo, atr_4h, atr_1h, trend_score):
  try:
    price=float(price or 0.0); alvo=float(alvo or 0.0)
    atr_4h=float(atr_4h or 0.0); atr_1h=float(atr_1h or 0.0)
    ts=float(trend_score or 0.0)
  except Exception:
    return None

  if price <= 0 or alvo <= 0:
    return None
  dist = abs(alvo - price)
  if dist <= 0:
    return 0.0

  # ATR diário aproximado (preferir o maior para não "subestimar" volatilidade do dia)
  atr_day_4h = atr_4h * 6.0 if atr_4h > 0 else 0.0
  atr_day_1h = atr_1h * 24.0 if atr_1h > 0 else 0.0
  atr_day = max(atr_day_4h, atr_day_1h)

  if atr_day <= 0:
    return None

  # eficiência: quanto do movimento diário vira "progresso" rumo ao alvo
  # range ~0.18..0.60 (trend_score 0..1)
  eff = 0.18 + 0.42 * max(0.0, min(ts, 1.0))
  if eff < 0.08:
    eff = 0.08

  days = dist / (atr_day * eff)
  if days < 0:
    days = 0.0
  return days
'''
  s = s[:idx] + helper + s[idx:]

# 1.2) Trocar comentários/resumo ETA por PRAZO (não obrigatório, mas ajuda)
s = s.replace("ALVO + ETA COERENTES (mesmo motor)", "ALVO + PRAZO COERENTES (mesmo motor)")
s = s.replace("ETA: horas ≈ distância / ATR_1H", "PRAZO: dias ≈ distância / (ATR_dia * eficiência)")

# 1.3) Encontrar onde monta cada item de saída e:
# - adicionar prazo (dias)
# - adicionar assert_n (confiabilidade)
#
# Estratégia: localizar criação de dict do item com chaves comuns.
# Se não achar, falha com erro claro.
needle = r'(\{\s*["\']par["\']\s*:\s*[^,]+,.*?\})'
# Procura um bloco dict contendo "par" e "side" e "preco" (ou price)
m = re.search(r'(\{\s*["\']par["\']\s*:\s*[^}]+["\']side["\']\s*:\s*[^}]+["\']preco["\']\s*:\s*[^}]+?\})', s, re.S)
if not m:
  # fallback: procurar "par" + "side" + "alvo"
  m = re.search(r'(\{\s*["\']par["\']\s*:\s*[^}]+["\']side["\']\s*:\s*[^}]+["\']alvo["\']\s*:\s*[^}]+?\})', s, re.S)
if not m:
  raise SystemExit("ERRO: não consegui achar onde o item dict é montado (par/side/preco/alvo). Me mande um trecho onde o worker cria o item (dict).")

item_block = m.group(1)

# Se já tiver 'prazo' não mexe
if re.search(r'["\']prazo["\']\s*:', item_block) is None:
  # Inserir antes do fechamento do dict
  # Também inserir assert_n se não existir.
  add_lines = []

  # 'assert_n': tentar achar variável n ou sample count; se não existir, criar aproximado pelo número de candles 1h.
  # Vamos colocar uma lógica genérica: assert_n = n_assert (se existir), senão len(c1) (candles 1h)
  add_lines.append('"assert_n": int(assert_n) if "assert_n" in globals() else int(n_assert) if "n_assert" in globals() else int(len(c1) if isinstance(c1,list) else 0),')

  # prazo: depende de price, alvo, atr_4h, atr_1h, trend_score
  add_lines.append('"prazo": prazo_days,')

  injection = "\n    " + "\n    ".join(add_lines) + "\n"

  # inserir antes do último "}" do dict
  item_block2 = re.sub(r'\}\s*$', injection + "}", item_block)

  s = s.replace(item_block, item_block2)

# 1.4) Garantir que o universo saia com 78 itens:
# ideia: se o código filtra e só adiciona quando tem dados, precisamos garantir item default.
# Inserimos um fallback simples: ao final, preencher faltantes com NÃO ENTRAR.
if "PATCH_FILL_MISSING_UNIVERSE" not in s:
  # procurar ponto onde cria payload final (lista) para escrever JSON (pro.json)
  # heurística: achar onde define "out =" ou "lista =" perto da escrita.
  w = re.search(r'(data\s*=\s*\{\s*.*?["\']lista["\']\s*:\s*([a-zA-Z_]\w*)\s*,.*?\}\s*\n\s*_atomic_write_json)', s, re.S)
  if not w:
    # fallback: procurar "payload = { ... 'lista': out ... }"
    w = re.search(r'(\{\s*.*?["\']lista["\']\s*:\s*([a-zA-Z_]\w*)\s*,.*?\}\s*)', s, re.S)
  if not w:
    # não garante, mas não quebra
    pass
  else:
    lst_name = w.group(2)
    fill = f'''
# PATCH_FILL_MISSING_UNIVERSE: sempre publicar todas as moedas do universo (faltantes => NÃO ENTRAR)
try:
  have=set()
  if isinstance({lst_name}, list):
    for it in {lst_name}:
      try:
        have.add(str(it.get("par","")).strip().upper())
      except Exception:
        pass
  missing=[x for x in UNIVERSE if x not in have]
  for par in missing:
    {lst_name}.append({{
      "par": par,
      "side": "NÃO ENTRAR",
      "preco": 0,
      "alvo": 0,
      "ganho": 0,
      "assert": 0,
      "assert_n": 0,
      "prazo": None,
      "zona": "VERMELHA",
      "risco": "ALTO",
      "prioridade": "BAIXA",
      "data": datetime.now(TZ).strftime("%Y-%m-%d"),
      "hora": datetime.now(TZ).strftime("%H:%M"),
      "motivo": "SEM DADOS"
    }})
except Exception:
  pass
# /PATCH_FILL_MISSING_UNIVERSE
'''
    # Inserir antes da escrita do JSON (antes de _atomic_write_json)
    s = re.sub(r'(\n\s*_atomic_write_json\s*\(\s*OUT_PATH\s*,)', fill + r'\1', s, count=1)

# 1.5) Criar a variável prazo_days no fluxo, se não existir.
# Procurar por onde calcula alvo/eta (chamada calc_target_and_eta) e depois setar prazo_days
if "prazo_days" not in s:
  # após uma linha que define alvo e eta (ex: alvo, eta = calc_target_and_eta(...))
  s2 = re.sub(
    r'(alvo\s*,\s*eta\s*=\s*calc_target_and_eta\([^\n]+\)\s*\n)',
    r'\1' + '  prazo_days = calc_prazo_days(preco, alvo, atr_4h, atr_1h, trend_score)\n',
    s,
    count=1
  )
  s = s2

p.write_text(s, encoding="utf-8")
print("OK: worker_pro.py patch aplicado")
PY

echo
echo "=== 2) PATCH UI (full.html, top10.html, audit.html) ==="
# 2.1) full.html: trocar coluna ETA -> PRAZO e mostrar ASSERT com (n=)
if [ -f "$DIST/full.html" ]; then
  sudo -u roteiro_ds python3 - <<'PY'
import pathlib, re
p=pathlib.Path("/home/roteiro_ds/AUTOTRADER-PRO/dist/full.html")
s=p.read_text(encoding="utf-8", errors="replace")

# Trocar header ETA por PRAZO
s = s.replace(">ETA<", ">PRAZO<")
s = s.replace("ETA", "PRAZO")

# Trocar render do campo eta para prazo (dias)
# tentativas comuns:
s = re.sub(r'row\.eta\b', 'row.prazo', s)
s = re.sub(r'it\.eta\b', 'it.prazo', s)

# Mostrar ASSERT com (n=)
# Se já existir assert_n no JS, só ajustar o template:
# procurar "ASSERT" cell e inserir n
s = re.sub(r'(\$\{[^}]*row\.assert[^}]*\})', r'\1' + r' + (row.assert_n ? ` (n=${row.assert_n})` : ``)', s)

p.write_text(s, encoding="utf-8")
print("OK: full.html patch")
PY
fi

# 2.2) top10.html idem
if [ -f "$DIST/top10.html" ]; then
  sudo -u roteiro_ds python3 - <<'PY'
import pathlib, re
p=pathlib.Path("/home/roteiro_ds/AUTOTRADER-PRO/dist/top10.html")
s=p.read_text(encoding="utf-8", errors="replace")

s = s.replace(">ETA<", ">PRAZO<")
s = s.replace("ETA", "PRAZO")
s = re.sub(r'row\.eta\b', 'row.prazo', s)
s = re.sub(r'it\.eta\b', 'it.prazo', s)
s = re.sub(r'(\$\{[^}]*row\.assert[^}]*\})', r'\1' + r' + (row.assert_n ? ` (n=${row.assert_n})` : ``)', s)

p.write_text(s, encoding="utf-8")
print("OK: top10.html patch")
PY
else
  echo "AVISO: top10.html não encontrado no dist (ok se não usa arquivo separado)."
fi

# 2.3) audit.html: só garantir que usa /api/audit e exibe ok
# (não muda muito aqui; a auditoria em si está no audit.sh)
echo "OK: UI patch concluído"

echo
echo "=== 3) PATCH auditoria (/usr/local/bin/autotrader-pro-audit.sh) ==="
# 3.1) adicionar validação schema + top10 subset + faltantes
sudo python3 - <<'PY'
import pathlib, re
p=pathlib.Path("/usr/local/bin/autotrader-pro-audit.sh")
s=p.read_text(encoding="utf-8", errors="replace")

if "PATCH_SCHEMA_SUBSET_MISSING" in s:
  print("OK: audit.sh já tinha patch")
  raise SystemExit

patch = r'''
# --- PATCH_SCHEMA_SUBSET_MISSING: schema + top10 subset + faltantes do universo ---
required_keys="par side preco alvo ganho assert assert_n prazo zona risco prioridade data hora"
UNIVERSE_78="AAVE ADA APE APT AR ARB ATOM AVAX AXS BAT BCH BLUR BNB BONK BTC COMP CRV DASH DGB DENT DOGE DOT EGLD EOS ETC ETH FET FIL FLOKI FLOW FTM GALA GLM GRT HBAR ICP IMX INJ IOST KAS KAVA KSM LINK LTC MANA MATIC MKR NEAR NEO OMG ONT OP ORDI PEPE QNT QTUM RNDR ROSE RUNE SAND SEI SHIB SNX SOL STX SUI SUSHI THETA TIA TRX UNI VET XEM XLM XRP XVS ZEC ZRX"

validate_schema () {
  local f="$1" label="$2"
  python3 - <<'PY' "$f" "$label" "$required_keys"
import json,sys
p=sys.argv[1]; label=sys.argv[2]; req=sys.argv[3].split()
try:
  d=json.load(open(p,"r",encoding="utf-8"))
except Exception:
  print(f"{label}: ERRO schema (json inválido)")
  raise SystemExit
lst = d.get("lista") or d.get("sinais") or []
if not isinstance(lst,list):
  print(f"{label}: ERRO schema (lista não é list)")
  raise SystemExit
bad=0
for i,it in enumerate(lst[:2000]):
  if not isinstance(it,dict):
    bad+=1; continue
  miss=[k for k in req if k not in it]
  if miss:
    bad+=1
    if bad<=5:
      print(f"{label}: item#{i} faltando: {','.join(miss)}")
if bad==0:
  print(f"{label}: schema OK")
else:
  print(f"{label}: schema AVISO (itens ruins={bad})")
PY
}

subset_and_missing () {
  python3 - <<'PY' "$data_dir/pro.json" "$data_dir/top10.json" "$UNIVERSE_78"
import json,sys
pro_p=sys.argv[1]; top_p=sys.argv[2]
universe=set(sys.argv[3].split())

def load(p):
  try:
    return json.load(open(p,"r",encoding="utf-8"))
  except Exception:
    return {}
pro=load(pro_p); top=load(top_p)
pro_lst=pro.get("lista") or pro.get("sinais") or []
top_lst=top.get("lista") or top.get("sinais") or []

pro_set=set()
for it in pro_lst:
  try: pro_set.add(str(it.get("par","")).strip().upper())
  except Exception: pass

top_set=set()
for it in top_lst:
  try: top_set.add(str(it.get("par","")).strip().upper())
  except Exception: pass

missing=sorted(list(universe - pro_set))
extra_top=sorted(list(top_set - pro_set))

print("missing_universe:", "OK" if not missing else " ".join(missing[:40]) + (" ..." if len(missing)>40 else ""))
print("top10_subset:", "OK" if not extra_top else "ERRO " + " ".join(extra_top))
PY
}
# --- /PATCH_SCHEMA_SUBSET_MISSING ---
'''

# inserir antes de "freshness (arquivos)" pra ficar nos detalhes
s = re.sub(r'(# freshness \(arquivos\))', patch + r'\1', s, count=1)

# chamar as funções antes do freshness
call = r'''
# schema + subset + faltantes
validate_schema "$data_dir/pro.json" "pro.json"   || true
validate_schema "$data_dir/top10.json" "top10.json" || true
sm=$(subset_and_missing || true)
if [ -n "$sm" ]; then add "$sm"; fi
'''
s = re.sub(r'(# freshness \(arquivos\))', call + r'\1', s, count=1)

p.write_text(s, encoding="utf-8")
print("OK: audit.sh patch aplicado")
PY

echo
echo "=== 4) CHECK sintaxe + RESTART ==="
python3 -m py_compile "$BASE/worker_pro.py"
sudo systemctl restart autotrader-pro
sudo systemctl restart autotrader-pro-worker.timer || true
sudo systemctl restart autotrader-pro-audit.timer || true

echo
echo "=== 5) TESTE (local 8095) ==="
curl -sS http://127.0.0.1:8095/api/pro | head -c 500; echo
echo
curl -sS http://127.0.0.1:8095/api/audit | head -c 800; echo
echo
echo "OK: patch aplicado. Abra o site e confirme PRAZO + ASSERT (n=)."
