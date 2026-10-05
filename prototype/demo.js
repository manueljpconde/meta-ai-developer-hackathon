// Demonstrações autónomas (protótipo descartável), separadas do modo de testes acompanhados.
// Não há motor de cálculo: todos os montantes são literais, em cêntimos, iguais aos da
// especificação UX, secções 5.3 e 5.4. Os testes comparam os registos individuais com os totais.
const { createApp, nextTick } = Vue;
const VERSAO = '2026-10-04.8';
const M = (c, rec, por, entrou, porEntrar, prot, desp, teu) => ({ c, rec, por, entrou, porEntrar, prot, desp, teu });
const ZERO = M(0, 0, 0, 0, 0, [0, 0, 0], 0, 0);
const tudo = (m) => ({ confirmado: m, provavel: m, total: m });

// ---------------- Demonstração 1: seis meses de atividade (só consulta)
const SEIS = {
  hoje: '14/11/2026',
  mesInicial: '2026-11',
  meses: [
    { key: '2026-08', label: 'agosto 2026', curto: 'ago 2026', tipo: 'historico' },
    { key: '2026-09', label: 'setembro 2026', curto: 'set 2026', tipo: 'historico' },
    { key: '2026-10', label: 'outubro 2026', curto: 'out 2026', tipo: 'historico' },
    { key: '2026-11', label: 'novembro 2026', curto: 'nov 2026', tipo: 'atual' },
    { key: '2026-12', label: 'dezembro 2026', curto: 'dez 2026', tipo: 'futuro' },
    { key: '2027-01', label: 'janeiro 2027', curto: 'jan 2027', tipo: 'futuro' },
  ],
  previsao: {
    '2026-08': tudo(M(0, 0, 0, 0, 0, [0, 0, 0], 33500, -33500)),
    '2026-09': tudo(M(500000, 500000, 0, 490000, 0, [115000, 25000, 50000], 59000, 241000)),
    '2026-10': tudo(M(320000, 320000, 0, 313600, 0, [73600, 16000, 32000], 64000, 128000)),
    '2026-11': tudo(M(480000, 180000, 300000, 176400, 294000, [110400, 24000, 48000], 57000, 231000)),
    '2026-12': {
      confirmado: M(320000, 0, 320000, 0, 313600, [73600, 16000, 32000], 39000, 153000),
      provavel: M(730000, 0, 730000, 0, 715400, [167900, 36500, 73000], 39000, 399000),
      total: M(730000, 0, 730000, 0, 715400, [167900, 36500, 73000], 39000, 399000),
    },
    '2027-01': {
      confirmado: M(0, 0, 0, 0, 0, [0, 0, 0], 59000, -59000),
      provavel: M(0, 0, 0, 0, 0, [0, 0, 0], 59000, -59000),
      total: M(260000, 0, 260000, 0, 254800, [59800, 13000, 26000], 59000, 97000),
    },
  },
  negocios: [
    { id: 't2', nome: 'T2 Campo de Ourique', fase: 'Confirmado', agencia: 1000000, parte: 500000,
      partes: [{ mes: 'setembro 2026', key: '2026-09', valor: 500000, recebido: '12/09/2026', entrou: 490000 }] },
    { id: 't3', nome: 'T3 Av. de Roma · Ref 2841', fase: 'Confirmado', agencia: 1280000, parte: 640000,
      partes: [{ mes: 'outubro 2026', key: '2026-10', valor: 320000, recebido: '20/10/2026', entrou: 313600 },
        { mes: 'dezembro 2026', key: '2026-12', valor: 320000 }] },
    { id: 'loja', nome: 'Loja Alvalade', fase: 'Confirmado', agencia: 360000, parte: 180000,
      partes: [{ mes: 'novembro 2026', key: '2026-11', valor: 180000, recebido: '06/11/2026', entrou: 176400 }] },
    { id: 't1', nome: 'T1 Arroios', fase: 'Confirmado', agencia: 600000, parte: 300000,
      partes: [{ mes: 'novembro 2026', key: '2026-11', valor: 300000 }] },
    { id: 'colares', nome: 'Moradia Colares', fase: 'Provável', agencia: 820000, parte: 410000,
      partes: [{ mes: 'dezembro 2026', key: '2026-12', valor: 410000 }] },
    { id: 'estrela', nome: 'Apartamento Estrela', fase: 'Potencial', agencia: 520000, parte: 260000,
      partes: [{ mes: 'janeiro 2027', key: '2027-01', valor: 260000 }] },
  ],
  despesas: {
    '2026-08': [['Portal imobiliário', 12000, '03/08/2026'], ['Telemóvel', 4500, '05/08/2026'], ['Contabilista', 7500, '28/08/2026'], ['Combustível', 9500, '31/08/2026']],
    '2026-09': [['Portal imobiliário', 12000, '03/09/2026'], ['Telemóvel', 4500, '05/09/2026'], ['Fotografia · T2 Campo de Ourique', 18000, '08/09/2026'], ['Contabilista', 7500, '28/09/2026'], ['Combustível', 17000, '30/09/2026']],
    '2026-10': [['Portal imobiliário', 12000, '03/10/2026'], ['Telemóvel', 4500, '05/10/2026'], ['Seguro de responsabilidade civil', 24000, '15/10/2026'], ['Contabilista', 7500, '28/10/2026'], ['Combustível', 16000, '31/10/2026']],
    '2026-11': [['Portal imobiliário', 12000, '03/11/2026'], ['Telemóvel', 4500, '05/11/2026'], ['Contabilista', 7500, ''], ['Combustível', 15000, ''], ['Fotografia · T1 Arroios', 18000, '', '20/11/2026']],
    '2026-12': [['Portal imobiliário', 12000, ''], ['Telemóvel', 4500, ''], ['Contabilista', 7500, ''], ['Combustível', 15000, '']],
    '2027-01': [['Portal imobiliário', 12000, ''], ['Telemóvel', 4500, ''], ['Contabilista', 7500, ''], ['Combustível', 15000, ''], ['Publicidade de início de ano', 20000, '']],
  },
  // [total, pago, previsto] de cada mês
  totaisDesp: { '2026-08': [33500, 33500, 0], '2026-09': [59000, 59000, 0], '2026-10': [64000, 64000, 0], '2026-11': [57000, 16500, 40500], '2026-12': [39000, 0, 39000], '2027-01': [59000, 0, 59000] },
  recibos: [
    { negocio: 'T2 Campo de Ourique', recebido: 500000, comRecibo: 500000, nota: 'Registado a 12/09/2026 · lido do PDF, documento verificado' },
    { negocio: 'T3 Av. de Roma · Ref 2841', recebido: 320000, comRecibo: 320000, nota: 'Registado a 21/10/2026 · dados escritos pelo agente' },
    { negocio: 'Loja Alvalade', recebido: 180000, comRecibo: 0, nota: '' },
  ],
  totaisRecibos: [1000000, 820000, 180000],
  folha: [
    ['NIF do adquirente', '999 999 990', 'agência, no negócio'], ['Nome do adquirente', 'Imo Lisboa, Lda', 'agência, no negócio'],
    ['Descrição', 'Comissão · Loja Alvalade', ''], ['Valor base', '1800,00', 'recebimento registado'], ['IVA (23 %)', '414,00', 'recebimento registado'],
    ['Retenção na fonte (25 %)', '450,00', 'recebimento registado'], ['Importância recebida', '1764,00', 'recebimento registado'],
  ],
  pontos: [null,
    { c: 'Novembro: recebido, esperado e disponível.', t: 'Em novembro já entraram 1 764,00 € na conta, esperam-se mais 2 940,00 €, e a previsão para o mês completo é de 2 310,00 € disponíveis depois das reservas e despesas.', ir: { vista: 'previsao', mesKey: '2026-11', cenario: 'confirmado' } },
    { c: 'T3 Av. de Roma: pagamento repartido.', t: 'Este negócio paga em duas partes: 3 200,00 € já recebidos em outubro e 3 200,00 € previstos para dezembro.', ir: { vista: 'negocio', negId: 't3' } },
    { c: 'Dezembro: compara Confirmado e Provável.', t: 'Só com o que está confirmado, dezembro deixa 1 530,00 € disponíveis. Contando com o negócio provável, 3 990,00 €. Toca em «Provável» para comparar.', ir: { vista: 'previsao', mesKey: '2026-12', cenario: 'confirmado' } },
  ],
};

// ---------------- Demonstração 2: do início ao fim (um negócio, dez estados válidos)
const P_T2 = [115000, 25000, 50000];
const JORNADA = {
  hoje: '14/11/2026',
  meses: [
    { key: '2026-11', label: 'novembro 2026', curto: 'nov 2026', tipo: 'atual' },
    { key: '2026-12', label: 'dezembro 2026', curto: 'dez 2026', tipo: 'futuro' },
    { key: '2027-01', label: 'janeiro 2027', curto: 'jan 2027', tipo: 'futuro' },
  ],
  // novembro por (recebimento confirmado?, despesa registada?)
  nov: {
    ff: M(500000, 0, 500000, 0, 490000, P_T2, 0, 300000),
    ft: M(500000, 0, 500000, 0, 490000, P_T2, 15000, 285000),
    tf: M(500000, 500000, 0, 490000, 0, P_T2, 0, 300000),
    tt: M(500000, 500000, 0, 490000, 0, P_T2, 15000, 285000),
  },
  folha: [
    ['NIF do adquirente', '999 999 990', 'agência, no negócio'], ['Nome do adquirente', 'Imo Lisboa, Lda', 'agência, no negócio'],
    ['Descrição', 'Comissão · T3 Telheiras', ''], ['Valor base', '5000,00', 'recebimento registado'], ['IVA (23 %)', '1150,00', 'recebimento registado'],
    ['Retenção na fonte (25 %)', '1250,00', 'recebimento registado'], ['Importância recebida', '4900,00', 'recebimento registado'],
  ],
  passos: [null,
    { c: 'Vê o estado inicial, vazio.', t: 'A aplicação começa sem negócios, despesas, recebimentos ou recibos. O perfil financeiro de exemplo já está configurado.', v: 'previsao' },
    { c: 'Regista o negócio.', t: 'Regista o negócio de exemplo «T3 Telheiras», na fase Confirmado.', v: 'novo' },
    { c: 'Vê o impacto na previsão.', t: 'A previsão de novembro passa a mostrar a comissão, o que vai entrar na conta, o que fica protegido e o que é realmente teu.', v: 'previsao' },
    { c: 'Regista a despesa e o seu pagamento.', t: 'Regista a despesa de fotografia associada ao negócio e, depois, confirma o seu pagamento. Uma despesa prevista e uma despesa paga contam o mesmo na previsão.', v: 'despesas' },
    { c: 'Confirma o recebimento.', t: 'A agência pagou a comissão. Confirma o recebimento e vê a passagem de previsto a recebido.', v: 'negocio' },
    { c: 'Prepara e regista o recibo.', t: 'Prepara a folha de cópia da fatura-recibo e regista o recibo. A emissão no Portal e a leitura do PDF são simulações.', v: 'recibos' },
    { c: 'Revê o resultado final.', t: 'Vê o que ficou feito e o resultado financeiro, e lê as três perguntas.', v: 'previsao' },
  ],
  msg: {
    neg: 'Novembro passou a contar com 5 000,00 € de comissão por receber: 4 900,00 € por entrar na conta e 3 000,00 € disponíveis depois das reservas. Ainda não entrou nada na conta.',
    desp: 'As despesas de novembro passaram a 150,00 €, ainda previstas, e o disponível desceu 150,00 €. A comissão e as reservas não mudaram.',
    pago: 'A despesa passou de prevista a paga. Não foi descontada outra vez: as despesas continuam em 150,00 € e o disponível não mudou.',
    rec: 'Os 5 000,00 € passaram de «por receber» a «já recebido», e os 4 900,00 € de «por entrar» a «já entrou». Não é rendimento novo: o disponível do mês não mudou.',
    recibo: 'O montante por cobrir com recibo passou de 5 000,00 € para 0,00 €. O recibo não acrescenta rendimento: a previsão não mudou.',
  },
  // Versão de uma linha, para a faixa compacta no telemóvel
  curta: {
    neg: 'novembro passou a prever 3 000,00 € disponíveis.',
    desp: 'o disponível desceu 150,00 €.',
    pago: 'a despesa ficou paga; o disponível não mudou.',
    rec: 'passou de «por receber» a «já recebido»; o disponível não mudou.',
    recibo: 'o montante por cobrir com recibo passou a 0,00 €.',
  },
};
window.DEMO_DADOS = { SEIS, JORNADA, VERSAO };

const INI1 = { cenario: 'confirmado', mesKey: '2026-11', ponto: 1 };
const INI2 = { passo: 1, neg: false, desp: false, pago: false, rec: false, recibo: false, reciboModo: '', reciboNum: '', ultimo: '', cenario: 'confirmado', mesKey: '2026-11' };
const CHAVES = { geral: 'agentimo-demo', seis: 'agentimo-demo-seis', jornada: 'agentimo-demo-jornada' };

function fmt(c) {
  const neg = c < 0; const s = String(Math.abs(c)).padStart(3, '0');
  return (neg ? '−' : '') + s.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ',' + s.slice(-2) + ' €';
}
// crypto.randomUUID só existe em contexto seguro; o recurso produz um UUID v4 com a mesma origem aleatória.
function novoId() {
  if (window.crypto.randomUUID) return window.crypto.randomUUID();
  const b = window.crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
}
// Estado guardado por demonstração, com versão dos dados: um estado de outra versão é ignorado.
function ler(chave, inicial) {
  try { const g = JSON.parse(localStorage.getItem(chave) || 'null'); if (g && g.v === VERSAO) return Object.assign({}, inicial, g.d); } catch (e) { /* sem armazenamento */ }
  return Object.assign({}, inicial);
}
function escrever(chave, d) { try { localStorage.setItem(chave, JSON.stringify({ v: VERSAO, d })); } catch (e) { /* sem armazenamento: funciona, mas não sobrevive a recarregar */ } }

window.demo = createApp({
  data() {
    const g = ler(CHAVES.geral, { modo: 'entrada', demo: '', guiaVisivel: true });
    // Numa publicação dedicada, a nota fica fixa na página (window.DEMO_FIXA) em vez de depender da ligação.
    const demoUrl = window.DEMO_FIXA || new URLSearchParams(location.search).get('demo');
    return {
      modo: g.modo, demo: demoUrl || g.demo, s1: ler(CHAVES.seis, INI1), s2: ler(CHAVES.jornada, INI2),
      vista: 'previsao', negId: 't3', aberto: { como: false, proteger: false }, toast: '', aviso: '', aRecomecar: false,
      novaDesp: false, confPago: false, recEcra: 'lista', copiado: '', falhouCopia: '', colado: {}, modoRecibo: '', numero: '', sobre: false,
      guiaVisivel: g.guiaVisivel, guiaAberta: null, avisoGuia: '', recPasso: 1, simPortal: false,
      comentariosUrl: window.DEMO_COMENTARIOS || '',
      comentario: { id: '', texto: '', contexto: '', atual: '', estado: 'rascunho', erro: '' },
    };
  },
  computed: {
    seis() { return this.modo === 'seis'; },
    e() { return this.seis ? this.s1 : this.s2; },
    meses() { return this.seis ? SEIS.meses : JORNADA.meses; },
    mes() { return this.meses.find((m) => m.key === this.e.mesKey) || this.meses[0]; },
    dados() { return this.previsao(this.mes.key, this.e.cenario); },
    proteger() { const p = this.dados.prot; return p[0] + p[1] + p[2]; },
    cenarioNome() { return { confirmado: 'Confirmado', provavel: 'Provável', total: 'Total' }[this.e.cenario]; },
    negocios() {
      if (this.seis) return SEIS.negocios;
      if (!this.s2.neg) return [];
      return [{ id: 't2', nome: 'T3 Telheiras', fase: 'Confirmado', agencia: 1000000, parte: 500000,
        partes: [{ mes: 'novembro 2026', key: '2026-11', valor: 500000, recebido: this.s2.rec ? '14/11/2026' : '', entrou: 490000 }] }];
    },
    negocio() { return this.negocios.find((n) => n.id === this.negId) || this.negocios[0]; },
    despesas() {
      if (this.seis) return SEIS.despesas[this.mes.key].map((d) => ({ nome: d[0], valor: d[1], pago: d[2], para: d[3] || '' }));
      if (!this.s2.desp || this.mes.key !== '2026-11') return [];
      return [{ nome: 'Fotografia profissional · T3 Telheiras', valor: 15000, pago: this.s2.pago ? '12/11/2026' : '', para: '10/11/2026' }];
    },
    totaisDesp() {
      if (this.seis) return SEIS.totaisDesp[this.mes.key];
      if (!this.s2.desp || this.mes.key !== '2026-11') return [0, 0, 0];
      return this.s2.pago ? [15000, 15000, 0] : [15000, 0, 15000];
    },
    recibos() {
      if (this.seis) return SEIS.recibos;
      if (!this.s2.rec) return [];
      return [{ negocio: 'T3 Telheiras', recebido: 500000, comRecibo: this.s2.recibo ? 500000 : 0,
        nota: this.s2.recibo ? 'Registado a 14/11/2026 · ' + (this.s2.reciboModo === 'pdf' ? 'lido do PDF, documento verificado' : 'dados escritos pelo agente') + (this.s2.reciboNum ? ' · n.º ' + this.s2.reciboNum : '') : '' }];
    },
    totaisRecibos() {
      if (this.seis) return SEIS.totaisRecibos;
      if (!this.s2.rec) return [0, 0, 0];
      return this.s2.recibo ? [500000, 500000, 0] : [500000, 0, 500000];
    },
    folha() { return this.seis ? SEIS.folha : JORNADA.folha; },
    impacto() { return this.seis ? '' : (JORNADA.msg[this.s2.ultimo] || ''); },
    ultimoPasso() { return !this.seis && this.s2.passo === 7; },
    curta() { return this.seis ? '' : (JORNADA.curta[this.s2.ultimo] || ''); },
    // No telemóvel o guia abre-se sozinho nos formulários e no último passo; na previsão fica compacto.
    // A escolha da pessoa prevalece sempre; sem escolha, o guia só se abre sozinho no último passo.
    corpoAberto() { return this.guiaAberta === null ? this.ultimoPasso : this.guiaAberta; },
    // O guia só explica o ecrã que está aberto. Fora do destino do passo, diz que a pessoa está a explorar.
    noDestino() {
      if (!this.emGuia) return true;
      if (this.seis) {
        const d = SEIS.pontos[this.s1.ponto].ir;
        return this.vista === d.vista && (!d.mesKey || this.s1.mesKey === d.mesKey) && (!d.negId || this.negId === d.negId);
      }
      const permitidos = { 1: ['previsao'], 2: ['novo', 'negocios', 'negocio', 'previsao'], 3: ['previsao'], 4: ['despesas', 'previsao'], 5: ['negocio', 'receber', 'negocios', 'previsao'], 6: ['recibos', 'previsao'], 7: ['previsao'] }[this.s2.passo];
      // A jornada passa-se em novembro: noutro mês, a previsão e as despesas já não são o ecrã que o guia explica.
      if ((this.vista === 'previsao' || this.vista === 'despesas') && this.s2.mesKey !== '2026-11') return false;
      return permitidos.includes(this.vista) && !this.simPortal || (this.simPortal && this.s2.passo === 6);
    },
    // Aviso curto, sempre visível na barra da demonstração, mesmo com o guia oculto.
    notaCurta() {
      if (this.avisoGuia) return this.avisoGuia;
      if (this.simPortal) return 'Simulação do Portal: nada é emitido nem enviado.';
      if (this.seis) return 'Exemplo preenchido, só para consulta.';
      if ((this.vista === 'novo' && !this.s2.neg) || (this.vista === 'receber' && !this.s2.rec) || (this.vista === 'despesas' && (this.novaDesp || this.confPago))) return 'Campos preenchidos e bloqueados nesta visita.';
      if (this.vista === 'recibos' && this.recEcra === 'registar') return this.modoRecibo === 'pdf' ? 'Leitura do PDF simulada: nenhum ficheiro foi pedido nem lido.' : 'A leitura do PDF é simulada nesta visita.';
      if (this.vista === 'recibos' && this.recEcra === 'folha') return 'A emissão no Portal é simulada; os nomes dos campos são provisórios.';
      return '';
    },
    // Explicações que pertencem ao guia, não à aplicação.
    notaEcra() {
      if (this.simPortal) return 'Isto é uma simulação do guia. Não é o Portal das Finanças nem faz parte do Agentimo. Nada é emitido nem enviado.';
      if (this.seis) return this.vista === 'recibos' ? 'Exemplo preenchido, só para consulta: aqui não se guarda nem altera nada. O registo de um recibo experimenta-se na visita guiada.' : 'Exemplo preenchido, só para consulta: aqui não se guarda nem altera nada.';
      if (this.vista === 'novo' && !this.s2.neg) return 'Preenchemos os dados deste negócio para esta visita. Os campos estão bloqueados; na aplicação, é o agente que os escreve.';
      if (this.vista === 'receber' && !this.s2.rec) return 'Preenchemos os dados do recebimento para esta visita: a agência pagou o valor esperado. Na aplicação, nenhuma resposta vem escolhida.';
      if (this.vista === 'despesas' && (this.novaDesp || this.confPago)) return 'Preenchemos os dados da despesa para esta visita. Os campos estão bloqueados.';
      if (this.vista === 'recibos') return 'A emissão no Portal das Finanças e a leitura do PDF são simuladas nesta demonstração. Nenhum documento real é pedido. Os nomes dos campos da folha são provisórios.';
      return '';
    },
    // Faixa de orientação
    total() { return this.seis ? 3 : 7; },
    n() { return this.seis ? this.s1.ponto : this.s2.passo; },
    emGuia() { return this.seis ? this.s1.ponto >= 1 && this.s1.ponto <= 3 : true; },
    itemGuia() { return this.seis ? SEIS.pontos[this.s1.ponto] : JORNADA.passos[this.s2.passo]; },
    // Pré-requisito em falta no passo atual: o guia explica e oferece ir ao passo certo. Nunca guarda nada.
    falta() {
      if (this.seis) return null;
      const s = this.s2;
      if ([3, 4, 5, 6].includes(s.passo) && !s.neg) return { texto: 'Primeiro precisamos de registar o negócio.', passo: 2 };
      if (s.passo === 6 && !s.rec) return { texto: 'Primeiro precisamos de confirmar o recebimento.', passo: 5 };
      return null;
    },
    fraseGuia() {
      if (this.seis) return this.itemGuia.c;
      if (this.falta) return this.falta.texto;
      const s = this.s2;
      if (s.passo === 4 && s.desp && !s.pago) return 'Confirma agora o pagamento da despesa.';
      const feito = { 2: s.neg, 4: s.desp && s.pago, 5: s.rec, 6: s.recibo }[s.passo];
      return feito ? 'Feito. Toca em «Seguinte».' : this.itemGuia.c;
    },
  },
  methods: {
    fmt,
    previsao(key, cen) {
      if (this.seis) return SEIS.previsao[key][cen];
      const s = this.s2;
      if (key !== '2026-11' || !s.neg) return ZERO;
      return JORNADA.nov[(s.rec ? 't' : 'f') + (s.desp ? 't' : 'f')];
    },
    teu(key) { return this.previsao(key, this.e.cenario).teu; },
    contaFinal() {
      const m = this.previsao('2026-11', 'confirmado'); const p = m.prot[0] + m.prot[1] + m.prot[2];
      return fmt(m.entrou + m.porEntrar) + ' − ' + fmt(p) + ' a proteger − ' + fmt(m.desp) + ' de despesas = ' + fmt(m.teu);
    },
    // Comentários: nada aqui altera o estado da demonstração nem o que está guardado no browser.
    contextoAtual() {
      const comItem = (this.vista === 'negocio' || this.vista === 'receber') && this.negocio;
      return window.Comentario.contextoDoEcra({
        modo: this.modo, emGuia: this.emGuia, noDestino: this.noDestino, n: this.n, total: this.total, vista: this.vista,
        mesLabel: this.mes.label, mesTipo: this.mes.tipo, cenario: this.e.cenario, negocioNome: comItem ? this.negocio.nome : '',
        novaDesp: this.novaDesp, confPago: this.confPago, recEcra: this.recEcra, simPortal: this.simPortal,
      });
    },
    // Um rascunho, uma recusa ou um envio pendente ficam com o contexto em que foram escritos.
    // Só um comentário vazio, ou já enviado, passa a ser sobre o ecrã atual.
    abrirComentario() {
      const c = this.comentario;
      c.atual = this.contextoAtual();
      if (c.estado === 'enviado' || (c.estado === 'rascunho' && !c.texto.trim())) {
        Object.assign(c, { id: novoId(), texto: '', contexto: c.atual, estado: 'rascunho', erro: '' });
      }
      this.$refs.dialogoComentario.showModal();
      nextTick(() => { const t = document.getElementById('comentario-texto'); if (t) t.focus(); });
    },
    // Um texto ou um contexto diferente é outro comentário: recebe outro identificador.
    aoEditarComentario() { Object.assign(this.comentario, { id: novoId(), estado: 'rascunho', erro: '' }); },
    passarComentarioParaEcraAtual() { this.comentario.contexto = this.comentario.atual; this.aoEditarComentario(); },
    // Não cancela o envio pendente, que pode já ter sido recebido: começa outro comentário, com outro identificador.
    iniciarNovoComentario() { this.aoEditarComentario(); nextTick(() => document.getElementById('comentario-texto').focus()); },
    async enviarComentario() {
      const c = this.comentario;
      if (c.estado === 'a_enviar' || c.estado === 'enviado') return;
      const texto = c.texto.trim();
      if (!texto) { c.erro = 'Escreva a sua opinião antes de enviar.'; nextTick(() => document.getElementById('comentario-texto').focus()); return; }
      // Nova tentativa de um envio de resultado desconhecido: uma recusa agora não esclarece o que aconteceu ao primeiro pedido.
      const pendente = c.estado === 'desconhecido';
      c.erro = ''; c.estado = 'a_enviar';
      const controlo = new AbortController(); const relogio = setTimeout(() => controlo.abort(), 10000);
      let estado = 0; let corpo = null;
      try {
        const r = await fetch(this.comentariosUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: c.id, texto, contexto: c.contexto }), signal: controlo.signal });
        estado = r.status;
        try { corpo = await r.json(); } catch (erro) { corpo = null; }
      } catch (erro) { estado = 0; } finally { clearTimeout(relogio); }
      // Só a resposta da própria função confirma o envio: um 200 vindo de outro lado (uma página de erro, um proxy) não conta.
      const resposta = corpo !== null && typeof corpo === 'object' ? corpo.estado : '';
      if ((estado === 201 && resposta === 'guardado') || (estado === 200 && resposta === 'duplicado')) { c.estado = 'enviado'; return; }
      // Recusa clara de um primeiro envio: nada foi guardado e o texto pode ser corrigido.
      if (!pendente && ((estado >= 400 && estado < 500) || estado === 507)) {
        c.estado = 'falhou';
        c.erro = estado === 429 || estado === 507 ? 'De momento não é possível receber opiniões. O texto fica aqui; tente mais tarde.'
          : estado === 400 || estado === 413 ? 'O texto não foi aceite. Encurte-o e tente novamente.'
          : 'Não foi possível enviar. O texto fica aqui; tente novamente.';
        return;
      }
      // Sem resposta, erro do servidor, resposta que não é a da função, ou recusa de uma nova tentativa: o comentário pode ter sido guardado.
      // O texto, o contexto e o identificador ficam como estão até haver confirmação ou a pessoa iniciar um novo comentário.
      c.estado = 'desconhecido';
      c.erro = estado === 429 || estado === 507 ? 'Não foi possível confirmar o envio. O texto fica aqui; tente mais tarde.' : 'Não foi possível confirmar o envio. O texto fica aqui; tente novamente.';
    },
    fecharComentario() { this.$refs.dialogoComentario.close(); },
    aoFecharComentario() { nextTick(() => { const b = this.$refs.botaoComentar; if (b) b.focus(); }); },

    guardar() { escrever(CHAVES.geral, { modo: this.modo, demo: this.demo, guiaVisivel: this.guiaVisivel }); escrever(CHAVES.seis, this.s1); escrever(CHAVES.jornada, this.s2); },
    ir(v, id) { this.vista = v; if (id) this.negId = id; this.toast = ''; this.aviso = ''; this.avisoGuia = ''; this.copiado = ''; this.falhouCopia = ''; this.recEcra = 'lista'; this.recPasso = 1; this.simPortal = false; this.focar(); },
    bloqueado() { this.avisoGuia = 'Campos bloqueados: os dados desta visita já estão preenchidos.'; },
    mostrarGuia(v) { this.guiaVisivel = v; this.guardar(); },
    focar() { nextTick(() => { window.scrollTo(0, 0); const h = document.querySelector('[data-foco]'); if (h) h.focus(); }); },
    escolher(modo) { this.modo = modo; this.aRecomecar = false; this.sobre = false; this.copiado = ''; this.falhouCopia = ''; this.colado = {}; this.guardar(); if (modo === 'entrada') { this.focar(); return; } this.irDestino(); },
    setMes(k) { this.e.mesKey = k; this.guardar(); },
    mudarMes(d) { const i = this.meses.findIndex((m) => m.key === this.e.mesKey) + d; if (i >= 0 && i < this.meses.length) this.setMes(this.meses[i].key); },
    abrirDespesas() { this.ir('despesas'); },

    // Navegação da orientação: nunca executa operações.
    irN(n) { this.guiaAberta = null; if (this.seis) this.s1.ponto = n; else this.s2.passo = n; this.guardar(); this.irDestino(); },
    irDestino() {
      if (this.seis) {
        const p = SEIS.pontos[this.s1.ponto];
        if (!p) { this.ir('previsao'); return; }
        if (p.ir.mesKey) { this.s1.mesKey = p.ir.mesKey; this.s1.cenario = p.ir.cenario; this.guardar(); }
        this.ir(p.ir.vista, p.ir.negId);
      } else {
        const v = JORNADA.passos[this.s2.passo].v;
        this.s2.mesKey = '2026-11'; this.guardar(); // retomar a visita volta sempre a novembro
        this.ir(v, 't2');
      }
    },
    recomecar() {
      this.sobre = false; this.guiaVisivel = true; this.guiaAberta = null;
      if (this.seis) this.s1 = Object.assign({}, INI1); else this.s2 = Object.assign({}, INI2);
      Object.assign(this, { aRecomecar: false, novaDesp: false, confPago: false, recEcra: 'lista', copiado: '', falhouCopia: '', colado: {}, modoRecibo: '', numero: '' });
      this.guardar(); this.irDestino();
    },

    // Operações da visita guiada: só pelos botões da aplicação, uma única vez, e só com os pré-requisitos.
    feito(tipo, texto) { this.s2.ultimo = tipo; this.s2.mesKey = '2026-11'; this.guardar(); this.ir('previsao'); this.toast = texto; },
    guardarNegocio() { if (this.seis || this.s2.neg) return; this.s2.neg = true; this.feito('neg', 'Negócio guardado.'); },
    guardarDespesa() { if (this.seis || !this.s2.neg || this.s2.desp) return; this.s2.desp = true; this.novaDesp = false; this.feito('desp', 'Despesa guardada.'); },
    confirmarPagamento() { if (this.seis || !this.s2.desp || this.s2.pago) return; this.s2.pago = true; this.confPago = false; this.feito('pago', 'Pagamento da despesa confirmado.'); },
    confirmarRecebimento() { if (this.seis || !this.s2.neg || this.s2.rec) return; this.s2.rec = true; this.feito('rec', 'Recebimento registado.'); },
    registarRecibo() {
      if (this.seis || !this.s2.rec || this.s2.recibo) return;
      if (!this.modoRecibo) { this.aviso = 'Escolhe como queres registar o recibo.'; return; }
      this.s2.recibo = true; this.s2.reciboModo = this.modoRecibo; this.s2.reciboNum = this.numero; this.s2.ultimo = 'recibo'; this.guardar();
      this.recEcra = 'lista'; this.aviso = ''; this.toast = 'Recibo registado no Agentimo.'; this.focar();
    },

    // «Copiado» só depois de a cópia ter sucesso; se falhar, o valor fica selecionado para copiar à mão.
    async copiar(rotulo, valor) {
      let ok = false;
      if (navigator.clipboard && window.isSecureContext) { try { await navigator.clipboard.writeText(valor); ok = true; } catch (e) { ok = false; } }
      if (!ok) ok = this.copiarSemApi(valor);
      this.copiado = ok ? this.modo + '|' + rotulo : ''; this.falhouCopia = ok ? '' : this.modo + '|' + rotulo;
      if (!ok) nextTick(() => { const el = document.querySelector('input.manual'); if (el) { el.focus(); el.select(); } });
    },
    copiarSemApi(valor) {
      const t = document.createElement('textarea');
      t.value = valor; t.setAttribute('readonly', ''); t.style.position = 'fixed'; t.style.top = '0'; t.style.opacity = '0';
      document.body.appendChild(t); t.focus(); t.select(); t.setSelectionRange(0, valor.length);
      let ok = false; try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(t); return ok;
    },
  },
  mounted() { this.guardar(); if (this.modo !== 'entrada') this.irDestino(); },
}).mount('#app');
