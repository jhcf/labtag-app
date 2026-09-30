"""
Conversor: planilha Excel (.xlsx) -> dados.json

Roda no COMPUTADOR (não no celular), sempre que voce editar a planilha de
escolas, itens e tombamentos. Gera o arquivo leve 'dados.json' que o
aplicativo le.

Uso:
    python planilha_para_dados.py Cadastro_Escolas_e_Itens.xlsx

Gera 'dados.json' na mesma pasta. Copie esse dados.json para junto do app
(mesma pasta do main.py) antes de compilar o APK.

Le tres folhas:
  - "Escolas":     colunas Codigo | Nome da escola | (Cidade/RA) | Ativo
  - "Itens":       colunas Codigo | Nome do item | Categoria | URL do guia |
                    Ativo | Valor unitario (R$)
  - "Tombamentos": colunas Numero de Tombamento | Codigo do Item | Codigo da
                    Escola | Ativo
    Vincula um numero de tombamento (ja colado como QR no equipamento, um
    numero opaco — nao decodificavel por formula) a um item + escola
    especificos. Usado pelo modo simples de leitura por QR code, alternativo
    ao NFC: o app escaneia o QR, procura o numero aqui e mostra o mesmo guia
    que a etiqueta NFC mostraria.
So entram as linhas com Ativo = SIM.
"""

import json
import sys


def _norm(s):
    return (str(s).strip() if s is not None else "")


def _ativo(v):
    return _norm(v).upper() in ("SIM", "S", "1", "TRUE", "X", "")


def _valor(v):
    """Converte a celula de valor unitario para float. Aceita numero direto
    (celula formatada como numero no Excel) ou texto em formato brasileiro
    (virgula decimal, ex.: '2.656,26'). Vazio/invalido vira 0.0."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def converter(xlsx_path, out_path="dados.json"):
    import openpyxl
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)

    # ---- Escolas ----
    escolas = {}
    ws = wb["Escolas"]
    header_row = _achar_header(ws, "Código")
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        cod = _norm(row[0])
        nome = _norm(row[1]) if len(row) > 1 else ""
        ativo = row[3] if len(row) > 3 else "SIM"
        if not cod or not nome:
            continue
        if not _ativo(ativo):
            continue
        escolas[cod] = nome

    # ---- Itens ----
    itens = {}
    ws = wb["Itens"]
    header_row = _achar_header(ws, "Código")
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        cod = _norm(row[0])
        nome = _norm(row[1]) if len(row) > 1 else ""
        cat = _norm(row[2]) if len(row) > 2 else "Outros"
        url = _norm(row[3]) if len(row) > 3 else ""
        ativo = row[4] if len(row) > 4 else "SIM"
        valor = _valor(row[5]) if len(row) > 5 else 0.0
        if not cod or not nome:
            continue
        if not _ativo(ativo):
            continue
        itens[cod] = {
            "code": cod,
            "name": nome,
            "short": nome,
            "category": cat or "Outros",
            "url": url,
            "value": valor,
        }

    # ---- Tombamentos (opcional — folha pode nao existir ainda) ----
    tombamentos = {}
    if "Tombamentos" in wb.sheetnames:
        ws = wb["Tombamentos"]
        header_row = _achar_header_tombamento(ws)
        for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
            numero = _norm(row[0])
            item_cod = _norm(row[1]) if len(row) > 1 else ""
            escola_cod = _norm(row[2]) if len(row) > 2 else ""
            ativo = row[3] if len(row) > 3 else "SIM"
            if not numero or not item_cod or not escola_cod:
                continue
            if not _ativo(ativo):
                continue
            if item_cod not in itens:
                print("AVISO: tombamento %s referencia item '%s' que nao "
                      "existe (ou esta inativo) na aba Itens — ignorado."
                      % (numero, item_cod))
                continue
            if escola_cod not in escolas:
                print("AVISO: tombamento %s referencia escola '%s' que nao "
                      "existe (ou esta inativa) na aba Escolas — ignorado."
                      % (numero, escola_cod))
                continue
            if numero in tombamentos:
                print("AVISO: numero de tombamento %s duplicado na planilha "
                      "— mantendo a primeira ocorrencia." % numero)
                continue
            tombamentos[numero] = {"item": item_cod, "escola": escola_cod}
    else:
        print("AVISO: aba 'Tombamentos' nao encontrada — modo QR/tombamento "
              "ficara vazio (nenhum numero cadastrado).")

    dados = {"escolas": escolas, "itens": itens, "tombamentos": tombamentos}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print("OK: %d escolas, %d itens, %d tombamentos -> %s"
          % (len(escolas), len(itens), len(tombamentos), out_path))


def _achar_header(ws, primeira_coluna_nome):
    """Acha a linha do cabecalho procurando 'Codigo'/'Código' na coluna A."""
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row and _norm(row[0]).lower().startswith("cód") or \
           (row and _norm(row[0]).lower() == "codigo"):
            return i
    return 4  # fallback: cabecalho na linha 4 (padrao da planilha modelo)


def _achar_header_tombamento(ws):
    """Acha a linha do cabecalho da aba Tombamentos (coluna A comeca com
    'Numero'/'Número')."""
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        primeira = _norm(row[0]).lower() if row else ""
        if primeira.startswith("núm") or primeira.startswith("num"):
            return i
    return 4  # fallback, mesmo padrao das outras abas


if __name__ == "__main__":
    xlsx = sys.argv[1] if len(sys.argv) > 1 else "Cadastro_Escolas_e_Itens.xlsx"
    saida = sys.argv[2] if len(sys.argv) > 2 else "dados.json"
    converter(xlsx, saida)
