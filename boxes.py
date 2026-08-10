"""
Escolas e itens do projeto REDEMAISCIENCIADF — carregados de 'dados.json'.

Este modulo NAO contem dados embutidos. Ele le o arquivo 'dados.json', que e
gerado a partir da planilha Excel pelo conversor 'planilha_para_dados.py'.

Fluxo de manutencao:
    1. Voce edita a planilha Cadastro_Escolas_e_Itens.xlsx (escolas e itens).
    2. Roda:  python planilha_para_dados.py Cadastro_Escolas_e_Itens.xlsx
       -> gera dados.json
    3. dados.json vai junto com o app (mesma pasta do main.py) no APK.

O app le dados.json em tempo de execucao. Assim, mudar escolas/itens nunca
exige mexer no codigo.

Formato gravado na etiqueta:  REDEMAISDF|<codigo_item>|<codigo_escola>
"""

import json
import os

SCHEME = "REDEMAISDF"

# Paleta ciclica para colorir itens por categoria (a planilha nao traz cor).
_PALETTE = [
    (0.77, 0.35, 0.07, 1),  # laranja
    (0.18, 0.46, 0.71, 1),  # azul
    (0.12, 0.22, 0.39, 1),  # azul-marinho
    (0.14, 0.60, 0.07, 1),  # verde
    (0.55, 0.24, 0.52, 1),  # roxo
    (0.72, 0.11, 0.11, 1),  # vermelho
    (0.10, 0.50, 0.50, 1),  # teal
    (0.60, 0.44, 0.10, 1),  # ambar
]


def _dados_path():
    # dados.json fica ao lado deste arquivo (empacotado junto no APK).
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados.json")


def _carregar():
    caminho = _dados_path()
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except Exception as exc:
        print("Erro ao ler dados.json (%s): %s" % (caminho, exc))
        dados = {"escolas": {}, "itens": {}}

    escolas = dados.get("escolas", {})
    itens_raw = dados.get("itens", {})

    # completa itens com campos derivados (cor por categoria) sem exigir
    # que estejam no JSON.
    cat_color = {}
    itens = {}
    for cod, it in itens_raw.items():
        cat = it.get("category", "Outros")
        if cat not in cat_color:
            cat_color[cat] = _PALETTE[len(cat_color) % len(_PALETTE)]
        itens[cod] = {
            "code": it.get("code", cod),
            "name": it.get("name", cod),
            "short": it.get("short", it.get("name", cod)),
            "category": cat,
            "url": it.get("url", ""),
            "color": it.get("color") or cat_color[cat],
        }
    return escolas, itens


# --------------------------------------------------------------- carga inicial
SCHOOL_NAMES, ITEMS = _carregar()
SCHOOLS = list(SCHOOL_NAMES.keys())

# compatibilidade retro (o app ainda usa BOXES/box_by_code em alguns pontos)
BOXES = ITEMS


def recarregar():
    """Recarrega dados.json em tempo de execucao (apos atualizar o arquivo)."""
    global SCHOOL_NAMES, ITEMS, SCHOOLS, BOXES
    SCHOOL_NAMES, ITEMS = _carregar()
    SCHOOLS = list(SCHOOL_NAMES.keys())
    BOXES = ITEMS


# ------------------------------------------------------------------- escolas
def school_name(code):
    return SCHOOL_NAMES.get(code, code)


def valid_school(code):
    return code in SCHOOL_NAMES


# --------------------------------------------------------------------- itens
def item_by_code(code):
    return ITEMS.get(str(code))


def box_by_code(code):
    return item_by_code(code)


def categories():
    seen = []
    for it in ITEMS.values():
        cat = it.get("category", "Outros")
        if cat not in seen:
            seen.append(cat)
    return seen


def items_in_category(cat):
    return [(c, it) for c, it in ITEMS.items()
            if it.get("category", "Outros") == cat]
