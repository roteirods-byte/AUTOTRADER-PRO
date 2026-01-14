# AUTOTRADER-PRO — Painel Único

Stack (conforme DOCX):
- Node.js + Express (API + HTML)
- Python 3 workers (gera JSON local)
- NGINX + DuckDNS + HTTPS (certbot)
- systemd

## Estrutura
```
/home/roteiro_ds/AUTOTRADER-PRO/
  server.js
  package.json
  dist/
    index.html
    top10.html
  engine/
    worker_pro.py
    providers/
  data/
    pro.json
    top10.json
```

## Rotas obrigatórias
- GET /health
- GET /api/pro
- GET /api/top10
- GET /
- GET /top10

## Rodar local (VM)
1) `cd /home/roteiro_ds/AUTOTRADER-PRO`
2) `npm install`
3) gerar JSON: `python3 -m engine.worker_pro`
4) subir API: `node server.js`
5) abrir: `http://IP_DA_VM:3000/`

## systemd (copiar/colar)
Arquivos prontos em: `deploy/systemd/`
- autotrader-pro.service
- autotrader-pro-worker.service
- autotrader-pro-worker.timer

## NGINX
Exemplo em: `deploy/nginx/autotrader-pro.conf`
