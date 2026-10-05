#!/bin/sh
# Monta em prototype/.publicar/ a pasta de publicação: os ficheiros servidos ficam em public/, a função em api/.
# O guia do moderador, o modo de teste moderado e o resto do repositório nunca entram.
# Publicar (projeto agentimo-demo, equipa crmware):
#   sh prototype/publicar.sh && cd prototype/.publicar && vercel link --yes --scope crmware --project agentimo-demo && vercel deploy --prod --scope crmware
set -eu
cd "$(dirname "$0")"
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
