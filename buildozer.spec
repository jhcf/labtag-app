[app]

# Identificação do app
# "title" é o nome exibido sob o ícone no Android — a marca do app é LabTag.
# package.name/package.domain NÃO foram alterados de propósito: são o
# identificador interno do Android (application ID). Mudá-los faria o
# Android tratar qualquer atualização como um app NOVO e diferente do já
# instalado nos aparelhos de teste — quem já tem o app instalado não
# receberia a atualização, teria os dois lado a lado. Se quiser mesmo
# renomear o identificador interno, avise: é uma decisão consciente, não
# um esquecimento.
title = LabTag
package.name = labtag
package.domain = br.unb.maiscienciadf

# Código-fonte
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,xml,env

# A senha do modo Preparacao (e qualquer outro segredo futuro) vai em
# "secrets.json" (nao commitado — ver .gitignore), NAO em ".env". Testamos
# na pratica: um dotfile ".env" e uma copia "app.env" (extensao "env", que
# esta na lista acima) NAO apareceram dentro do assets/private.tar do APK
# gerado (conferido com "unzip -p bin/*.apk assets/private.tar | tar -t").
# Ja "dados.json" (extensao "json") sempre chegou certinho — entao usamos
# esse mesmo caminho, comprovadamente confiavel neste pipeline, para o
# segredo tambem. Veja secrets.json.example para o formato. env_config.py
# ainda tenta ".env" e "app.env" como fallback, mas nao dependa deles.
source.include_patterns = .env

version = 1.0

# --- Splash (tela exibida ao abrir o app, antes do Python carregar) ---------
# Imagem: logos REDE+CIÊNCIA / UnB + "App LABTAG" / MEC-CNPq-FNDCT-Brasil.
# Esta é a splash NATIVA do Android — a identificação do PROJETO guarda-chuva,
# não do app em si (o app tem sua própria segunda splash, em main.py, com a
# marca LabTag). O arquivo splash.png deve ficar na raiz do projeto.
presplash.filename = %(source.dir)s/splash.png
# Fundo branco, para casar com o fundo branco da própria imagem.
android.presplash_color = #FFFFFF

# Ícone do app: a marca LabTag (etiqueta + ondas de NFC) sobre fundo navy,
# em versão quadrada simplificada (sem texto, legível mesmo pequeno).
icon.filename = %(source.dir)s/icon_labtag.png

# Dependências Python empacotadas no APK.
requirements = python3,kivy,pyjnius

orientation = portrait
fullscreen = 0

# Fixa o python-for-android numa release estável (Python 3.11) — evita que o p4a
# baixe/compile o CPython 3.14, que quebra a build. NÃO remover.
p4a.branch = v2024.01.21

# --- Android -----------------------------------------------------------------
# Permissão necessária para NFC (é isto que habilita ler/gravar etiquetas).
android.permissions = NFC

# Registra o app no MANIFESTO como candidato a receber etiquetas NFC, além
# do registro dinâmico (enableForegroundDispatch) feito em nfc_reader.py.
# Sem isto, qualquer lapso do dispatch dinâmico faz o Android entregar a
# etiqueta para o leitor de NFC do próprio sistema em vez do nosso app —
# aparecendo como uma tela genérica e sem estilo ("Nova tag coletada" ou
# similar) no lugar da nossa interface. Ver intent_filters.xml.
android.manifest_intent_filters = %(source.dir)s/intent_filters.xml

# OBS.: NÃO use "android.features" com p4a v2024.01.21 — essa release do
# toolchain não reconhece a opção --feature e o build falha. A exigência de
# hardware NFC na Play Store pode ser adicionada depois, por outro caminho.

# API levels (ajuste conforme o toolchain instalado).
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a

# pyjnius é necessário para acessar a API android.nfc
android.enable_androidx = True

# Mantém a Activity como singleTop para o foreground dispatch de NFC funcionar
# corretamente (a tag chega via onNewIntent na mesma instância).
android.manifest.launch_mode = singleTop
android.release_artifact = apk
android.extra_manifest_xml = android_extra_manifest.xml

[buildozer]
log_level = 2
warn_on_root = 1



