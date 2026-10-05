# Comentários da demonstração

Cada comentário enviado em `demo.agentimo.propware.pt` é um ficheiro `comentarios/<id>.json` na loja Blob privada `agentimo-demo-comentarios` (`store_GYFcxqKXTos8HRMs`, equipa `crmware`, região `fra1`), ligada só à produção. A loja `agentimo-demo-comentarios-testes` (`store_b0xMnqzAYRIejilZ`) recebe só os testes das pré-visualizações.

Um ficheiro tem o texto, o contexto do ecrã e a hora de receção. Não são pedidos nem acrescentados campos de identificação do visitante. O texto livre pode conter informação que a pessoa introduza. Os registos de pedidos da Vercel, fora destes ficheiros, guardam dados técnicos como o endereço IP durante um período limitado.

## Ler e apagar

Há duas lojas com nomes parecidos. Antes de ler, e sobretudo antes de apagar, confirmar que a loja é a de produção: `agentimo-demo-comentarios`, com o identificador `store_GYFcxqKXTos8HRMs`. A que termina em `-testes` (`store_b0xMnqzAYRIejilZ`) não tem comentários reais.

**No painel da Vercel (caminho normal):** projeto `agentimo-demo` → Storage → `agentimo-demo-comentarios`. O nome e o identificador da loja aparecem no topo da página; confirmar ambos. Os ficheiros estão na pasta `comentarios/`, com a data de cada um, e podem ser abertos e apagados um a um.

**Pela CLI (alternativa):** a CLI escolhe a loja pelo token que recebe, por isso o token tem de ser o de produção. Numa pasta ligada ao projeto (`vercel link --scope crmware --project agentimo-demo`):

    umask 077
    vercel env pull /tmp/agentimo-producao.env --environment production --scope crmware
    TOKEN="$(grep '^BLOB_READ_WRITE_TOKEN=' /tmp/agentimo-producao.env | cut -d= -f2- | tr -d '"')"

    # Confirmar a loja antes de qualquer outro comando: tem de mostrar GYFcxqKXTos8HRMs
    # (sem contar maiúsculas e minúsculas). Se mostrar b0xMnqzAYRIejilZ, é a loja de testes: parar.
    echo "$TOKEN" | cut -d_ -f4

    vercel blob list --prefix comentarios/ --rw-token "$TOKEN"
    vercel blob get comentarios/<id>.json --rw-token "$TOKEN"
    vercel blob del comentarios/<id>.json --rw-token "$TOKEN"

    rm /tmp/agentimo-producao.env

- Apagar sempre um ficheiro de cada vez, pelo caminho exato. Nunca usar `vercel blob empty-store` na loja de produção, exceto ao retirar a demonstração.
- O token dá acesso de leitura e escrita à loja. Não se copia para o repositório nem para mensagens, e o ficheiro temporário apaga-se no fim.

## Retenção

Nenhum comentário fica guardado mais de 90 dias.

- **Responsável:** o dono do produto.
- **Quando:** de 30 em 30 dias a contar da publicação, e no dia em que a demonstração for retirada.
- **Como:** confirmar que a loja é a de produção, como descrito acima; listar os ficheiros; apagar, um a um e pelo caminho exato, os que tenham mais de 60 dias. Apagar aos 60 garante que nenhum chega aos 90 antes da revisão seguinte.
- **Ao retirar a demonstração:** apagar as duas lojas (`vercel blob delete-store`) e a regra da Firewall.
- **Registo:** um comentário na issue #12 com a data da revisão e o número de ficheiros apagados, sem o conteúdo.

Publicação: 5 de outubro de 2026.
Primeira revisão: 4 de novembro de 2026.

## Limites conhecidos

A função é pública e não distingue quem escreve. O que existe são travões, não uma proteção suficiente contra abuso: o limite da Firewall (5 pedidos por minuto por IP), o tamanho máximo do pedido e um teto de cerca de 500 comentários guardados.

- **O teto pode ser esgotado de propósito.** Quem enviar comentários válidos sem parar enche a loja: um só endereço IP demora cerca de 100 minutos, vários demoram menos. O custo de armazenamento fica limitado, mas a partir daí os visitantes reais veem «De momento não é possível receber opiniões» e nada avisa disso.
- **Como se nota:** a loja tem perto de 500 ficheiros, muitos recebidos em pouco tempo e sem sentido.
- **Como se recupera:** confirmar que a loja é a de produção e apagar os ficheiros sem valor, um a um; a função volta a aceitar comentários assim que o número desce.
- **Decisão do dono do produto, de 5 de outubro de 2026:** aceitar este risco residual para esta demonstração, enviada a poucas pessoas. A decisão vale só neste contexto: não é uma avaliação de que os travões acima chegam contra abuso, e não se aplica ao produto nem a uma demonstração divulgada mais amplamente, casos em que tem de ser reavaliada. Ver o número de ficheiros faz parte de cada revisão de retenção.

## Reversão da publicação

O deployment de produção anterior aos comentários é `agentimo-demo-idmh28ike-crmware.vercel.app` (`dpl_JAv4iqBXcZAvePqggChMMThTZTHm`, de 5 de outubro de 2026): a demonstração sem o botão «Comentar este ecrã».

    vercel rollback agentimo-demo-idmh28ike-crmware.vercel.app --scope crmware

A reversão repõe a aplicação e não toca nas lojas: os comentários já recebidos ficam guardados. O progresso dos visitantes não é afetado, porque o endereço e a versão dos dados são os mesmos.
