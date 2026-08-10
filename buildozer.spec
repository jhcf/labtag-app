[app]

# Identificação do app
title = REDEMAIS Etiquetas
package.name = redemaisetiquetas
package.domain = br.unb.redemaisdf

# Código-fonte
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,xml

# O arquivo ".env" e um "dotfile" sem extensao reconhecivel pelo filtro
# acima (Python trata ".env" como nome sem extensao, nao como extensao
# "env"), entao precisa ser incluido explicitamente aqui para ir junto no
# APK. Sem isto, o app cairia no valor padrao inseguro em tempo de execucao.
source.include_patterns = .env

version = 1.0

# --- Splash (tela exibida ao abrir o app, antes do Python carregar) ---------
# Imagem: logos REDE+CIÊNCIA / UnB + "App LABTAG" / MEC-CNPq-FNDCT-Brasil.
# O arquivo splash.png deve ficar na raiz do projeto (junto do main.py).
presplash.filename = %(source.dir)s/splash.png
# Fundo branco, para casar com o fundo branco da própria imagem.
android.presplash_color = #FFFFFF
# OBS.: não usamos esta imagem como icon.filename — ela tem muito texto e
# vários logos lado a lado, o que fica ilegível reduzido ao tamanho de ícone
# (48x48 a 192x192 px). Para o ícone do app, vale criar uma versão quadrada
# simplificada (ex.: só o símbolo, sem o texto "App LABTAG") e apontar aqui:
#   icon.filename = %(source.dir)s/icon.png

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

[buildozer]
log_level = 2
warn_on_root = 1
