AUTOTRADER-PRO — FIX DEFINITIVO V2

POR QUE NÃO MUDOU (pelos seus prints):
- Você subiu arquivos no GitHub, mas o site (paineljorge.duckdns.org) NÃO está sendo atualizado automaticamente pelo GitHub.
- Resultado: o painel continua lendo o mesmo PRO/TOP10 antigo (DATA/HORA travadas em 2026-01-24 19:42 e PRAZO “—”).

O que este pacote resolve:
1) Atualiza server.js para normalizar DATA/HORA (BRT) e PRAZO.
2) Atualiza dist/full.html e dist/top10.html para usar "Atualizado" vindo do /api (não do relógio do PC).
3) Cria DEPLOY AUTOMÁTICO (GitHub Actions):
   - você NÃO usa SSH manual
   - ao dar push no GitHub, ele copia para a VM, reinicia e faz SELF-AUDIT
   - se PRAZO continuar vazio, o deploy falha (não “passa errado”)

ATIVAR (no GitHub, só cliques):
1) Repo AUTOTRADER-PRO → Settings
2) Secrets and variables → Actions
3) New repository secret (crie 4):
   - VM_HOST  (IP/host da VM)
   - VM_USER  (roteiro_ds)
   - VM_PORT  (22)
   - VM_SSH_KEY (chave privada)

Depois:
4) Suba estes arquivos no GitHub (mesmas pastas):
   - server.js
   - dist/full.html
   - dist/top10.html
   - dist/audit.html
   - deploy/deploy_vm.sh
   - .github/workflows/deploy_vm.yml

VALIDAR (sem SSH):
- GitHub → Actions → workflow "Deploy AUTOTRADER-PRO (VM)" precisa ficar VERDE.
- Abra:
  https://paineljorge.duckdns.org/full.html
  https://paineljorge.duckdns.org/top10.html
- Confirme:
  - Atualizado = agora (BRT)
  - DATA/HORA das linhas = agora
  - PRAZO não fica tudo “—”
