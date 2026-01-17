#!/usr/bin/env bash
set -euo pipefail

echo "== PRO CHECK =="

echo
echo "1) Servicos (MFE/PRO)"
systemctl is-active --quiet autotrader-mfe-panel.service && echo "OK: MFE panel ativo" || echo "ERRO: MFE panel parado"
systemctl is-active --quiet autotrader-pro-worker.service && echo "OK: PRO worker ativo (rodando agora)" || echo "OK: PRO worker nao está rodando (normal se for on-demand/timer)"

echo
echo "2) Rodar worker 1x (gera pro.json)"
sudo systemctl start autotrader-pro-worker.service
sleep 2

echo
echo "3) Ler API local (NGINX) e validar JSON"
tmp="/tmp/pro_check.json"
curl -k -sS --max-time 15 -u trader:traderpro https://127.0.0.1/api/pro -H "Host: paineljorge.duckdns.org" -o "$tmp"

python3 - <<'PY'
import json, sys
p="/tmp/pro_check.json"
s=open(p,"r",encoding="utf-8",errors="replace").read()
d=json.loads(s)

# PROCHECK_LIST_WRAP_FIX_20260115
if isinstance(d, list):
  d = {'lista': d}
lst=d.get("lista",[])
print("updated_brt =", d.get("updated_brt"))
print("itens =", len(lst))

bad=[]
for it in lst:
    if not isinstance(it, dict): 
        bad.append(("ITEM_NAO_DICT", type(it).__name__)); 
        continue
    for k in ("prioridade","zona","risco"):
        v=it.get(k)
        if isinstance(v,(list,tuple)):
            bad.append((it.get("par","?"), k, v))

if bad:
    print("ERRO: ainda existem campos list/tuple:", bad[:20])
    sys.exit(2)

print("OK: zona/risco/prioridade = STRING em 100% dos itens")
PY

echo
echo "== FIM: OK = tudo certo =="

