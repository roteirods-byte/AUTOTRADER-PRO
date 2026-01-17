#!/usr/bin/env bash
set -e

echo "== SERVICOS =="
sudo systemctl is-active autotrader-mfe-panel.service autotrader-pro-worker.timer || true

echo
echo "== TIMER =="
systemctl list-timers --all | grep -i autotrader-pro-worker || true

echo
echo "== API LOCAL =="
curl -k -sS --max-time 15 -u trader:traderpro https://127.0.0.1/api/pro -H "Host: paineljorge.duckdns.org" \
| python3 -c "import sys,json; d=json.load(sys.stdin); print('updated_brt=',d.get('updated_brt'),'itens=',len(d.get('lista',[])))"
