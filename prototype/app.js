// Protótipo descartável do percurso principal. Não é código de produção.
// Não implementa nenhum motor de cálculo: os valores vêm de fixtures.js.
const { createApp, nextTick } = Vue;
const params = new URLSearchParams(location.search);
const FX = (params.get('f') || 'B').toUpperCase();
const SIM = params.get('sim') || '';
const DEMO = params.get('demo') || '';
const clone = (o) => JSON.parse(JSON.stringify(o));
const FASES = { potencial: 'Potencial', provavel: 'Provável', confirmado: 'Confirmado' };

function fmt(c) {
  const neg = c < 0;
  const s = String(Math.abs(c)).padStart(3, '0');
  const int = s.slice(0, -2).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  return (neg ? '−' : '') + int + ',' + s.slice(-2) + ' €';
}
// Regra de introdução numérica (fundação, 14.3): só dígitos e vírgula decimal.
function lerValor(txt) {
  const t = (txt || '').trim();
  if (!/^\d+(,\d{1,2})?$/.test(t)) return null;
  const [i, d = ''] = t.split(',');
  return Number(i) * 100 + Number((d + '00').slice(0, 2));
}
function lerPerc(txt) {
  const t = (txt || '').trim();
  return /^\d{1,3}(,\d{1,2})?$/.test(t) ? t.replace(/,0+$/, '') : null;
}
const isoParaPt = (iso) => iso.split('-').reverse().join('/');
const ptParaIso = (pt) => pt.split('/').reverse().join('-');
const ERRO_VALOR = 'Introduz o valor sem separadores de milhares: 5000,50.';
const ERRO_PERC = 'Introduz a percentagem só com algarismos: 12,5.';
const NAO_PREVISTO = 'Este protótipo só conhece os valores do exercício. Usa os valores indicados.';

createApp({
  data() {
    const f = clone(window.FIXTURES[FX] || window.FIXTURES.B);
    return {
      fx: FX, demo: DEMO, f, FASES,
      vista: 'previsao', cenario: 'confirmado', mesKey: f.mesAtual, negId: null,
      aberto: { proteger: false, como: false },
      aviso: '', toast: '',
      novo: null, fluxo: null, pedido: 0, falhou: false, tentouDesconhecido: false,
      usado: false, limite: '', exemplos: window.EXEMPLOS,
    };
  },
  computed: {
    mes() { return this.f.meses.find((m) => m.key === this.mesKey); },
    dados() { return (this.f.previsao[this.mesKey] || {})[this.cenario] || window.VAZIO; },
    proteger() { return this.dados.prot[0] + this.dados.prot[1] + this.dados.prot[2]; },
    negocio() { return this.f.negocios.find((n) => n.id === this.negId); },
    semNegocios() { return this.f.negocios.length === 0; },
    emFluxo() { return this.vista === 'novo' || this.vista === 'receber'; },
    cenarioNome() { return { confirmado: 'Confirmado', provavel: 'Provável', total: 'Total' }[this.cenario]; },
    cenarioTexto() {
      return {
        confirmado: 'Confirmado: só negócios confirmados e valores já recebidos.',
        provavel: 'Provável: junta os negócios prováveis aos confirmados.',
        total: 'Total: junta também os negócios potenciais.',
      }[this.cenario];
    },
  },
  methods: {
    fmt,
    pv(base) { return window.PREVIEWS[base]; },
    teu(key) { return ((this.f.previsao[key] || {})[this.cenario] || window.VAZIO).teu; },
    ir(v) { this.vista = v; this.aviso = ''; this.limite = ''; this.toast = ''; this.focar(); },
    abrirExemplo(f) { location.search = '?f=' + f + (this.demo ? '&demo=' + this.demo : '') + (SIM ? '&sim=' + SIM : ''); },
    reiniciar() { location.reload(); },
    dica(t) { return this.demo ? t : ''; },
    focar() { nextTick(() => { window.scrollTo(0, 0); const h = document.querySelector('[data-foco]'); if (h) h.focus(); }); },
    mudarMes(d) {
      const i = this.f.meses.findIndex((m) => m.key === this.mesKey) + d;
      if (i >= 0 && i < this.f.meses.length) this.mesKey = this.f.meses[i].key;
    },
    abrirNegocio(id) { this.negId = id; this.ir('negocio'); },
    estadoRecebimento(n) {
      const rec = n.partes.filter((p) => p.recebido).length;
      const porReceber = n.partes.filter((p) => !p.recebido).length;
      if (!rec) return 'Por receber';
      return porReceber ? 'Parcialmente recebido' : 'Recebido';
    },
    fora(o) { this.aviso = o + ': fora deste protótipo.'; },

    // Pré-visualização simulada do servidor: atraso, falha e respostas antigas.
    previsualizar(alvo, procurar) {
      const id = ++this.pedido;
      alvo.estado = 'a_calcular';
      const atraso = SIM === 'lento' ? 2500 : 450;
      setTimeout(() => {
        if (id !== this.pedido) return; // resposta para dados já alterados: ignorada
        if (SIM === 'falha' && !this.falhou) { this.falhou = true; alvo.estado = 'erro'; return; }
        const r = procurar();
        if (r == null) { alvo.estado = 'nao_previsto'; return; }
        alvo.valor = r; alvo.estado = 'ok';
      }, atraso);
    },

    // ---- Novo negócio (W1)
    abrirNovo() {
      if (!this.f.criar) { this.limite = 'criar'; return; }
      if (this.usado) { this.limite = 'usado'; return; }
      this.novo = { nome: '', agencia: '', perc: '50', mes: this.f.mesAtual, fase: '', erros: {}, parte: { estado: 'vazio', valor: null }, aGuardar: false };
      this.ir('novo');
    },
    novoMudou() {
      const n = this.novo; n.erros.agencia = ''; n.erros.perc = '';
      const a = lerValor(n.agencia); const p = lerPerc(n.perc);
      if (!n.agencia.trim() || !n.perc.trim()) { n.parte.estado = 'vazio'; this.pedido++; return; }
      if (a == null) { n.erros.agencia = ERRO_VALOR; n.parte.estado = 'vazio'; this.pedido++; return; }
      if (p == null) { n.erros.perc = ERRO_PERC; n.parte.estado = 'vazio'; this.pedido++; return; }
      this.previsualizar(n.parte, () => window.PARTES[a + ':' + p]);
    },
    guardarNovo() {
      const n = this.novo; const e = {};
      if (!n.nome.trim()) e.nome = 'Indica o nome do negócio.';
      if (!n.agencia.trim()) e.agencia = 'Indica a comissão da agência.';
      else if (lerValor(n.agencia) == null) e.agencia = ERRO_VALOR;
      if (lerPerc(n.perc) == null) e.perc = ERRO_PERC;
      if (!n.fase) e.fase = 'Escolhe a fase do negócio.';
      if (!e.agencia && !e.perc && n.parte.estado !== 'ok') e.geral = n.parte.estado === 'nao_previsto' ? NAO_PREVISTO : 'Aguarda o cálculo da tua parte.';
      n.erros = e;
      if (Object.keys(e).length) { this.focarErro(); return; }
      n.aGuardar = true;
      setTimeout(() => {
        const mes = this.f.meses.find((m) => m.key === n.mes);
        this.f.negocios.push({ id: 't2', nome: n.nome.trim(), agencia: lerValor(n.agencia), perc: lerPerc(n.perc), parte: n.parte.valor, fase: n.fase,
          partes: [{ id: 'p1', mes: mes.label, esperado: n.parte.valor }] });
        const T = window.T2_MES, V = window.VAZIO;
        this.f.meses.forEach((m) => { this.f.previsao[m.key] = { confirmado: V, provavel: V, total: V }; });
        this.f.previsao[n.mes] = { confirmado: n.fase === 'confirmado' ? T : V, provavel: n.fase === 'potencial' ? V : T, total: T };
        this.usado = true;
        this.mesKey = n.mes; this.novo = null; this.ir('previsao');
        this.toast = 'Negócio guardado. A previsão foi atualizada.';
      }, 500);
    },
    sairNovo() {
      const n = this.novo;
      if ((n.nome || n.agencia) && !n.confirmarSaida) { n.confirmarSaida = true; return; }
      this.novo = null; this.ir(this.semNegocios ? 'previsao' : 'negocios');
    },
    // O foco vai para o primeiro campo com erro; as mensagens têm role="alert".
    focarErro() {
      nextTick(() => {
        let el = document.querySelector('[aria-invalid="true"]');
        if (el && el.tagName === 'FIELDSET') el = el.querySelector('input');
        if (!el) el = document.querySelector('.erro');
        if (el) { if (el.focus) el.focus(); el.scrollIntoView({ block: 'center' }); }
      });
    },

    // ---- Registar ou corrigir recebimento (W4 a W6)
    abrirReceber(n, parte) {
      const correcao = !!parte.recebido;
      const base = correcao ? parte.recebido.base : parte.esperado;
      if (this.f.semRecebimentos) { this.limite = 'receber'; return; }
      if (this.usado) { this.limite = 'usado'; return; }
      if (!window.PREVIEWS[base] || !n.janela) { this.aviso = 'Este pagamento não está preparado neste protótipo.'; return; }
      this.fluxo = {
        passo: 'w4', neg: n, parte, correcao, baseEsperada: base, entraEsperado: window.PREVIEWS[base].entra,
        data: ptParaIso(correcao && parte.recebido.data ? parte.recebido.data : this.f.hoje), janela: n.janela,
        resposta: '', baseTxt: '', obsTxt: '', prev: { estado: 'vazio', valor: null },
        caso: null, opcao: '', origem: null, base: null, obs: null, confirmaDif: false, erros: {},
        envio: { estado: 'parado', chave: null, payload: null, msg: '' }, confirmarSaida: false,
      };
      this.ir('receber');
    },
    baseMudou() {
      const x = this.fluxo; x.erros.base = '';
      if (!x.baseTxt.trim()) { x.prev.estado = 'vazio'; this.pedido++; return; }
      const b = lerValor(x.baseTxt);
      if (b == null) { x.erros.base = ERRO_VALOR; x.prev.estado = 'vazio'; this.pedido++; return; }
      this.previsualizar(x.prev, () => window.PREVIEWS[b]);
    },
    continuarW4() {
      const x = this.fluxo; const e = {};
      if (!x.data) e.data = 'Indica a data do recebimento.';
      else if (x.data > ptParaIso(this.f.hoje)) e.data = 'A data não pode ser no futuro.';
      else if (x.data < x.janela[0] || x.data > x.janela[1]) e.data = 'Neste protótipo, a data tem de estar entre ' + isoParaPt(x.janela[0]) + ' e ' + isoParaPt(x.janela[1]) + '.';
      if (!x.resposta) e.resposta = 'Escolhe uma das opções.';
      let base = x.baseEsperada; let obs = null;
      if (x.resposta === 'outra') {
        base = lerValor(x.baseTxt);
        if (!x.baseTxt.trim()) e.base = 'Indica o valor da tua comissão.';
        else if (base == null) e.base = ERRO_VALOR;
        else if (x.prev.estado === 'a_calcular') e.base = 'Aguarda o cálculo.';
        else if (x.prev.estado !== 'ok') e.base = x.prev.estado === 'erro' ? 'Não foi possível calcular. Tenta novamente.' : NAO_PREVISTO;
      }
      if (x.resposta === 'outro_banco' || (x.resposta === 'outra' && x.obsTxt.trim())) {
        obs = lerValor(x.obsTxt);
        if (!x.obsTxt.trim()) e.obs = 'Indica o valor que entrou na conta.';
        else if (obs == null) e.obs = ERRO_VALOR;
      }
      const caso = base != null ? window.CASOS[x.neg.id + ':' + base] : null;
      if (!Object.keys(e).length && !caso) e.base = NAO_PREVISTO;
      x.erros = e;
      if (Object.keys(e).length) { this.focarErro(); return; }
      x.base = base; x.obs = obs; x.caso = caso; x.opcao = ''; x.origem = null; x.confirmaDif = false;
      x.passo = caso.residuo === 0 ? 'w6' : 'w5';
      this.focar();
    },
    continuarW5() {
      const x = this.fluxo;
      if (!x.opcao) { x.erros = { opcao: 'Escolhe uma das opções.' }; this.focarErro(); return; }
      x.erros = {};
      const o = this.opcaoEscolhida();
      if (o.origem) {
        x.origem = { agencia: String(x.neg.agencia / 100) + ',00', perc: x.neg.perc, prev: { estado: 'vazio', valor: null }, erros: {} };
        x.passo = 'w5c';
      } else { x.origem = null; x.passo = 'w6'; }
      this.focar();
    },
    opcaoEscolhida() { return this.fluxo.caso.opcoes.find((o) => o.id === this.fluxo.opcao); },
    origemMudou() {
      const x = this.fluxo; const g = x.origem; g.erros = {};
      const a = lerValor(g.agencia); const p = lerPerc(g.perc);
      if (a == null) { g.erros.agencia = ERRO_VALOR; g.prev.estado = 'vazio'; this.pedido++; return; }
      if (p == null) { g.erros.perc = ERRO_PERC; g.prev.estado = 'vazio'; this.pedido++; return; }
      const alvo = this.opcaoEscolhida().origem;
      this.previsualizar(g.prev, () => (a + ':' + p === alvo.chave ? alvo.linhas : null));
    },
    continuarW5c() {
      const g = this.fluxo.origem;
      if (g.prev.estado !== 'ok') { g.erros = { geral: g.prev.estado === 'a_calcular' ? 'Aguarda o cálculo.' : g.prev.estado === 'erro' ? 'Não foi possível calcular. Tenta novamente.' : NAO_PREVISTO }; this.focarErro(); return; }
      this.fluxo.passo = 'w6'; this.focar();
    },
    voltar() {
      const x = this.fluxo;
      if (x.passo === 'w6') x.passo = x.origem ? 'w5c' : x.caso.residuo === 0 ? 'w4' : 'w5';
      else if (x.passo === 'w5c') { x.origem = null; x.passo = 'w5'; }
      else if (x.passo === 'w5') x.passo = 'w4';
      this.focar();
    },
    sairFluxo() {
      const x = this.fluxo;
      if (x.envio.estado === 'desconhecido') return;
      if ((x.resposta || x.passo !== 'w4') && !x.confirmarSaida) { x.confirmarSaida = true; return; }
      this.fluxo = null; this.ir('negocio');
    },
    difObservada() { const x = this.fluxo; return x.obs != null ? x.obs - window.PREVIEWS[x.base].entra : 0; },
    confirmar() {
      const x = this.fluxo;
      if (this.difObservada() !== 0 && !x.confirmaDif) { x.erros = { dif: 'Confirma a diferença antes de registar.' }; this.focarErro(); return; }
      x.erros = {};
      // O conteúdo enviado fica fixo: uma repetição envia exatamente o mesmo, com a mesma chave.
      if (!x.envio.payload) {
        x.envio.chave = 'k-' + Math.random().toString(36).slice(2, 10);
        x.envio.payload = Object.freeze({ negocio: x.neg.id, parte: x.parte.id, data: x.data, base: x.base, observado: x.obs, opcao: x.opcao || null });
      }
      x.envio.estado = 'a_enviar'; x.envio.msg = '';
      setTimeout(() => {
        if (SIM === 'rejeitado') { x.envio.estado = 'rejeitado'; x.envio.payload = null; x.envio.msg = 'Não foi possível registar o recebimento. Nada foi alterado. Motivo: o negócio foi alterado noutra sessão.'; return; }
        if (SIM === 'desconhecido' && !this.tentouDesconhecido) { this.tentouDesconhecido = true; x.envio.estado = 'desconhecido'; return; }
        this.aplicar();
      }, 700);
    },
    aplicar() {
      const x = this.fluxo; const p = x.envio.payload;
      const id = x.caso.residuo === 0 ? x.caso.resultado : this.opcaoEscolhida().resultado;
      const r = clone(window.RESULTADOS[id]);
      const n = this.f.negocios.find((k) => k.id === p.negocio);
      Object.assign(n, r.negocio);
      const parte = n.partes.find((k) => k.id === p.parte);
      if (parte.recebido) { parte.recebido.data = isoParaPt(p.data); if (p.observado != null) parte.recebido.observado = p.observado; }
      Object.assign(this.f.previsao, r.previsao);
      this.usado = true;
      this.fluxo = null; this.negId = n.id; this.ir('negocio');
      this.toast = x.correcao ? 'Correção registada. A previsão foi atualizada.' : 'Recebimento registado. A previsão foi atualizada.';
      nextTick(() => { const t = document.querySelector('.toast'); if (t) t.focus(); });
    },
    isoParaPt,

  },
  mounted() { document.documentElement.dataset.pronto = '1'; },
}).mount('#app');
