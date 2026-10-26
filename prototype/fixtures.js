// Protótipo descartável. Dados fictícios e resultados predefinidos.
// Nenhum valor é calculado aqui: todos os montantes foram calculados uma vez,
// à mão, pelas regras da especificação do núcleo do produto, e estão escritos
// como literais (em cêntimos).

// Mês de previsão: comissão, já recebido, por receber, entra na conta,
// [reserva IVA, reserva IRS, Seg. Social], despesas, é realmente teu.
const M = (c, rec, por, entra, prot, desp, teu) => ({ c, rec, por, entra, prot, desp, teu });
const VAZIO = M(0, 0, 0, 0, [0, 0, 0], 35000, -35000);
const T2_MES = M(500000, 0, 500000, 490000, [115000, 25000, 50000], 35000, 265000);
const T2_RECEBIDO = M(500000, 500000, 0, 490000, [115000, 25000, 50000], 35000, 265000);
const T2_CURTO = M(450000, 450000, 0, 441000, [103500, 22500, 45000], 35000, 235000);
const T3_MES = M(320000, 0, 320000, 313600, [73600, 16000, 32000], 35000, 157000);
const COLARES_MES = M(410000, 0, 410000, 401800, [94300, 20500, 41000], 35000, 211000);
const tudo = (m) => ({ confirmado: m, provavel: m, total: m });

// Pré-visualizações do "servidor" por base sem IVA (cêntimos).
window.PREVIEWS = {
  500000: { entra: 490000, proteger: 190000 },
  450000: { entra: 441000, proteger: 171000 },
  320000: { entra: 313600, proteger: 121600 },
  90000: { entra: 88200, proteger: 34200 },
  95000: { entra: 93100, proteger: 36100 },
};

// Parte do agente por (comissão da agência, percentagem).
// Só entram aqui combinações cujo resultado na previsão está preparado.
window.PARTES = {
  '1000000:50': 500000,
};

// Exemplos que a demonstração deixa escolher. Não contêm respostas do moderador.
window.EXEMPLOS = [
  { f: 'A', nome: 'Começar sem negócios (hoje: 14/10/2026)' },
  { f: 'B', nome: 'Negócios em curso (hoje: 14/11/2026)' },
  { f: 'C', nome: 'Um recebimento por corrigir (hoje: 14/11/2026)' },
];

const MESES_A = [
  { key: '2026-10', label: 'outubro 2026', curto: 'out 2026' },
  { key: '2026-11', label: 'novembro 2026', curto: 'nov 2026' },
  { key: '2026-12', label: 'dezembro 2026', curto: 'dez 2026' },
  { key: '2027-01', label: 'janeiro 2027', curto: 'jan 2027' },
];
const MESES_B = MESES_A.slice(1).concat([{ key: '2027-02', label: 'fevereiro 2027', curto: 'fev 2027' }]);

window.T2_MES = T2_MES;
window.VAZIO = VAZIO;

window.FIXTURES = {
  A: {
    hoje: '14/10/2026',
    mesAtual: '2026-10',
    meses: MESES_A,
    criar: true,
    semRecebimentos: true,
    negocios: [],
    previsao: {},
  },
  B: {
    hoje: '14/11/2026',
    mesAtual: '2026-11',
    meses: MESES_B,
    negocios: [
      { id: 't2', nome: 'T2 Campo de Ourique', agencia: 1000000, perc: '50', parte: 500000, fase: 'confirmado', janela: ['2026-11-01', '2026-11-14'],
        partes: [{ id: 'p1', mes: 'novembro 2026', esperado: 500000 }] },
      { id: 't3', nome: 'T3 Av. de Roma · Ref 2841', agencia: 640000, perc: '50', parte: 320000, fase: 'provavel', janela: ['2026-11-01', '2026-11-14'],
        partes: [{ id: 'p1', mes: 'dezembro 2026', esperado: 320000 }] },
      { id: 'colares', nome: 'Moradia Colares', agencia: 820000, perc: '50', parte: 410000, fase: 'potencial',
        partes: [{ id: 'p1', mes: 'janeiro 2027', esperado: 410000 }] },
    ],
    previsao: {
      '2026-11': tudo(T2_MES),
      '2026-12': { confirmado: VAZIO, provavel: T3_MES, total: T3_MES },
      '2027-01': { confirmado: VAZIO, provavel: VAZIO, total: COLARES_MES },
      '2027-02': tudo(VAZIO),
    },
  },
  C: {
    hoje: '14/11/2026',
    mesAtual: '2026-11',
    meses: MESES_B,
    negocios: [
      { id: 'loja', nome: 'Loja Alvalade', agencia: 200000, perc: '50', parte: 100000, fase: 'confirmado', janela: ['2026-10-01', '2026-10-31'],
        partes: [
          { id: 'p1', mes: 'outubro 2026', esperado: 100000, recebido: { data: '10/10/2026', base: 90000, entra: 88200 } },
          { id: 'p2', mes: 'dezembro 2026', esperado: 10000 },
        ] },
    ],
    previsao: {
      '2026-11': tudo(VAZIO),
      '2026-12': tudo(M(10000, 0, 10000, 9800, [2300, 500, 1000], 35000, -29000)),
      '2027-01': tudo(VAZIO),
      '2027-02': tudo(VAZIO),
    },
  },
};

// Casos previstos ao registar ou corrigir um recebimento.
// Chave: id do negócio + ':' + base sem IVA (cêntimos).
window.CASOS = {
  't2:500000': { residuo: 0, resultado: 'B_igual' },
  't2:450000': {
    residuo: 50000,
    titulo: 'Faltam 500,00 € neste negócio',
    linhas: [['A tua parte', 500000], ['Recebido', 450000], ['Por receber', 0], ['Por explicar', 50000]],
    pergunta: 'O que acontece a estes 500,00 €?',
    opcoes: [
      { id: 'falta', rotulo: 'Ainda falta receber', efeito: 'Por receber passa a 500,00 €.', mes: 'dezembro 2026',
        resumo: 'Diferença de 500,00 €: fica previsto para dezembro 2026', resultado: 'B_falta' },
      { id: 'menor', rotulo: 'A comissão foi menor', efeito: 'A tua comissão neste negócio passa a 4 500,00 €.',
        resumo: 'Diferença de 500,00 €: a tua comissão neste negócio passa a 4 500,00 €', resultado: 'B_menor' },
      { id: 'origem', rotulo: 'A comissão ou a percentagem estavam erradas', efeito: 'Corrigir os dados do negócio',
        origem: { agencia: '9000', perc: '50', chave: '900000:50',
          linhas: [['A tua parte', 450000], ['Recebido', 450000], ['Por receber', 0], ['Por explicar', 0]],
          resumo: ['Comissão da agência: 10 000,00 € → 9 000,00 €', 'A tua parte: 5 000,00 € → 4 500,00 €'] },
        resultado: 'B_origem' },
    ],
  },
  't3:320000': { residuo: 0, resultado: 'B_t3' },
  'loja:90000': { residuo: 0, resultado: 'C_igual' },
  'loja:95000': {
    residuo: -5000,
    titulo: 'Há 50,00 € a mais neste negócio',
    linhas: [['A tua parte', 100000], ['Recebido', 95000], ['Por receber', 10000], ['A mais', 5000]],
    pergunta: 'O que acontece a estes 50,00 €?',
    opcoes: [
      { id: 'antecipa', rotulo: 'Antecipa valores em falta', efeito: 'Por receber passa de 100,00 € a 50,00 €.',
        resumo: 'Diferença de 50,00 €: por receber passa de 100,00 € a 50,00 €', resultado: 'C_antecipa' },
      { id: 'maior', rotulo: 'A comissão foi maior', efeito: 'A tua comissão neste negócio passa a 1 050,00 €.',
        resumo: 'Diferença de 50,00 €: a tua comissão neste negócio passa a 1 050,00 €', resultado: 'C_maior' },
      { id: 'origem', rotulo: 'A comissão ou a percentagem estavam erradas', efeito: 'Corrigir os dados do negócio',
        origem: { agencia: '2100', perc: '50', chave: '210000:50',
          linhas: [['A tua parte', 105000], ['Recebido', 95000], ['Por receber', 10000], ['Por explicar', 0]],
          resumo: ['Comissão da agência: 2 000,00 € → 2 100,00 €', 'A tua parte: 1 000,00 € → 1 050,00 €'] },
        resultado: 'C_origem' },
    ],
  },
};

// Estado resultante de cada caso: alterações ao negócio e à previsão.
const NOV_T3 = M(820000, 320000, 500000, 803600, [188600, 41000, 82000], 35000, 457000);
window.RESULTADOS = {
  B_igual: { negocio: { partes: [{ id: 'p1', mes: 'novembro 2026', esperado: 500000, recebido: { base: 500000, entra: 490000 } }] },
    previsao: { '2026-11': tudo(T2_RECEBIDO) } },
  B_falta: { negocio: { partes: [
      { id: 'p1', mes: 'novembro 2026', esperado: 500000, recebido: { base: 450000, entra: 441000 } },
      { id: 'p2', mes: 'dezembro 2026', esperado: 50000 }] },
    previsao: { '2026-11': tudo(T2_CURTO),
      '2026-12': { confirmado: M(50000, 0, 50000, 49000, [11500, 2500, 5000], 35000, -5000),
        provavel: M(370000, 0, 370000, 362600, [85100, 18500, 37000], 35000, 187000),
        total: M(370000, 0, 370000, 362600, [85100, 18500, 37000], 35000, 187000) } } },
  B_menor: { negocio: { ajuste: -50000, efetiva: 450000,
      partes: [{ id: 'p1', mes: 'novembro 2026', esperado: 500000, recebido: { base: 450000, entra: 441000 } }] },
    previsao: { '2026-11': tudo(T2_CURTO) } },
  B_origem: { negocio: { agencia: 900000, parte: 450000,
      partes: [{ id: 'p1', mes: 'novembro 2026', esperado: 450000, recebido: { base: 450000, entra: 441000 } }] },
    previsao: { '2026-11': tudo(T2_CURTO) } },
  B_t3: { negocio: { fase: 'confirmado',
      partes: [{ id: 'p1', mes: 'dezembro 2026', esperado: 320000, recebido: { base: 320000, entra: 313600 } }] },
    previsao: { '2026-11': tudo(NOV_T3), '2026-12': tudo(VAZIO) } },
  C_igual: { negocio: {}, previsao: {} },
  C_antecipa: { negocio: { partes: [
      { id: 'p1', mes: 'outubro 2026', esperado: 100000, recebido: { data: '10/10/2026', base: 95000, entra: 93100 } },
      { id: 'p2', mes: 'dezembro 2026', esperado: 5000 }] },
    previsao: { '2026-12': tudo(M(5000, 0, 5000, 4900, [1150, 250, 500], 35000, -32000)) } },
  C_maior: { negocio: { ajuste: 5000, efetiva: 105000, partes: [
      { id: 'p1', mes: 'outubro 2026', esperado: 100000, recebido: { data: '10/10/2026', base: 95000, entra: 93100 } },
      { id: 'p2', mes: 'dezembro 2026', esperado: 10000 }] },
    previsao: {} },
  C_origem: { negocio: { agencia: 210000, parte: 105000, partes: [
      { id: 'p1', mes: 'outubro 2026', esperado: 100000, recebido: { data: '10/10/2026', base: 95000, entra: 93100 } },
      { id: 'p2', mes: 'dezembro 2026', esperado: 10000 }] },
    previsao: {} },
};
