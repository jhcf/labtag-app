"""
Base de dados local (SQLite) que registra a associação etiqueta RFID <-> tipo de caixa.

Cada etiqueta física recebe um identificador único (tag_uid, lido do próprio chip)
e um registro do tipo de caixa a que foi associada. Guardamos também data/hora do
cadastro e um contador de leituras, útil para o mapa de uso do projeto.

O arquivo do banco fica na pasta de dados do app (no Android, o diretório privado
do aplicativo; no desktop, a pasta local).
"""

import os
import sqlite3
import time

 
def _default_db_path():
    # No Android, App.user_data_dir aponta para o diretório privado do app.
    # Aqui deixamos um fallback simples para rodar no desktop.
    try:
        from android.storage import app_storage_path  # type: ignore
        base = app_storage_path()
    except Exception:
        base = os.path.join(os.path.expanduser("~"), ".redemaisdf")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "etiquetas.db")


class TagDatabase:
    def __init__(self, path=None):
        self.path = path or _default_db_path()
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._create()

    def _create(self):
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS etiquetas (
                tag_uid      TEXT PRIMARY KEY,
                box_code     TEXT NOT NULL,
                school_code  TEXT,
                created_at   INTEGER NOT NULL,
                last_read_at INTEGER,
                read_count   INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        # Configurações do aparelho (ex.: a escola deste kit/telefone).
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        self._conn.commit()
        self._migrate()

    def _migrate(self):
        # Garante a coluna school_code em bancos criados antes desta versão.
        cols = [r["name"] for r in self._conn.execute(
            "PRAGMA table_info(etiquetas)")]
        if "school_code" not in cols:
            self._conn.execute(
                "ALTER TABLE etiquetas ADD COLUMN school_code TEXT")
            self._conn.commit()

    # -- configurações do aparelho ----------------------------------------
    def get_setting(self, key, default=None):
        cur = self._conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row["value"] if row else default

    def set_setting(self, key, value):
        self._conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value))
        self._conn.commit()

    def get(self, tag_uid):
        cur = self._conn.execute(
            "SELECT * FROM etiquetas WHERE tag_uid = ?", (tag_uid,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def register(self, tag_uid, box_code, school_code=None):
        """Grava a associação de uma etiqueta em branco a uma caixa e escola."""
        now = int(time.time())
        self._conn.execute(
            """
            INSERT OR REPLACE INTO etiquetas
                (tag_uid, box_code, school_code, created_at, last_read_at, read_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tag_uid, str(box_code), school_code, now, now, 0),
        )
        self._conn.commit()
        return self.get(tag_uid)

    def mark_read(self, tag_uid):
        now = int(time.time())
        self._conn.execute(
            "UPDATE etiquetas SET last_read_at = ?, read_count = read_count + 1 "
            "WHERE tag_uid = ?",
            (now, tag_uid),
        )
        self._conn.commit()

    def all(self):
        cur = self._conn.execute(
            "SELECT * FROM etiquetas ORDER BY created_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]

    def count_by_box(self):
        cur = self._conn.execute(
            "SELECT box_code, COUNT(*) AS n FROM etiquetas GROUP BY box_code"
        )
        return {r["box_code"]: r["n"] for r in cur.fetchall()}

    def boxes_for_school(self, school_code):
        """Conjunto de códigos de caixa já cadastrados para uma escola."""
        cur = self._conn.execute(
            "SELECT DISTINCT box_code FROM etiquetas WHERE school_code = ?",
            (school_code,))
        return {r["box_code"] for r in cur.fetchall()}

    def schools_progress(self):
        """Para cada escola, quantas caixas distintas já foram cadastradas."""
        cur = self._conn.execute(
            "SELECT school_code, COUNT(DISTINCT box_code) AS n "
            "FROM etiquetas WHERE school_code IS NOT NULL GROUP BY school_code")
        return {r["school_code"]: r["n"] for r in cur.fetchall()}

    def close(self):
        self._conn.close()
