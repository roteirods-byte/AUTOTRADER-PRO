# Auditoria interna antes de liberar (V1)

1) Browser Console: **zero erro** (principal: “Unexpected token 'if'”)
2) Público:
   - `full.html` contém `AUTO_COLORIZE_V1`
   - `top10.html` contém `AUTO_COLORIZE_V1`
3) API:
   - `/api/pro` retorna `updated_brt` e cada linha com `prazo` preenchido
   - `/api/top10` idem
4) Se GitHub atualiza e o público não muda:
   - deploy GitHub→VM não está rodando (ou está apontando para pasta errada)
