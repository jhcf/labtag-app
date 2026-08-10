#!/usr/bin/env bash
#
# release.sh — automatiza a geracao do APK de release assinado do LabTag.
#
# Faz, em sequencia:
#   1. buildozer android release          (gera o .aab assinado)
#   2. bundletool build-apks --universal  (converte o .aab num .apk unico)
#   3. extrai o universal.apk do pacote .apks
#   4. confere a assinatura do APK final com apksigner
#
# Cada etapa existe porque, neste projeto, o buildozer/python-for-android
# (fixado em p4a v2024.01.21, por causa de outro problema de build) so
# sabe gerar .aab no modo release — nao .apk direto — entao convertemos
# o .aab ja assinado usando o bundletool oficial do Google.
#
# ---------------------------------------------------------------------------
# VARIAVEIS DE AMBIENTE OBRIGATORIAS
# ---------------------------------------------------------------------------
#   RELEASE_PROJECT_NAME       Nome do projeto/app (ex.: "LabTag"). Usado
#                               para nomear o APK final e, por convencao,
#                               para achar o arquivo do keystore (veja abaixo).
#   RELEASE_KEYSTORE_PASSWORD  Senha de acesso ao keystore de release. Por
#                               padrao e usada tanto para o keystore quanto
#                               para o alias da chave (e como este projeto
#                               foi configurado — as duas senhas iguais).
#                               Se as suas senhas forem diferentes, defina
#                               tambem RELEASE_KEY_PASSWORD (veja abaixo).
#
# Exemplo de uso:
#   export RELEASE_PROJECT_NAME=LabTag
#   export RELEASE_KEYSTORE_PASSWORD='sua_senha_aqui'
#   ./release.sh
#
# Se seu shell tiver HISTCONTROL=ignorespace configurado, comece a linha do
# export da senha com um espaco em branco para ela nao ficar salva no
# historico do terminal.
#
# ---------------------------------------------------------------------------
# VARIAVEIS OPCIONAIS (tem um padrao sensato, derivado do nome do projeto)
# ---------------------------------------------------------------------------
#   RELEASE_KEYSTORE_FILE   Caminho do .keystore.
#                           Padrao: "<nome-do-projeto-minusculo>-release.keystore"
#                           na raiz do repositorio.
#   RELEASE_KEY_ALIAS       Alias da chave dentro do keystore.
#                           Padrao: "<nome-do-projeto-minusculo>"
#   RELEASE_KEY_PASSWORD    Senha do alias, se for DIFERENTE da senha do
#                           keystore. Padrao: igual a RELEASE_KEYSTORE_PASSWORD.
#   BUNDLETOOL_JAR          Caminho do bundletool.jar.
#                           Padrao: "bundletool.jar" na raiz do repositorio
#                           (baixado automaticamente se nao existir).
#   BUNDLETOOL_VERSION      Versao do bundletool a baixar, se precisar.
#                           Padrao: 1.17.2
#   SKIP_BUILD              Se definido como "1", pula a etapa do buildozer
#                           e reaproveita o .aab mais recente ja existente
#                           em bin/ — util para reprocessar so a conversao
#                           para .apk sem esperar o build inteiro de novo.
#
# ---------------------------------------------------------------------------

set -euo pipefail

# --- localizacao do projeto (funciona independente de onde o script e chamado)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- cores para mensagens (desativadas se a saida nao for um terminal) -------
if [ -t 1 ]; then
    C_RESET='\033[0m'; C_BOLD='\033[1m'; C_RED='\033[31m'
    C_GREEN='\033[32m'; C_YELLOW='\033[33m'; C_BLUE='\033[34m'
else
    C_RESET=''; C_BOLD=''; C_RED=''; C_GREEN=''; C_YELLOW=''; C_BLUE=''
fi

log()   { echo -e "${C_BLUE}${C_BOLD}==>${C_RESET} $*"; }
ok()    { echo -e "${C_GREEN}${C_BOLD}OK${C_RESET}  $*"; }
warn()  { echo -e "${C_YELLOW}${C_BOLD}AVISO${C_RESET} $*"; }
fail()  { echo -e "${C_RED}${C_BOLD}ERRO${C_RESET} $*" >&2; exit 1; }

# --- 1. validar variaveis obrigatorias ---------------------------------------
: "${RELEASE_PROJECT_NAME:?ERRO: defina RELEASE_PROJECT_NAME (ex.: export RELEASE_PROJECT_NAME=LabTag)}"
: "${RELEASE_KEYSTORE_PASSWORD:?ERRO: defina RELEASE_KEYSTORE_PASSWORD com a senha do keystore}"

# nome do projeto em minusculas, sem espacos, para usar em nomes de arquivo
PROJECT_SLUG="$(echo "$RELEASE_PROJECT_NAME" | tr '[:upper:]' '[:lower:]' | tr -s ' ' '-')"

# --- 2. variaveis opcionais (com padrao derivado do nome do projeto) --------
RELEASE_KEYSTORE_FILE="${RELEASE_KEYSTORE_FILE:-${PROJECT_SLUG}-release.keystore}"
RELEASE_KEY_ALIAS="${RELEASE_KEY_ALIAS:-${PROJECT_SLUG}}"
RELEASE_KEY_PASSWORD="${RELEASE_KEY_PASSWORD:-$RELEASE_KEYSTORE_PASSWORD}"
BUNDLETOOL_JAR="${BUNDLETOOL_JAR:-bundletool.jar}"
BUNDLETOOL_VERSION="${BUNDLETOOL_VERSION:-1.17.2}"
SKIP_BUILD="${SKIP_BUILD:-0}"

log "Projeto: ${C_BOLD}${RELEASE_PROJECT_NAME}${C_RESET} (slug: ${PROJECT_SLUG})"
log "Keystore: ${RELEASE_KEYSTORE_FILE}"
log "Alias: ${RELEASE_KEY_ALIAS}"

if [ ! -f "$RELEASE_KEYSTORE_FILE" ]; then
    fail "Keystore nao encontrado em '${RELEASE_KEYSTORE_FILE}'. Ajuste RELEASE_KEYSTORE_FILE ou verifique o caminho."
fi

# --- 3. buildozer.spec: achar package.name (para localizar o .aab gerado)
#        e a versao (para nomear o APK final) -------------------------------
[ -f buildozer.spec ] || fail "buildozer.spec nao encontrado em ${SCRIPT_DIR}. Rode este script na raiz do projeto."

APP_VERSION="$(grep -E '^\s*version\s*=' buildozer.spec | head -1 | cut -d= -f2 | tr -d ' ')"
[ -n "$APP_VERSION" ] || { warn "Nao foi possivel ler 'version' do buildozer.spec; usando '0.0'."; APP_VERSION="0.0"; }
log "Versao do app (buildozer.spec): ${APP_VERSION}"

# --- 4. exportar as variaveis que o python-for-android espera ---------------
export P4A_RELEASE_KEYSTORE="$SCRIPT_DIR/$RELEASE_KEYSTORE_FILE"
export P4A_RELEASE_KEYSTORE_PASSWD="$RELEASE_KEYSTORE_PASSWORD"
export P4A_RELEASE_KEYALIAS="$RELEASE_KEY_ALIAS"
export P4A_RELEASE_KEYALIAS_PASSWD="$RELEASE_KEY_PASSWORD"

# --- 5. buildozer android release (gera o .aab assinado) --------------------
if [ "$SKIP_BUILD" = "1" ]; then
    warn "SKIP_BUILD=1 — pulando 'buildozer android release', reaproveitando o .aab mais recente."
else
    log "Rodando 'buildozer android release' (pode demorar alguns minutos)..."
    if ! buildozer android release; then
        fail "buildozer android release falhou. Veja o log acima."
    fi
    ok "buildozer android release concluido."
fi

# --- 6. localizar o .aab mais recente em bin/ --------------------------------
AAB_FILE="$(ls -t bin/*-release.aab 2>/dev/null | head -1 || true)"
[ -n "$AAB_FILE" ] || fail "Nenhum arquivo *-release.aab encontrado em bin/. O build falhou ou gerou outro nome?"
log "Pacote .aab: ${AAB_FILE}"

# --- 7. bundletool: baixar se necessario -------------------------------------
if [ ! -f "$BUNDLETOOL_JAR" ]; then
    log "bundletool nao encontrado — baixando versao ${BUNDLETOOL_VERSION}..."
    BT_URL="https://github.com/google/bundletool/releases/download/${BUNDLETOOL_VERSION}/bundletool-all-${BUNDLETOOL_VERSION}.jar"
    if command -v curl >/dev/null 2>&1; then
        curl -fL -o "$BUNDLETOOL_JAR" "$BT_URL" || fail "Falha ao baixar bundletool de ${BT_URL}"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$BUNDLETOOL_JAR" "$BT_URL" || fail "Falha ao baixar bundletool de ${BT_URL}"
    else
        fail "Nem curl nem wget disponiveis para baixar o bundletool. Baixe manualmente em https://github.com/google/bundletool/releases e salve como '${BUNDLETOOL_JAR}'."
    fi
    ok "bundletool baixado."
fi

command -v java >/dev/null 2>&1 || fail "Java nao encontrado no PATH (necessario para rodar o bundletool)."

# --- 8. gerar o .apks (universal) a partir do .aab ---------------------------
APKS_FILE="bin/${PROJECT_SLUG}-${APP_VERSION}.apks"
log "Gerando APK universal com o bundletool..."
rm -f "$APKS_FILE"
java -jar "$BUNDLETOOL_JAR" build-apks \
    --bundle="$AAB_FILE" \
    --output="$APKS_FILE" \
    --mode=universal \
    --ks="$P4A_RELEASE_KEYSTORE" \
    --ks-pass="pass:$P4A_RELEASE_KEYSTORE_PASSWD" \
    --ks-key-alias="$P4A_RELEASE_KEYALIAS" \
    --key-pass="pass:$P4A_RELEASE_KEYALIAS_PASSWD" \
    || fail "bundletool build-apks falhou."
ok "APK universal gerado dentro de ${APKS_FILE}."

# --- 9. extrair o universal.apk do pacote .apks ------------------------------
FINAL_APK="bin/${RELEASE_PROJECT_NAME}-${APP_VERSION}-release.apk"
log "Extraindo o APK final para ${FINAL_APK}..."
unzip -p "$APKS_FILE" universal.apk > "$FINAL_APK" \
    || fail "Nao foi possivel extrair universal.apk de dentro de ${APKS_FILE}."
ok "APK extraido."

# --- 10. confirmar a assinatura ----------------------------------------------
BUILD_TOOLS_DIR="$(ls -d "$HOME"/.buildozer/android/platform/android-sdk/build-tools/*/ 2>/dev/null | tail -1 || true)"
if [ -z "$BUILD_TOOLS_DIR" ]; then
    warn "Nao encontrei o diretorio build-tools do Android SDK automaticamente."
    warn "Confira a assinatura manualmente com: apksigner verify --print-certs ${FINAL_APK}"
else
    log "Conferindo assinatura com apksigner..."
    if "${BUILD_TOOLS_DIR}apksigner" verify --print-certs "$FINAL_APK"; then
        ok "Assinatura valida."
    else
        fail "apksigner NAO conseguiu validar a assinatura de ${FINAL_APK}. Nao distribua este arquivo."
    fi
fi

echo
ok "Pronto! APK de release: ${C_BOLD}${FINAL_APK}${C_RESET}"
log "Esse e o arquivo para subir no GitHub Releases / distribuir por QR code."
