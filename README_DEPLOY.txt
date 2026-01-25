PASSO A PASSO (sem SSH manual)

1) No GitHub do AUTOTRADER-PRO:
   - Settings -> Secrets and variables -> Actions -> New repository secret
   - Crie estes 4 secrets:
     VM_HOST   = IP da VM (ex: 34.x.x.x)
     VM_USER   = roteiro_ds
     VM_PORT   = 22
     VM_SSH_KEY= chave privada (SSH) do deploy

2) Copie estes arquivos do zip para o repo (main):
   - .github/workflows/deploy_vm.yml
   - deploy/deploy_vm.sh
   - dist/full.html, dist/top10.html, dist/audit.html (se estiverem no zip)
   - server.js (se estiver no zip)

3) Vá em Actions -> Deploy VM -> Run workflow (ou faça um commit e ele roda sozinho).

4) Validação visual (o que você precisa ver):
   - Painel PRO (full.html): PRAZO preenchido (não “—” em tudo).
   - Painel TOP10: PRAZO preenchido.
   - “Atualizado:” igual/consistente com a última auditoria.
   - Auditoria não mostra “pro.json desatualizado”.

Se falhar, o Actions vai mostrar “ERRO” e não aplica deploy incompleto.
