"""
LabTag — Cadastro e leitura de etiquetas RFID das caixas do kit.
App do projeto REDEMAISCIENCIADF (CNPq Chamada 13/2024).

PADRAO DE GRAVACAO: "decidir primeiro, agir no toque depois".

Gravar num objeto Tag capturado numa leitura anterior e fragil: o Tag so e
valido enquanto a etiqueta esta fisicamente no campo NFC, e qualquer navegacao
de tela no meio (escolher categoria, escolher item) da tempo dela sair do
campo — daí instabilidade ("nao consegue regravar", "detecta nova tag" no
meio do fluxo).

Este app faz o oposto: a escolha do item acontece numa tela PURA DE UI, sem
nenhuma etiqueta envolvida (self.write_target guarda so o CODIGO escolhido).
So depois disso o app entra em modo "armado" e pede o toque — e a gravacao
roda IMEDIATAMENTE dentro do proprio evento de deteccao (_do_write_now),
sem qualquer UI no meio. Isso elimina a janela onde a tag pode sumir.

Alem disso, o app so processa toques quando esta "escutando":
  - tela de espera, em leitura normal; ou
  - em modo armado (write_target definido), em qualquer tela.
Fora disso (navegando categorias/itens, menu, etc.) toques sao ignorados —
sem isso, qualquer aproximacao acidental reabre o fluxo no meio de uma
operacao. Ha tambem um debounce por UID para engolir entregas duplicadas
de um unico toque fisico (comum em alguns aparelhos/etiquetas).

Telas:
  - espera      : le normalmente (idle) OU mostra o prompt de gravacao
                  armada ("aproxime para gravar: <item>")
  - info        : mostra o que uma leitura trouxe (reconhecida, de outra
                  escola, item extinto, ou em branco) com um botao para
                  cadastrar/regravar (que leva a "escolher")
  - escolher    : escolhe categoria e item — TELA PURA DE UI, sem etiqueta
  - menu        : escola, modo de operacao, progresso, lista de etiquetas
  - escola      : escolher a escola deste kit
  - progresso   : painel vertical das escolas

Conteudo gravado na etiqueta:  REDEMAISDF|<item>|<escola>
"""

import time
import webbrowser

from kivy.app import App
from kivy.core.window import Window
from kivy.clock import mainthread, Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.textinput import TextInput

from boxes import (ITEMS, SCHOOLS, SCHEME, box_by_code, valid_school,
                   school_name, categories, items_in_category,
                   resource_by_tombamento)
from db import TagDatabase
from nfc_reader import get_nfc, is_mock
import qr_scanner
import env_config

DEBOUNCE_SECONDS = 1.2  # ignora releituras do mesmo UID neste intervalo

# Senha de 6 digitos exigida para ENTRAR no modo Preparacao (gravar/regravar
# etiquetas). Sair da Preparacao de volta para Uso nao exige senha.
# ALTERE AQUI para trocar a senha — e fixa no codigo (hardcoded), nao fica
# em nenhum arquivo de configuracao nem no banco de dados.
# Senha de 6 digitos exigida para ENTRAR no modo Preparacao (gravar/regravar
# etiquetas). Sair da Preparacao de volta para Uso nao exige senha.
#
# A senha vem de secrets.json (chave PREP_PASSWORD) — ou de .env em
# desenvolvimento local — nenhum dos dois e commitado no repositorio. Veja
# secrets.json.example para o modelo. Se nada for encontrado, usa-se um
# valor padrao obviamente inseguro ("000000") e um aviso e impresso no
# log — isso nunca deve acontecer numa instalacao real, so serve para o
# app nao travar em ambiente de desenvolvimento sem configuracao.
PREP_PASSWORD = env_config.get("PREP_PASSWORD")
if not PREP_PASSWORD:
    PREP_PASSWORD = "000000"
    print("[LABTAG] AVISO: PREP_PASSWORD nao encontrado (nem em secrets.json "
          "nem em .env) — usando senha padrao insegura '000000'. Copie "
          "secrets.json.example para secrets.json e defina uma senha real "
          "antes de distribuir o app.")


def _log(msg):
    print("[LABTAG] %s" % msg)


def encode_payload(box_code, school_code):
    return "%s|%s|%s" % (SCHEME, box_code, school_code)


def decode_payload(text):
    if not text:
        return None
    text = text.strip()
    if not text.startswith(SCHEME + "|"):
        return None
    parts = text.split("|")
    if len(parts) < 2:
        return None
    box_code = parts[1].strip()
    if not box_by_code(box_code):
        return None
    school = parts[2].strip() if len(parts) >= 3 and parts[2].strip() else None
    return (box_code, school)


NAVY = (0.12, 0.22, 0.39, 1)
ACCENT = (0.18, 0.46, 0.71, 1)
LIGHT = (0.96, 0.96, 0.97, 1)
WARN = (0.80, 0.42, 0.09, 1)
GREEN = (0.18, 0.49, 0.20, 1)


class FlatButton(Button):
    def __init__(self, text="", bg=NAVY, fg=(1, 1, 1, 1), height=64,
                 font_size="17sp", **kw):
        super().__init__(text=text, **kw)
        self.background_normal = ""
        self.background_down = ""
        self.background_color = bg
        self.color = fg
        self.font_size = font_size
        self.size_hint_y = None
        self.height = dp(height)
        self.halign = "center"
        self.valign = "middle"
        self.bind(size=self._wrap)

    def _wrap(self, *_):
        self.text_size = (self.width - dp(20), None)


def title_label(text, size="20sp", color=(0.1, 0.1, 0.1, 1), height=None):
    lbl = Label(text=text, markup=True, font_size=size, color=color,
                halign="center", valign="middle", size_hint_y=None)
    lbl.height = dp(height) if height else dp(40)
    lbl.bind(size=lambda *_: setattr(lbl, "text_size", (lbl.width, None)))
    return lbl


def spacer(h=None):
    s = BoxLayout(size_hint_y=None if h else 1)
    if h:
        s.height = dp(h)
    return s


# ============================================================ TELA: splash
class ProjectSplashScreen(Screen):
    """
    Primeira splash: identificacao do PROJETO guarda-chuva (REDE+CIENCIA /
    UnB / MEC-CNPq-FNDCT-Brasil) — nao e a marca do app em si, e sim do
    programa institucional do qual o LabTag faz parte.

    Complementa a splash NATIVA do Android (configurada no buildozer.spec via
    presplash.filename), que aparece antes mesmo do Python carregar. Esta
    tela cobre o intervalo seguinte, entre o Python iniciar e a interface
    normal aparecer — e tambem funciona no modo desktop de teste, onde a
    splash nativa do Android nao existe.

    Em seguida vem a AppSplashScreen, essa sim com a marca propria do app
    (LabTag), em tela cheia.
    """
    SPLASH_SECONDS = 2.0

    def __init__(self, app, **kw):
        super().__init__(name="splash", **kw)
        self.app = app
        root = BoxLayout(orientation="vertical")
        # Fundo branco explicito: por padrao o Kivy pinta a tela de preto,
        # o que destoaria das margens brancas da propria imagem (ela e mais
        # "paisagem" que a tela do celular, entao sobra espaco acima/abaixo).
        with root.canvas.before:
            Color(1, 1, 1, 1)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._sync_bg, size=self._sync_bg)
        img = KivyImage(source="splash.png", allow_stretch=True,
                        keep_ratio=True)
        root.add_widget(img)
        self.add_widget(root)

    def _sync_bg(self, instance, _value):
        self._bg.pos = instance.pos
        self._bg.size = instance.size

    def on_enter(self, *_):
        Clock.schedule_once(self._go_next, self.SPLASH_SECONDS)

    def _go_next(self, *_):
        self.app.go("splash_app", direction="left")


class AppSplashScreen(Screen):
    """
    Segunda splash: a marca do PROPRIO APP (LabTag) — a arte oficial e um
    "cartao" com cantos arredondados sobre fundo branco (nao uma ilustracao
    de sangria total), entao usamos o mesmo tratamento da ProjectSplashScreen:
    fundo branco solido + imagem inteira preservada (sem cortar nem
    distorcer), centralizada e ocupando o maximo de espaco possivel na tela.
    Usar fit_mode="cover" aqui cortaria os cantos arredondados e as bordas
    da ilustracao de forma feia, ja que a arte nao foi desenhada para
    sangria total.
    """
    SPLASH_SECONDS = 1.6

    def __init__(self, app, **kw):
        super().__init__(name="splash_app", **kw)
        self.app = app
        root = BoxLayout(orientation="vertical")
        with root.canvas.before:
            Color(1, 1, 1, 1)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._sync_bg, size=self._sync_bg)
        img = KivyImage(source="splash_labtag.png", allow_stretch=True,
                        keep_ratio=True)
        root.add_widget(img)
        self.add_widget(root)

    def _sync_bg(self, instance, _value):
        self._bg.pos = instance.pos
        self._bg.size = instance.size

    def on_enter(self, *_):
        Clock.schedule_once(self._go_next, self.SPLASH_SECONDS)

    def _go_next(self, *_):
        self.app.go("espera", direction="left")


# ============================================================ TELA: espera
class WaitScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(name="espera", **kw)
        self.app = app
        root = BoxLayout(orientation="vertical")

        header = BoxLayout(orientation="vertical", size_hint_y=None,
                           height=dp(72), padding=(dp(12), dp(8)))
        header.add_widget(title_label("[b]LabTag[/b]", size="24sp",
                                      color=NAVY, height=34))
        self.school_tag = title_label("", size="13sp",
                                      color=(0.4, 0.4, 0.4, 1), height=22)
        header.add_widget(self.school_tag)
        root.add_widget(header)

        center = BoxLayout(orientation="vertical", spacing=dp(10),
                           padding=(dp(24), dp(6)))
        center.add_widget(spacer())
        self.icon = Label(text="[size=52sp][b]NFC[/b][/size]", markup=True,
                          size_hint_y=None, height=dp(80), color=ACCENT)
        center.add_widget(self.icon)
        self._default_instr = (
            "[b]Aproxime uma etiqueta[/b]\n[color=666666][size=14sp]encoste "
            "uma caixa na parte de tras do celular[/size][/color]")
        self.instr = title_label(self._default_instr, size="18sp", height=76)
        center.add_widget(self.instr)

        self.error_label = title_label("", size="13sp", color=(0.8, 0.2, 0.2, 1),
                                       height=0)
        center.add_widget(self.error_label)

        self.cancel_btn = FlatButton("Cancelar", bg=WARN, height=0,
                                     font_size="14sp")
        self.cancel_btn.opacity = 0
        self.cancel_btn.disabled = True
        self.cancel_btn.bind(on_release=lambda *_: self.app.cancel_write())
        center.add_widget(self.cancel_btn)
        center.add_widget(spacer())
        root.add_widget(center)

        bottom = BoxLayout(orientation="vertical", size_hint_y=None,
                           height=dp(178), padding=(dp(16), dp(6)),
                           spacing=dp(8))
        self.menu_btn = FlatButton("MENU", bg=NAVY, height=58, font_size="18sp")
        self.menu_btn.bind(on_release=lambda *_: self.app.go("menu"))
        bottom.add_widget(self.menu_btn)
        self.qr_btn = FlatButton("Ler QR de tombamento", bg=ACCENT,
                                 height=48, font_size="15sp")
        self.qr_btn.bind(on_release=lambda *_: self.app.scan_tombamento())
        bottom.add_widget(self.qr_btn)
        self.mode_bar = FlatButton("", bg=LIGHT, fg=(0.3, 0.3, 0.3, 1),
                                   height=44, font_size="14sp")
        self.mode_bar.bind(on_release=lambda *_: self.app.toggle_mode())
        bottom.add_widget(self.mode_bar)
        root.add_widget(bottom)
        self.add_widget(root)

    def on_pre_enter(self, *_):
        # Reforca o registro de leitura NFC toda vez que a tela de espera
        # (a unica tela que "escuta" toques normais) volta a ficar ativa.
        try:
            self.app.nfc.ensure_active()
        except Exception:
            pass
        self.refresh()

    def refresh(self):
        # A escola definida so importa para quem esta cadastrando etiquetas
        # (modo Preparacao). No modo Uso e informacao irrelevante para quem
        # so esta lendo — ocultar reduz ruido na tela principal.
        if self.app.mode == "preparacao":
            esc = self.app.school or "nao definida"
            self.school_tag.text = "Escola deste kit: %s" % esc
            self.school_tag.height = dp(22)
            self.school_tag.opacity = 1
        else:
            self.school_tag.text = ""
            self.school_tag.height = 0
            self.school_tag.opacity = 0
        modo = "USO" if self.app.mode == "uso" else "PREPARACAO"
        self.mode_bar.text = "Modo: %s  -  toque p/ trocar" % modo
        self.error_label.text = ""
        self.error_label.height = 0
        if self.app.write_target is not None:
            nome = self.app.write_target.get("name", "?")
            self.instr.text = (
                "[b][color=CC6600]Aproxime a etiqueta[/color][/b]\n"
                "[color=666666][size=14sp]para gravar: %s[/size][/color]"
                % nome)
            self.icon.color = WARN
            self.cancel_btn.height = dp(48)
            self.cancel_btn.opacity = 1
            self.cancel_btn.disabled = False
        else:
            self.instr.text = self._default_instr
            self.icon.color = ACCENT
            self.cancel_btn.height = 0
            self.cancel_btn.opacity = 0
            self.cancel_btn.disabled = True

    def show_error(self, msg):
        self.error_label.text = "[color=CC3300]%s[/color]" % msg
        self.error_label.height = dp(40)


# ============================================================ TELA: escolher
class ChooseScreen(Screen):
    """
    Escolha de categoria e item. TELA PURA DE UI — nenhuma etiqueta
    envolvida aqui. Ao escolher um item, arma a gravacao (app.arm_write) e
    volta para a tela de espera, que entao pede o toque.
    """
    def __init__(self, app, **kw):
        super().__init__(name="escolher", **kw)
        self.app = app
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)
        self.selected_category = None

    def on_pre_enter(self, *_):
        self.selected_category = None
        self.build()

    def build(self):
        self.root.clear_widgets()
        top = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(12), 0))
        close = FlatButton("Cancelar", bg=LIGHT, fg=(0.15, 0.15, 0.15, 1),
                           height=44, font_size="15sp")
        close.size_hint_x = None
        close.width = dp(110)
        close.bind(on_release=lambda *_: self.app.go("espera", "right"))
        top.add_widget(close)
        top.add_widget(spacer())
        top.add_widget(title_label("Escola: [b]%s[/b]" % (self.app.school or "--"),
                                   size="14sp", color=(0.4, 0.4, 0.4, 1),
                                   height=52))
        self.root.add_widget(top)
        if self.selected_category is None:
            self._build_categories()
        else:
            self._build_items()

    def _build_categories(self):
        self.root.add_widget(title_label("[b]Escolha a categoria:[/b]",
                                         size="17sp", height=36))
        scroll = ScrollView()
        col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8),
                        padding=(dp(12), dp(4)))
        col.bind(minimum_height=col.setter("height"))
        for cat in categories():
            n = len(items_in_category(cat))
            btn = FlatButton("%s  (%d)" % (cat, n), bg=NAVY, height=60,
                             font_size="16sp")
            btn.halign = "left"
            btn.bind(on_release=lambda inst, c=cat: self._open_category(c))
            col.add_widget(btn)
        scroll.add_widget(col)
        self.root.add_widget(scroll)

    def _open_category(self, cat):
        self.selected_category = cat
        self.build()

    def _build_items(self):
        cat = self.selected_category
        bar = BoxLayout(size_hint_y=None, height=dp(46), padding=(dp(12), 0),
                        spacing=dp(8))
        back = FlatButton("< Categorias", bg=LIGHT, fg=(0.15, 0.15, 0.15, 1),
                          height=42, font_size="14sp")
        back.size_hint_x = None
        back.width = dp(140)
        back.bind(on_release=lambda *_: self._back())
        bar.add_widget(back)
        bar.add_widget(title_label("[b]%s[/b]" % cat, size="15sp", height=46))
        self.root.add_widget(bar)
        done = self.app.db.boxes_for_school(self.app.school) if self.app.school else set()
        scroll = ScrollView()
        col = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8),
                        padding=(dp(12), dp(4)))
        col.bind(minimum_height=col.setter("height"))
        for code, item in items_in_category(cat):
            bg = item.get("color", NAVY)
            marca = "   (feita)" if code in done else ""
            btn = FlatButton("%s%s" % (item["name"], marca),
                             bg=bg, fg=(1, 1, 1, 1), height=64, font_size="15sp")
            btn.halign = "left"
            btn.bind(on_release=lambda inst, it=item: self.app.arm_write(it))
            col.add_widget(btn)
        scroll.add_widget(col)
        self.root.add_widget(scroll)

    def _back(self):
        self.selected_category = None
        self.build()


# ============================================================ TELA: info
class InfoScreen(Screen):
    """
    Mostra o resultado de uma leitura: item reconhecido, de outra escola,
    codigo extinto, ou etiqueta em branco. Nunca grava nada sozinha — so
    oferece o caminho para "escolher" (que arma uma futura gravacao).
    """
    def __init__(self, app, **kw):
        super().__init__(name="info", **kw)
        self.app = app
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)
        self._data = None

    def show_blank(self, uid, text):
        self._data = ("blank", uid, text, None, None, False)

    def show(self, box_code, school, uid, registro, ndef=None, foreign=False):
        self._data = ("item", box_code, school, uid, registro, ndef, foreign)

    def show_qr(self, numero, resolved):
        """
        `resolved` e (item_code, school_code) se o numero de tombamento
        estiver cadastrado na aba Tombamentos, ou None se nao for
        encontrado. Modo QR e sempre SO LEITURA — a etiqueta fisica ja
        existe no equipamento; nao ha "cadastrar/regravar" pelo aparelho,
        so pela planilha central.
        """
        self._data = ("qr", numero, resolved)

    def on_pre_enter(self, *_):
        self.build()

    def _top(self):
        top = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(12), 0))
        close = FlatButton("< Voltar", bg=LIGHT, fg=(0.15, 0.15, 0.15, 1),
                           height=44, font_size="15sp")
        close.size_hint_x = None
        close.width = dp(100)
        close.bind(on_release=lambda *_: self.app.go("espera", "right"))
        top.add_widget(close)
        top.add_widget(spacer())
        top.add_widget(title_label("Escola: [b]%s[/b]" % (self.app.school or "--"),
                                   size="14sp", color=(0.4, 0.4, 0.4, 1),
                                   height=52))
        self.root.add_widget(top)

    def build(self):
        self.root.clear_widgets()
        if self._data is None:
            self.app.go("espera", "right")
            return
        kind = self._data[0]
        self._top()
        b = BoxLayout(orientation="vertical", spacing=dp(8),
                      padding=(dp(20), dp(10)))

        if kind == "blank":
            _, uid, text, *_r = self._data
            b.add_widget(title_label(
                "[color=666666][b]Etiqueta em branco[/b][/color]",
                size="18sp", height=32))
            b.add_widget(title_label(
                "[color=666666][size=12sp]UID: %s[/size][/color]" % uid,
                height=20))
            if text:
                b.add_widget(title_label(
                    "[color=CC6600][size=12sp]Conteudo nao reconhecido: "
                    "%s[/size][/color]" % text, height=22))
            b.add_widget(spacer(8))
            if self.app.mode == "preparacao":
                btn = FlatButton("Cadastrar item", bg=ACCENT, height=54,
                                 font_size="15sp")
                btn.bind(on_release=lambda *_: self.app.go_choose())
                b.add_widget(btn)
            else:
                b.add_widget(title_label(
                    "[color=666666][size=13sp]Esta etiqueta ainda nao foi "
                    "cadastrada. Para cadastra-la, mude para o modo "
                    "Preparacao no menu.[/size][/color]", height=54))
        elif kind == "qr":
            _, numero, resolved = self._data
            if resolved is None:
                b.add_widget(title_label(
                    "[color=CC3300][b]Tombamento nao cadastrado[/b][/color]",
                    size="18sp", height=32))
                b.add_widget(title_label(
                    "[color=666666]numero: %s[/color]" % numero,
                    size="14sp", height=24))
                b.add_widget(title_label(
                    "[color=666666][size=13sp]Este numero nao esta na "
                    "planilha de tombamentos. Para cadastra-lo, adicione "
                    "uma linha na aba Tombamentos e gere um novo "
                    "dados.json — nao da para corrigir pelo "
                    "aparelho.[/size][/color]", height=70))
            else:
                item_code, school_code = resolved
                box = box_by_code(item_code)
                if box is None:
                    b.add_widget(title_label(
                        "[color=CC3300][b]Item do tombamento nao "
                        "encontrado[/b][/color]", size="18sp", height=32))
                    b.add_widget(title_label(
                        "[color=666666]codigo: %s[/color]" % item_code,
                        size="14sp", height=24))
                else:
                    b.add_widget(title_label("[b]%s[/b]" % box["name"],
                                             size="18sp", height=34,
                                             color=ACCENT))
                    b.add_widget(title_label(
                        "[color=666666]%s (%s)[/color]"
                        % (school_name(school_code), school_code),
                        size="14sp", height=26))
                    if self.app.mode == "uso" and box.get("url"):
                        openbtn = FlatButton("Ver guia na Wikiversidade",
                                            bg=ACCENT, height=52,
                                            font_size="14sp")
                        openbtn.bind(on_release=lambda *_:
                                    self.app.open_guide(box["url"]))
                        b.add_widget(openbtn)
                b.add_widget(title_label(
                    "[color=666666][size=12sp]Tombamento: %s[/size][/color]"
                    % numero, height=20))
        else:
            _, box_code, school, uid, registro, ndef, foreign = self._data
            box = box_by_code(box_code)
            if box is None:
                b.add_widget(title_label(
                    "[color=CC3300][b]Item nao reconhecido[/b][/color]",
                    size="18sp", height=32))
                b.add_widget(title_label(
                    "[color=666666]codigo gravado: %s[/color]" % box_code,
                    size="14sp", height=24))
                if self.app.mode == "uso":
                    b.add_widget(title_label(
                        "[color=666666][size=13sp]Para corrigir, mude "
                        "para o modo Preparacao no menu.[/size][/color]",
                        height=40))
            else:
                b.add_widget(title_label("[b]%s[/b]" % box["name"], size="18sp",
                                         height=34, color=ACCENT))
                if school:
                    b.add_widget(title_label(
                        "[color=666666]%s (%s)[/color]"
                        % (school_name(school), school), size="14sp", height=26))
                if self.app.mode == "uso" and box.get("url"):
                    openbtn = FlatButton("Ver guia na Wikiversidade", bg=ACCENT,
                                        height=52, font_size="14sp")
                    openbtn.bind(on_release=lambda *_: self.app.open_guide(box["url"]))
                    b.add_widget(openbtn)
            b.add_widget(title_label(
                "[color=666666][size=12sp]UID: %s[/size][/color]" % uid, height=20))
            if ndef:
                b.add_widget(title_label(
                    "[color=666666][size=12sp]Conteudo: %s[/size][/color]" % ndef,
                    height=20))
            if registro:
                b.add_widget(title_label(
                    "[color=666666][size=12sp]%d leitura(s)[/size][/color]"
                    % registro.get("read_count", 0), height=20))
            # Aviso de "etiqueta de outra escola": e informacao de controle
            # de cadastro, so faz sentido para quem esta preparando/
            # conferindo etiquetas. No modo Uso (leitura pura do guia) isso
            # e ruido irrelevante para professor/estudante.
            if (self.app.mode == "preparacao" and foreign and school
                    and self.app.school and school != self.app.school):
                b.add_widget(title_label(
                    "[color=CC3300](!) Esta etiqueta e da %s, nao da %s[/color]"
                    % (school, self.app.school), size="13sp", height=36))
            b.add_widget(spacer(8))
            # Regravar e uma acao administrativa/de escrita — so faz sentido
            # no modo Preparacao. No modo Uso o app e estritamente de
            # leitura (abrir o guia), sem opcoes de gravacao na tela.
            if self.app.mode == "preparacao":
                regbtn = FlatButton("Regravar esta etiqueta", bg=LIGHT,
                                    fg=(0.3, 0.3, 0.3, 1), height=50, font_size="14sp")
                regbtn.bind(on_release=lambda *_: self.app.go_choose())
                b.add_widget(regbtn)
        b.add_widget(spacer())
        self.root.add_widget(b)


# ============================================================ TELA: senha
class PasswordScreen(Screen):
    """
    Pede a senha de 6 digitos (PREP_PASSWORD) para entrar no modo
    Preparacao. So aparece ao TENTAR ENTRAR em Preparacao — sair de volta
    para Uso nao passa por aqui (ver RedemaisApp.toggle_mode).
    """
    def __init__(self, app, **kw):
        super().__init__(name="senha", **kw)
        self.app = app
        root = BoxLayout(orientation="vertical")

        top = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(12), 0))
        cancel = FlatButton("Cancelar", bg=LIGHT, fg=(0.15, 0.15, 0.15, 1),
                            height=44, font_size="15sp")
        cancel.size_hint_x = None
        cancel.width = dp(110)
        cancel.bind(on_release=lambda *_: self.app.cancel_password())
        top.add_widget(cancel)
        top.add_widget(spacer())
        root.add_widget(top)

        body = BoxLayout(orientation="vertical", spacing=dp(14),
                         padding=(dp(28), dp(10)))
        body.add_widget(spacer())
        body.add_widget(title_label(
            "[b]Modo Preparacao[/b]\n[color=666666][size=14sp]digite a "
            "senha de 6 digitos[/size][/color]", size="19sp", height=70))

        self.input = TextInput(
            password=True, input_filter="int", multiline=False,
            halign="center", font_size="26sp", size_hint_y=None, height=dp(56),
            write_tab=False,
        )
        self.input.bind(text=self._on_text)
        self.input.bind(on_text_validate=lambda *_: self._try_confirm())
        body.add_widget(self.input)

        self.error_label = title_label("", size="13sp",
                                       color=(0.8, 0.2, 0.2, 1), height=0)
        body.add_widget(self.error_label)

        self.confirm_btn = FlatButton("Entrar", bg=ACCENT, height=54,
                                      font_size="16sp")
        self.confirm_btn.bind(on_release=lambda *_: self._try_confirm())
        body.add_widget(self.confirm_btn)
        body.add_widget(spacer())
        root.add_widget(body)
        self.add_widget(root)

    def _on_text(self, instance, value):
        # Trava em 6 digitos, so numeros (input_filter='int' ja bloqueia
        # letras, isto aqui so garante o tamanho maximo).
        if len(value) > 6:
            self.input.text = value[:6]

    def on_pre_enter(self, *_):
        self.input.text = ""
        self._clear_error()

    def _clear_error(self):
        self.error_label.text = ""
        self.error_label.height = 0

    def show_error(self, msg):
        self.error_label.text = "[color=CC3300]%s[/color]" % msg
        self.error_label.height = dp(30)
        self.input.text = ""

    def _try_confirm(self):
        self.app.confirm_password(self.input.text)


# ============================================================ TELA: menu
class MenuScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(name="menu", **kw)
        self.app = app
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self, *_):
        self.build()

    def build(self):
        self.root.clear_widgets()
        top = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(12), 0))
        close = FlatButton("< Voltar", bg=LIGHT, fg=(0.15, 0.15, 0.15, 1),
                           height=44, font_size="15sp")
        close.size_hint_x = None
        close.width = dp(100)
        close.bind(on_release=lambda *_: self.app.go("espera", "right"))
        top.add_widget(close)
        top.add_widget(title_label("[b]Menu[/b]", size="16sp", height=52))
        top.add_widget(spacer())
        self.root.add_widget(top)
        body = BoxLayout(orientation="vertical", padding=(dp(12), dp(4)),
                         spacing=dp(10))
        if self.app.school:
            esc = "%s - %s" % (self.app.school, school_name(self.app.school))
        else:
            esc = "nao definida"
        b1 = FlatButton("Escola:  %s" % esc, bg=LIGHT,
                        fg=(0.15, 0.15, 0.15, 1), height=58, font_size="14sp")
        b1.halign = "left"
        b1.bind(on_release=lambda *_: self.app.go("escola"))
        body.add_widget(b1)
        modo = "Uso" if self.app.mode == "uso" else "Preparacao"
        b2 = FlatButton("Modo:  %s  (trocar)" % modo, bg=LIGHT,
                        fg=(0.15, 0.15, 0.15, 1), height=58, font_size="15sp")
        b2.halign = "left"
        b2.bind(on_release=lambda *_: self.app.toggle_mode())
        body.add_widget(b2)
        body.add_widget(title_label(
            "[color=666666][size=12sp]Uso mostra o botao do guia. "
            "Preparacao so cadastra.[/size][/color]", height=34))
        prog = self.app.db.schools_progress() if self.app.school else {}
        n = prog.get(self.app.school, 0) if self.app.school else 0
        b3 = FlatButton("Progresso dos kits  (%d/%d aqui)" % (n, len(ITEMS)), bg=LIGHT,
                        fg=(0.15, 0.15, 0.15, 1), height=58, font_size="15sp")
        b3.halign = "left"
        b3.bind(on_release=lambda *_: self.app.go("progresso"))
        body.add_widget(b3)
        total = len(self.app.db.all())
        b4 = FlatButton("Etiquetas cadastradas:  %d" % total, bg=LIGHT,
                        fg=(0.15, 0.15, 0.15, 1), height=58, font_size="15sp")
        b4.halign = "left"
        body.add_widget(b4)
        body.add_widget(spacer())
        self.root.add_widget(body)


class SchoolScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(name="escola", **kw)
        self.app = app
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self, *_):
        self.build()

    def build(self):
        self.root.clear_widgets()
        top = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(12), 0))
        back = FlatButton("< Voltar", bg=LIGHT, fg=(0.15, 0.15, 0.15, 1),
                          height=44, font_size="15sp")
        back.size_hint_x = None
        back.width = dp(110)
        back.bind(on_release=lambda *_: self.app.after_school_cancel())
        top.add_widget(back)
        top.add_widget(title_label("[b]Escola do kit[/b]", size="16sp",
                                   height=52))
        top.add_widget(spacer())
        self.root.add_widget(top)
        scroll = ScrollView()
        lst = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=(dp(12), dp(6)), spacing=dp(8))
        lst.bind(minimum_height=lst.setter("height"))
        for sch in SCHOOLS:
            sel = (sch == self.app.school)
            label = "%s - %s" % (sch, school_name(sch))
            btn = FlatButton(label, bg=(ACCENT if sel else LIGHT),
                             fg=((1, 1, 1, 1) if sel else (0.2, 0.2, 0.2, 1)),
                             height=56, font_size="15sp")
            btn.halign = "left"
            btn.bind(on_release=lambda inst, s=sch: self.app.choose_school(s))
            lst.add_widget(btn)
        scroll.add_widget(lst)
        self.root.add_widget(scroll)


class ProgressScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(name="progresso", **kw)
        self.app = app
        self.root = BoxLayout(orientation="vertical")
        self.add_widget(self.root)

    def on_pre_enter(self, *_):
        self.build()

    def build(self):
        self.root.clear_widgets()
        top = BoxLayout(size_hint_y=None, height=dp(52), padding=(dp(12), 0))
        back = FlatButton("< Voltar", bg=LIGHT, fg=(0.15, 0.15, 0.15, 1),
                          height=44, font_size="15sp")
        back.size_hint_x = None
        back.width = dp(110)
        back.bind(on_release=lambda *_: self.app.go("menu", "right"))
        top.add_widget(back)
        top.add_widget(title_label("[b]Progresso[/b]", size="16sp", height=52))
        top.add_widget(spacer())
        self.root.add_widget(top)

        scroll = ScrollView()
        lst = BoxLayout(orientation="vertical", size_hint_y=None,
                        padding=(dp(12), dp(4)), spacing=dp(4))
        lst.bind(minimum_height=lst.setter("height"))
        item_codes = list(ITEMS.keys())
        per_school = len(item_codes) or 1
        total = 0
        for sch in SCHOOLS:
            done = self.app.db.boxes_for_school(sch)
            n = len(done)
            total += n
            marks = "".join("#" if c in done else "o" for c in item_codes)
            cor = "2E7D32" if n == per_school else (
                  "1F3864" if sch == self.app.school else "555555")
            atual = "  <<" if sch == self.app.school else ""
            row = title_label(
                "[color=%s][b]%s[/b]  %s  %d/%d%s[/color]"
                % (cor, sch, marks, n, per_school, atual), size="15sp", height=32)
            row.halign = "left"
            lst.add_widget(row)
        lst.add_widget(title_label(
            "[color=666666]Total: %d / %d etiquetas[/color]"
            % (total, len(SCHOOLS) * per_school), size="14sp", height=34))
        scroll.add_widget(lst)
        self.root.add_widget(scroll)

        self.status = title_label("", size="13sp", color=(0.3, 0.3, 0.3, 1),
                                  height=30)
        self.root.add_widget(self.status)

        nextbtn = FlatButton("Ir para proxima escola incompleta", bg=ACCENT,
                             height=56, font_size="15sp")
        nextbtn.bind(on_release=lambda *_: self.app.next_incomplete_school())
        self.root.add_widget(nextbtn)

    def set_status(self, text):
        if hasattr(self, "status"):
            self.status.text = text


# ============================================================ APP
class LabTagApp(App):
    title = "LabTag"

    def build(self):
        # Fundo branco GLOBAL. Sem isto, qualquer tela que nao pinte seu
        # proprio fundo (a maioria) cai no preto padrao do Kivy — e os
        # textos escuros/cinza pensados para fundo claro ficam ilegiveis
        # ou invisiveis sobre ele. As telas de splash ja pintam seu proprio
        # fundo branco explicitamente (redundante com isto, mas inofensivo).
        Window.clearcolor = (1, 1, 1, 1)

        self.db = TagDatabase()
        self.nfc = get_nfc()
        self.scanner = qr_scanner.get_scanner()
        self.school = self.db.get_setting("school")
        if self.school and not valid_school(self.school):
            _log("aviso: escola salva '%s' nao existe mais - limpando" % self.school)
            self.school = None
            self.db.set_setting("school", "")
        # O modo SEMPRE comeca como "uso" ao abrir o app — Preparacao nunca
        # e restaurado automaticamente entre sessoes, mesmo que tenha sido
        # o ultimo modo usado. Isso garante que a senha seja pedida toda
        # vez que alguem quiser entrar em Preparacao, inclusive apos reabrir
        # o app (sem isso, bastaria fechar e abrir o app para "herdar" o
        # modo Preparacao sem digitar a senha).
        self.mode = "uso"
        self._mode_return_screen = "espera"

        # Estado de gravacao: None = nao armado. Quando definido, e um dict
        # do item (ITEMS[...]) escolhido na tela "escolher"; o PROXIMO toque
        # grava esse item imediatamente.
        self.write_target = None
        self._after_school = None  # 'escolher' se a escolha de escola veio
                                    # de um fluxo de cadastro/regravacao
        self.last_uid = None
        self.last_text = None
        self._last_seen_uid = None
        self._last_seen_time = 0.0

        self.sm = ScreenManager(transition=SlideTransition(duration=0.18))
        self.screens = {
            "splash": ProjectSplashScreen(self),
            "splash_app": AppSplashScreen(self),
            "espera": WaitScreen(self),
            "escolher": ChooseScreen(self),
            "info": InfoScreen(self),
            "senha": PasswordScreen(self),
            "menu": MenuScreen(self),
            "escola": SchoolScreen(self),
            "progresso": ProgressScreen(self),
        }
        for s in self.screens.values():
            self.sm.add_widget(s)
        self.sm.current = "splash"
        if is_mock(self.nfc):
            return self._wrap_with_sim(self.sm)
        return self.sm

    def go(self, name, direction="left"):
        _log("go(%s)" % name)
        self.sm.transition.direction = direction
        self.sm.current = name

    # ---------------------------------------------------------- ciclo de vida
    def on_start(self):
        try:
            self.nfc.start(self.on_tag)
            _log("NFC start OK")
        except Exception as exc:
            _log("NFC start FALHOU: %s" % exc)
            self.screens["espera"].instr.text = "NFC indisponivel:\n%s" % exc
        try:
            self.scanner.start(self.on_qr_result)
            _log("scanner QR start OK")
        except Exception as exc:
            _log("scanner QR start FALHOU: %s" % exc)

    def on_resume(self):
        try:
            self.nfc.resume()
        except Exception as exc:
            _log("NFC resume falhou: %s" % exc)

    def on_pause(self):
        try:
            self.nfc.pause()
        except Exception:
            pass
        return True

    def on_stop(self):
        try:
            self.nfc.stop()
        except Exception:
            pass
        try:
            self.scanner.stop()
        except Exception:
            pass
        self.db.close()

    # ---------------------------------------------------------- QR / tombamento
    def scan_tombamento(self):
        """Chamado pelo botao 'Ler QR de tombamento'. Dispara o Intent do
        scanner externo; o resultado chega depois, de forma assincrona,
        em on_qr_result."""
        _log("scan_tombamento: disparando scan")
        try:
            self.scanner.scan()
        except Exception as exc:
            _log("scan_tombamento: falhou: %s" % exc)

    @mainthread
    def on_qr_result(self, value):
        _log("on_qr_result: valor=%r" % value)
        if not value:
            # Cancelado pelo usuario, ou nenhum app scanner respondeu ao
            # Intent — nao ha nada de util a mostrar; so volta a espera.
            return
        numero = value.strip()
        resolved = resource_by_tombamento(numero)
        self.screens["info"].show_qr(numero, resolved)
        self.go("info")

    # ---------------------------------------------------------- leitura
    @mainthread
    def on_tag(self, payload):
        uid = payload.get("uid")
        text = payload.get("text")
        raw = payload.get("raw_tag")

        # Debounce: um unico toque fisico pode gerar mais de uma entrega do
        # mesmo Intent em alguns aparelhos/etiquetas. Ignora repeticoes do
        # mesmo UID dentro de uma janela curta.
        now = time.time()
        if (uid == self._last_seen_uid
                and (now - self._last_seen_time) < DEBOUNCE_SECONDS
                and self.write_target is None):
            _log("debounce: ignorando releitura de %s" % uid)
            return
        self._last_seen_uid = uid
        self._last_seen_time = now

        self.last_uid = uid
        self.last_text = text
        _log("on_tag uid=%s text=%r write_target=%s tela=%s"
             % (uid, text, self.write_target and self.write_target.get("code"),
                self.sm.current))

        # ---- MODO ARMADO: grava imediatamente, em qualquer tela.
        if self.write_target is not None:
            self._do_write_now(uid, raw, self.write_target)
            return

        # ---- MODO LEITURA NORMAL: so processa se estivermos "escutando"
        # (tela de espera). Em qualquer outra tela (escolhendo item, no
        # menu, etc.) um toque acidental e ignorado, para nao reabrir o
        # fluxo no meio de uma operacao.
        if self.sm.current != "espera":
            _log("tag ignorada: app nao esta escutando (tela=%s)"
                 % self.sm.current)
            return

        decoded = decode_payload(text)
        known = self.db.get(uid)

        if decoded:
            box_code, school = decoded
            self.db.mark_read(uid)
            self.screens["info"].show(box_code, school, uid,
                                      self.db.get(uid), text, foreign=True)
            self.go("info")
            return
        if known:
            self.db.mark_read(uid)
            self.screens["info"].show(known["box_code"],
                                      known.get("school_code"), uid,
                                      self.db.get(uid), text, foreign=False)
            self.go("info")
            return
        self.screens["info"].show_blank(uid, text)
        self.go("info")

    # ---------------------------------------------------------- gravacao
    def _do_write_now(self, uid, raw, target):
        """Executa a gravacao IMEDIATAMENTE, no mesmo evento de deteccao."""
        payload_text = encode_payload(target["code"], self.school)
        _log("_do_write_now: uid=%s payload=%s" % (uid, payload_text))
        try:
            self.nfc.write_text(raw, payload_text)
        except Exception as exc:
            _log("_do_write_now: FALHOU: %s" % exc)
            # Mantem armado (mesmo alvo) para o usuario so tocar de novo,
            # sem precisar refazer a escolha do item.
            self.screens["espera"].show_error(
                "Falha ao gravar: %s\nMantenha a etiqueta parada e "
                "toque de novo." % exc)
            return
        self.db.register(uid, target["code"], self.school)
        _log("_do_write_now: OK")
        self.write_target = None
        # Mostra a confirmacao reaproveitando a tela de info.
        self.screens["info"].show(target["code"], self.school, uid,
                                  self.db.get(uid), payload_text, foreign=False)
        self.go("info")

    def go_choose(self):
        """Leva a tela de escolha de item (pura UI). Pede escola se faltar."""
        if not self.school:
            self._after_school = "escolher"
            self.go("escola")
            return
        self.go("escolher")

    def arm_write(self, item):
        """Chamado pela ChooseScreen ao selecionar um item. Nao toca em
        nenhuma etiqueta agora — so guarda o alvo e espera o proximo toque."""
        _log("arm_write: item=%s" % item.get("code"))
        self.write_target = item
        self.go("espera", direction="right")

    def cancel_write(self):
        _log("cancel_write")
        self.write_target = None
        self.screens["espera"].refresh()

    def choose_school(self, sch):
        if not valid_school(sch):
            _log("choose_school: codigo invalido %s" % sch)
            return
        self.school = sch
        self.db.set_setting("school", sch)
        dest = self._after_school
        self._after_school = None
        if dest == "escolher":
            self.go("escolher")
        else:
            self.go("menu", direction="right")

    def after_school_cancel(self):
        dest = self._after_school
        self._after_school = None
        if dest == "escolher":
            self.go("espera", "right")
        else:
            self.go("menu", direction="right")

    def toggle_mode(self):
        if self.mode == "preparacao":
            # Sair de Preparacao de volta para Uso NAO exige senha.
            _log("saindo do modo preparacao (sem senha)")
            self.mode = "uso"
            self._refresh_mode_dependent_screen()
            return
        # Entrar em Preparacao EXIGE a senha de 6 digitos.
        _log("solicitando senha para entrar em preparacao")
        self._mode_return_screen = self.sm.current
        self.go("senha")

    def confirm_password(self, digits):
        if digits == PREP_PASSWORD:
            _log("senha correta: modo preparacao ativado")
            self.mode = "preparacao"
            dest = self._mode_return_screen or "espera"
            self.go(dest, "right")
        else:
            _log("senha incorreta")
            self.screens["senha"].show_error("Senha incorreta. Tente de novo.")

    def cancel_password(self):
        _log("entrada em preparacao cancelada")
        dest = self._mode_return_screen or "espera"
        self.go(dest, "right")

    def _refresh_mode_dependent_screen(self):
        # WaitScreen e MenuScreen ja se atualizam sozinhas via on_pre_enter;
        # isto so cobre o caso de mudar o modo SEM navegar para outra tela
        # (ex.: alternar de Preparacao->Uso enquanto ja se esta na espera).
        cur = self.sm.current
        if cur == "espera":
            self.screens["espera"].refresh()
        elif cur == "menu":
            self.screens["menu"].build()

    def next_incomplete_school(self):
        prog = self.db.schools_progress()
        alvo = None
        for sch in SCHOOLS:
            if prog.get(sch, 0) < len(ITEMS):
                alvo = sch
                break
        prog_screen = self.screens["progresso"]
        if alvo is None:
            prog_screen.set_status("Todas as escolas estao completas!")
            return
        if alvo == self.school:
            faltam = len(ITEMS) - prog.get(alvo, 0)
            prog_screen.set_status(
                "Escola atual %s ainda incompleta (falta %d)." % (alvo, faltam))
            return
        self.school = alvo
        self.db.set_setting("school", alvo)
        prog_screen.build()
        prog_screen.set_status("Agora na escola %s." % alvo)

    def open_guide(self, url):
        _log("open_guide: %s" % url)
        try:
            from jnius import autoclass, cast
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_VIEW)
            intent.setData(Uri.parse(url))
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            cast("android.app.Activity",
                 PythonActivity.mActivity).startActivity(intent)
        except Exception as exc:
            _log("open_guide via Android falhou (%s); usando webbrowser" % exc)
            webbrowser.open(url)

    # ---------------------------------------------------------- simulacao
    def _wrap_with_sim(self, sm):
        wrap = BoxLayout(orientation="vertical")
        wrap.add_widget(sm)
        bar = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6),
                        padding=(dp(6), dp(4)))
        self._mock_n = 0
        b1 = FlatButton("Nova tag", bg=LIGHT, fg=(0.2, 0.2, 0.2, 1), height=38,
                        font_size="13sp")
        b1.bind(on_release=lambda *_: self._sim_blank())
        b2 = FlatButton("Reler ultima", bg=LIGHT, fg=(0.2, 0.2, 0.2, 1),
                        height=38, font_size="13sp")
        b2.bind(on_release=lambda *_: self._sim_last())
        bar.add_widget(b1)
        bar.add_widget(b2)
        wrap.add_widget(bar)

        bar2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6),
                         padding=(dp(6), dp(4)))
        b3 = FlatButton("QR cadastrado", bg=LIGHT, fg=(0.2, 0.2, 0.2, 1),
                        height=38, font_size="12sp")
        b3.bind(on_release=lambda *_: self._sim_qr_known())
        b4 = FlatButton("QR desconhecido", bg=LIGHT, fg=(0.2, 0.2, 0.2, 1),
                        height=38, font_size="12sp")
        b4.bind(on_release=lambda *_: self._sim_qr_unknown())
        bar2.add_widget(b3)
        bar2.add_widget(b4)
        wrap.add_widget(bar2)
        return wrap

    def _sim_blank(self):
        self._mock_n += 1
        self._last_mock = "MOCK-%03d" % self._mock_n
        self.nfc.simulate_tag(self._last_mock, blank=True)

    def _sim_last(self):
        uid = getattr(self, "_last_mock", None)
        if uid:
            self.nfc.simulate_tag(uid, blank=False)

    def _sim_qr_known(self):
        # usa o primeiro numero de tombamento realmente cadastrado em
        # dados.json, se houver algum — assim o teste reflete dados reais.
        from boxes import TOMBAMENTOS
        numero = next(iter(TOMBAMENTOS.keys()), "123456")
        self.scanner.simulate_scan(numero)

    def _sim_qr_unknown(self):
        self.scanner.simulate_scan("000000-nao-cadastrado")


if __name__ == "__main__":
    LabTagApp().run()
