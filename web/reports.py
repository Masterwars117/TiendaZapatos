"""Combina fragmentos y conserva la procedencia de cada resultado."""

from dataclasses import dataclass
from math import ceil
from time import perf_counter

import pymysql

import queries as q
from database import Batch, NODES, PRIMARY

PAGE_SIZE = 20


@dataclass
class Page:
    rows: list
    known_total: int
    number: int

    @property
    def last(self):
        return max(1, ceil(self.known_total / PAGE_SIZE))


def paginated(db, nodes, build, number, sort_key, descending=False):
    local = len(nodes) == 1
    offset = (number - 1) * PAGE_SIZE

    def read(node, cursor):
        query = build(node)
        total = q.count(query, cursor)
        limit = PAGE_SIZE if local else min(total, offset + PAGE_SIZE)
        rows = query.read(cursor, limit, offset if local else 0) if limit else ()
        return total, [dict(row, nodo_id=node.id, nodo_nombre=node.name, nodo_key=node.key) for row in rows]

    batch = db.run(nodes, read)
    total = sum(count for count, _ in batch.values.values())
    rows = [row for _, results in batch.values.values() for row in results]
    if not local:
        rows.sort(key=sort_key, reverse=descending)
        rows = rows[offset:offset + PAGE_SIZE]
    return Page(rows, total, number), batch


def from_catalog_copy(read):
    """Lee una sola copia de un catálogo replicado y registra su procedencia."""
    errors = {}
    for node in NODES:
        payload, batch = read((node,))
        if batch.complete:
            return payload, batch
        errors.update(batch.errors)
    return payload, Batch({}, errors)


def catalog_page(db, name, nodes, number, search=""):
    _, _, key, _ = q.CATALOGS[name]

    def read(db, selected):
        return paginated(db, selected, lambda node: q.catalog(node, name, search), number,
                         lambda row: (row["nodo_id"], row[key]))

    if name == "empleados":
        return read(db, nodes)
    if name == "clientes":
        return read(db, (PRIMARY,))
    return from_catalog_copy(lambda selected: read(db, selected))


def dashboard(db):
    counts = q.Select(
        "(SELECT COUNT(*) FROM sucursal) AS sucursales, (SELECT COUNT(*) FROM producto) AS productos",
        "DUAL",
    )
    _, catalog = from_catalog_copy(
        lambda nodes: (None, db.run(nodes, lambda node, cursor: counts.read(cursor)[0]))
    )

    def read(node, cursor):
        stock = q.inventory_summary(node).read(cursor)
        return {
            "pares": int(stock[0]["pares"]) if stock else 0,
            **q.sales_summary(node).read(cursor)[0],
            "transferencias": q.count(q.transfers(node), cursor),
        }

    return db.check(), catalog, db.run(NODES, read)


def sales_report(db, nodes, start=None, end=None):
    def read(node, cursor):
        return {
            **q.sales_summary(node, start, end).read(cursor)[0],
            "ranking": q.best_sellers(node, start, end).read(cursor),
        }
    return db.run(nodes, read)


def product_totals(rows_by_node):
    products = {}
    for rows in rows_by_node:
        for row in rows:
            key = row["id_producto"]
            product = products.setdefault(key, {
                "id_producto": key, "producto": None, "modelo": None, "pares": 0,
            })
            product["producto"] = product["producto"] or row["producto"]
            product["modelo"] = product["modelo"] or row["modelo"]
            product["pares"] += int(row["pares"])
    return sorted(products.values(), key=lambda row: (-row["pares"], row["id_producto"]))


def statistics(db):
    def read(node, cursor):
        stock = q.stock_by_product(node).read(cursor)
        return {
            **q.sales_summary(node).read(cursor)[0],
            "ranking": q.best_sellers(node).read(cursor),
            "existencias": stock,
            "pares": sum(int(row["pares"]) for row in stock),
        }

    return db.run(NODES, read)


@dataclass(frozen=True)
class Demo:
    title: str
    description: str
    approach: str


DEMOS = {
    "local": Demo("Inventario local", "Cuenta las referencias y los pares en una sucursal.",
                  "La consulta se ejecuta contra la tabla inventario del nodo seleccionado."),
    "distribuida": Demo("Inventario de los tres nodos", "Compara los pares y referencias por sucursal.",
                        "Flask consulta cada fragmento en paralelo y reúne una fila por sucursal."),
    "vista-global": Demo("Inventario mediante la vista global", "Lee las existencias mediante inventario_global.",
                        "Villahermosa reúne su tabla local y las tablas FEDERATED que apuntan a Cárdenas y Cunduacán."),
    "ventas": Demo("Ventas e ingresos por sucursal", "Calcula la cantidad de ventas y sus ingresos por nodo.",
                  "Cada MariaDB agrega su fragmento y Flask reúne los resultados por sucursal."),
}


def _demo_query(query, cursor):
    sql = cursor.mogrify(query.sql, query.args)
    started = perf_counter()
    rows = query.read(cursor)
    elapsed = (perf_counter() - started) * 1000
    plan, plan_error = (), False
    try:
        cursor.execute("EXPLAIN " + query.sql, query.args)
        plan = cursor.fetchall()
    except pymysql.MySQLError:
        plan_error = True
    return {"rows": rows, "sql": sql, "elapsed": elapsed, "plan": plan, "plan_error": plan_error}


def academic(db, key, branch):
    started = perf_counter()
    targets = (branch,) if key == "local" else NODES
    inconsistent = False
    dependencies = Batch({}, {})

    if key == "vista-global":
        # Comprueba por conexión directa que la vista cubra los tres fragmentos observados.
        dependencies = db.run(NODES, lambda node, cursor: q.inventory_summary(node).read(cursor))
        batch = Batch({}, {})
        if dependencies.complete:
            batch = db.run((PRIMARY,), lambda node, cursor: _demo_query(q.GLOBAL_INVENTORY, cursor))
        if batch.complete and batch.values:
            direct = {row["id_sucursal"]: row for rows in dependencies.values.values() for row in rows}
            through_view = {row["id_sucursal"]: row for row in batch.values[PRIMARY]["rows"]}
            inconsistent = direct != through_view
    else:
        build = q.sales_summary if key == "ventas" else q.inventory_summary
        batch = db.run(targets, lambda node, cursor: _demo_query(build(node), cursor))

    return {
        "targets": targets, "batch": batch, "dependencies": dependencies,
        "inconsistent": inconsistent, "elapsed": (perf_counter() - started) * 1000,
    }
