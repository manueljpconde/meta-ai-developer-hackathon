import test from 'node:test';
import assert from 'node:assert/strict';
import { criarManipulador } from '../publicacao/servico/comentario-servico.js';

const ORIGEM = 'https://demo.agentimo.propware.pt';
const ID1 = '11111111-1111-4111-8111-111111111111';
const ID2 = '22222222-2222-4222-8222-222222222222';
const CONTEXTO = 'Seis meses de atividade · Ponto 1 de 3 · Previsão · novembro 2026 · cenário Confirmado';

function loja() {
  const ficheiros = new Map();
  return {
    ficheiros,
    ler: async (c) => (ficheiros.has(c) ? ficheiros.get(c) : null),
    guardar: async (c, t) => { if (ficheiros.has(c)) throw new Error('já existe'); ficheiros.set(c, t); },
    contar: async () => ficheiros.size,
  };
}
const valido = (m = {}) => ({ id: ID1, texto: 'O valor a proteger devia estar mais visível.', contexto: CONTEXTO, ...m });
function pedido(corpo, { metodo = 'POST', origem = ORIGEM, tipo = 'application/json', cabecalhos = {} } = {}) {
  const h = { host: 'demo.agentimo.propware.pt', 'x-forwarded-for': '203.0.113.9', 'user-agent': 'NavegadorDeTeste/1.0', ...cabecalhos };
  if (origem) h.origin = origem;
  if (tipo) h['content-type'] = tipo;
  const body = metodo === 'POST' ? (typeof corpo === 'string' ? corpo : JSON.stringify(corpo)) : undefined;
  return new Request(ORIGEM + '/api/comentario', { method: metodo, headers: h, body });
}
const novo = (l, opcoes = {}) => criarManipulador({ ler: l.ler, guardar: l.guardar, contar: l.contar, agora: () => new Date('2026-10-05T10:20:30.456Z'), ...opcoes });

test('guarda um ficheiro com o texto e o contexto exatos', async () => {
  const l = loja();
  const r = await novo(l)(pedido(valido()));
  assert.equal(r.status, 201);
  assert.deepEqual(await r.json(), { estado: 'guardado' });
  assert.deepEqual([...l.ficheiros.keys()], ['comentarios/' + ID1 + '.json']);
  assert.deepEqual(JSON.parse(l.ficheiros.get('comentarios/' + ID1 + '.json')), {
    versao: 1, id: ID1, recebido_em: '2026-10-05T10:20:30Z', texto: 'O valor a proteger devia estar mais visível.', contexto: CONTEXTO,
  });
});

test('não guarda o endereço IP nem o agente do browser', async () => {
  const l = loja();
  await novo(l)(pedido(valido()));
  const texto = [...l.ficheiros.values()][0];
  assert.ok(!texto.includes('203.0.113.9'));
  assert.ok(!texto.includes('NavegadorDeTeste'));
});

test('as respostas não ficam em cache', async () => {
  const r = await novo(loja())(pedido(valido()));
  assert.equal(r.headers.get('cache-control'), 'no-store');
});

test('apara o texto', async () => {
  const l = loja();
  await novo(l)(pedido(valido({ texto: '  com espaços  \n' })));
  assert.equal(JSON.parse([...l.ficheiros.values()][0]).texto, 'com espaços');
});

test('mesmo id e mesmo conteúdo é duplicado, sem segundo ficheiro', async () => {
  const l = loja(); const tratar = novo(l);
  await tratar(pedido(valido()));
  const r = await tratar(pedido(valido()));
  assert.equal(r.status, 200);
  assert.deepEqual(await r.json(), { estado: 'duplicado' });
  assert.equal(l.ficheiros.size, 1);
});

test('mesmo id com outro conteúdo é conflito', async () => {
  const l = loja(); const tratar = novo(l);
  await tratar(pedido(valido()));
  assert.equal((await tratar(pedido(valido({ texto: 'Outro texto.' })))).status, 409);
  assert.equal((await tratar(pedido(valido({ contexto: 'Outro ecrã' })))).status, 409);
  assert.equal(l.ficheiros.size, 1);
});

test('leitura desatualizada seguida de escrita recusada: reconhece o que já está guardado', async () => {
  const l = loja();
  await novo(l)(pedido(valido()));
  // A primeira leitura deste pedido ainda não vê o ficheiro; a escrita falha porque ele já existe.
  let primeira = true;
  const ler = async (c) => { if (primeira) { primeira = false; return null; } return l.ler(c); };
  const r = await novo(l, { ler })(pedido(valido()));
  assert.equal(r.status, 200);
  assert.equal(l.ficheiros.size, 1);
});

// Loja em que a leitura demora: dois pedidos lançados juntos leem ambos antes de qualquer um escrever.
function lojaLenta() {
  const l = loja();
  return { ...l, ler: async (c) => { const v = await l.ler(c); await new Promise((r) => setTimeout(r, 5)); return v; } };
}

test('dois pedidos sobrepostos com o mesmo id e o mesmo conteúdo guardam um só comentário', async () => {
  const l = lojaLenta(); const tratar = novo(l);
  const respostas = await Promise.all([tratar(pedido(valido())), tratar(pedido(valido()))]);
  assert.deepEqual(respostas.map((r) => r.status).sort(), [200, 201]);
  assert.equal(l.ficheiros.size, 1);
});

test('dois pedidos sobrepostos com o mesmo id e conteúdo diferente: um guarda, o outro é conflito', async () => {
  const l = lojaLenta(); const tratar = novo(l);
  const respostas = await Promise.all([tratar(pedido(valido())), tratar(pedido(valido({ texto: 'Outro texto.' })))]);
  assert.deepEqual(respostas.map((r) => r.status).sort(), [201, 409]);
  assert.equal(l.ficheiros.size, 1);
});

test('pedido de outra origem, ou sem origem, é recusado', async () => {
  const l = loja(); const tratar = novo(l);
  assert.equal((await tratar(pedido(valido(), { origem: 'https://exemplo.pt' }))).status, 403);
  assert.equal((await tratar(pedido(valido(), { origem: 'http://demo.agentimo.propware.pt' }))).status, 403);
  assert.equal((await tratar(pedido(valido(), { origem: null }))).status, 403);
  assert.equal(l.ficheiros.size, 0);
});

test('aceita o endereço vercel.app do mesmo projeto, por ser a mesma origem do pedido', async () => {
  const l = loja();
  const r = await novo(l)(pedido(valido(), { origem: 'https://agentimo-demo.vercel.app', cabecalhos: { host: 'agentimo-demo.vercel.app' } }));
  assert.equal(r.status, 201);
});

test('só aceita POST', async () => {
  const tratar = novo(loja());
  for (const metodo of ['GET', 'PUT', 'DELETE', 'PATCH']) assert.equal((await tratar(pedido(null, { metodo }))).status, 405, metodo);
});

test('só aceita JSON', async () => {
  const tratar = novo(loja());
  assert.equal((await tratar(pedido(valido(), { tipo: 'text/plain' }))).status, 415);
  assert.equal((await tratar(pedido('{nao e json'))).status, 400);
  assert.equal((await tratar(pedido('[1,2]'))).status, 400);
});

test('corpo demasiado grande', async () => {
  const l = loja();
  assert.equal((await novo(l)(pedido(JSON.stringify(valido({ contexto: 'c'.repeat(17000) }))))).status, 413);
  assert.equal(l.ficheiros.size, 0);
});

test('corpo anunciado como demasiado grande é recusado pelo cabeçalho, sem ser lido', async () => {
  const l = loja();
  const r = await novo(l)(pedido(valido(), { cabecalhos: { 'content-length': '20000' } }));
  assert.equal(r.status, 413);
  assert.equal(l.ficheiros.size, 0);
});

test('corpo enviado em pedaços, sem tamanho anunciado: a leitura para no limite', async () => {
  const l = loja(); let lidos = 0; let cancelado = false;
  const pedaco = new Uint8Array(4096).fill(97);
  const corpo = new ReadableStream({
    pull(c) { if (lidos >= 5 * 1024 * 1024) { c.close(); return; } lidos += pedaco.length; c.enqueue(pedaco); },
    cancel() { cancelado = true; },
  }, { highWaterMark: 0 });
  const r = await novo(l)(new Request(ORIGEM + '/api/comentario', { method: 'POST', duplex: 'half', body: corpo, headers: { host: 'demo.agentimo.propware.pt', origin: ORIGEM, 'content-type': 'application/json' } }));
  assert.equal(r.status, 413);
  assert.ok(cancelado, 'a leitura devia ser interrompida');
  assert.ok(lidos <= 16384 + 2 * 4096, 'foram lidos ' + lidos + ' bytes de um corpo de 5 MB');
  assert.equal(l.ficheiros.size, 0);
});

test('2 000 caracteres são aceites seja qual for o seu tamanho em bytes', async () => {
  const casos = { acentos: 'ç'.repeat(2000), simbolos: '€'.repeat(2000), emoji: '😀'.repeat(1000), aspas: '"'.repeat(2000), controlo: '\u0001'.repeat(2000) };
  let n = 0;
  for (const [nome, texto] of Object.entries(casos)) {
    assert.equal(texto.length, 2000, nome);
    const l = loja();
    const id = '0000000' + (n++) + '-0000-4000-8000-000000000000';
    assert.equal((await novo(l)(pedido(valido({ id, texto })))).status, 201, nome);
    assert.equal(JSON.parse([...l.ficheiros.values()][0]).texto, texto, nome);
  }
  assert.equal((await novo(loja())(pedido(valido({ texto: '😀'.repeat(1000) + 'a' })))).status, 400, '2 001 caracteres');
});

test('texto vazio, só com espaços ou demasiado longo', async () => {
  const l = loja(); const tratar = novo(l);
  assert.equal((await tratar(pedido(valido({ texto: '' })))).status, 400);
  assert.equal((await tratar(pedido(valido({ texto: '   \n ' })))).status, 400);
  assert.equal((await tratar(pedido(valido({ texto: 'a'.repeat(2001) })))).status, 400);
  assert.equal((await tratar(pedido(valido({ texto: 42 })))).status, 400);
  assert.equal((await tratar(pedido(valido({ texto: 'a'.repeat(2000) })))).status, 201);
});

test('id ou contexto inválidos, e campos a mais', async () => {
  const l = loja(); const tratar = novo(l);
  for (const m of [{ id: 'abc' }, { id: '../' + ID1 }, { id: 7 }, { contexto: '' }, { contexto: 'c'.repeat(301) }, { contexto: { a: 1 } }, { email: 'a@b.pt' }]) {
    assert.equal((await tratar(pedido(valido(m)))).status, 400, JSON.stringify(m));
  }
  assert.equal(l.ficheiros.size, 0);
});

test('loja no limite: recusa sem guardar (o limite é aproximado quando há pedidos sobrepostos)', async () => {
  const l = loja(); const tratar = novo(l, { maxFicheiros: 1 });
  assert.equal((await tratar(pedido(valido()))).status, 201);
  assert.equal((await tratar(pedido(valido({ id: ID2 })))).status, 507);
  assert.equal(l.ficheiros.size, 1);
  assert.equal((await tratar(pedido(valido()))).status, 200, 'um reenvio do que já está guardado continua a ser reconhecido');
});

test('se o armazenamento falhar, responde 503 e nunca diz que guardou', async () => {
  const l = loja();
  const falha = async () => { throw new Error('indisponível'); };
  assert.equal((await novo(l, { guardar: falha })(pedido(valido()))).status, 503);
  assert.equal((await novo(l, { ler: falha })(pedido(valido()))).status, 503);
  assert.equal((await novo(l, { contar: falha })(pedido(valido()))).status, 503);
  assert.equal(l.ficheiros.size, 0);
});

test('não escreve o texto do comentário nos registos', async () => {
  const escrito = [];
  const originais = { log: console.log, error: console.error, warn: console.warn };
  console.log = console.error = console.warn = (...a) => escrito.push(a.join(' '));
  try {
    const l = loja();
    await novo(l)(pedido(valido({ texto: 'segredo-do-comentario' })));
    await novo(l, { guardar: async () => { throw new Error('indisponível'); } })(pedido(valido({ id: ID2, texto: 'segredo-do-comentario' })));
  } finally { Object.assign(console, originais); }
  assert.ok(!escrito.join('\n').includes('segredo-do-comentario'));
});
