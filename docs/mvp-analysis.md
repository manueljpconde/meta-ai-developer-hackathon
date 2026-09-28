# Análise e definição do MVP

Data: 28 de setembro de 2026

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
| 1 | Registo de negócios e comissões | O agente não consegue prever quanto e quando receberá | Conversa com o diretor; referências do InsulaCRM | Nome do negócio, valor da comissão, percentagem do agente, mês previsto e estado: potencial, provável, confirmado ou recebido | O agente regista um negócio em menos de 60 segundos e vê imediatamente a comissão que lhe cabe | O agente poderá considerar este registo uma duplicação do CRM da agência |
| 2 | Perfil financeiro configurável | A comissão bruta não representa o rendimento disponível | Conversa com o diretor; Tuttle e FlowBooks demonstram viabilidade | Percentagens configuráveis para reservas fiscais, Segurança Social e outras retenções, sem aconselhamento fiscal | O agente configura as suas regras e compreende o cálculo apresentado | As regras portuguesas podem ser demasiado variáveis para uma estimativa simples gerar confiança |
| 3 | Registo de despesas | Custos da atividade reduzem o ganho real e estão dispersos | Conversa e pesquisa sobre custos suportados pelos agentes | Despesas pontuais ou recorrentes, associadas a um negócio ou à atividade geral | Ao adicionar uma despesa, o rendimento líquido previsto é atualizado automaticamente | O registo manual pode criar fricção e abandono |
| 4 | Previsão de rendimento líquido | Falta uma resposta imediata para "quanto vou realmente ganhar?" | Necessidade descrita pelo diretor; padrão demonstrado pelo Tuttle | Visão mensal com comissão bruta, parte do agente, despesas, reservas e valor disponível; cenários confirmado, provável e total | Depois de introduzir um negócio e uma despesa, o agente obtém a resposta numa única página | O valor percebido pode não ser suficiente para justificar uma subscrição mensal |

Os estados dos negócios devem produzir cenários separados, não uma previsão aparentemente precisa baseada em probabilidades arbitrárias.

"Marcar como recebido" deve fazer parte do registo do negócio, atualizando automaticamente os valores previstos e realizados. Não justifica uma quinta funcionalidade.

## 5. Fluxo principal

1. O agente cria a conta e escolhe o plano pago.
2. Configura a percentagem habitual que recebe da comissão.
3. Introduz percentagens de reserva para impostos e Segurança Social.
4. Regista despesas recorrentes da atividade.
5. Adiciona os negócios em curso, com comissão prevista, estado e mês esperado.
6. O sistema apresenta três cenários: confirmado, provável e total.
7. Em cada cenário, mostra comissão bruta, parte do agente, despesas, reservas e valor realmente disponível.
8. Quando recebe uma comissão, marca o negócio como recebido e compara a previsão com o resultado.

A primeira resposta útil deve surgir durante o onboarding, usando pelo menos um negócio real do agente.

## 6. Fora do MVP

- **CRM completo:** contactos, chamadas, emails e tarefas já podem existir no sistema da agência.
- **Gestão de imóveis:** não é necessária para calcular o rendimento do agente.
- **Automação de leads:** resolve uma dor real, mas mudaria a categoria e a promessa do produto.
- **Integrações com CRMs:** só devem surgir depois de se provar que o registo manual impede a utilização.
- **Integração bancária:** complexidade e risco desproporcionais para validar a proposta.
- **Faturação e recibos:** aproximariam o produto de software contabilístico.
- **Cálculo fiscal automático oficial:** criaria expectativas de exatidão e responsabilidade que o MVP não deve assumir.
- **Aplicação móvel nativa:** uma aplicação web responsiva é suficiente.
- **IA, recomendações e saúde financeira automática:** não são necessárias para entregar a primeira resposta.
- **Equipas, rankings e gestão de performance:** o utilizador-alvo inicial é o agente individual.
- **Plano gratuito:** produziria utilização sem validar disposição para pagar.

## 7. Maior incerteza

A maior incerteza não é técnica. É saber se o agente sente esta dor com intensidade suficiente para pagar 15 EUR por mês, em vez de continuar com Excel, usar o CRM da agência ou falar com o contabilista.

A experiência paga mais pequena seria:

1. Obter dez apresentações através da associação;
2. Demonstrar um protótipo funcional com as quatro funcionalidades;
3. Pedir o pagamento imediato de 15 EUR por 30 dias de acesso;
4. Fazer o onboarding com um negócio real de cada agente;
5. Observar se o agente regressa para atualizar negócios ou consultar a previsão;
6. Não oferecer período gratuito.

Um sinal inicial proposto, não uma previsão de mercado, seria conseguir cinco pagamentos entre dez apresentações qualificadas e utilização repetida por pelo menos três desses agentes durante o primeiro mês.

## 8. Recomendação final

**Construir este MVP, mas apenas como piloto pago e limitado às quatro funcionalidades identificadas.**

A evidência é suficiente para justificar um produto comercial mínimo, mas não um SaaS completo. O piloto deve validar simultaneamente três comportamentos:

1. O agente entrega dados financeiros reais;
2. Atualiza os negócios ao longo do mês;
3. Paga para obter esta visibilidade.

Se os agentes pagarem mas não atualizarem os dados, o problema será a fricção operacional. Se utilizarem o produto mas recusarem pagar, a dor existe, mas não sustenta o modelo proposto. Se não introduzirem sequer o primeiro negócio real, a proposta central não tem força suficiente.
