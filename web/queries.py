"""Consultas SQL fijas y reglas de distribución verificadas en los nodos."""

from dataclasses import dataclass, replace
from datetime import datetime

from database import NODE_BY_ID


@dataclass(frozen=True)
class Select:
    fields: str
    source: str
    conditions: tuple = ()
    args: tuple = ()
    order: str = ""
    group: str = ""

    def where(self, condition, *args):
        return replace(self, conditions=(*self.conditions, condition), args=(*self.args, *args))

    @property
    def clause(self):
        filters = " WHERE " + " AND ".join(self.conditions) if self.conditions else ""
        grouping = f" GROUP BY {self.group}" if self.group else ""
        return f"FROM {self.source}{filters}{grouping}"

    @property
    def sql(self):
        order = f" ORDER BY {self.order}" if self.order else ""
        return f"SELECT {self.fields} {self.clause}{order}"

    def read(self, cursor, limit=None, offset=0):
        if limit is None:
            cursor.execute(self.sql, self.args)
        else:
            cursor.execute(self.sql + " LIMIT %s OFFSET %s", (*self.args, limit, offset))
        return cursor.fetchall()


def like_text(search):
    """Trata los comodines y el carácter de escape como texto de búsqueda."""
    return "%" + search.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def inventory(node, search="", size=None, minimum=None):
    query = Select(
        "i.id_producto, i.id_talla, p.nombre AS producto, p.modelo, p.marca, "
        "t.numero_talla AS talla, i.cantidad AS pares, i.fecha_actualizacion AS actualizado",
        "inventario i LEFT JOIN producto p ON p.id_producto = i.id_producto "
        "LEFT JOIN talla t ON t.id_talla = i.id_talla",
        order="i.id_producto, i.id_talla",
    ).where("i.id_sucursal = %s", node.id)
    if search:
        pattern = like_text(search)
        query = query.where(
            "(p.nombre LIKE %s ESCAPE '!' OR p.modelo LIKE %s ESCAPE '!' "
            "OR p.marca LIKE %s ESCAPE '!' OR CAST(t.numero_talla AS CHAR) LIKE %s ESCAPE '!')",
            pattern, pattern, pattern, pattern,
        )
    if size is not None:
        query = query.where("t.numero_talla = %s", size)
    if minimum is not None:
        query = query.where("i.cantidad >= %s", minimum)
    return query


def sales_scope(node, start=None, end=None):
    query = Select("", "venta v").where("v.id_sucursal = %s", node.id)
    if start:
        query = query.where("v.fecha >= %s", start)
    if end:
        query = query.where("v.fecha < DATE_ADD(%s, INTERVAL 1 DAY)", end)
    return query


def sales(node, start=None, end=None):
    return replace(
        sales_scope(node, start, end),
        fields=(
            "v.id_venta, v.fecha, v.total, "
            "NULLIF(CONCAT_WS(' ', e.nombre, e.apellidos), '') AS empleado, "
            "NULLIF(CONCAT_WS(' ', c.nombre, c.apellidos), '') AS cliente"
        ),
        source=(
            "venta v LEFT JOIN empleado e ON e.id_empleado = v.id_empleado "
            "LEFT JOIN cliente c ON c.id_cliente = v.id_cliente"
        ),
        order="v.fecha DESC, v.id_venta DESC",
    )


def transfers(node):
    # La sucursal de origen identifica la copia que se cuenta en el historial global.
    return Select(
        "t.id_transferencia, t.id_sucursal_origen, t.id_sucursal_destino, t.fecha, t.estado",
        "transferencia t",
        order="t.fecha DESC, t.id_transferencia DESC",
    ).where("t.id_sucursal_origen = %s", node.id)


def sale_lines(sale_id):
    return Select(
        "d.id_producto, p.nombre AS producto, p.modelo, t.numero_talla AS talla, "
        "d.cantidad AS pares, d.precio_unitario, d.subtotal",
        "detalle_venta d LEFT JOIN producto p ON p.id_producto = d.id_producto "
        "LEFT JOIN talla t ON t.id_talla = d.id_talla",
        order="d.id_detalle_venta",
    ).where("d.id_venta = %s", sale_id)


def transfer_lines(transfer_id):
    return Select(
        "d.id_producto, p.nombre AS producto, p.modelo, t.numero_talla AS talla, d.cantidad AS pares",
        "detalle_transferencia d LEFT JOIN producto p ON p.id_producto = d.id_producto "
        "LEFT JOIN talla t ON t.id_talla = d.id_talla",
        order="d.id_detalle_transferencia",
    ).where("d.id_transferencia = %s", transfer_id)


CATALOGS = {
    "productos": ("Productos", "producto", "id_producto", (
        ("id_producto", "ID"), ("nombre", "Producto"), ("modelo", "Modelo"),
        ("marca", "Marca"), ("categoria", "Categoría"), ("color", "Color"),
        ("precio", "Precio"), ("id_proveedor", "ID proveedor"),
    )),
    "tallas": ("Tallas", "talla", "id_talla", (
        ("id_talla", "ID"), ("numero_talla", "Talla"),
    )),
    "proveedores": ("Proveedores", "proveedor", "id_proveedor", (
        ("id_proveedor", "ID"), ("nombre", "Proveedor"), ("telefono", "Teléfono"),
        ("correo", "Correo"), ("direccion", "Dirección"),
    )),
    "clientes": ("Clientes", "cliente", "id_cliente", (
        ("id_cliente", "ID"), ("nombre", "Nombre"), ("apellidos", "Apellidos"),
        ("telefono", "Teléfono"), ("correo", "Correo"),
    )),
    "empleados": ("Empleados", "empleado", "id_empleado", (
        ("id_empleado", "ID"), ("nombre", "Nombre"), ("apellidos", "Apellidos"),
        ("puesto", "Puesto"), ("nodo_nombre", "Sucursal"),
    )),
    "sucursales": ("Sucursales", "sucursal", "id_sucursal", (
        ("id_sucursal", "ID"), ("nombre", "Sucursal"), ("municipio", "Municipio"),
        ("direccion", "Dirección"), ("telefono", "Teléfono"),
    )),
}


CATALOG_SEARCH = {
    "productos": ("nombre", "modelo", "marca", "categoria"),
    "tallas": ("CAST(numero_talla AS CHAR)",),
    "proveedores": ("nombre", "correo"),
    "clientes": ("CONCAT_WS(' ', nombre, apellidos)", "correo"),
    "empleados": ("CONCAT_WS(' ', nombre, apellidos)", "puesto"),
    "sucursales": ("nombre", "municipio"),
}


def catalog(node, name, search=""):
    _, table, key, columns = CATALOGS[name]
    fields = ", ".join(column for column, _ in columns if column != "nodo_nombre")
    query = Select(fields, table, order=key)
    if name == "empleados":
        query = query.where("id_sucursal = %s", node.id)
    if search:
        fields = CATALOG_SEARCH[name]
        condition = " OR ".join(f"{field} LIKE %s ESCAPE '!'" for field in fields)
        query = query.where(f"({condition})", *((like_text(search),) * len(fields)))
    return query


def inventory_summary(node):
    return Select(
        "id_sucursal, COUNT(*) AS referencias, COALESCE(SUM(cantidad), 0) AS pares",
        "inventario",
        group="id_sucursal",
    ).where("id_sucursal = %s", node.id)


GLOBAL_INVENTORY = Select(
    "id_sucursal, COUNT(*) AS referencias, COALESCE(SUM(cantidad), 0) AS pares",
    "inventario_global",
    group="id_sucursal",
    order="id_sucursal",
)


def sales_summary(node, start=None, end=None):
    return replace(
        sales_scope(node, start, end),
        fields="COUNT(*) AS ventas, COALESCE(SUM(v.total), 0) AS ingresos",
    )


def best_sellers(node, start=None, end=None):
    return replace(
        sales_scope(node, start, end),
        fields="d.id_producto, MAX(p.nombre) AS producto, MAX(p.modelo) AS modelo, SUM(d.cantidad) AS pares",
        source=(
            "venta v JOIN detalle_venta d ON d.id_venta = v.id_venta "
            "LEFT JOIN producto p ON p.id_producto = d.id_producto"
        ),
        group="d.id_producto",
    )


def stock_by_product(node):
    return Select(
        "i.id_producto, MAX(p.nombre) AS producto, MAX(p.modelo) AS modelo, SUM(i.cantidad) AS pares",
        "inventario i LEFT JOIN producto p ON p.id_producto = i.id_producto",
        group="i.id_producto",
    ).where("i.id_sucursal = %s", node.id)


def count(query, cursor):
    cursor.execute(f"SELECT COUNT(*) AS total {query.clause}", query.args)
    return cursor.fetchone()["total"]


def by_date(row, key):
    return row["fecha"] or datetime.min, row["nodo_id"], row[key]


def branch_name(node_id):
    node = NODE_BY_ID.get(node_id)
    return node.name if node else f"Sucursal {node_id}"
