# "Comentar este ecrã" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person exploring the self-guided demonstration send an opinion about the screen they are looking at, with the context shown when the window opened, without interrupting the visit or touching its saved progress.

**Architecture:** A pure function describes the open screen. A native `<dialog>` in the demonstration bar (outside the application frame) collects the text and posts it to a Vercel Function on the same origin. The function validates the request and writes one JSON file per comment to a private Vercel Blob store, authenticated by the platform (OIDC), so no credential exists in the frontend or in the repository. Static files move under `public/` so that nothing else in the deployment is served.

**Tech Stack:** Vue 3 global build (already vendored), plain JavaScript, Vercel Functions (Node.js runtime, web `fetch` handler), `@vercel/blob` >= 2.3 (private storage), Vercel CLI >= 50.20 (installed: 54.18.7), Node's built-in test runner (`node --test`, Node 20), a browser test page.

**Spec:** [issue #12](https://github.com/CrmWare/propware-agentimo/issues/12) (scope, acceptance criteria 1 to 7, out of scope); `docs/superpowers/specs/2026-10-04-ux-design.md` section 5.2; the `stakeholder-demo` skill, section "Collect Feedback Proportionately" (integrated submission, approved by the product owner on 5 October 2026).

**Supersedes:** two earlier versions of this plan: a service on the Hetzner server (the demonstration has since moved to Vercel) and a handoff by email or copy with no service.

## Global Constraints

- **No commit, push or publication without explicit approval.** Every "Commit" step, Task 4 and the issue comment of Task 5 are gates: stop and ask.
- The demonstration is live at `https://demo.agentimo.propware.pt` (Vercel project `agentimo-demo`, team `crmware`) and has been sent to the president of API Portugal. Nothing may interrupt a visit or discard saved progress.
- `VERSAO` in `prototype/demo.js` stays exactly `'2026-10-04.8'`, and the stored state under `agentimo-demo`, `agentimo-demo-seis` and `agentimo-demo-jornada` keeps its shape. Nothing about a comment is written to `localStorage`.
- The comment control lives in the demonstration bar, outside `.app-moldura`. Nothing about comments appears inside the application frame.
- The window never opens by itself, and feedback is never required.
- No account, name or email is asked for. The stored file holds no IP address, no user agent and no other identifier. The function never logs the text of a comment.
- The window does not claim anonymity: the notice says that the hosting records technical data of the request.
- No credential in the frontend or in the repository. Comments are not readable over the web: the Blob store is private and no route serves it.
- A draft stays attached to the screen it was written for. It is never moved to another screen silently.
- A submission whose outcome is unknown is not editable: the same request is repeated with the same id.
- Success is shown only when the answer is recognisably the function's own: the expected status together with the expected body. Any other answer, including a 200 from something else, is an unknown outcome.
- Tests never write to the store that receives real comments, except one reserved test id in the production check, deleted by its exact path.
- Comments are about a screen. No element selection, screenshots, session recording, star ratings or behavioural tracking.
- No change to the production product or to the financial data of the demonstration.
- Interface copy is European Portuguese. The comment window addresses the visitor formally ("a sua opinião").
- The only new dependency is `@vercel/blob`, pinned to an exact version with a lockfile (`prototype/publicacao/package-lock.json`, created with `npm install --package-lock-only`): the duplicate and conflict guarantees depend on how the library's `get` and `put` behave, so a redeploy must not pick up a new version silently.

## Decisions proposed for confirmation

| Decision | Proposal |
| --- | --- |
| Destination | One JSON file per comment, `comentarios/<id>.json`, in a private Vercel Blob store named `agentimo-demo-comentarios`, region `fra1` (Frankfurt), connected to production only. Preview deployments use a second private store, `agentimo-demo-comentarios-testes` |
| Who can read them | Members of the Vercel team `crmware`, with the CLI (`vercel blob list`, `vercel blob get`) or the dashboard. No route serves them |
| Retention | Never kept more than 90 days after receipt, and all deleted when the demonstration is withdrawn. The product owner reviews the store every 30 days and deletes what is older than 60 days, following `prototype/publicacao/COMENTARIOS.md` (Task 5) |
| Notice shown | "Enviamos este texto e o contexto acima. Não pedimos o seu nome nem o seu email. O alojamento regista dados técnicos do pedido, como o endereço IP, durante um período limitado." |
| Duplicates | The client generates one id per comment; the same id with the same content is answered as already stored |
| Unknown outcome | No answer, a timeout, a 5xx or an answer that is not the function's: the text is locked and the same request is repeated with the same id. A refusal of a repeated request (for example a 429 from the firewall) does not settle what happened to the first one: the comment stays locked, with the same id and content, until a valid confirmation arrives. The visitor can start a new comment instead, after being told that the earlier one may already have been received |
| Abuse of a public endpoint | Text at most 2 000 characters (the same count in the window and in the function), body at most 16 384 bytes (enough for any 2 000 characters once encoded), requests from another origin refused, and a Vercel Firewall rule of 5 requests per minute per IP on `POST /api/comentario`. The store stops accepting at about 500 comments: this is an approximate ceiling, because counting and writing are separate operations and concurrent requests can pass it by a few |
| What the hosting records | Vercel's request logs and firewall see the IP address and user agent of every request, comment or not. This is outside the function's control and is what the notice discloses |

## Review Focus

1. **A draft reopened on another screen.** It keeps the context it was written for until the visitor moves it explicitly. Browser test in Task 3.
2. **Double tap on "Enviar opinião", or a retry after a lost answer.** One stored comment. Button disabled while sending (Task 3 test); same id and content answered as a duplicate, and same id with other content as a conflict, including when the two requests overlap (Task 2 tests, repeated against the real store in Task 4).
3. **Storage unavailable or full, or an answer that is not the function's.** A failed write answers 503 and never 201; a full store answers 507; a 200 carrying HTML or unexpected JSON is not a success. The window keeps the text, context and id and shows no success (Task 2 and Task 3 tests).
4. **Whitespace-only, over-long or multi-byte text.** Whitespace-only and over-long text is refused in the window before any request (Task 3 test) and by the function; 2 000 characters of accented text, symbols or emoji are accepted (Task 2 tests).
5. **The journey's negócio screen before a negócio exists, or an unknown screen.** The context never contains "undefined" (Task 1 tests).

---

## File Structure

| File | Responsibility |
| --- | --- |
| `prototype/comentario.js` (create) | Pure function: the context of the open screen. Works in the browser and in Node |
| `prototype/testes/comentario.test.js` (create) | Node tests for the context |
| `prototype/publicacao/servico/comentario-servico.js` (create) | The request handler, with storage injected. No platform code |
| `prototype/testes/comentario-servico.test.mjs` (create) | Node tests for the handler, with an in-memory store |
| `prototype/publicacao/api/comentario.js` (create) | The Vercel Function: connects the handler to the private Blob store |
| `prototype/publicacao/package.json` (create) | ES modules and the `@vercel/blob` dependency for the deployment |
| `prototype/publicacao/COMENTARIOS.md` (create) | How to read the comments, and the retention procedure |
| `prototype/publicacao/config.js` (modify) | Turns the comment control on in the published demonstration |
| `prototype/publicar.sh` (modify) | Builds the deployment folder with static files under `public/` |
| `prototype/demo.html`, `prototype/demo.js`, `prototype/styles.css` (modify) | The button, the window and its state. `VERSAO` untouched |
| `prototype/testes/comentario.test.html` (create) | Browser test page that drives `demo.html` in an iframe |
| `docs/superpowers/specs/2026-10-04-ux-design.md` (modify) | Section 5.6 recording the behaviour |

---

### Task 1: Context of the open screen

**Files:**
- Create: `prototype/comentario.js`
- Test: `prototype/testes/comentario.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces, as `module.exports` in Node and `window.Comentario` in the browser: `contextoDoEcra(e) -> string`, with `e = { modo: 'seis'|'jornada', emGuia: boolean, noDestino: boolean, n: number, total: number, vista: string, mesLabel: string, mesTipo: 'historico'|'atual'|'futuro', cenario: string, negocioNome: string, novaDesp: boolean, confPago: boolean, recEcra: 'lista'|'folha'|'registar', simPortal: boolean }`. The longest possible result is under 300 characters.

- [ ] **Step 1: Write the failing tests**

Create `prototype/testes/comentario.test.js`:

```js
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd prototype && node --test testes/comentario.test.js`
Expected: FAIL with `Cannot find module '../comentario.js'`.

- [ ] **Step 3: Write the implementation**

Create `prototype/comentario.js`:

```js
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd prototype && node --test testes/comentario.test.js`
Expected: `# pass 12`, `# fail 0`.

- [ ] **Step 5: Commit (gate: only with explicit approval)**

```bash
git add prototype/comentario.js prototype/testes/comentario.test.js
git commit -m "feat(demo): describe the open screen for a comment"
```

---

### Task 2: The function that stores one file per comment

**Files:**
- Create: `prototype/publicacao/package.json`
- Create: `prototype/publicacao/servico/comentario-servico.js`
- Create: `prototype/publicacao/api/comentario.js`
- Test: `prototype/testes/comentario-servico.test.mjs`

**Interfaces:**
- Consumes: the request body produced by Task 3: `{"id": "<uuid>", "texto": "<1 to 2000 characters>", "contexto": "<1 to 300 characters>"}`.
- Produces:
  - `criarManipulador({ ler, guardar, contar, agora?, maxFicheiros? }) -> (request: Request) => Promise<Response>`, where `ler(caminho) -> Promise<string|null>`, `guardar(caminho, conteudo) -> Promise<void>` (rejects if the path already exists) and `contar() -> Promise<number>`.
  - `POST /api/comentario` answers: `201 {"estado":"guardado"}`, `200 {"estado":"duplicado"}` (same id, same content), `409` (same id, other content; also when the two requests overlap), `400` (invalid body), `403` (not same-origin), `405` (not POST), `413` (body over 16 384 bytes), `415` (not JSON), `507` (store at its approximate limit), `503` (storage failed; the comment may or may not be stored).
  - One file per comment at `comentarios/<id>.json`: `{"versao": 1, "id", "recebido_em", "texto", "contexto"}`.

- [ ] **Step 1: Write the failing tests**

Create `prototype/testes/comentario-servico.test.mjs`:

```js
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
```

- [ ] **Step 2: Create the deployment's `package.json` and run the tests to verify they fail**

Create `prototype/publicacao/package.json`:

```json
{
  "name": "agentimo-demo",
  "private": true,
  "type": "module",
  "engines": { "node": "22.x" },
  "dependencies": {
    "@vercel/blob": "2.8.0"
  }
}
```

Run: `cd prototype && node --test testes/comentario-servico.test.mjs`
Expected: FAIL with `Cannot find module` for `comentario-servico.js`.

- [ ] **Step 3: Write the handler**

Create `prototype/publicacao/servico/comentario-servico.js`:

```js
// Recebe um comentário da demonstração e guarda um ficheiro JSON por comentário.
// Não guarda endereço IP, agente do browser nem outra identificação, e nunca escreve o texto nos registos.
// 2 000 caracteres de texto e 300 de contexto cabem sempre: cada um ocupa no máximo 6 bytes depois de codificado em JSON.
const MAX_CORPO = 16384;
const MAX_TEXTO = 2000;
const MAX_CONTEXTO = 300;
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function responder(estado, corpo) {
  return new Response(corpo ? JSON.stringify(corpo) : null, {
    status: estado,
    headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' },
  });
}

// Lê o corpo até ao limite e devolve-o como texto, ou null se o ultrapassar.
// Um pedido sem tamanho anunciado não chega a ser guardado em memória para lá do limite.
async function lerCorpo(request) {
  if (!request.body) return '';
  const leitor = request.body.getReader();
  const partes = []; let total = 0;
  for (;;) {
    const { done, value } = await leitor.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_CORPO) { await leitor.cancel(); return null; }
    partes.push(value);
  }
  return new TextDecoder().decode(Buffer.concat(partes));
}

// Devolve { id, texto, contexto } normalizados, ou null se o corpo não for válido.
function validar(corpo) {
  if (corpo === null || typeof corpo !== 'object' || Array.isArray(corpo)) return null;
  if (Object.keys(corpo).sort().join() !== 'contexto,id,texto') return null;
  const { id, texto, contexto } = corpo;
  if (typeof id !== 'string' || !ID.test(id)) return null;
  if (typeof texto !== 'string' || typeof contexto !== 'string') return null;
  const aparado = texto.trim();
  if (aparado.length < 1 || aparado.length > MAX_TEXTO) return null;
  if (contexto.length < 1 || contexto.length > MAX_CONTEXTO) return null;
  return { id, texto: aparado, contexto };
}

const igual = (guardado, c) => {
  try { const g = JSON.parse(guardado); return g.texto === c.texto && g.contexto === c.contexto; } catch (erro) { return false; }
};

export function criarManipulador({ ler, guardar, contar, agora = () => new Date(), maxFicheiros = 500 }) {
  return async function tratar(request) {
    if (request.method !== 'POST') return responder(405);
    // Só a própria página pode enviar: a origem do pedido tem de ser o endereço que o recebeu.
    if (request.headers.get('origin') !== 'https://' + request.headers.get('host')) return responder(403);
    if (!(request.headers.get('content-type') || '').toLowerCase().startsWith('application/json')) return responder(415);
    if (Number(request.headers.get('content-length') || 0) > MAX_CORPO) return responder(413);
    const bruto = await lerCorpo(request);
    if (bruto === null) return responder(413);
    let c;
    try { c = validar(JSON.parse(bruto)); } catch (erro) { c = null; }
    if (!c) return responder(400);

    const caminho = 'comentarios/' + c.id + '.json';
    try {
      const antigo = await ler(caminho);
      if (antigo !== null) return igual(antigo, c) ? responder(200, { estado: 'duplicado' }) : responder(409);
      // Teto aproximado: contar e escrever são operações separadas, e pedidos sobrepostos podem passá-lo por alguns ficheiros.
      if (await contar() >= maxFicheiros) return responder(507);
      const registo = { versao: 1, id: c.id, recebido_em: agora().toISOString().replace(/\.\d{3}Z$/, 'Z'), texto: c.texto, contexto: c.contexto };
      try {
        await guardar(caminho, JSON.stringify(registo, null, 2) + '\n');
      } catch (erro) {
        // Outro pedido com o mesmo id pode ter escrito entretanto: o que lá está decide a resposta.
        const agoraGuardado = await ler(caminho);
        if (agoraGuardado === null) throw erro;
        return igual(agoraGuardado, c) ? responder(200, { estado: 'duplicado' }) : responder(409);
      }
      return responder(201, { estado: 'guardado' });
    } catch (erro) {
      console.error('comentario: armazenamento indisponível');
      return responder(503);
    }
  };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd prototype && node --test testes/comentario-servico.test.mjs`
Expected: `# pass 22`, `# fail 0`.

- [ ] **Step 5: Write the Vercel Function**

Create `prototype/publicacao/api/comentario.js`. It has no logic of its own to test locally; it is verified on a preview deployment in Task 4.

```js
// Função da Vercel: liga o serviço de comentários à loja Blob privada do projeto.
// A loja é escolhida e autenticada pelo token que a Vercel entrega à função como variável de ambiente cifrada,
// um por ambiente (produção e pré-visualização). Não há chave no código nem no repositório.
import { get, list, put } from '@vercel/blob';
import { criarManipulador } from '../servico/comentario-servico.js';

const PREFIXO = 'comentarios/';

const tratar = criarManipulador({
  // Leitura direta da origem, sem cache: um comentário acabado de guardar tem de ser visto por um reenvio.
  async ler(caminho) {
    const r = await get(caminho, { access: 'private', useCache: false });
    return r && r.statusCode === 200 ? await new Response(r.stream).text() : null;
  },
  // Sem sufixo aleatório e sem substituição: a escrita falha se o ficheiro já existir.
  async guardar(caminho, conteudo) {
    await put(caminho, conteudo, { access: 'private', contentType: 'application/json; charset=utf-8', addRandomSuffix: false, allowOverwrite: false });
  },
  async contar() {
    const r = await list({ prefix: PREFIXO, limit: 1000 });
    return r.hasMore ? Infinity : r.blobs.length;
  },
});

export default { fetch: tratar };
```

- [ ] **Step 6: Commit (gate: only with explicit approval)**

```bash
git add prototype/publicacao/package.json prototype/publicacao/servico prototype/publicacao/api prototype/testes/comentario-servico.test.mjs
git commit -m "feat(demo): function that stores one file per screen comment"
```

---

### Task 3: The comment window in the demonstration

**Files:**
- Modify: `prototype/demo.html` (demonstration bar, the `<dialog>`, one script tag)
- Modify: `prototype/demo.js` (state and methods; `VERSAO` untouched)
- Modify: `prototype/styles.css`
- Test: `prototype/testes/comentario.test.html`

**Interfaces:**
- Consumes: `window.Comentario.contextoDoEcra` (Task 1) and `POST <url>` (Task 2). The URL comes from `window.DEMO_COMENTARIOS`, set by the published `config.js`; when absent, the button is not rendered.
- Produces, on the Vue instance (`window.demo`): data `comentariosUrl: string` and `comentario: { id, texto, contexto, atual, estado, erro }`, with `estado` one of `'rascunho' | 'a_enviar' | 'enviado' | 'falhou' | 'desconhecido'`; methods `contextoAtual()`, `abrirComentario()`, `aoEditarComentario()`, `passarComentarioParaEcraAtual()`, `enviarComentario()`, `iniciarNovoComentario()`, `fecharComentario()`. The window treats as stored only `201` with `{"estado":"guardado"}` or `200` with `{"estado":"duplicado"}`.

- [ ] **Step 1: Write the failing browser tests**

Create `prototype/testes/comentario.test.html`:

```html
<!doctype html>
<html lang="pt-PT">
<head><meta charset="utf-8"><title>Testes: comentar este ecrã</title>
<style>body{font:15px system-ui;margin:16px} .ok{color:#1a7f37} .falha{color:#b00020} iframe{width:390px;height:700px;border:1px solid #999}</style>
</head>
<body>
<h1>Testes: comentar este ecrã</h1>
<p id="resumo">A correr…</p>
<ul id="lista"></ul>
<iframe id="alvo" title="demonstração"></iframe>
<script>
const espera = (ms) => new Promise((r) => setTimeout(r, ms));
const CHAVES = ['agentimo-demo', 'agentimo-demo-seis', 'agentimo-demo-jornada'];
const NOV = 'Seis meses de atividade · Ponto 1 de 3 · Previsão · novembro 2026 · cenário Confirmado';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const resultados = [];
// Resposta simulada: sem corpo indicado, ler o JSON falha, como numa página HTML.
const resp = (status, corpo) => ({ status, json: async () => { if (corpo === undefined) throw new SyntaxError('não é JSON'); return corpo; } });
function igual(a, b, msg) { if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error((msg || 'diferente') + ': ' + JSON.stringify(a) + ' ≠ ' + JSON.stringify(b)); }
function certo(v, msg) { if (!v) throw new Error(msg || 'falso'); }

async function abrir(estadoGuardado) {
  CHAVES.forEach((k) => localStorage.removeItem(k));
  Object.entries(estadoGuardado || {}).forEach(([k, v]) => localStorage.setItem(k, JSON.stringify(v)));
  const f = document.getElementById('alvo');
  await new Promise((r) => { f.onload = r; f.src = '../demo.html?t=' + Math.random(); });
  await espera(150);
  const w = f.contentWindow;
  const pedidos = [];
  w.__resposta = async () => resp(201, { estado: 'guardado' });
  w.fetch = async (url, opcoes) => { pedidos.push({ url, opcoes }); return w.__resposta(); };
  return { w, d: w.demo, doc: w.document, pedidos };
}
async function emSeis() { const x = await abrir(); x.d.comentariosUrl = '/api/comentario'; x.d.escolher('seis'); await espera(120); return x; }
const botao = (doc) => [...doc.querySelectorAll('.demo-barra button')].find((b) => b.innerText.trim() === 'Comentar este ecrã');
const janela = (doc) => doc.querySelector('dialog.comentario');
const sobre = (doc) => doc.querySelector('.comentario-contexto').innerText.replace(/\s+/g, ' ').trim();
const instantaneo = (w) => JSON.stringify({ modo: w.demo.modo, vista: w.demo.vista, s1: w.demo.s1, s2: w.demo.s2, guardado: CHAVES.map((k) => w.localStorage.getItem(k)) });

const testes = {
  async 'sem endereço configurado não há botão'() {
    const { d, doc } = await abrir(); d.escolher('seis'); await espera(120);
    certo(!botao(doc), 'o botão não devia existir');
  },
  async 'o botão fica na barra da demonstração, fora da aplicação, e a janela não abre sozinha'() {
    const { doc } = await emSeis();
    certo(botao(doc), 'falta o botão');
    certo(!doc.querySelector('.app-moldura').contains(botao(doc)), 'o botão está dentro da aplicação');
    certo(!doc.querySelector('.app-moldura').contains(janela(doc)), 'a janela está dentro da aplicação');
    certo(!janela(doc).open, 'a janela abriu sozinha');
  },
  async 'critério 1: previsão de novembro, cenário Confirmado, mostra esse contexto'() {
    const { doc } = await emSeis();
    botao(doc).click(); await espera(120);
    certo(janela(doc).open, 'a janela não abriu');
    igual(sobre(doc), 'Sobre: ' + NOV);
  },
  async 'o contexto diz qual é o negócio aberto'() {
    const { d, doc } = await emSeis();
    d.ir('negocio', 't3'); await espera(100); botao(doc).click(); await espera(120);
    igual(sobre(doc), 'Sobre: Seis meses de atividade · exploração livre · Negócio · T3 Av. de Roma · Ref 2841');
  },
  async 'critério 2: o que é enviado é o texto e exatamente o contexto mostrado na abertura'() {
    const { d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120);
    d.s1.cenario = 'total'; d.s1.mesKey = '2026-12'; await espera(60);
    d.comentario.texto = '  O valor a proteger devia estar mais visível.  ';
    await d.enviarComentario(); await espera(60);
    igual(pedidos.length, 1, 'número de pedidos');
    igual(pedidos[0].url, '/api/comentario'); igual(pedidos[0].opcoes.method, 'POST');
    igual(pedidos[0].opcoes.headers['Content-Type'], 'application/json');
    const corpo = JSON.parse(pedidos[0].opcoes.body);
    igual(Object.keys(corpo).sort(), ['contexto', 'id', 'texto']);
    igual(corpo.texto, 'O valor a proteger devia estar mais visível.');
    igual(corpo.contexto, NOV, 'o contexto enviado não é o que foi mostrado');
    certo(UUID.test(corpo.id), 'id inválido');
    igual(d.comentario.estado, 'enviado');
    certo(janela(doc).innerText.includes('Opinião enviada'), 'falta a confirmação');
    certo(!doc.getElementById('comentario-texto'), 'o campo devia desaparecer depois do envio');
  },
  async 'critério 3: abrir, escrever e fechar não altera a demonstração nem o que está guardado'() {
    const { w, d, doc } = await abrir(); d.comentariosUrl = '/api/comentario'; d.escolher('jornada'); await espera(120);
    d.irN(2); await espera(80); d.guardarNegocio(); await espera(120);
    const antes = instantaneo(w);
    botao(doc).click(); await espera(120); d.comentario.texto = 'rascunho-de-teste'; await d.enviarComentario(); d.fecharComentario(); await espera(120);
    igual(instantaneo(w), antes, 'o estado mudou');
    certo(!CHAVES.some((k) => (w.localStorage.getItem(k) || '').includes('rascunho-de-teste')), 'o comentário foi guardado no browser');
  },
  async 'critério 4: uma recusa mantém o texto, não mostra sucesso e permite corrigir e tentar de novo'() {
    const { w, d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Texto a preservar';
    w.__resposta = async () => resp(429);
    await d.enviarComentario(); await espera(60);
    igual(d.comentario.estado, 'falhou'); igual(d.comentario.texto, 'Texto a preservar');
    certo(!janela(doc).innerText.includes('Opinião enviada'), 'sucesso indevido');
    certo(doc.getElementById('comentario-erro'), 'falta a mensagem de erro');
    certo(!doc.getElementById('comentario-texto').disabled, 'depois de uma recusa o texto pode ser corrigido');
    d.fecharComentario(); await espera(80); botao(doc).click(); await espera(120);
    igual(d.comentario.texto, 'Texto a preservar', 'o texto perdeu-se ao reabrir');
    w.__resposta = async () => resp(201, { estado: 'guardado' });
    await d.enviarComentario(); await espera(60);
    igual(pedidos.length, 2); igual(d.comentario.estado, 'enviado');
  },
  async 'resultado desconhecido: bloqueia o texto e repete exatamente o mesmo pedido'() {
    const { w, d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Sem resposta';
    w.__resposta = async () => { throw new Error('rede'); };
    await d.enviarComentario(); await espera(60);
    igual(d.comentario.estado, 'desconhecido');
    certo(doc.getElementById('comentario-texto').disabled, 'o texto devia ficar bloqueado');
    certo(!janela(doc).innerText.includes('Opinião enviada'), 'sucesso indevido');
    certo(!doc.querySelector('.comentario-outro'), 'um envio pendente não pode mudar de ecrã');
    w.__resposta = async () => resp(503);
    await d.enviarComentario(); await espera(60);
    igual(d.comentario.estado, 'desconhecido', 'um erro do servidor também é resultado desconhecido');
    w.__resposta = async () => resp(200, { estado: 'duplicado' });
    await d.enviarComentario(); await espera(60);
    igual(pedidos.length, 3); igual(pedidos[1].opcoes.body, pedidos[0].opcoes.body); igual(pedidos[2].opcoes.body, pedidos[0].opcoes.body);
    igual(d.comentario.estado, 'enviado');
  },
  async 'uma recusa numa nova tentativa não desbloqueia um envio de resultado desconhecido'() {
    const { w, d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Pode já ter chegado';
    w.__resposta = async () => { throw new Error('tempo esgotado'); };
    await d.enviarComentario(); await espera(60);
    igual(d.comentario.estado, 'desconhecido');
    for (const estado of [429, 507, 400, 403, 409, 413]) {
      w.__resposta = async () => resp(estado);
      await d.enviarComentario(); await espera(60);
      igual(d.comentario.estado, 'desconhecido', 'depois de ' + estado);
      certo(doc.getElementById('comentario-texto').disabled, 'depois de ' + estado + ' o texto continua bloqueado');
      certo(doc.querySelector('.comentario-pendente'), 'depois de ' + estado + ' continua a oferecer um novo comentário');
      certo(doc.getElementById('comentario-erro'), 'depois de ' + estado + ' falta a mensagem');
      certo(!janela(doc).innerText.includes('Opinião enviada'), 'depois de ' + estado + ': sucesso indevido');
    }
    w.__resposta = async () => resp(200, { estado: 'duplicado' });
    await d.enviarComentario(); await espera(60);
    igual(d.comentario.estado, 'enviado');
    igual(pedidos.length, 8);
    certo(pedidos.every((x) => x.opcoes.body === pedidos[0].opcoes.body), 'todas as tentativas têm de repetir o mesmo pedido, com o mesmo id');
    igual(JSON.parse(pedidos[0].opcoes.body).texto, 'Pode já ter chegado');
  },
  async 'uma resposta que não é a da função não confirma o envio'() {
    const { w, d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Resposta estranha';
    const id = d.comentario.id; const contexto = d.comentario.contexto;
    const estranhas = { '200 com HTML': resp(200), '201 com HTML': resp(201), '200 com outro JSON': resp(200, { ok: true }), '200 com JSON que não é objeto': resp(200, 'guardado'), '201 com o corpo do 200': resp(201, { estado: 'duplicado' }), '200 com o corpo do 201': resp(200, { estado: 'guardado' }), '204 sem corpo': resp(204) };
    for (const [nome, r] of Object.entries(estranhas)) {
      w.__resposta = async () => r;
      await d.enviarComentario(); await espera(40);
      igual(d.comentario.estado, 'desconhecido', nome);
      certo(!janela(doc).innerText.includes('Opinião enviada'), nome + ': sucesso indevido');
      igual([d.comentario.texto, d.comentario.contexto, d.comentario.id], ['Resposta estranha', contexto, id], nome + ': texto, contexto ou id mudaram');
    }
    certo(pedidos.every((x) => x.opcoes.body === pedidos[0].opcoes.body), 'as tentativas não repetiram o mesmo pedido');
    w.__resposta = async () => resp(200, { estado: 'duplicado' });
    await d.enviarComentario(); igual(d.comentario.estado, 'enviado');
  },
  async 'iniciar um novo comentário depois de um envio pendente avisa que o anterior pode ter sido recebido'() {
    const { w, d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Primeira versão';
    w.__resposta = async () => { throw new Error('rede'); };
    await d.enviarComentario(); await espera(60);
    const pendente = doc.querySelector('.comentario-pendente');
    certo(pendente && pendente.innerText.includes('O comentário anterior pode já ter sido recebido. Continuar inicia um novo comentário.'), 'falta o aviso');
    certo(!/cancel|desist/i.test(pendente.innerText), 'a opção não pode parecer um cancelamento do envio anterior');
    d.iniciarNovoComentario(); await espera(60);
    igual(d.comentario.estado, 'rascunho'); igual(d.comentario.texto, 'Primeira versão');
    certo(!doc.getElementById('comentario-texto').disabled, 'o texto devia poder ser editado');
    certo(!doc.querySelector('.comentario-pendente'), 'o aviso devia desaparecer');
    w.__resposta = async () => resp(201, { estado: 'guardado' });
    await d.enviarComentario(); await espera(60);
    certo(JSON.parse(pedidos[1].opcoes.body).id !== JSON.parse(pedidos[0].opcoes.body).id, 'um comentário novo tem outro id');
  },
  async 'escrever no campo depois de uma recusa cria um comentário novo, com outro identificador'() {
    const { w, d, doc, pedidos } = await emSeis();
    const escrever = (texto) => { const t = doc.getElementById('comentario-texto'); t.value = texto; t.dispatchEvent(new w.Event('input', { bubbles: true })); };
    botao(doc).click(); await espera(120);
    const idInicial = d.comentario.id;
    escrever('Primeira versão'); await espera(60);
    igual(d.comentario.texto, 'Primeira versão'); certo(d.comentario.id !== idInicial, 'escrever devia dar outro identificador');
    w.__resposta = async () => resp(429);
    await d.enviarComentario(); await espera(60);
    igual(d.comentario.estado, 'falhou');
    const idRecusado = JSON.parse(pedidos[0].opcoes.body).id;
    escrever('Segunda versão, corrigida'); await espera(60);
    igual(d.comentario.estado, 'rascunho', 'editar depois de uma recusa volta a rascunho');
    certo(!doc.getElementById('comentario-erro'), 'a mensagem de erro devia desaparecer ao editar');
    w.__resposta = async () => resp(201, { estado: 'guardado' });
    await d.enviarComentario(); await espera(60);
    const segundo = JSON.parse(pedidos[1].opcoes.body);
    igual(segundo.texto, 'Segunda versão, corrigida'); certo(UUID.test(segundo.id) && segundo.id !== idRecusado, 'o texto corrigido tem de seguir com outro identificador');
    igual(d.comentario.estado, 'enviado');
  },
  async 'texto vazio ou só com espaços não é enviado'() {
    const { d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = '   \n ';
    await d.enviarComentario(); await espera(60);
    igual(pedidos.length, 0); certo(doc.getElementById('comentario-erro'), 'falta a mensagem');
    igual(doc.getElementById('comentario-texto').maxLength, 2000);
    certo(doc.getElementById('comentario-limite').innerText.includes('2 000 caracteres'), 'o limite não é explicado antes do envio');
  },
  async 'dois toques seguidos enviam um só pedido'() {
    const { w, d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Uma vez';
    w.__resposta = async () => { await espera(150); return resp(201, { estado: 'guardado' }); };
    const a = d.enviarComentario(); await espera(30);
    certo([...janela(doc).querySelectorAll('button')].find((b) => b.innerText.includes('A enviar')).disabled, 'o botão devia ficar desativado');
    const b = d.enviarComentario(); await Promise.all([a, b]);
    igual(pedidos.length, 1);
  },
  async 'um rascunho fica ligado ao ecrã em que foi escrito, até ser passado de propósito'() {
    const { d, doc, pedidos } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Sobre novembro'; d.fecharComentario(); await espera(100);
    d.ir('despesas'); await espera(100); botao(doc).click(); await espera(120);
    igual(sobre(doc), 'Sobre: ' + NOV, 'o rascunho mudou de ecrã sozinho');
    igual(d.comentario.texto, 'Sobre novembro');
    const aviso = doc.querySelector('.comentario-outro');
    certo(aviso && aviso.innerText.includes('Despesas · novembro 2026'), 'falta o aviso de que o rascunho é de outro ecrã');
    d.passarComentarioParaEcraAtual(); await espera(80);
    igual(sobre(doc), 'Sobre: Seis meses de atividade · exploração livre · Despesas · novembro 2026');
    certo(!doc.querySelector('.comentario-outro'), 'o aviso devia desaparecer');
    await d.enviarComentario();
    igual(JSON.parse(pedidos[0].opcoes.body).contexto, 'Seis meses de atividade · exploração livre · Despesas · novembro 2026');
  },
  async 'depois de enviar, a janela reabre vazia e com o contexto do ecrã atual'() {
    const { d, doc } = await emSeis();
    botao(doc).click(); await espera(120); d.comentario.texto = 'Primeiro'; await d.enviarComentario(); d.fecharComentario(); await espera(100);
    d.ir('negocios'); await espera(100); botao(doc).click(); await espera(120);
    igual(d.comentario.texto, ''); igual(d.comentario.estado, 'rascunho');
    igual(sobre(doc), 'Sobre: Seis meses de atividade · exploração livre · Negócios');
    certo(!doc.querySelector('.comentario-outro'), 'aviso indevido');
  },
  async 'critério 5: o foco entra na janela e volta ao botão ao fechar'() {
    const { d, doc } = await emSeis();
    const b = botao(doc); b.focus(); b.click(); await espera(150);
    igual(doc.activeElement.id, 'comentario-texto', 'o foco não entrou no texto');
    igual(janela(doc).getAttribute('aria-labelledby'), 'comentario-titulo');
    d.fecharComentario(); await espera(150);
    certo(doc.activeElement === botao(doc), 'o foco não voltou ao botão');
  },
  async 'sem contexto seguro o identificador continua a ser um UUID'() {
    const { w, d, doc, pedidos } = await emSeis();
    Object.defineProperty(w.crypto, 'randomUUID', { value: undefined, configurable: true });
    botao(doc).click(); await espera(120); d.comentario.texto = 'x'; await d.enviarComentario();
    certo(UUID.test(JSON.parse(pedidos[0].opcoes.body).id), 'id inválido');
  },
  async 'critério 6: o progresso guardado por quem já abriu a ligação é preservado'() {
    const v = '2026-10-04.8';
    const guardado = {
      'agentimo-demo': { v, d: { modo: 'jornada', demo: 'api', guiaVisivel: true } },
      'agentimo-demo-jornada': { v, d: { passo: 5, neg: true, desp: true, pago: true, rec: false, recibo: false, reciboModo: '', reciboNum: '', ultimo: 'pago', cenario: 'confirmado', mesKey: '2026-11' } },
      'agentimo-demo-seis': { v, d: { cenario: 'provavel', mesKey: '2026-12', ponto: 4 } },
    };
    const { w, d } = await abrir(guardado);
    igual(w.DEMO_DADOS.VERSAO, v, 'a versão dos dados mudou');
    igual(d.modo, 'jornada'); igual([d.s2.passo, d.s2.neg, d.s2.desp, d.s2.pago, d.s2.rec], [5, true, true, true, false]);
    igual([d.s1.cenario, d.s1.mesKey, d.s1.ponto], ['provavel', '2026-12', 4]);
  },
};

(async () => {
  for (const [nome, fn] of Object.entries(testes)) {
    let erro = '';
    try { await fn(); } catch (e) { erro = e.message; }
    resultados.push({ nome, ok: !erro, erro });
    const li = document.createElement('li'); li.className = erro ? 'falha' : 'ok'; li.textContent = (erro ? '✗ ' : '✓ ') + nome + (erro ? ' — ' + erro : '');
    document.getElementById('lista').appendChild(li);
  }
  const ok = resultados.filter((r) => r.ok).length;
  document.getElementById('resumo').textContent = ok + ' de ' + resultados.length + ' passaram';
  window.__resultados = { ok, total: resultados.length, falhas: resultados.filter((r) => !r.ok) };
})();
</script>
</body>
</html>
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd prototype && python3 -m http.server 8767 --bind 127.0.0.1`, and open `http://127.0.0.1:8767/testes/comentario.test.html`.
Expected: `2 de 19 passaram`. Only "sem endereço configurado não há botão" and "critério 6" pass: neither depends on the new code, and the second is the guard that saved progress survives. Any other pass is a defect in the test.

- [ ] **Step 3: Add the script tag, the button and the window to `prototype/demo.html`**

Before `<script src="demo.js"></script>` add:

```html
<script src="comentario.js"></script>
```

In the demonstration bar, inside `<div class="demo-barra-acoes" v-if="!aRecomecar">`, after the "Recomeçar" button, add:

```html
        <button class="link" v-if="comentariosUrl" ref="botaoComentar" @click="abrirComentario">Comentar este ecrã</button>
```

Immediately after the closing `</div>` of `.demo-barra` (inside `.palco`, before the guide panel, outside `.app-moldura`), add:

```html
    <!-- COMENTAR ESTE ECRÃ: pertence à demonstração, não à aplicação. -->
    <dialog class="comentario" ref="dialogoComentario" aria-labelledby="comentario-titulo" @close="aoFecharComentario">
      <div class="comentario-topo">
        <h2 id="comentario-titulo">Comentar este ecrã</h2>
        <button class="link" @click="fecharComentario">Fechar</button>
      </div>
      <p class="comentario-contexto"><strong>Sobre:</strong> {{ comentario.contexto }}</p>
      <template v-if="comentario.estado !== 'enviado'">
        <div class="comentario-outro" v-if="comentario.atual !== comentario.contexto && comentario.estado !== 'desconhecido' && comentario.estado !== 'a_enviar'">
          <p>Este rascunho é sobre outro ecrã. Está agora em: {{ comentario.atual }}</p>
          <button class="link" @click="passarComentarioParaEcraAtual">Passar o rascunho para o ecrã atual</button>
        </div>
        <label for="comentario-texto">A sua opinião</label>
        <textarea id="comentario-texto" v-model="comentario.texto" rows="5" maxlength="2000" @input="aoEditarComentario"
          :disabled="comentario.estado==='a_enviar' || comentario.estado==='desconhecido'"
          :aria-invalid="!!comentario.erro" aria-describedby="comentario-limite comentario-aviso comentario-erro"></textarea>
        <p class="nota" id="comentario-limite">Até 2 000 caracteres. Escritos: {{ comentario.texto.length }}.</p>
        <p class="erro" id="comentario-erro" role="alert" v-if="comentario.erro">{{ comentario.erro }}</p>
        <p class="nota" id="comentario-aviso">Enviamos este texto e o contexto acima. Não pedimos o seu nome nem o seu email. O alojamento regista dados técnicos do pedido, como o endereço IP, durante um período limitado. O rascunho perde-se se recarregar a página.</p>
        <div class="comentario-acoes">
          <button class="botao" @click="enviarComentario" :disabled="comentario.estado==='a_enviar'">
            {{ comentario.estado==='a_enviar' ? 'A enviar…' : (comentario.estado==='falhou' || comentario.estado==='desconhecido' ? 'Tentar novamente' : 'Enviar opinião') }}
          </button>
        </div>
        <div class="comentario-pendente" v-if="comentario.estado==='desconhecido'">
          <p>O comentário anterior pode já ter sido recebido. Continuar inicia um novo comentário.</p>
          <button class="link" @click="iniciarNovoComentario">Iniciar um novo comentário</button>
        </div>
      </template>
      <p v-else class="toast" role="status">Opinião enviada. Obrigado.</p>
    </dialog>
```

- [ ] **Step 4: Add the state and the methods to `prototype/demo.js`**

Do not change `VERSAO`, `INI1`, `INI2`, `CHAVES`, `ler`, `escrever` or `guardar`.

At the top of the file, after the `fmt` function, add:

```js
// crypto.randomUUID só existe em contexto seguro; o recurso produz um UUID v4 com a mesma origem aleatória.
function novoId() {
  if (window.crypto.randomUUID) return window.crypto.randomUUID();
  const b = window.crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, '0')).join('');
  return h.slice(0, 8) + '-' + h.slice(8, 12) + '-' + h.slice(12, 16) + '-' + h.slice(16, 20) + '-' + h.slice(20);
}
```

In `data()`, in the returned object, add:

```js
      comentariosUrl: window.DEMO_COMENTARIOS || '',
      comentario: { id: '', texto: '', contexto: '', atual: '', estado: 'rascunho', erro: '' },
```

In `methods`, add:

```js
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
```

- [ ] **Step 5: Add the styles to `prototype/styles.css`**

Append:

```css
/* Janela «Comentar este ecrã»: pertence à demonstração, não à aplicação */
dialog.comentario { width: min(92vw, 480px); max-height: 90vh; overflow: auto; border: 3px solid #b26a00; border-radius: 10px; padding: 14px 16px; background: #fff8e1; color: #1e1e1e; }
dialog.comentario::backdrop { background: rgba(0, 0, 0, .45); }
/* «Fechar» fica no topo para estar sempre ao alcance, mesmo quando o conteúdo rola dentro da janela */
.comentario-topo { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 0 0 6px; }
dialog.comentario h2 { margin: 0; font-size: 1.1rem; color: #7a4a00; }
dialog.comentario textarea { width: 100%; min-height: 110px; padding: 8px 12px; border: 1.5px solid #555; border-radius: 8px; font: inherit; background: #fff; }
dialog.comentario textarea:disabled { background: #eee; }
.comentario-contexto { margin: 0 0 8px; font-size: .9rem; }
.comentario-outro, .comentario-pendente { margin: 0 0 8px; padding: 8px 10px; border: 1.5px dashed #b26a00; border-radius: 8px; font-size: .9rem; }
.comentario-outro p, .comentario-pendente p { margin: 0 0 4px; }
.comentario-acoes { display: flex; flex-wrap: wrap; gap: 8px 14px; align-items: center; margin: 10px 0 4px; }
```

- [ ] **Step 6: Run the browser tests to verify they pass**

Reload `http://127.0.0.1:8767/testes/comentario.test.html`.
Expected: `19 de 19 passaram`.

- [ ] **Step 7: Check what the tests cannot, and run the earlier tests again**

In Chrome at 390×844, 360×640 and 1280×800, with the guide expanded, collapsed and hidden, set `demo.comentariosUrl = '/api/comentario'` in the console and open the window on the previsão, on a negócio and on the recibos sheet. Expected: the window fits or scrolls inside itself, nothing is clipped, `Tab` cycles inside the window, `Esc` closes it and returns focus to "Comentar este ecrã". Sending fails locally (no function): the window shows the failure and keeps the text.

Run: `cd prototype && node --test testes/comentario.test.js testes/comentario-servico.test.mjs`
Expected: `# pass 34`, `# fail 0`.

- [ ] **Step 8: Commit (gate: only with explicit approval)**

```bash
git add prototype/demo.html prototype/demo.js prototype/styles.css prototype/testes/comentario.test.html
git commit -m "feat(demo): comment on the open screen from the demonstration bar"
```

---

### Task 4: Publish on Vercel (gate: explicit approval required before any step that changes Vercel)

**Files:**
- Modify: `prototype/publicar.sh`
- Modify: `prototype/publicacao/config.js`

**Interfaces:**
- Consumes: everything from Tasks 1 to 3.
- Produces: `POST https://demo.agentimo.propware.pt/api/comentario`, and comment files in the private Blob store `agentimo-demo-comentarios`.

- [ ] **Step 1: Move the static files under `public/` in the build**

With a `package.json` and function sources in the deployment, Vercel must serve only the static folder. Replace the body of `prototype/publicar.sh` after `cd "$(dirname "$0")"` with:

```sh
rm -rf .publicar
mkdir -p .publicar/public/vendor .publicar/api .publicar/servico
# index.html é a demonstração com a configuração da publicação carregada antes do Vue.
awk '/<script src="vendor\/vue.global.prod.js"><\/script>/ { print "<script src=\"config.js\"></script>"; n++ } { print } END { if (n != 1) exit 1 }' demo.html > .publicar/public/index.html
cp demo.js styles.css comentario.js publicacao/config.js .publicar/public/
cp vendor/vue.global.prod.js .publicar/public/vendor/
# Só o que está em public/ é servido. A função e o seu serviço ficam fora.
cp publicacao/api/comentario.js .publicar/api/
cp publicacao/servico/comentario-servico.js .publicar/servico/
cp publicacao/package.json publicacao/package-lock.json publicacao/vercel.json .publicar/
echo "Pasta pronta: prototype/.publicar"
```

Change `prototype/publicacao/config.js` to:

```js
// Publicação dedicada: a nota da API Portugal fica sempre visível.
window.DEMO_FIXA = 'api';
// Função que recebe os comentários, na mesma origem.
window.DEMO_COMENTARIOS = '/api/comentario';
```

Run: `sh prototype/publicar.sh && find prototype/.publicar -type f | sort`
Expected: exactly `api/comentario.js`, `package.json`, `public/comentario.js`, `public/config.js`, `public/demo.js`, `public/index.html`, `public/styles.css`, `public/vendor/vue.global.prod.js`, `servico/comentario-servico.js`, `vercel.json`.

- [ ] **Step 2: Create the two private Blob stores and connect them to the project (gate)**

Creates billable resources on the team `crmware` (usage-based; a few kilobytes). The store for real comments is connected to production only, and a separate store to preview only, so no test before production can touch real comments.

```bash
cd prototype/.publicar && vercel link --yes --scope crmware --project agentimo-demo
vercel blob create-store agentimo-demo-comentarios --access private --region fra1 --yes --environment production --scope crmware
vercel blob create-store agentimo-demo-comentarios-testes --access private --region fra1 --yes --environment preview --scope crmware
vercel blob list-stores --scope crmware
vercel env ls --scope crmware
```

Expected: both stores listed as private in `fra1`, and one encrypted `BLOB_READ_WRITE_TOKEN` per environment (production and preview), each belonging to its own store. With CLI 54.18.7 this is what the command creates, instead of the OIDC connection described in the documentation; the function works with either. The token stays in Vercel: it is never copied to the repository or to a conversation. To read the test store from the CLI, pull the preview environment to a private temporary file outside the repository, use it without printing it, and delete it afterwards. Note the two store ids: the commands below name the store explicitly.

- [ ] **Step 3: Deploy a preview and verify it against the test store**

```bash
cd prototype/.publicar && vercel deploy --scope crmware
```

With `P` the preview URL printed, run each check through `vercel curl --deployment $P` (preview deployments are behind Vercel Authentication):

| Request | Expected |
| --- | --- |
| `GET /`, `/demo.js`, `/config.js`, `/styles.css`, `/comentario.js`, `/vendor/vue.global.prod.js` | 200, each byte-identical to the file of the same name in the local `prototype/.publicar/public/`. On a preview, `/` differs by one line: Vercel appends its preview toolbar script (`vercel.live`), which production does not have and the page's CSP does not allow to load |
| `GET /package.json`, `/vercel.json`, `/servico/comentario-servico.js`, `/moderador.html`, `/testes/comentario.test.html`, `/.env.local`, `/public/index.html` | 404 |
| `GET /api/comentario.js` | 405 with an empty body: Vercel routes it to the function, and the source is not served |
| `GET /api/comentario` | 405 |
| `POST /api/comentario` with `Origin: https://exemplo.pt` | 403 |
| `POST /api/comentario`, same-origin, valid body with id `00000000-0000-4000-8000-000000000001` | 201 `{"estado":"guardado"}` |
| The same request again | 200 `{"estado":"duplicado"}` |
| The same id with another text | 409 |
| Two requests launched together (`… & … & wait`), same new id `…0002`, same content | one 201 and one 200; one file |
| Two requests launched together, same new id `…0003`, different text | one 201 and one 409; one file, holding the text of the request that got 201 |
| Same-origin, valid body with 2 000 times `€` as text, id `…0004` | 201, and the stored text is intact |
| Response headers of `/` and of `/api/comentario` | CSP, `X-Robots-Tag: noindex, nofollow`, HSTS, `nosniff` present |

The two overlapping cases are repeated five times each with fresh ids, because an overlap is not guaranteed on any single attempt; every repetition must give the results above.

Saved progress and data version are checked separately from the file comparison: the deployed `/demo.js` contains `const VERSAO = '2026-10-04.8';`, and the preview opened in a browser passes the "critério 6" scenario (state stored under the three keys with that version is restored).

Then, naming the test store: `vercel blob list --prefix comentarios/` shows only the test ids; `vercel blob get` of the first one shows the text and context sent and no IP address or user agent; fetching a file's URL with plain `curl` answers 401 or 403. `vercel logs $P --scope crmware` shows the requests and does not contain the text of any comment.

Empty the test store only: `vercel blob empty-store` with the id of `agentimo-demo-comentarios-testes`. Before running it, print the store id and compare it with the production store id noted in Step 2; if they are equal, stop.

If any check fails, stop: production is untouched.

- [ ] **Step 4: Add the firewall rule (gate; done by the product owner in the dashboard)**

Project `agentimo-demo` → Firewall → Configure → New Rule: name "Comentários: limite por IP"; If request path equals `/api/comentario` and method equals `POST`; Then Rate Limit, fixed window, 60 seconds, 5 requests, key IP, action default (429). Publish.

- [ ] **Step 5: Deploy to production and verify (gate)**

Note the current production deployment first, for rollback: `vercel ls agentimo-demo --prod --scope crmware | head -5`.

```bash
cd prototype/.publicar && vercel deploy --prod --scope crmware
```

Against `https://demo.agentimo.propware.pt`, with plain `curl`: repeat the status, header and 404 rows of the Step 3 table, and send one comment only, with the reserved id `00000000-0000-4000-8000-000000000000` (201, then 200 when repeated). Read it back, then delete it by its exact path, `vercel blob del comentarios/00000000-0000-4000-8000-000000000000.json`, naming the production store. No other write, and no bulk deletion, is run against the production store. Then:

- Six POSTs within a minute from the same address, all with an invalid body so that nothing is stored: the first five answer 400 and the sixth answers 429.
- A browser profile that already holds saved progress opens on the same demonstration, step and data (criterion 6).
- A first visit (clean profile) works, and the console shows no Content-Security-Policy error after sending a comment.
- On November, Confirmado, the window shows "Seis meses de atividade · Ponto 1 de 3 · Previsão · novembro 2026 · cenário Confirmado" (criterion 1). Sending from the window is checked in the preview, not here, so that the production store receives no test comment other than the reserved one.
- In the preview, sending from the window shows "Opinião enviada. Obrigado." and the stored file holds that text and that context (criterion 2).
- `https://propware.pt` still answers 200.
- The real phone test (criterion 5 on a device) stays pending until the product owner does it.

To go back: `vercel rollback <previous deployment URL> --scope crmware`.

- [ ] **Step 6: Commit (gate: only with explicit approval)**

```bash
git add prototype/publicar.sh prototype/publicacao/config.js
git commit -m "chore(demo): publish the comment function and serve only public/"
```

---

### Task 5: Record the behaviour and the decision

**Files:**
- Modify: `docs/superpowers/specs/2026-10-04-ux-design.md` (new subsection after 5.5)

**Interfaces:**
- Consumes: the behaviour built in Tasks 1 to 4 and the decisions table of this plan, as confirmed at plan review.
- Produces: section 5.6 of the UX spec and a comment on issue #12.

- [ ] **Step 1: Add section 5.6**

Insert before `## 6. Testing plan for the core journey`:

```markdown
### 5.6 Commenting on a screen

Tracking: [issue #12](https://github.com/CrmWare/propware-agentimo/issues/12).

A person exploring a demonstration can send an opinion about the screen they are looking at, without leaving the visit.

- **Where.** "Comentar este ecrã" is a control of the demonstration bar, outside the application. Nothing about comments appears inside the application.
- **Never imposed.** The window never opens by itself and feedback is never required.
- **What is asked.** One text field and "Enviar opinião". No account, name or email.
- **Context.** Captured when the window opens and shown in it: demonstration, step or point of the guide, screen and what is open in it (the negócio, the month and scenario, the sub-screen of expenses or receipts). Free exploration is distinguished from a step actually accompanied by the guide. The context sent is exactly the one shown.
- **Notice.** "Enviamos este texto e o contexto acima. Não pedimos o seu nome nem o seu email. O alojamento regista dados técnicos do pedido, como o endereço IP, durante um período limitado. O rascunho perde-se se recarregar a página." The window does not claim anonymity.
- **Result.** "Opinião enviada. Obrigado." only after the service's own answer confirms that the comment is stored; any other answer is not a success. A refusal keeps the text, editable, and offers another attempt. When the outcome is unknown, the text is locked and the same request is repeated; a refusal of a repeated request does not unlock it. The person can start a new comment instead, and is told first: "O comentário anterior pode já ter sido recebido. Continuar inicia um novo comentário."
- **Limit.** Up to 2 000 characters, stated next to the field with the count written so far.
- **Drafts.** A draft exists only in memory and stays attached to the screen it was written for. Reopening the window elsewhere says so and offers to move the draft to the current screen; it is never moved silently.
- **No effect on the visit.** Opening, writing, sending and closing changes no negócio, expense, payment, receipt, month, scenario or progress, and nothing about a comment is stored in the browser.
- **Screen level only.** No element selection, screenshots, session recording, ratings or behavioural tracking.
- **Where comments go.** One file per comment in a private store of the demonstration's hosting, readable only by the team that runs it and not reachable over the web. The file holds the text, the context and the time of receipt. No field identifying the visitor is asked for or added; the free text may contain whatever the person chooses to write. No file is kept more than 90 days: the product owner reviews the store every 30 days and deletes what is older than 60 days, and deletes everything when the demonstration is withdrawn.
- **Accessibility.** The window is a modal dialog with an accessible name; focus moves into the text field on opening and returns to the control on closing; it can be used by keyboard alone and on a phone.
```

- [ ] **Step 2: Write the operating procedure**

Create `prototype/publicacao/COMENTARIOS.md`, replacing the two store ids with the ones noted in Task 4 and the first review date with the production date plus 30 days:

```markdown
# Comentários da demonstração

Cada comentário enviado em `demo.agentimo.propware.pt` é um ficheiro `comentarios/<id>.json` na loja Blob privada `agentimo-demo-comentarios` (equipa `crmware`, região `fra1`). A loja `agentimo-demo-comentarios-testes` recebe só os testes das pré-visualizações.

Um ficheiro tem o texto, o contexto do ecrã e a hora de receção. Não tem nome, email, endereço IP nem agente do browser.

## Ler

    vercel blob list --prefix comentarios/ --scope crmware
    vercel blob get comentarios/<id>.json --scope crmware

Ambos com a loja de produção indicada. A lista mostra a data de cada ficheiro.

## Retenção

Nenhum comentário fica guardado mais de 90 dias.

- **Responsável:** o dono do produto.
- **Quando:** de 30 em 30 dias a contar da publicação (primeira revisão na data indicada abaixo), e no dia em que a demonstração for retirada.
- **Como:** listar os ficheiros; apagar, um a um e pelo caminho exato, os que tenham mais de 60 dias (`vercel blob del comentarios/<id>.json`). Apagar aos 60 garante que nenhum chega aos 90 antes da revisão seguinte.
- **Ao retirar a demonstração:** apagar as duas lojas (`vercel blob delete-store`) e a regra da Firewall.
- **Registo:** um comentário na issue #12 com a data da revisão e o número de ficheiros apagados, sem o conteúdo.

Primeira revisão: (data)
```

The product owner creates the recurring 30-day reminder in their own calendar.

- [ ] **Step 3: Record the decision on the issue (gate: explicit approval)**

Comment on issue #12 with:
- the decision: a Vercel Function on the same origin writes one file per comment to a private Vercel Blob store, with the decisions table of this plan as confirmed;
- the options rejected: a service on the Hetzner server (the demonstration moved to Vercel); handoff by the visitor's own email or by copying, with no service; an email service; writing to a GitHub repository; a third-party form service;
- how each acceptance criterion is met, with the test output;
- the known limits: the ceiling of about 500 comments is approximate; the hosting records IP addresses in its own logs;
- what stays unverified: the real phone test.

Also add to `CrmWare/propware-gestimo#107` one line: the demonstration now has a function and two private Blob stores on Vercel; nothing on the Hetzner server changed.

- [ ] **Step 4: Commit (gate: only with explicit approval)**

```bash
git add docs/superpowers/specs/2026-10-04-ux-design.md docs/superpowers/plans/2026-10-04-comentar-este-ecra.md prototype/publicacao/COMENTARIOS.md
git commit -m "docs(demo): record the screen comment behaviour and its storage"
```
