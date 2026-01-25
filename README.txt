AUTOTRADER-PRO — FIX (V1) — PRAZO + DATA/HORA (PRO e TOP10)

O que este FIX resolve
1) PRAZO no /api/pro: o campo `prazo` é preenchido (se houver base: ETA/prazo_dias etc). Não fica em branco.
2) DATA/HORA das linhas: forçadas para bater com `updated_brt` (BRT). Assim PRO e TOP10 não ficam com data/hora antiga nas colunas.
3) TOP10: se não existir top10.json, ele passa a ser derivado do PRO (sem divergência) e também normalizado.

Arquivos
- server.js (substituir no repo AUTOTRADER-PRO)

Como aplicar (SEM SSH) — GitHub Web
1) Abra o repo AUTOTRADER-PRO
2) Abra o arquivo `server.js`
3) Clique em Edit (lápis)
4) Apague tudo e cole o `server.js` deste ZIP
5) Commit em `main`

Validação no navegador (após seu deploy/pipeline)
- Abra full.html e top10.html
- Recarregue com CTRL+F5
- Confirme:
  - PRAZO aparece no PRO
  - DATA/HORA nas linhas batem com “Atualizado: …” do topo

Se o PRAZO continuar "—" mesmo assim:
=> o `pro.json` NÃO está trazendo nenhum campo de prazo/ETA. Aí o próximo passo é ajustar o worker_pro.py para gravar `prazo_dias` ou `ETA`.
