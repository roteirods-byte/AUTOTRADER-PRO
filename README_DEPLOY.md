# AUTOTRADER-PRO — Correção PRAZO + DATA/HORA + Auditoria Pública (V1)

Problema visto nos prints:
- Você atualizou arquivos (GitHub/zip), mas **o painel público não mudou**.
- Isso acontece quando **o servidor (VM/Nginx/Node) NÃO está publicando a versão nova**.
- Também explica: TOP10 com PRAZO e PRO sem PRAZO (API diferente / campos diferentes).

Este pacote inclui:
1) **Auditoria pública** (prova se o público está servindo a versão nova)
2) **Patches** para padronizar **PRAZO + DATA/HORA (BRT)** na API
3) **Deploy automático GitHub → VM** (sem SSH manual)

Arquivos:
- `bin/pro_check_public.sh`
- `PATCHES/server.js.patch`
- `PATCHES/snapshot_top10.py.patch`
- `.github/workflows/deploy_autotrader_pro.yml`
- `CHECKLIST_INTERNA.md`
