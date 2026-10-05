#!/bin/sh
# Monta em prototype/.publicar/ a pasta pública da demonstração: só os ficheiros que são servidos.
# O guia do moderador, o modo de teste moderado e o resto do repositório nunca entram.
# Publicar (projeto agentimo-demo, equipa crmware):
#   sh prototype/publicar.sh && cd prototype/.publicar && vercel link --yes --scope crmware --project agentimo-demo && vercel deploy --prod --scope crmware
set -eu
cd "$(dirname "$0")"
rm -rf .publicar
mkdir -p .publicar/vendor
# index.html é a demonstração com a configuração da publicação carregada antes do Vue.
awk '/<script src="vendor\/vue.global.prod.js"><\/script>/ { print "<script src=\"config.js\"></script>"; n++ } { print } END { if (n != 1) exit 1 }' demo.html > .publicar/index.html
cp demo.js styles.css .publicar/
cp vendor/vue.global.prod.js .publicar/vendor/
cp publicacao/config.js publicacao/vercel.json .publicar/
echo "Pasta pronta: prototype/.publicar"
