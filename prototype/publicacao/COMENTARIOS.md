# Comentários da demonstração

Cada comentário enviado em `demo.agentimo.propware.pt` é um ficheiro `comentarios/<id>.json` na loja Blob privada `agentimo-demo-comentarios` (`store_GYFcxqKXTos8HRMs`, equipa `crmware`, região `fra1`), ligada só à produção. A loja `agentimo-demo-comentarios-testes` (`store_b0xMnqzAYRIejilZ`) recebe só os testes das pré-visualizações.

Um ficheiro tem o texto, o contexto do ecrã e a hora de receção. Não tem nome, email, endereço IP nem agente do browser. Os registos de pedidos da Vercel, fora destes ficheiros, guardam dados técnicos como o endereço IP durante um período limitado.

## Ler

No painel da Vercel: projeto `agentimo-demo` → Storage → `agentimo-demo-comentarios`.

Pela CLI, com a loja de produção indicada:

    vercel blob list --prefix comentarios/
    vercel blob get comentarios/<id>.json

A lista mostra a data de cada ficheiro. O token da loja fica na Vercel: não se copia para o repositório.

## Retenção

Nenhum comentário fica guardado mais de 90 dias.

- **Responsável:** o dono do produto.
- **Quando:** de 30 em 30 dias a contar da publicação, e no dia em que a demonstração for retirada.
- **Como:** listar os ficheiros; apagar, um a um e pelo caminho exato, os que tenham mais de 60 dias (`vercel blob del comentarios/<id>.json`). Apagar aos 60 garante que nenhum chega aos 90 antes da revisão seguinte.
- **Ao retirar a demonstração:** apagar as duas lojas (`vercel blob delete-store`) e a regra da Firewall.
- **Registo:** um comentário na issue #12 com a data da revisão e o número de ficheiros apagados, sem o conteúdo.

Publicação: 5 de outubro de 2026.
Primeira revisão: 4 de novembro de 2026.

## Reversão da publicação

O deployment de produção anterior aos comentários é `agentimo-demo-idmh28ike-crmware.vercel.app` (`dpl_JAv4iqBXcZAvePqggChMMThTZTHm`, de 5 de outubro de 2026): a demonstração sem o botão «Comentar este ecrã».

    vercel rollback agentimo-demo-idmh28ike-crmware.vercel.app --scope crmware

A reversão repõe a aplicação e não toca nas lojas: os comentários já recebidos ficam guardados. O progresso dos visitantes não é afetado, porque o endereço e a versão dos dados são os mesmos.
