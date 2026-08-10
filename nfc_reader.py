"""
Camada de acesso ao NFC.

O Kivy nao tem suporte nativo a NFC, entao no Android acessamos a API
`android.nfc` diretamente via pyjnius. Este modulo expoe uma interface simples:

    nfc = get_nfc()                 # devolve backend Android ou Mock (desktop)
    nfc.start(on_tag)              # comeca a escutar; chama on_tag(payload) a cada tag
    nfc.stop()
    nfc.write_text(tag, texto)     # grava um registro NDEF de texto na tag

`on_tag` recebe um dicionario:
    {
        "uid": "<hex do id fisico da tag>",
        "text": "<conteudo NDEF de texto, ou None se vazia>",
        "raw_tag": <objeto Tag do Android, ou tupla no mock>,
    }

No Android, a leitura usa o "foreground dispatch": enquanto o app esta aberto,
qualquer tag aproximada gera um Intent que capturamos e convertemos em payload.
A gravacao usa Ndef.writeNdefMessage().

Todas as mensagens de depuracao vao para o logcat com o prefixo [NFC].
Para ver: buildozer android deploy run logcat | grep -i NFC

Referencias de API: android.nfc.NfcAdapter, android.nfc.Ndef,
android.nfc.NdefMessage, android.nfc.NdefRecord.
"""


def _log(msg):
    print("[NFC] %s" % msg)


# ------------------------------------------------------------------ deteccao
def _on_android():
    try:
        import jnius  # noqa: F401
        from jnius import autoclass
        autoclass("org.kivy.android.PythonActivity")
        return True
    except Exception as exc:
        _log("_on_android: nao esta no Android (%s)" % exc)
        return False


def _bytes_to_hex(byte_array):
    # byte_array e um jbytearray (bytes assinados). Convertemos para hex.
    if byte_array is None:
        return "?"
    out = []
    for b in byte_array:
        try:
            out.append("%02X" % (int(b) & 0xFF))
        except Exception:
            continue
    return ":".join(out) if out else "?"


# --------------------------------------------------------------- backend real
class AndroidNFC:
    def __init__(self):
        from jnius import autoclass
        self.autoclass = autoclass
        self.PythonActivity = autoclass("org.kivy.android.PythonActivity")
        self.NfcAdapter = autoclass("android.nfc.NfcAdapter")
        self.Intent = autoclass("android.content.Intent")
        self.PendingIntent = autoclass("android.app.PendingIntent")
        self.IntentFilter = autoclass("android.content.IntentFilter")
        self.Ndef = autoclass("android.nfc.tech.Ndef")
        self.NdefMessage = autoclass("android.nfc.NdefMessage")
        self.NdefRecord = autoclass("android.nfc.NdefRecord")
        self.Tag = autoclass("android.nfc.Tag")

        self.activity = self.PythonActivity.mActivity
        self.adapter = self.NfcAdapter.getDefaultAdapter(self.activity)
        _log("adapter=%r (None = sem NFC ou desligado)" % self.adapter)
        self._on_tag = None
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

    # -- ciclo de vida -----------------------------------------------------
    def start(self, on_tag):
        if self.adapter is None:
            raise RuntimeError("Este aparelho nao possui NFC ou esta desligado.")
        if self._activity_module is None:
            raise RuntimeError(
                "nao foi possivel acessar o modulo de eventos da Activity "
                "(android.activity). Verifique a versao do python-for-android.")
        self._on_tag = on_tag
        self._activity_module.bind(on_new_intent=self._on_new_intent)
        self._enable_dispatch()
        _log("start(): dispatch habilitado, bind feito")
        # Processa tambem a tag que pode ter aberto o app (intent inicial).
        try:
            initial = self.activity.getIntent()
            _log("start(): verificando intent inicial: action=%s"
                 % (initial.getAction() if initial else None))
            self._on_new_intent(initial)
        except Exception as exc:
            _log("start(): erro ao processar intent inicial: %s" % exc)

    def stop(self):
        try:
            self._disable_dispatch()
            if self._activity_module is not None:
                self._activity_module.unbind(on_new_intent=self._on_new_intent)
            _log("stop(): dispatch desabilitado, unbind feito")
        except Exception as exc:
            _log("stop(): erro %s" % exc)

    def resume(self):
        self._enable_dispatch()
        _log("resume(): dispatch reabilitado")

    def pause(self):
        self._disable_dispatch()
        _log("pause(): dispatch desabilitado")

    def ensure_active(self):
        """
        Reforca o registro do foreground dispatch. Chamado defensivamente ao
        entrar na tela de espera e apos processar qualquer evento de NFC —
        o dispatch e uma API de runtime que pode 'cair' silenciosamente em
        certas condicoes (troca de tela, oscilacao de foco); reafirma-lo com
        frequencia reduz a janela em que o Android entregaria uma etiqueta
        para o leitor de NFC do sistema em vez do nosso app.
        """
        self._enable_dispatch()

    # -- foreground dispatch ----------------------------------------------
    def _enable_dispatch(self):
        try:
            intent = self.Intent(self.activity, self.activity.getClass())
            intent.addFlags(self.Intent.FLAG_ACTIVITY_SINGLE_TOP)
            # PendingIntent.FLAG_MUTABLE = 0x02000000 (Android 12+)
            flag_mutable = 0x02000000
            pending = self.PendingIntent.getActivity(
                self.activity, 0, intent, flag_mutable
            )
            self.adapter.enableForegroundDispatch(
                self.activity, pending, None, None
            )
            _log("_enable_dispatch: OK")
        except Exception as exc:
            _log("_enable_dispatch: FALHOU: %s" % exc)

    def _disable_dispatch(self):
        if self.adapter is not None:
            try:
                self.adapter.disableForegroundDispatch(self.activity)
            except Exception as exc:
                _log("_disable_dispatch: erro %s" % exc)

    # -- recepcao da tag ---------------------------------------------------
    def _on_new_intent(self, intent):
        try:
            if intent is None:
                _log("_on_new_intent: intent e None, ignorando")
                return
            action = intent.getAction()
            _log("_on_new_intent: action=%s" % action)
            if action is None or "nfc" not in action.lower():
                _log("_on_new_intent: acao nao e de NFC, ignorando")
                return
            from jnius import cast
            raw_extra = intent.getParcelableExtra(self.NfcAdapter.EXTRA_TAG)
            if raw_extra is None:
                _log("_on_new_intent: EXTRA_TAG veio None")
                return
            # Cast explicito: sem isso o pyjnius pode nao expor os metodos
            # de Tag (getId, etc.) no objeto Parcelable generico.
            tag = cast("android.nfc.Tag", raw_extra)
            _log("_on_new_intent: tag obtida, lendo...")
            payload = self._read_tag(tag)
            _log("_on_new_intent: payload uid=%s text=%r"
                 % (payload.get("uid"), payload.get("text")))
            if self._on_tag:
                self._on_tag(payload)
            else:
                _log("_on_new_intent: nenhum callback registrado (_on_tag None)")
        except Exception as exc:
            _log("_on_new_intent: ERRO: %s" % exc)
        finally:
            # Reforca o dispatch apos processar qualquer evento (sucesso ou
            # nao) — defesa extra contra o registro 'cair' silenciosamente.
            self.ensure_active()

    def _read_tag(self, tag):
        # UID: protegido, pois getId()/conversao podem variar por aparelho.
        uid = "?"
        try:
            raw_id = tag.getId()
            uid = _bytes_to_hex(raw_id)
        except Exception as exc:
            _log("_read_tag: erro ao ler UID: %s" % exc)
            try:
                uid = str(tag.toString())
            except Exception:
                uid = "desconhecido"
        text = None
        try:
            ndef = self.Ndef.get(tag)
            if ndef is None:
                _log("_read_tag: Ndef.get(tag) retornou None "
                     "(tag pode nao suportar NDEF)")
            else:
                ndef.connect()
                msg = ndef.getCachedNdefMessage()
                if msg is None:
                    msg = ndef.getNdefMessage()
                if msg is None:
                    _log("_read_tag: nenhuma NdefMessage (etiqueta em branco)")
                else:
                    text = self._extract_text(msg)
                    _log("_read_tag: texto extraido: %r" % text)
                ndef.close()
        except Exception as exc:
            _log("_read_tag: erro NDEF: %s" % exc)
        return {"uid": uid, "text": text, "raw_tag": tag}

    def _extract_text(self, ndef_message):
        records = ndef_message.getRecords()
        for rec in records:
            try:
                payload = rec.getPayload()
                data = bytes([b & 0xFF for b in payload])
                if not data:
                    continue
                status = data[0]
                lang_len = status & 0x3F
                text = data[1 + lang_len:].decode("utf-8", errors="replace")
                return text
            except Exception as exc:
                _log("_extract_text: erro num registro: %s" % exc)
                continue
        return None

    # -- gravacao ----------------------------------------------------------
    def write_text(self, tag, text):
        """Grava um unico registro NDEF de texto (idioma 'pt') na tag."""
        _log("write_text: gravando %r" % text)
        record = self._make_text_record(text, lang="pt")
        message = self.NdefMessage([record])
        ndef = self.Ndef.get(tag)
        if ndef is None:
            raise RuntimeError("Etiqueta nao e compativel com NDEF (nao gravavel).")
        ndef.connect()
        try:
            if not ndef.isWritable():
                raise RuntimeError("Etiqueta esta protegida contra gravacao.")
            max_size = ndef.getMaxSize()
            if message.getByteArrayLength() > max_size:
                raise RuntimeError("Conteudo maior que a capacidade da etiqueta.")
            ndef.writeNdefMessage(message)
            _log("write_text: OK")
        except Exception as exc:
            _log("write_text: FALHOU: %s" % exc)
            raise
        finally:
            ndef.close()

    def _make_text_record(self, text, lang="pt"):
        lang_bytes = lang.encode("ascii")
        text_bytes = text.encode("utf-8")
        status = len(lang_bytes)  # bit 7 = 0 => UTF-8
        payload = bytes([status]) + lang_bytes + text_bytes
        empty = bytes()
        return self.NdefRecord(
            self.NdefRecord.TNF_WELL_KNOWN,
            self.NdefRecord.RTD_TEXT,
            empty,
            payload,
        )


# --------------------------------------------------------------- backend mock
class MockNFC:
    """
    Backend de testes para desktop. Simula tags em branco e ja gravadas para
    validar todo o fluxo do app sem um celular.
    """

    def __init__(self):
        self._on_tag = None
        self._store = {}  # uid -> texto NDEF simulado

    def start(self, on_tag):
        self._on_tag = on_tag

    def stop(self):
        self._on_tag = None

    def resume(self):
        pass

    def ensure_active(self):
        pass

    def pause(self):
        pass

    def simulate_tag(self, uid, blank=True):
        text = None if blank else self._store.get(uid)
        payload = {"uid": uid, "text": text, "raw_tag": ("MOCK", uid)}
        if self._on_tag:
            self._on_tag(payload)

    def write_text(self, tag, text):
        _, uid = tag
        self._store[uid] = text


# ------------------------------------------------------------------ fabrica
def get_nfc():
    if _on_android():
        return AndroidNFC()
    return MockNFC()


def is_mock(nfc):
    return isinstance(nfc, MockNFC)
