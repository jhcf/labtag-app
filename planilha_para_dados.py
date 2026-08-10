"""
Conversor: planilha Excel (.xlsx) -> dados.json

Roda no COMPUTADOR (não no celular), sempre que voce editar a planilha de
escolas e itens. Gera o arquivo leve 'dados.json' que o aplicativo le.

Uso:
    python planilha_para_dados.py Cadastro_Escolas_e_Itens.xlsx

Gera 'dados.json' na mesma pasta. Copie esse dados.json para junto do app
(mesma pasta do main.py) antes de compilar o APK.

Le duas folhas:
  - "Escolas": colunas Codigo | Nome da escola | (Cidade/RA) | Ativo
  - "Itens":   colunas Codigo | Nome do item | Categoria | URL do guia | Ativo
So entram as linhas com Ativo = SIM.
"""

import json
import sys


def _norm(s):
    return (str(s).strip() if s is not None else "")


def _ativo(v):
    return _norm(v).upper() in ("SIM", "S", "1", "TRUE", "X", "")


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
        }

    dados = {"escolas": escolas, "itens": itens}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print("OK: %d escolas, %d itens -> %s"
          % (len(escolas), len(itens), out_path))


def _achar_header(ws, primeira_coluna_nome):
    """Acha a linha do cabecalho procurando 'Codigo'/'Código' na coluna A."""
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row and _norm(row[0]).lower().startswith("cód") or \
           (row and _norm(row[0]).lower() == "codigo"):
            return i
    return 4  # fallback: cabecalho na linha 4 (padrao da planilha modelo)


if __name__ == "__main__":
    xlsx = sys.argv[1] if len(sys.argv) > 1 else "Cadastro_Escolas_e_Itens.xlsx"
    saida = sys.argv[2] if len(sys.argv) > 2 else "dados.json"
    converter(xlsx, saida)
