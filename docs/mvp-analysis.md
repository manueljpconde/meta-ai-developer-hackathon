# Análise e definição do MVP

Data: 28 de setembro de 2026

Revisão: 4 de outubro de 2026 (secções 4 a 8, alinhadas com as especificações de desenho e as issues #1, #2 e #3)

Estado: hipótese de produto para validação comercial

## Contexto

Esta análise procura definir o menor MVP comercialmente testável para agentes imobiliários independentes em Portugal.

Baseia-se em:

- Uma conversa com um diretor de uma associação portuguesa do setor imobiliário sobre comissões, despesas, impostos, Segurança Social e dificuldade em perceber o rendimento líquido real;
- Pesquisa recente sobre os principais problemas dos agentes imobiliários em Portugal;
- Pesquisa de soluções e repositórios adjacentes, incluindo [Tuttle](https://github.com/tuttle-dev/tuttle), [FlowBooks](https://github.com/MuhammadTanveerAbbas/flowbooks), [InsulaCRM](https://github.com/InsulaCRM/InsulaCRM) e [Open-Akquise](https://github.com/echtjetztki/Open-Immo-Akquise);
- A hipótese de preço de 15 EUR por mês ou 150 EUR por ano, sem plano gratuito.

O objetivo é testar se os agentes pagam por um produto que lhes permita perceber se o negócio está saudável, quanto esperam receber e quanto desse dinheiro é efetivamente deles.

## 1. Promessa central do MVP

> Vê quanto vais receber das tuas vendas, quanto deves reservar e quanto desse dinheiro é realmente teu.

## 2. Job to be done

> Quando tenho negócios em diferentes fases e comissões previstas, quero visualizar os recebimentos, despesas e reservas associados, para conseguir saber quanto posso efetivamente considerar rendimento meu nos próximos meses.

## 3. Evidência disponível

| Pain point | Evidência concreta | Origem da evidência | Força da evidência |
| --- | --- | --- | --- |
| Confusão entre comissão e rendimento real | O diretor relatou que agentes tratam a comissão como lucro e descobrem no final do ano que ganharam menos do que pensavam | Conversa direta com o diretor | Média: evidência direta, mas proveniente de uma única pessoa |
| Rendimentos irregulares | A pesquisa encontrou referências recorrentes a meses sem rendimento, pipeline instável e dificuldade em construir uma carreira sustentável | Pesquisa sobre agentes em Portugal | Média: problema recorrente, mas com poucos relatos recentes em primeira pessoa |
| Gestão feita em Excel | O diretor gere desta forma as próprias comissões, despesas e obrigações | Conversa direta com o diretor | Média: comportamento real observado, mas ainda não generalizado à classe |
| Despesas suportadas pelo agente | Foram referidos custos com deslocações, publicidade, fotografia, equipamentos e atividade comercial | Pesquisa e discussões públicas | Média: existência do custo confirmada; dificuldade de gestão ainda não quantificada |
| Necessidade de previsão | O diretor descreveu a necessidade de conhecer no presente os ganhos efetivos futuros | Conversa direta com o diretor | Média: alinhada com o problema, mas sem validação quantitativa |
| Ferramentas semelhantes são tecnicamente viáveis | Tuttle calcula rendimento disponível; FlowBooks agrega receitas, despesas e impostos; InsulaCRM modela negócios e comissões | Pesquisa de repositórios | Alta para viabilidade técnica; baixa como prova de procura |
| Agentes pagarão 15 EUR por mês | Não existe ainda pagamento, reserva ou compromisso financeiro de agentes | Hipótese comercial | Baixa: principal hipótese por validar |
| Prospecção e leads são uma dor mais visível | A pesquisa encontrou evidência mais forte sobre angariação, qualificação e follow-up do que sobre gestão financeira | Pesquisa recente | Alta, mas fora da promessa central deste MVP |

## 4. Funcionalidades do MVP

| Prioridade | Funcionalidade | Problema resolvido | Evidência que a suporta | Escopo mínimo | Critério de aceitação | Hipótese ou risco |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Registo de negócios e comissões | O agente não consegue prever quanto e quando receberá | Conversa com o diretor; referências do InsulaCRM | Nome do negócio, comissão da agência sem IVA, percentagem do agente, mês previsto e fase: potencial, provável, confirmado ou perdido. Uma parte de pagamento por omissão, com divisão opcional em várias partes | O agente regista um negócio em menos de 60 segundos e vê imediatamente a comissão que lhe cabe | O agente poderá considerar este registo uma duplicação do CRM da agência |
| 2 | Perfil financeiro configurável | A comissão bruta não representa o rendimento disponível | Conversa com o diretor; Tuttle e FlowBooks demonstram viabilidade | Definições de IVA e de retenção na fonte, e percentagens de reserva para IRS, Segurança Social (apresentada como estimativa) e outras. Todos os valores são introduzidos pelo agente, sem aconselhamento fiscal | O agente configura as suas regras e compreende o cálculo apresentado | As regras portuguesas podem ser demasiado variáveis para uma estimativa simples gerar confiança |
| 3 | Registo de despesas | Custos da atividade reduzem o ganho real e estão dispersos | Conversa e pesquisa sobre custos suportados pelos agentes | Despesas pontuais ou recorrentes, previstas ou pagas, associadas a um negócio ou à atividade geral. Só a confirmação transforma uma despesa prevista em paga | Ao adicionar uma despesa, o valor disponível previsto é atualizado automaticamente | O registo manual pode criar fricção e abandono |
| 4 | Previsão de rendimento líquido | Falta uma resposta imediata para "quanto vou realmente ganhar?" | Necessidade descrita pelo diretor; padrão demonstrado pelo Tuttle | Visão mensal com quatro valores distintos: comissão sem IVA, o que entrará na conta, o dinheiro a proteger (reserva de IVA, IRS, Segurança Social e outras) e o que é realmente do agente. Cenários confirmado, provável e total. Previsão do mês atual e dos onze seguintes, e histórico dos doze meses até ao atual | Depois de introduzir um negócio e uma despesa, o agente obtém a resposta numa única página | O valor percebido pode não ser suficiente para justificar uma subscrição mensal |
| 5 | Assistente de recibos | O agente volta a escrever no Portal das Finanças valores que o produto já conhece | Sem evidência direta de agentes; decisão de produto registada na issue #1 | Para cada recebimento, prepara os campos da fatura-recibo para o agente emitir no Portal das Finanças. Regista o recibo emitido, por introdução manual ou por leitura do PDF carregado. Não emite documentos nem acede ao Portal | O agente passa de um recebimento a um recibo registado sem escrever um valor duas vezes | Dor ainda não validada; aproxima o produto de software de faturação se o âmbito crescer |

Os estados dos negócios devem produzir cenários separados, não uma previsão aparentemente precisa baseada em probabilidades arbitrárias.

Receber faz parte do registo do negócio e não é uma funcionalidade separada. O agente confirma o recebimento de cada parte de pagamento, e essa confirmação fixa os valores usados no cálculo. "Recebido" é um estado derivado dos recebimentos, não uma fase do negócio.

O valor que entra na conta e o valor que é realmente do agente são conceitos distintos, sempre apresentados com rótulos separados, mesmo quando coincidem numericamente (por exemplo, sem reservas nem despesas). O IVA cobrado entra na conta mas é tratado como reserva prudente, e a retenção na fonte reduz o que entra mas conta como imposto já entregue.

Especificações de desenho: `docs/superpowers/specs/` (base técnica, núcleo do produto e assistente de recibos; issues #1, #2 e #3).

## 5. Fluxo principal

1. O agente cria a conta e subscreve um plano com método de pagamento. No plano mensal, o primeiro mês é gratuito e a cobrança de 15 EUR é automática ao fim de 30 dias; o plano anual é cobrado na subscrição.
2. Configura a percentagem habitual que recebe da comissão e a agência com que trabalha.
3. Introduz as suas definições de IVA e de retenção na fonte e as percentagens de reserva para IRS, Segurança Social e outras.
4. Regista, se quiser, despesas recorrentes da atividade; este passo é opcional.
5. Adiciona os negócios em curso, com a comissão da agência, a sua percentagem, a fase e o mês esperado. Cada negócio começa com uma parte de pagamento, que pode ser dividida.
6. O sistema apresenta três cenários: confirmado, provável e total.
7. Em cada cenário, mostra a comissão, o que entrará na conta, o dinheiro a proteger e o que é realmente do agente.
8. Quando recebe um pagamento, confirma o recebimento dessa parte, com a data e o valor reais. O negócio passa a "recebido" por derivação, quando existe pelo menos um recebimento válido e nenhuma parte prevista ativa; o agente não o marca manualmente.
9. Para cada recebimento, o assistente de recibos prepara os dados da fatura-recibo, que o agente emite no Portal das Finanças e regista de seguida.
10. O histórico compara o que estava previsto com o que foi efetivamente recebido.

A primeira resposta útil deve surgir durante o onboarding, usando pelo menos um negócio real do agente.

## 6. Fora do MVP

- **CRM completo:** contactos, chamadas, emails e tarefas já podem existir no sistema da agência.
- **Gestão de imóveis:** não é necessária para calcular o rendimento do agente.
- **Automação de leads:** resolve uma dor real, mas mudaria a categoria e a promessa do produto.
- **Integrações com CRMs:** só devem surgir depois de se provar que o registo manual impede a utilização.
- **Integração bancária:** complexidade e risco desproporcionais para validar a proposta.
- **Emissão de faturas e recibos:** o produto não emite documentos fiscais nem se integra com o Portal das Finanças. O assistente de recibos (funcionalidade 5) apenas prepara os dados e regista o recibo que o agente emite. A integração com um fornecedor de faturação certificado fica para depois do piloto (issue #1).
- **Cálculo fiscal automático oficial:** criaria expectativas de exatidão e responsabilidade que o MVP não deve assumir.
- **Aplicação móvel nativa:** uma aplicação web responsiva é suficiente.
- **IA, recomendações e saúde financeira automática:** não são necessárias para entregar a primeira resposta.
- **Equipas, rankings e gestão de performance:** o utilizador-alvo inicial é o agente individual.
- **Plano gratuito:** produziria utilização sem validar disposição para pagar. O primeiro mês gratuito do plano mensal não é um plano gratuito: exige método de pagamento e converte automaticamente em subscrição paga (secção 7).

## 7. Maior incerteza

A maior incerteza não é técnica. É saber se o agente sente esta dor com intensidade suficiente para pagar 15 EUR por mês, em vez de continuar com Excel, usar o CRM da agência ou falar com o contabilista.

A experiência paga mais pequena seria:

1. Obter dez apresentações através da associação;
2. Demonstrar um protótipo funcional com as cinco funcionalidades;
3. Pedir a subscrição do plano mensal com método de pagamento: o primeiro mês é gratuito e os 15 EUR são cobrados automaticamente ao fim de 30 dias, salvo cancelamento;
4. Fazer o onboarding com um negócio real de cada agente;
5. Observar se o agente regressa para atualizar negócios ou consultar a previsão;
6. Não oferecer plano gratuito nem período experimental sem método de pagamento.

Como critérios propostos para o piloto, e não como previsão de mercado: cinco conversões pagas entre dez apresentações qualificadas e utilização repetida por pelo menos três desses agentes durante o primeiro mês.

Uma conversão conta apenas quando a primeira cobrança é bem-sucedida, nunca pela subscrição do mês gratuito. O sinal de pagamento passa assim a ser conhecido cerca de 30 dias depois de cada adesão. Introduzir o método de pagamento é um sinal intermédio de compromisso, mas não substitui a cobrança (issue #2).

## 8. Recomendação final

**Construir este MVP, mas apenas como piloto pago e limitado às cinco funcionalidades identificadas.**

A evidência é suficiente para justificar um produto comercial mínimo, mas não um SaaS completo. Quatro das funcionalidades assentam na evidência da secção 3. A quinta, o assistente de recibos, é uma decisão de produto (issue #1) cuja procura ainda não foi validada; o piloto deve medi-la, não pressupô-la. O piloto deve validar simultaneamente três comportamentos:

1. O agente entrega dados financeiros reais;
2. Atualiza os negócios ao longo do mês;
3. Paga para obter esta visibilidade, o que só se confirma com a primeira cobrança bem-sucedida. A adesão ao mês gratuito não é validação de pagamento.

Se os agentes pagarem mas não atualizarem os dados, o problema será a fricção operacional. Se utilizarem o produto mas recusarem pagar, a dor existe, mas não sustenta o modelo proposto. Se não introduzirem sequer o primeiro negócio real, a proposta central não tem força suficiente.
