"""Conexiones y ejecución independiente en los fragmentos de MariaDB."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pymysql
from dotenv import dotenv_values

logger = logging.getLogger(__name__)
MISSING_CREDENTIALS = "Faltan las credenciales de consulta en .env."


@dataclass(frozen=True)
class Node:
    id: int
    key: str
    name: str
    port: int


NODES = (
    Node(1, "villahermosa", "Villahermosa", 3307),
    Node(2, "cardenas", "Cárdenas", 3308),
    Node(3, "cunduacan", "Cunduacán", 3309),
)
PRIMARY = NODES[0]
NODE_BY_KEY = {node.key: node for node in NODES}
NODE_BY_ID = {node.id: node for node in NODES}


@dataclass
class Batch:
    values: dict
    errors: dict

    @property
    def complete(self):
        return not self.errors


class NodeError(Exception):
    """Incidencia con un mensaje apto para mostrar en la interfaz."""


class Database:
    def __init__(self, env_file=None):
        self.env_file = env_file or Path(__file__).with_name(".env")

    @contextmanager
    def session(self, node, config):
        prefix = f"DB_{node.key.upper()}_"
        user = config.get(prefix + "USER", "").strip()
        password = config.get(prefix + "PASSWORD", "")
        password_file = config.get(prefix + "PASSWORD_FILE")
        if user and not password and password_file:
            try:
                password = Path(password_file).read_text(encoding="utf-8").rstrip("\r\n")
            except (OSError, UnicodeError) as error:
                raise NodeError("Revisa el archivo de credenciales de lectura del nodo.") from error
        if not user or not password:
            raise NodeError(MISSING_CREDENTIALS)
        if user.lower() == "root":
            raise NodeError("Configura una cuenta de solo lectura para este nodo.")

        try:
            options = {
                "host": config.get(prefix + "HOST", "127.0.0.1"),
                "port": int(config.get(prefix + "PORT", node.port)),
                "user": user,
                "password": password,
                "database": config.get("DB_NAME", "zapateria_distribuida"),
                "connect_timeout": int(config.get("DB_CONNECT_TIMEOUT", 3)),
                "read_timeout": int(config.get("DB_READ_TIMEOUT", 5)),
                "write_timeout": int(config.get("DB_WRITE_TIMEOUT", 3)),
                "charset": "utf8mb4",
                "cursorclass": pymysql.cursors.DictCursor,
            }
            if not 1 <= options["port"] <= 65535 or any(
                not 1 <= options[key] <= 60
                for key in ("connect_timeout", "read_timeout", "write_timeout")
            ):
                raise ValueError("Puerto o tiempo límite fuera de rango")
            connection = pymysql.connect(**options)
        except ValueError as error:
            raise NodeError("Revisa el puerto y los tiempos límite en .env.") from error

        # El cierre termina la transacción de lectura, incluso si una consulta falla.
        with connection, connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("START TRANSACTION READ ONLY")
            cursor.execute("SELECT @@server_id AS servidor")
            if cursor.fetchone()["servidor"] != node.id:
                raise NodeError("El puerto configurado corresponde a otro servidor.")
            yield cursor

    def run(self, nodes, operation):
        # Vuelve a leer el archivo al actualizar el panel. El entorno de Windows tiene prioridad.
        try:
            config = dotenv_values(self.env_file, interpolate=False, encoding="utf-8-sig")
        except (OSError, UnicodeError):
            return Batch({}, dict.fromkeys(nodes, "Revisa el archivo web/.env. Flask no pudo leerlo."))
        config = {key: value for key, value in config.items() if value is not None}
        config.update(os.environ)

        def attempt(node):
            try:
                with self.session(node, config) as cursor:
                    return operation(node, cursor), None
            except NodeError as error:
                return None, str(error)
            except pymysql.MySQLError as error:
                code = error.args[0] if error.args else None
                logger.info("Consulta MariaDB fallida en %s, código %s", node.key, code)
                if code in {1044, 1045, 1142, 1143, 1698}:
                    return None, "Acceso denegado. Revisa la cuenta y sus permisos de lectura."
                if code in {2002, 2003, 2006, 2013, 1927, 1969}:
                    return None, "MariaDB no respondió dentro del tiempo límite."
                if code in {1049, 1146, 1356, 1932}:
                    return None, "La base, tabla o vista requerida no está disponible."
                return None, "MariaDB no pudo completar la consulta."

        values, errors = {}, {}
        if len(nodes) == 1:
            responses = (attempt(nodes[0]),)
        else:
            with ThreadPoolExecutor(max_workers=len(nodes)) as workers:
                responses = tuple(workers.map(attempt, nodes))
        for node, (value, error) in zip(nodes, responses):
            if error:
                errors[node] = error
            else:
                values[node] = value
        return Batch(values, errors)

    def check(self):
        return self.run(NODES, lambda node, cursor: True)
