// Função da Vercel: liga o serviço de comentários à loja Blob privada do projeto.
// A autenticação é feita pela plataforma (OIDC); não há chave no código nem no repositório.
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
