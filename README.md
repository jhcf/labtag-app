# LabTag — Cadastro e Leitura de Etiquetas RFID das Caixas

App Kivy (nome do app: **LabTag**) que gerencia os qrcodes e as etiquetas RFID/NFC dos recursos dos laboratórios das escolas que participam do projeto Rede Mais Ciência nas Escolas Públicas do DF.

> **Nota:** este README descreve o comportamento geral do app; algumas seções (fluxo de gravação, telas, senha do modo Preparação) foram bastante revisadas nas últimas iterações — se algo aqui destoar do código, o código é a fonte da verdade.

## Como obter o código

```bash
git clone <URL-do-repositorio>
cd labtag-app
```


Se você crê que pode colaborar com esse projeto mander e-mail para JORGE HENRIQUE CABRAL FERNANDES: jhcf@unb.br.

O repositório **não** contém os arquivos de configuração sensível
(`.env`, `secrets.json`, o `.keystore` de assinatura) — eles ficam de fora do
controle de versão de propósito (veja `.gitignore`). Depois de clonar, siga a
seção [Ambiente de desenvolvimento local](#ambiente-de-desenvolvimento-local)
para criar sua própria configuração local antes de rodar o app.

## O que o app faz - USANDO TAG RFID

Ao aproximar uma etiqueta do smartphone:

1. **Etiqueta em branco** → o app pede para escolher a categoria e o item
   (caixa do kit ou equipamento — veja `boxes.py`/`dados.json`), **grava essa
   informação na própria etiqueta** (registro NDEF de texto) e **registra a
   associação** num banco de dados local (SQLite).
2. **Etiqueta já cadastrada** → no **modo Uso**, o app mostra a página do item
   e o botão para abrir o guia de exploração na Wikiversidade. No **modo
   Preparação** (protegido por senha — veja abaixo), mostra os dados
   completos da etiqueta (UID, conteúdo gravado, histórico de leituras) e
   permite regravar.

O conteúdo gravado na etiqueta tem o formato `REDEMAISDF|<item>|<escola>`, por
exemplo `REDEMAISDF|I02|E07` para o item I02 da escola E07. Assim cada
etiqueta identifica tanto o **item** (caixa ou equipamento) quanto a
**escola** de origem. O prefixo `REDEMAISDF` permite o app distinguir uma
etiqueta do projeto de qualquer outra etiqueta NFC — **não mude esse
prefixo**, ele já está gravado fisicamente nas etiquetas em uso.

**Modo Uso vs. modo Preparação:** o app abre sempre em modo Uso (leitura). A
entrada no modo Preparação (necessário para cadastrar/regravar etiquetas)
exige uma senha de 6 dígitos, configurada localmente (veja
[Ambiente de desenvolvimento local](#ambiente-de-desenvolvimento-local)) —
nunca fica hardcoded no código-fonte.

**Escola do aparelho:** ao cadastrar a primeira etiqueta, o app pede para
escolher a escola deste kit e memoriza a escolha no banco local. Todas as
etiquetas gravadas depois já saem com essa escola. Dá para trocar a qualquer
momento pelo menu.

### Modo simples: leitura por QR de tombamento

Além das etiquetas NFC (que o próprio LabTag grava), alguns equipamentos já
têm uma etiqueta de **QR code com o número de tombamento** colada pelo
patrimônio da escola. O botão **"Ler QR de tombamento"** na tela de espera
abre um app scanner de QR já instalado no aparelho (o LabTag não tem câmera
embutida — veja o porquê na seção técnica abaixo); ao ler o código, o app
procura o número numa tabela local (aba **"Tombamentos"** da planilha, veja
[Dados: itens, escolas e tombamentos](#3-dados-itens-escolas-e-tombamentos))
e mostra a mesma página de item/guia que uma etiqueta NFC mostraria.

Diferença importante: o modo QR é **sempre só leitura** — a etiqueta física
já existe no equipamento, então o app nunca grava nela. Se um número não
estiver cadastrado, a correção é feita editando a planilha central (não há
"cadastrar pelo aparelho" nesse fluxo, ao contrário do NFC).

## Arquivos

| Arquivo | Função |
|---|---|
| `main.py` | App Kivy: telas, navegação e lógica de leitura/gravação/abertura de URL |
| `nfc_reader.py` | Ponte com o NFC do Android via pyjnius (+ backend "mock" para desktop) |
| `qr_scanner.py` | Leitura de QR (modo tombamento) via app scanner externo (+ backend "mock" para desktop) |
| `db.py` | Banco de dados local SQLite (associação etiqueta ↔ item ↔ escola) |
| `boxes.py` | Carrega itens e escolas a partir de `dados.json` (não edite os dados aqui direto) |
| `dados.json` | Itens (caixas/equipamentos) e escolas — gerado a partir da planilha, veja abaixo |
| `planilha_para_dados.py` | Conversor: planilha Excel → `dados.json` |
| `env_config.py` | Carrega a senha do modo Preparação de `.env`/`secrets.json` (nunca do código) |
| `buildozer.spec` | Configuração de build para gerar o APK/AAB Android |
| `release.sh` | Automatiza a geração do release assinado (veja [Gerando um release](#gerando-um-release-apk-assinado)) |

## Ambiente de desenvolvimento local

Passos para rodar o app no seu computador (sem precisar de celular nem
compilar nada) e para editar o conteúdo (itens/escolas).

### 1. Ambiente Python

```bash
cd labtag-app/
/usr/bin/python3 -m venv .venv
source .venv/bin/activate
python3 -m venv .venv
source .venv/bin/activate
pip install kivy
```

### 2. Configurar a senha do modo Preparação (local)

O modo Preparação (cadastro/regravação de etiquetas) é protegido por senha.
Para desenvolver localmente, crie um `.env` na raiz do projeto:

```bash
cp .env.example .env
```

Edite o `.env` e defina `PREP_PASSWORD` com uma senha de 6 dígitos à sua
escolha. Esse arquivo **nunca** deve ser commitado (já está no
`.gitignore`) — cada pessoa que desenvolve localmente usa a própria senha de
teste; a senha de produção (usada nos APKs distribuídos às escolas) é
definida à parte, na hora de gerar o release (veja mais abaixo).

### 3. Dados: itens, escolas e tombamentos

O app lê os itens (caixas do kit, equipamentos), as escolas e os vínculos de
tombamento de `dados.json`. Esse arquivo é gerado a partir de uma planilha
Excel com três abas — nunca edite `dados.json` nem `boxes.py` diretamente:

```bash
python planilha_para_dados.py Cadastro_Escolas_e_Itens.xlsx dados.json
```

- **Escolas**: Código | Nome da escola | (Cidade/RA) | Ativo
- **Itens**: Código | Nome do item | Categoria | URL do guia | Ativo
- **Tombamentos**: Número de Tombamento | Código do Item | Código da Escola |
  Ativo | Observações — vincula um número de tombamento (opaco, já colado
  como QR no equipamento) a um item e uma escola específicos. Essa aba é
  **opcional**: se não existir na planilha, o modo QR simplesmente fica sem
  nenhum número cadastrado, sem erro.

Veja os comentários no topo de `planilha_para_dados.py` para detalhes do
formato de cada aba, e os avisos que o conversor imprime quando uma linha de
tombamento referencia um item/escola inexistente ou está duplicada.

### 4. Rodar no desktop (modo simulação)

```bash
pip install --upgrade pip buildozer cython==0.29.34
PATH="$(echo "$PATH" | tr ':' '\n' | grep -v '\.pyenv' | paste -sd:)"
sudo apt install -y git zip unzip openjdk-17-jdk autoconf libtool pkg-config   zlib1g-dev libncurses-dev libtinfo6 cmake libffi-dev libssl-dev build-essential ccache
pip install legacy-cgi setuptools
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH="$JAVA_HOME/bin:$PATH"
buildozer -v android debug
```

Sem celular, o app usa backends simulados de NFC (`MockNFC`) e de QR
(`MockScanner`). Na base da tela aparecem os botões:
- **"Nova tag"** simula uma etiqueta em branco (UID novo a cada clique) →
  escolha a categoria/item → o app "grava".
- **"Reler última"** simula reaproximar a mesma etiqueta.
- **"QR cadastrado"** simula ler o primeiro número de tombamento que existir
  em `dados.json`; **"QR desconhecido"** simula ler um número não cadastrado.

Isso permite testar o fluxo inteiro — leitura, gravação, modo Preparação,
progresso por escola, leitura por QR/tombamento — sem precisar compilar um
APK a cada mudança.

### 5. Gerar um APK de teste (debug, no celular)

Para testar de verdade no celular (leitura/gravação NFC real), é preciso
compilar com o [Buildozer](https://buildozer.readthedocs.io/) (exige Linux
ou WSL):

```bash
pip install buildozer cython
buildozer -v android debug
buildozer android deploy run   # instala e roda no celular conectado por USB
```

O APK de debug **não precisa** de keystore de release — o buildozer assina
automaticamente com uma chave de debug genérica, suficiente para testar no
seu próprio aparelho.

## Gerando um release (APK assinado)

> ⚠️ **Esta seção é só para quem gerencia centralmente a distribuição dos
> APKs do projeto — não para todo desenvolvedor.** Ao contrário do build de
> debug (que qualquer pessoa pode gerar para testar no próprio celular), o
> release usa uma **keystore de produção**: a chave que assina os APKs que
> vão para as escolas. Essa chave precisa ser **única** e **estável** ao
> longo do tempo — se cada desenvolvedor gerar a sua própria, os APKs
> ficam incompatíveis entre si (o Android trata apps assinados com chaves
> diferentes como aplicativos completamente diferentes, mesmo com o mesmo
> código). Gerar uma keystore nova por engano, ou perder a existente, impede
> que quem já tem o app instalado receba atualizações — a única saída
> nesse caso é desinstalar e reinstalar do zero em todos os aparelhos.
>
> Por isso: **a keystore de release é gerada uma única vez**, por quem
> coordena a distribuição, e depois é guardada com cuidado (gerenciador de
> senhas, backup seguro) — nunca commitada no repositório, nunca recriada
> "só para testar".

### Gerando a keystore (uma única vez, feito por quem coordena a distribuição)

```bash
keytool -genkey -v -keystore labtag-release.keystore \
  -alias labtag -keyalg RSA -keysize 2048 -validity 10000
```

O `keytool` vai pedir uma senha (anote com cuidado — sem ela, a keystore é
inútil) e alguns dados de identificação (nome, organização etc., podem ser
genéricos). Guarde o arquivo `labtag-release.keystore` gerado em local seguro
**fora do repositório** — ele nunca deve ser commitado (já está no
`.gitignore`).

### Gerando o release (com a keystore já em mãos)

Quem já tem a keystore de produção (recebida de quem a gerou, não gerada de
novo) usa o script `release.sh`:

```bash
export RELEASE_PROJECT_NAME=LabTag
export RELEASE_KEYSTORE_PASSWORD='a-senha-da-keystore'
./release.sh
```

O script automatiza: `buildozer android release` → conversão do `.aab`
gerado para um `.apk` universal instalável (via `bundletool`) → verificação
da assinatura. O `.apk` final sai em `bin/` e é esse arquivo que vai para a
distribuição (GitHub Releases, link direto, QR code etc.).

Por padrão, `release.sh` procura a keystore em `labtag-release.keystore` na
raiz do projeto (nome derivado de `RELEASE_PROJECT_NAME`) — se o arquivo
estiver em outro lugar, aponte com `RELEASE_KEYSTORE_FILE`. Veja os
comentários no topo do próprio `release.sh` para todas as variáveis
aceitas.

### Configurando a senha de produção do modo Preparação

Separado da keystore: a senha do modo Preparação **usada nos APKs
distribuídos** vem de `secrets.json` (não do `.env` de desenvolvimento — veja
por quê na seção de configuração local). Antes de gerar um release oficial:

```bash
cp secrets.json.example secrets.json
# edite secrets.json e defina a senha de producao (6 digitos)
```

Esse arquivo também não é commitado. Quem gerencia a distribuição decide e
guarda essa senha (é ela que os monitores/professores vão usar para entrar
no modo Preparação nos aparelhos já distribuídos).

## Como funciona o NFC no Android (resumo técnico)

O Kivy não tem NFC nativo. No Android, `nfc_reader.py` usa **pyjnius** para:

- **Ler**: registra um *foreground dispatch* (`NfcAdapter.enableForegroundDispatch`)
  enquanto o app está aberto; cada etiqueta aproximada chega como um `Intent` que
  capturamos em `on_new_intent`, de onde extraímos o UID e o texto NDEF. O app
  também está registrado no `AndroidManifest.xml` (via `intent_filters.xml`)
  como candidato a receber etiquetas NFC diretamente do sistema, como reforço
  caso o dispatch dinâmico falhe num instante específico.
- **Gravar**: monta um `NdefMessage` com um registro de texto e chama
  `Ndef.writeNdefMessage()` na etiqueta. A gravação só acontece no exato
  momento em que uma etiqueta é detectada com um item já escolhido
  ("armado") — nunca reaproveitando uma referência de uma leitura anterior,
  para evitar gravações instáveis se a etiqueta sair do campo NFC entre a
  leitura e a escrita.

No desktop, a classe `MockNFC` substitui essa camada para permitir os testes.

## Como funciona a leitura de QR/tombamento (resumo técnico)

Diferente do NFC, o LabTag **não embute câmera nem decodificador de QR**.
`qr_scanner.py` dispara um `Intent` padrão do Android
(`com.google.zxing.client.android.SCAN`) para um app scanner externo já
instalado no aparelho (compatível com o padrão ZXing — comum em câmeras/
launchers de fábrica, ou o app gratuito "Barcode Scanner" caso nenhum outro
responda) e recebe o texto decodificado de volta via `onActivityResult`.

Essa foi uma decisão deliberada: qualquer dependência nativa nova
(câmera, ML Kit, zbar) empacotada diretamente no app teria o mesmo tipo de
risco de instabilidade de build que o NFC já trouxe neste projeto (p4a
fixado numa versão antiga, Gradle sensível à versão do Java, etc.). Delegar
para um app externo evita esse risco por completo — e, como bônus, **não
exige a permissão `CAMERA`** no manifesto do LabTag, já que quem abre a
câmera é o app externo.

Se nenhum app compatível estiver instalado, o Android mostra automaticamente
uma lista de apps na Play Store capazes de responder a esse tipo de Intent
— comportamento padrão do sistema, não é algo que o LabTag precisa tratar.

No desktop, a classe `MockScanner` substitui essa camada.

## Notas de operação

- **Mantenha a etiqueta parada durante a gravação** — mover no meio pode falhar a
  escrita; o app avisa e você tenta de novo.
- **Etiquetas graváveis**: o app assume etiquetas NDEF (NTAG213/215/216 e similares,
  já previstas no kit). Etiquetas somente-leitura não podem ser cadastradas.
- **Banco local por aparelho**: cada telefone mantém seu próprio banco de dados
  (associações etiqueta↔item↔escola + a escola configurada do aparelho). Se uma
  etiqueta foi gravada por outro aparelho, o app ainda a reconhece pelo conteúdo
  NDEF da própria etiqueta.
- **A escola vai na etiqueta e no banco**: como o código da escola é gravado no
  próprio chip, qualquer aparelho que ler a etiqueta sabe de qual escola ela é.
