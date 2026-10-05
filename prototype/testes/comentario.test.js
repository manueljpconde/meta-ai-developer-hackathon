const test = require('node:test');
const assert = require('node:assert/strict');
const { contextoDoEcra } = require('../comentario.js');

const base = { modo: 'seis', emGuia: true, noDestino: true, n: 1, total: 3, vista: 'previsao', mesLabel: 'novembro 2026', mesTipo: 'atual', cenario: 'confirmado', negocioNome: '', novaDesp: false, confPago: false, recEcra: 'lista', simPortal: false };

test('previsão de novembro, cenário Confirmado, num ponto acompanhado', () => {
  assert.equal(contextoDoEcra(base), 'Seis meses de atividade · Ponto 1 de 3 · Previsão · novembro 2026 · cenário Confirmado');
});

test('visita guiada num passo acompanhado', () => {
  assert.equal(contextoDoEcra({ ...base, modo: 'jornada', n: 3, total: 7 }), 'Visita guiada · Passo 3 de 7 · Previsão · novembro 2026 · cenário Confirmado');
});

test('fora do destino do passo é exploração livre', () => {
  assert.equal(contextoDoEcra({ ...base, noDestino: false, cenario: 'total' }), 'Seis meses de atividade · exploração livre · Previsão · novembro 2026 · cenário Total');
});

test('depois dos pontos de orientação é exploração livre', () => {
  assert.equal(contextoDoEcra({ ...base, emGuia: false, n: 4, cenario: 'provavel' }), 'Seis meses de atividade · exploração livre · Previsão · novembro 2026 · cenário Provável');
});

test('mês histórico chama-se Histórico e não tem cenário', () => {
  assert.equal(contextoDoEcra({ ...base, emGuia: false, mesLabel: 'setembro 2026', mesTipo: 'historico' }), 'Seis meses de atividade · exploração livre · Histórico · setembro 2026');
});

test('o ecrã de um negócio diz qual é o negócio', () => {
  assert.equal(contextoDoEcra({ ...base, n: 2, vista: 'negocio', negocioNome: 'T3 Av. de Roma · Ref 2841' }), 'Seis meses de atividade · Ponto 2 de 3 · Negócio · T3 Av. de Roma · Ref 2841');
});

test('ecrã de negócio sem negócio não produz "undefined"', () => {
  assert.equal(contextoDoEcra({ ...base, modo: 'jornada', total: 7, vista: 'negocio', negocioNome: '' }), 'Visita guiada · Passo 1 de 7 · Negócio');
});

test('registar recebimento diz de que negócio', () => {
  assert.equal(contextoDoEcra({ ...base, modo: 'jornada', n: 5, total: 7, vista: 'receber', negocioNome: 'T3 Telheiras' }), 'Visita guiada · Passo 5 de 7 · Registar recebimento · T3 Telheiras');
});

test('despesas: mês e subvista', () => {
  const d = { ...base, modo: 'jornada', n: 4, total: 7, vista: 'despesas' };
  assert.equal(contextoDoEcra(d), 'Visita guiada · Passo 4 de 7 · Despesas · novembro 2026');
  assert.equal(contextoDoEcra({ ...d, novaDesp: true }), 'Visita guiada · Passo 4 de 7 · Despesas · novembro 2026 · nova despesa');
  assert.equal(contextoDoEcra({ ...d, confPago: true }), 'Visita guiada · Passo 4 de 7 · Despesas · novembro 2026 · confirmar pagamento');
});

test('recibos: subvista', () => {
  const r = { ...base, modo: 'jornada', n: 6, total: 7, vista: 'recibos' };
  assert.equal(contextoDoEcra(r), 'Visita guiada · Passo 6 de 7 · Recibos');
  assert.equal(contextoDoEcra({ ...r, recEcra: 'folha' }), 'Visita guiada · Passo 6 de 7 · Recibos · preparar fatura-recibo');
  assert.equal(contextoDoEcra({ ...r, recEcra: 'registar' }), 'Visita guiada · Passo 6 de 7 · Recibos · registar recibo');
});

test('a simulação do Portal é um ecrã próprio', () => {
  assert.equal(contextoDoEcra({ ...base, modo: 'jornada', n: 6, total: 7, vista: 'recibos', recEcra: 'folha', simPortal: true }), 'Visita guiada · Passo 6 de 7 · Simulação do Portal');
});

test('um ecrã desconhecido aparece pelo seu nome, nunca "undefined"', () => {
  assert.equal(contextoDoEcra({ ...base, vista: 'ecra-novo' }), 'Seis meses de atividade · Ponto 1 de 3 · ecra-novo');
});
