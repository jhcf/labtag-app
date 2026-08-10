"""
Carrega configuracao sensivel (a senha do modo Preparacao, etc.).

Procura, NESTA ORDEM, o primeiro arquivo que existir ao lado deste modulo:
    1. ".env"           — convencao de desenvolvimento/desktop (dotfile,
                           nunca commitado — ver .gitignore). So usado
                           quando voce roda "python main.py" direto no PC.
    2. "secrets.json"    — o arquivo usado para o EMPACOTAMENTO ANDROID.
                           Formato JSON simples: {"PREP_PASSWORD": "123456"}.
                           Usamos JSON aqui (em vez de outro .env) porque
                           JA TEMOS PROVA de que arquivos .json sao
                           empacotados corretamente pelo buildozer neste
                           projeto (dados.json, usado por boxes.py, chega
                           certinho dentro do APK) — enquanto tentativas
                           anteriores com um dotfile ".env" ou uma copia
                           "app.env" NAO apareceram dentro do
                           assets/private.tar do APK gerado (verificado
                           manualmente). Em vez de continuar caçando esse
                           comportamento do buildozer, usamos o caminho
                           que sabemos que funciona.
    3. "app.env"         — mantido como ultima tentativa (nao remove nada
                           que ja funcionava), mas NAO confie nele sozinho.

O arquivo NUNCA deve ser commitado no repositorio. Use secrets.json.example
e .env.example (esses sim versionados) como modelo.

Nao usamos a biblioteca python-dotenv de proposito: e uma dependencia a mais
no empacotamento Android (via buildozer/python-for-android), que ja e um
pipeline sensivel a versoes. O parser abaixo cobre exatamente o que este
projeto precisa, sem dependencia externa.

Prioridade de leitura de uma chave (a primeira que existir vale):
    1. variavel de ambiente real do sistema operacional
    2. valor lido do arquivo de configuracao encontrado
    3. valor padrao (default) passado pelo chamador
"""

import json
import os


def _log(msg):
    print("[LABTAG][env_config] %s" % msg)


def _parse_env_file(path):
    values = {}
    with open(path, encoding="utf-8-sig") as f:  # utf-8-sig: descarta BOM se houver
        for raw_line in f:
            line = raw_line.strip().replace("\r", "")
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    return values


def _parse_json_file(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("secrets.json precisa conter um objeto {chave: valor}")
    return {str(k): str(v) for k, v in data.items()}


# (nome_do_arquivo, funcao_de_parse), na ordem de prioridade de busca.
CANDIDATE_FILES = [
    (".env", _parse_env_file),
    ("secrets.json", _parse_json_file),
    ("app.env", _parse_env_file),
]


def _base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _load():
    base = _base_dir()
    checked = []
    for name, parser in CANDIDATE_FILES:
        path = os.path.join(base, name)
        exists = os.path.exists(path)
        checked.append((path, exists))
        if exists:
            try:
                values = parser(path)
                _log("configuracao carregada de '%s' (%d chave(s): %s)"
                     % (path, len(values), ", ".join(sorted(values.keys())) or "-"))
                return values, path
            except Exception as exc:
                _log("erro ao ler '%s': %s" % (path, exc))
    _log("nenhum arquivo de configuracao encontrado. Caminhos verificados:")
    for path, exists in checked:
        _log("  - %s (existe? %s)" % (path, exists))
    return {}, None


# Le a configuracao uma vez, na importacao do modulo.
_ENV, _ENV_PATH = _load()


def get(key, default=None):
    """Busca uma chave: ambiente do SO > arquivo de config > default."""
    return os.environ.get(key, _ENV.get(key, default))


def loaded_from():
    """Caminho do arquivo efetivamente usado, ou None se nenhum foi achado."""
    return _ENV_PATH


def reload():
    """Recarrega o arquivo do disco (util se ele mudar em tempo de execucao,
    ou em testes)."""
    global _ENV, _ENV_PATH
    _ENV, _ENV_PATH = _load()
