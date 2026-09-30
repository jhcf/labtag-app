"""
Escolas e itens do projeto REDEMAISCIENCIADF — carregados de 'dados.json'.

Este modulo NAO contem dados embutidos. Ele le o arquivo 'dados.json', que e
gerado a partir da planilha Excel pelo conversor 'planilha_para_dados.py'.

Fluxo de manutencao:
    1. Voce edita a planilha Cadastro_Escolas_e_Itens.xlsx (escolas, itens
       e tombamentos).
    2. Roda:  python planilha_para_dados.py Cadastro_Escolas_e_Itens.xlsx
       -> gera dados.json
    3. dados.json vai junto com o app (mesma pasta do main.py) no APK.

O app le dados.json em tempo de execucao. Assim, mudar escolas/itens/
tombamentos nunca exige mexer no codigo.

Formato gravado na etiqueta NFC:  REDEMAISDF|<codigo_item>|<codigo_escola>

Modo QR/tombamento: numeros de tombamento sao OPACOS (nao decodificaveis por
formula) — cada numero ja esta gravado numa etiqueta fisica colada no
equipamento, e a planilha (aba "Tombamentos") e quem diz a qual item e
escola cada numero pertence. Ver qr_scanner.py para a leitura do QR.
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
        dados = {"escolas": {}, "itens": {}, "tombamentos": {}}

    escolas = dados.get("escolas", {})
    itens_raw = dados.get("itens", {})
    tombamentos_raw = dados.get("tombamentos", {})

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
            "value": it.get("value", 0.0),
        }

    # tombamentos: numero (string) -> {"item": codigo_item, "escola": codigo_escola}
    tombamentos = {}
    for numero, info in tombamentos_raw.items():
        tombamentos[str(numero)] = {
            "item": info.get("item", ""),
            "escola": info.get("escola", ""),
        }

    return escolas, itens, tombamentos


# --------------------------------------------------------------- carga inicial
SCHOOL_NAMES, ITEMS, TOMBAMENTOS = _carregar()
SCHOOLS = list(SCHOOL_NAMES.keys())

# compatibilidade retro (o app ainda usa BOXES/box_by_code em alguns pontos)
BOXES = ITEMS


def recarregar():
    """Recarrega dados.json em tempo de execucao (apos atualizar o arquivo)."""
    global SCHOOL_NAMES, ITEMS, TOMBAMENTOS, SCHOOLS, BOXES
    SCHOOL_NAMES, ITEMS, TOMBAMENTOS = _carregar()
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


# --------------------------------------------------------------- tombamentos
def resource_by_tombamento(numero):
    """
    Dado um numero de tombamento (string lida do QR), devolve
    (item_code, school_code) se estiver cadastrado, ou None caso contrario.

    Nao tenta decodificar o numero — e so uma consulta na tabela carregada
    de dados.json (aba "Tombamentos" da planilha).
    """
    info = TOMBAMENTOS.get(str(numero).strip())
    if info is None:
        return None
    item_code = info.get("item", "")
    school_code = info.get("escola", "")
    if not item_by_code(item_code) or not valid_school(school_code):
        # dados.json pode estar desatualizado em relacao a itens/escolas
        # (ex.: item foi removido depois que o tombamento foi cadastrado).
        return None
    return (item_code, school_code)
