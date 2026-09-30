#!/usr/bin/env bash
# empacotar_codigo.sh — gera um .zip com todo o código-fonte do LabTag
# para enviar ao Claude (atualizar o contexto do projeto).
#
# Uso (na raiz do repositório labtag-app):
#   ./empacotar_codigo.sh            -> labtag-codigo-AAAAMMDD-HHMM.zip
#   ./empacotar_codigo.sh saida.zip  -> nome customizado
#
# Critério: inclui arquivos rastreados pelo git + arquivos novos ainda não
# commitados (respeitando o .gitignore). Depois remove, por segurança,
# qualquer coisa sensível ou pesada que tenha escapado do .gitignore.

set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERRO: rode dentro do repositório git do LabTag." >&2; exit 1; }

SAIDA="${1:-labtag-codigo-$(date +%Y%m%d-%H%M).zip}"
SAIDA_ABS="$(pwd)/$SAIDA"

# Padrões que NUNCA entram no zip (segredos, chaves, build, binários)
EXCLUIR_REGEX='(^|/)(secrets\.json|release\.local\.env|\.env[^/]*)$|\.(keystore|jks|p12|apk|aab|apks|zip|pyc|png)$|(^|/)(\.buildozer|bin|build|dist|__pycache__|\.venv|venv[^/]*)/'

LISTA="$(mktemp)"
trap 'rm -f "$LISTA"' EXIT

git ls-files -z --cached --others --exclude-standard \
  | tr '\0' '\n' \
  | grep -Ev "$EXCLUIR_REGEX" \
  | while IFS= read -r f; do [ -f "$f" ] && echo "$f"; done \
  | sort > "$LISTA"

N=$(wc -l < "$LISTA")
[ "$N" -gt 0 ] || { echo "ERRO: nenhum arquivo selecionado." >&2; exit 1; }

# Registro do estado do repositório dentro do zip
INFO="ESTADO_REPOSITORIO.txt"
{
  echo "Gerado em: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Branch:    $(git rev-parse --abbrev-ref HEAD)"
  echo "Commit:    $(git log -1 --format='%h %s (%ci)')"
  echo
  echo "Alterações não commitadas:"
  git status --short || true
  echo
  echo "Arquivos incluídos ($N):"
  cat "$LISTA"
} > "$INFO"
echo "$INFO" >> "$LISTA"

rm -f "$SAIDA_ABS"
zip -q -X "$SAIDA_ABS" -@ < "$LISTA"
rm -f "$INFO"

echo "OK: $SAIDA ($N arquivos, $(du -h "$SAIDA_ABS" | cut -f1))"
echo
echo "Conferência de segredos (deve ficar vazio):"
unzip -l "$SAIDA_ABS" | grep -Ei 'secrets\.json|release\.local\.env|keystore|\.jks' || echo "  nenhum segredo encontrado ✔"
