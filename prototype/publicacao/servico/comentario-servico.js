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
