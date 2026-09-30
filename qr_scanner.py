"""
Leitura de QR code para o modo simples de identificacao por numero de
tombamento — alternativa ao NFC para equipamentos que ja tem uma etiqueta
de QR colada pelo patrimonio da escola.

DECISAO DE ENGENHARIA: em vez de embutir uma camera + decodificador de QR
dentro do proprio app (o que exigiria uma dependencia nativa nova no
empacotamento Android — camera, ML Kit ou zbar), o LabTag delega a leitura
para um app scanner EXTERNO ja instalado no aparelho, via o Intent padrao
do ZXing ("com.google.zxing.client.android.SCAN"), amplamente suportado
(inclusive por scanners embutidos em cameras/launchers de varios fabricantes
e pelo app gratuito "Barcode Scanner" caso nenhum esteja disponivel).

Isso evita qualquer risco novo de empacotamento — o mesmo tipo de problema
que ja nos custou muito tempo com o NFC (p4a fixado, Gradle antigo, JDK
sensivel). O LabTag so dispara o Intent e recebe de volta o texto
decodificado via onActivityResult; nunca abre a camera ele mesmo, e por
isso nao precisa da permissao CAMERA no proprio manifesto.

RISCO CONHECIDO deste caminho: se NENHUM app scanner compativel estiver
instalado no aparelho, o Android lanca uma ActivityNotFoundException ao
tentar abrir o Intent — e, do ponto de vista de quem usa o app, isso parece
"o botao nao fez nada" se o erro so for parado no log. Por isso este modulo
SEMPRE repassa um motivo (`error`) distinguivel de um cancelamento normal do
usuario, para a tela poder mostrar uma mensagem clara em vez de ficar muda.

Uso:
    scanner = get_scanner()
    scanner.start(on_result)   # registra o callback (uma vez, no on_start do app)
    scanner.scan()             # dispara o Intent (chamado ao tocar o botao)
    scanner.stop()             # desregistra (no on_stop do app)

`on_result(value, error=None)`:
    - leitura com sucesso:          value = texto decodificado, error = None
    - usuario cancelou o scan:      value = None,               error = None
    - nenhum app scanner instalado
      (ou outra falha ao abrir):    value = None,               error = "<mensagem>"
"""


def _log(msg):
    print("[LABTAG][qr] %s" % msg)


# Codigo de requisicao usado para distinguir o resultado deste Intent de
# outros que a Activity possa receber (valor arbitrario, so precisa ser
# unico dentro do app — nao ha mais nenhum outro startActivityForResult
# no LabTag hoje).
REQUEST_CODE_SCAN = 0x5CA1

RESULT_OK = -1       # android.app.Activity.RESULT_OK
RESULT_CANCELED = 0  # android.app.Activity.RESULT_CANCELED — cancelamento normal

MSG_APP_AUSENTE = (
    "Nenhum app leitor de QR foi encontrado neste aparelho. Instale um "
    "app de leitura de QR/codigo de barras (ex.: \"Leitor de QR Code\" ou "
    "\"Barcode Scanner\") e tente de novo."
)


def _on_android():
    try:
        from jnius import autoclass
        autoclass("org.kivy.android.PythonActivity")
        return True
    except Exception as exc:
        _log("_on_android: nao esta no Android (%s)" % exc)
        return False


# --------------------------------------------------------------- backend real
class AndroidScanner:
    def __init__(self):
        from jnius import autoclass
        self.autoclass = autoclass
        self.PythonActivity = autoclass("org.kivy.android.PythonActivity")
        self.Intent = autoclass("android.content.Intent")
        self.activity = self.PythonActivity.mActivity
        self._on_result = None
        self._activity_module = self._load_activity_module()
        _log("activity_module carregado: %s" % (self._activity_module is not None))

    def _load_activity_module(self):
        try:
            from android import activity as activity_module
            return activity_module
        except Exception as exc:
            _log("import 'from android import activity' falhou: %s" % exc)
        try:
            import android.activity as activity_module
            return activity_module
        except Exception as exc:
            _log("import 'import android.activity' falhou: %s" % exc)
        return None

    def start(self, on_result):
        self._on_result = on_result
        if self._activity_module is not None:
            self._activity_module.bind(on_activity_result=self._on_activity_result)
            _log("start(): bind de on_activity_result OK")
        else:
            _log("start(): modulo android.activity indisponivel — "
                 "resultados de scan NAO serao recebidos")

    def stop(self):
        if self._activity_module is not None:
            try:
                self._activity_module.unbind(on_activity_result=self._on_activity_result)
            except Exception as exc:
                _log("stop(): erro ao desvincular: %s" % exc)

    def scan(self):
        if self._activity_module is None:
            msg = (
                "Nao foi possivel preparar a leitura de QR neste "
                "aparelho (modulo android.activity indisponivel)."
            )
            _log("scan(): abortado — %s" % msg)
            if self._on_result:
                self._on_result(None, error=msg)
            return

        try:
            intent = self.Intent("com.google.zxing.client.android.SCAN")
            intent.putExtra("SCAN_MODE", "QR_CODE_MODE")

            package_manager = self.activity.getPackageManager()

            #if intent.resolveActivity(package_manager) is None:
            #    _log("scan(): nenhum aplicativo responde ao Intent ZXing")
            #    if self._on_result:
            #        self._on_result(None, error=MSG_APP_AUSENTE)
            #    return

            self.activity.startActivityForResult(
                intent,
                REQUEST_CODE_SCAN
            )

            _log("scan(): Intent disparado")

        except Exception as exc:
            _log("scan(): FALHOU ao disparar Intent: %s" % exc)

            if self._on_result:
                self._on_result(
                    None,
                    error="Nao foi possivel iniciar o leitor de QR: %s" % exc
                )

    def _on_activity_result(self, request_code, result_code, intent):
        if request_code != REQUEST_CODE_SCAN:
            return  # nao e o nosso Intent — ignora
        _log("_on_activity_result: result_code=%s" % result_code)
        try:
            if result_code == RESULT_CANCELED:
                # Usuario apertou "voltar" ou fechou o scanner de proposito —
                # comportamento normal, sem erro a mostrar.
                _log("_on_activity_result: cancelado pelo usuario")
                if self._on_result:
                    self._on_result(None)
                return
            if result_code != RESULT_OK or intent is None:
                # Algum resultado inesperado que nao e nem sucesso nem
                # cancelamento normal — trata como erro, para nao ficar
                # silencioso sem explicacao.
                msg = "A leitura nao retornou um resultado valido (codigo %s)." % result_code
                _log("_on_activity_result: %s" % msg)
                if self._on_result:
                    self._on_result(None, error=msg)
                return
            contents = intent.getStringExtra("SCAN_RESULT")
            _log("_on_activity_result: conteudo lido=%r" % contents)
            if not contents:
                msg = "A leitura nao retornou nenhum conteudo."
                if self._on_result:
                    self._on_result(None, error=msg)
                return
            if self._on_result:
                self._on_result(contents)
        except Exception as exc:
            msg = "Erro ao processar o resultado da leitura: %s" % exc
            _log("_on_activity_result: %s" % msg)
            if self._on_result:
                self._on_result(None, error=msg)


# --------------------------------------------------------------- backend mock
class MockScanner:
    """
    Backend de testes para desktop. Nao ha camera nem Intent — a UI de
    simulacao chama simulate_scan(valor) diretamente para imitar o
    resultado de uma leitura (ou simulate_error() para imitar a falta de
    app scanner instalado).
    """
    def __init__(self):
        self._on_result = None

    def start(self, on_result):
        self._on_result = on_result

    def stop(self):
        self._on_result = None

    def scan(self):
        _log("scan() chamado em modo mock — use simulate_scan(valor) ou "
             "simulate_error() na barra de simulacao para imitar um "
             "resultado")

    def simulate_scan(self, value):
        if self._on_result:
            self._on_result(value)

    def simulate_error(self, msg=None):
        if self._on_result:
            self._on_result(None, error=msg or MSG_APP_AUSENTE)


# ------------------------------------------------------------------ fabrica
def get_scanner():
    if _on_android():
        return AndroidScanner()
    return MockScanner()


def is_mock(scanner):
    return isinstance(scanner, MockScanner)