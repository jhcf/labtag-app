# LabTag — Cadastro e Leitura de Etiquetas RFID das Caixas

App Kivy (nome do app: **LabTag**) que gerencia as etiquetas RFID/NFC das
caixas e itens do Kit de Robótica e Eletrônica do projeto REDEMAISCIENCIADF.

> **Nota:** este README descreve o comportamento geral do app; algumas seções
> (fluxo de gravação, telas, senha do modo Preparação) foram bastante
> revisadas nas últimas iterações — se algo aqui destoar do código, o código
> é a fonte da verdade.

## O que o app faz

Ao aproximar uma etiqueta do aparelho:

1. **Etiqueta em branco** → o app pede para escolher o tipo de caixa (1, 2 ou 3),
   **grava essa informação na própria etiqueta** (registro NDEF de texto) e
   **registra a associação** num banco de dados local (SQLite).
2. **Etiqueta já cadastrada** → o app registra a leitura e **abre a URL do guia de
   exploração** daquela caixa na Wikiversidade.

Em qualquer leitura, um **painel de detalhes** logo abaixo do status mostra os
dados da última etiqueta: o **UID** (id físico do chip), a situação (em branco /
gravada / já cadastrada), a caixa e a escola associadas, o **conteúdo NDEF
gravado** (ex.: `REDEMAISDF|2|E07`) e o registro local (número de leituras e
datas de cadastro/última leitura).

O conteúdo gravado na etiqueta tem o formato `REDEMAISDF|<caixa>|<escola>`, por
exemplo `REDEMAISDF|2|E07` para a Caixa 2 da escola E07. Assim cada etiqueta
identifica tanto o **tipo de caixa** quanto a **escola** de origem (UID por escola).
O prefixo `REDEMAISDF` permite o app distinguir uma etiqueta do projeto de
qualquer outra etiqueta NFC.

**Escola do aparelho:** na primeira vez que se vai cadastrar uma etiqueta, o app
pede para escolher a escola deste kit (E01–E15) e memoriza a escolha no banco
local. Todas as etiquetas gravadas depois já saem com essa escola. Dá para trocar
a qualquer momento na faixa azul no topo da tela. Etiquetas no formato antigo
(sem escola) continuam sendo reconhecidas normalmente.

## Arquivos

| Arquivo | Função |
|---|---|
| `main.py` | App Kivy: interface e lógica de leitura/gravação/abertura de URL |
| `nfc_reader.py` | Ponte com o NFC do Android via pyjnius (+ backend "mock" para desktop) |
| `db.py` | Banco de dados local SQLite (associação etiqueta ↔ caixa) |
| `boxes.py` | Definição dos 3 tipos de caixa, lista de escolas (E01–E15) e **URLs da Wikiversidade** (edite aqui) |
| `buildozer.spec` | Configuração de build para gerar o APK Android |

## Antes de compilar: configure as URLs

Abra `boxes.py` e substitua as URLs de exemplo pelos endereços reais das páginas
de cada caixa na Wikiversidade. Este é o único passo obrigatório de configuração.

## Testar no computador (sem celular)

O app tem um **modo simulação** que roda no desktop, sem NFC real, para você
validar todo o fluxo:

```bash
pip install kivy
python main.py
```

Na base da tela aparecem dois botões:
- **"Tag em branco"** simula uma etiqueta nova → escolha uma caixa → o app "grava".
- **"Tag já gravada"** simula reler a mesma etiqueta → o app abre a URL no navegador.

## Preparar os 15 kits de uma vez (modo lote)

O app abre em **modo lote**, pensado exatamente para cadastrar as 45 etiquetas
(15 escolas × 3 caixas) numa sessão só, sem interrupções:

- **Reler uma etiqueta já gravada NÃO abre o navegador.** Em vez disso, o app só
  confirma na tela o que ela contém — assim você pode conferir uma etiqueta sem
  ser jogado para fora do fluxo de cadastro.
- **Progresso por escola:** logo abaixo da faixa da escola, uma linha mostra
  `E01 2/3  ✓ Componentes  ✓ Resistores  ○ Ferramentas`, então você vê num
  relance o que ainda falta na escola atual.
- **Botão "Próxima escola ▶":** pula automaticamente para a próxima escola que
  ainda não está completa (na ordem E01…E15).
- **Marcação de caixa já feita:** ao escolher o tipo de caixa, os que já foram
  gravados naquela escola aparecem com "✓ já feita" (mas ainda dá para gravar
  outra etiqueta do mesmo tipo, se precisar).
- **Aviso de escola trocada:** se você reler uma etiqueta de outra escola, o app
  avisa em vermelho — evita misturar as caixas de escolas diferentes.

**Roteiro sugerido para a sessão:**
1. Toque na faixa azul e selecione a escola (ex.: E01).
2. Aproxime as 3 etiquetas dessa escola, uma a uma, escolhendo a caixa de cada.
   A linha de progresso vai de 0/3 até 3/3.
3. Toque em **"Próxima escola ▶"** e repita. O app já sugere a próxima incompleta.
4. Ao terminar, o app avisa quando todas as 15 escolas estão completas.

Para desligar o modo lote (por exemplo, para *usar* uma caixa e abrir o guia no
navegador), toque no botão laranja "Modo LOTE ligado". O estado fica salvo.



O empacotamento usa o [Buildozer](https://buildozer.readthedocs.io/) e precisa de
Linux (ou WSL no Windows). Resumo:

```bash
pip install buildozer cython
# dependências de sistema (Ubuntu): veja a doc do Buildozer
buildozer -v android debug
```

O APK sai em `bin/`. Instale no aparelho com:

```bash
buildozer android deploy run
```

Requisitos já configurados no `buildozer.spec`:
- permissão `NFC`;
- exigência de hardware NFC;
- `pyjnius` nas dependências (acesso à API `android.nfc`);
- `launch_mode = singleTop` (necessário para o NFC entregar a tag ao app aberto).

## Como funciona o NFC no Android (resumo técnico)

O Kivy não tem NFC nativo. No Android, `nfc_reader.py` usa **pyjnius** para:

- **Ler**: registra um *foreground dispatch* (`NfcAdapter.enableForegroundDispatch`)
  enquanto o app está aberto; cada etiqueta aproximada chega como um `Intent` que
  capturamos em `on_new_intent`, de onde extraímos o UID e o texto NDEF.
- **Gravar**: monta um `NdefMessage` com um registro de texto e chama
  `Ndef.writeNdefMessage()` na etiqueta.

No desktop, a classe `MockNFC` substitui essa camada para permitir os testes.

## Notas de operação

- **Mantenha a etiqueta parada durante a gravação** — mover no meio pode falhar a
  escrita; o app avisa e você tenta de novo.
- **Etiquetas graváveis**: o app assume etiquetas NDEF (NTAG213/215/216 e similares,
  já previstas no kit). Etiquetas somente-leitura não podem ser cadastradas.
- **Banco local por aparelho**: cada telefone mantém seu próprio `etiquetas.db`
  (associações etiqueta↔caixa↔escola + a escola configurada do aparelho). Se uma
  etiqueta foi gravada por outro aparelho, o app ainda a reconhece pelo conteúdo
  NDEF da própria etiqueta e abre o guia normalmente.
- **A escola vai na etiqueta e no banco**: como o código da escola é gravado no
  próprio chip, qualquer aparelho que ler a etiqueta sabe de qual escola ela é —
  o que já prepara o terreno para o log central e o mapa de uso da rede.
- Este app cobre o cadastro e a abertura do guia. O registro de uso com chaveiros
  (professor identificado internamente, monitor anônimo) e a sincronização com o
  sistema central são a etapa seguinte, descrita no documento de conceito do sistema.
