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
que already nos custou muito tempo com o NFC (p4a fixado, Gradle antigo,
JDK sensivel). O LabTag so dispara o Intent e recebe de volta o texto
decodificado via onActivityResult; nunca abre a camera ele mesmo, e por
isso nao precisa da permissao CAMERA no proprio manifesto.

Uso:
    scanner = get_scanner()
    scanner.start(on_result)   # registra o callback (uma vez, no on_start do app)
    scanner.scan()             # dispara o Intent (chamado ao tocar o botao)
    scanner.stop()             # desregistra (no on_stop do app)

`on_result` recebe um unico argumento: o texto decodificado (string) ou
None se o usuario cancelou o scan ou algo deu errado.
"""


def _log(msg):
    print("[LABTAG][qr] %s" % msg)


# Codigo de requisicao usado para distinguir o resultado deste Intent de
# outros que a Activity possa receber (valor arbitrario, so precisa ser
# unico dentro do app — nao ha mais nenhum outro startActivityForResult
# no LabTag hoje).
REQUEST_CODE_SCAN = 0x5CA1

RESULT_OK = -1  # android.app.Activity.RESULT_OK (constante fixa da API Android)


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
        """Dispara o Intent de scan. O resultado chega de forma assincrona
        no callback registrado via start()."""
        try:
            intent = self.Intent("com.google.zxing.client.android.SCAN")
            intent.putExtra("SCAN_MODE", "QR_CODE_MODE")
            self.activity.startActivityForResult(intent, REQUEST_CODE_SCAN)
            _log("scan(): Intent disparado")
        except Exception as exc:
            _log("scan(): FALHOU ao disparar Intent: %s" % exc)
            # Provavel causa: nenhum app instalado responde a este Intent.
            # Repassamos None com uma pista no log; a UI decide a mensagem.
            if self._on_result:
                self._on_result(None)

    def _on_activity_result(self, request_code, result_code, intent):
        if request_code != REQUEST_CODE_SCAN:
            return  # nao e o nosso Intent — ignora
        _log("_on_activity_result: result_code=%s" % result_code)
        try:
            if result_code != RESULT_OK or intent is None:
                _log("_on_activity_result: cancelado ou sem resultado")
                if self._on_result:
                    self._on_result(None)
                return
            contents = intent.getStringExtra("SCAN_RESULT")
            _log("_on_activity_result: conteudo lido=%r" % contents)
            if self._on_result:
                self._on_result(contents)
        except Exception as exc:
            _log("_on_activity_result: erro ao processar: %s" % exc)
            if self._on_result:
                self._on_result(None)


# --------------------------------------------------------------- backend mock
class MockScanner:
    """
    Backend de testes para desktop. Nao ha camera nem Intent — a UI de
    simulacao chama simulate_scan(valor) diretamente para imitar o
    resultado de uma leitura.
    """
    def __init__(self):
        self._on_result = None

    def start(self, on_result):
        self._on_result = on_result

    def stop(self):
        self._on_result = None

    def scan(self):
        _log("scan() chamado em modo mock — use simulate_scan(valor) "
             "na barra de simulacao para imitar uma leitura")

    def simulate_scan(self, value):
        if self._on_result:
            self._on_result(value)


# ------------------------------------------------------------------ fabrica
def get_scanner():
    if _on_android():
        return AndroidScanner()
    return MockScanner()


def is_mock(scanner):
    return isinstance(scanner, MockScanner)
