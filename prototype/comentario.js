// Contexto de um comentário: o que a pessoa está a ver quando abre a janela. Função pura.
(function (raiz) {
  const CENARIOS = { confirmado: 'Confirmado', provavel: 'Provável', total: 'Total' };
  const RECIBOS = { folha: 'Recibos · preparar fatura-recibo', registar: 'Recibos · registar recibo' };

  function ecra(e) {
    if (e.simPortal) return 'Simulação do Portal';
    const item = e.negocioNome ? ' · ' + e.negocioNome : '';
    switch (e.vista) {
      case 'previsao':
        if (e.mesTipo === 'historico') return 'Histórico · ' + e.mesLabel;
        return 'Previsão · ' + e.mesLabel + ' · cenário ' + (CENARIOS[e.cenario] || e.cenario);
      case 'negocios': return 'Negócios';
      case 'negocio': return 'Negócio' + item;
      case 'novo': return 'Novo negócio';
      case 'receber': return 'Registar recebimento' + item;
      case 'despesas': return 'Despesas · ' + e.mesLabel + (e.novaDesp ? ' · nova despesa' : e.confPago ? ' · confirmar pagamento' : '');
      case 'recibos': return RECIBOS[e.recEcra] || 'Recibos';
      default: return String(e.vista);
    }
  }

  // Demonstração, passo acompanhado ou exploração livre, ecrã e o que nele está aberto.
  function contextoDoEcra(e) {
    const seis = e.modo === 'seis';
    const guia = e.emGuia && e.noDestino ? (seis ? 'Ponto ' : 'Passo ') + e.n + ' de ' + e.total : 'exploração livre';
    return [seis ? 'Seis meses de atividade' : 'Visita guiada', guia, ecra(e)].join(' · ');
  }

  const api = { contextoDoEcra };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.Comentario = api;
})(typeof window !== 'undefined' ? window : globalThis);
