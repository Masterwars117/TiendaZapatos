"""Prepara las cuentas, la federación y las réplicas del entorno demo."""

from contextlib import ExitStack
from pathlib import Path
from time import sleep

import pymysql

from database import NODES, PRIMARY

DATABASE = "zapateria_distribuida"
READER = "zapateria_lectura"
FEDERATED = "zapateria_federada"
REPLICA = "zapateria_replica"
ADMIN_CREDENTIALS = Path("/run/zapateria-admin")
READER_PASSWORD = Path("/run/zapateria-reader/password")


def connect_demo_nodes(stack):
    password = (ADMIN_CREDENTIALS / "root").read_text(encoding="ascii")
    cursors = {}
    for node in NODES:
        connection = stack.enter_context(
            pymysql.connect(
                host=node.key,
                port=node.port,
                user="root",
                password=password,
                database=DATABASE,
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
                read_timeout=10,
                write_timeout=5,
                autocommit=True,
            )
        )
        cursor = stack.enter_context(connection.cursor())
        cursor.execute("SELECT @@server_id AS servidor, COUNT(*) AS sucursales FROM sucursal")
        status = cursor.fetchone()
        if status["servidor"] != node.id or status["sucursales"] < len(NODES):
            raise RuntimeError(f"Revisa la inicialización del nodo {node.name}.")
        cursors[node] = cursor
    return cursors


def create_account(cursor, username, password):
    cursor.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s", (username, "%", password))


def configure_accounts(cursors):
    read_password = READER_PASSWORD.read_text(encoding="ascii")
    replication_password = (ADMIN_CREDENTIALS / "replication").read_text(encoding="ascii")
    federated_password = (ADMIN_CREDENTIALS / "federated").read_text(encoding="ascii")
    for node, cursor in cursors.items():
        # Las cuentas y vistas se crean localmente en sus nodos correspondientes.
        cursor.execute("SET SESSION sql_log_bin = 0")
        create_account(cursor, READER, read_password)
        cursor.execute(f"GRANT SELECT ON {DATABASE}.* TO %s@%s", (READER, "%"))
        if node == PRIMARY:
            cursor.execute(f"GRANT SHOW VIEW ON {DATABASE}.* TO %s@%s", (READER, "%"))
            create_account(cursor, REPLICA, replication_password)
            cursor.execute("GRANT REPLICATION SLAVE ON *.* TO %s@%s", (REPLICA, "%"))
        else:
            create_account(cursor, FEDERATED, federated_password)
            cursor.execute(f"GRANT SELECT ON {DATABASE}.inventario TO %s@%s", (FEDERATED, "%"))


def configure_global_view(cursor):
    password = (ADMIN_CREDENTIALS / "federated").read_text(encoding="ascii")
    tables = ["inventario"]
    for node in NODES[1:]:
        server = f"demo_{node.key}"
        table = f"inventario_{node.key}"
        cursor.execute(
            f"CREATE SERVER IF NOT EXISTS {server} FOREIGN DATA WRAPPER mysql "
            "OPTIONS (HOST %s, DATABASE %s, USER %s, PASSWORD %s, PORT %s)",
            (node.key, DATABASE, FEDERATED, password, node.port),
        )
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {table} (
                id_inventario INT PRIMARY KEY,
                id_sucursal INT NOT NULL,
                id_producto INT NOT NULL,
                id_talla INT NOT NULL,
                cantidad INT NOT NULL,
                fecha_actualizacion DATETIME
            ) ENGINE=FEDERATED CONNECTION=%s""",
            (f"{server}/inventario",),
        )
        tables.append(table)
    columns = "id_inventario, id_sucursal, id_producto, id_talla, cantidad, fecha_actualizacion"
    union = " UNION ALL ".join(f"SELECT {columns} FROM {table}" for table in tables)
    cursor.execute(f"CREATE OR REPLACE SQL SECURITY DEFINER VIEW inventario_global AS {union}")
    cursor.execute("SELECT COUNT(*) AS filas FROM inventario_global")
    print(f"Vista inventario_global disponible con {cursor.fetchone()['filas']} filas.")


def start_replicas(cursors):
    password = (ADMIN_CREDENTIALS / "replication").read_text(encoding="ascii")
    primary = cursors[PRIMARY]
    primary.execute("SHOW MASTER STATUS")
    position = primary.fetchone()
    if not position:
        raise RuntimeError("El registro binario del nodo Villahermosa debe estar activo.")

    replicas = {node: cursors[node] for node in NODES[1:]}
    for node, cursor in replicas.items():
        cursor.execute("SHOW SLAVE STATUS")
        status = cursor.fetchone()
        if not status:
            # Los catálogos ya se sembraron en los tres nodos. Replica cambios posteriores.
            cursor.execute(
                "CHANGE MASTER TO MASTER_HOST=%s, MASTER_PORT=%s, MASTER_USER=%s, "
                "MASTER_PASSWORD=%s, MASTER_LOG_FILE=%s, MASTER_LOG_POS=%s, MASTER_CONNECT_RETRY=2",
                (PRIMARY.key, PRIMARY.port, REPLICA, password, position["File"], position["Position"]),
            )
        elif (status["Master_Host"], status["Master_Port"]) != (PRIMARY.key, PRIMARY.port):
            raise RuntimeError(f"El origen de replicación de {node.name} no coincide con el demo.")
        cursor.execute("START SLAVE")

    for _ in range(25):
        ready = []
        for node, cursor in replicas.items():
            cursor.execute("SHOW SLAVE STATUS")
            status = cursor.fetchone()
            if status["Slave_IO_Running"] == status["Slave_SQL_Running"] == "Yes":
                ready.append(node.name)
        if len(ready) == len(replicas):
            print("Réplicas de catálogos activas en " + " y ".join(ready) + ".")
            return
        sleep(1)
    raise RuntimeError("Las réplicas tardaron demasiado. Revisa la configuración y los logs de MariaDB.")


def main():
    with ExitStack() as stack:
        cursors = connect_demo_nodes(stack)
        configure_accounts(cursors)
        configure_global_view(cursors[PRIMARY])
        start_replicas(cursors)


if __name__ == "__main__":
    try:
        main()
    except pymysql.MySQLError as error:
        raise SystemExit(f"Falló la inicialización de MariaDB, código {error.args[0]}.") from None
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    except (OSError, UnicodeError):
        raise SystemExit("Revisa los volúmenes de credenciales del demo.") from None
