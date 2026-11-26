"""Entradas HTTP y comprobación local de Zapatería Distribuida."""

import re
from datetime import date
from decimal import Decimal

import click
from flask import Flask, abort, render_template, request, url_for
from werkzeug.exceptions import SecurityError

import queries as q
import reports
from database import Database, MISSING_CREDENTIALS, NODES, NODE_BY_KEY

NAVIGATION = (
    ("dashboard", "Panel general", "dashboard"),
    ("inventory", "Inventario", "inventory"),
    ("sales", "Ventas", "sales"),
    ("transfers", "Transferencias", "transfers"),
    ("catalogs", "Catálogos", "catalogs"),
    ("statistics", "Estadísticas", "statistics"),
    ("distributed", "Consultas distribuidas", "distributed"),
)

INVENTORY_COLUMNS = (
    ("producto", "Producto"), ("modelo", "Modelo"), ("marca", "Marca"), ("talla", "Talla"),
    ("nodo_nombre", "Sucursal"), ("pares", "Pares"), ("actualizado", "Actualizado"),
)
SALE_COLUMNS = (
    ("id_venta", "Venta"), ("nodo_nombre", "Sucursal"), ("fecha", "Fecha"),
    ("empleado", "Empleado"), ("cliente", "Cliente"), ("total", "Importe"),
)
PAGE_FILTERS = ("q", "sucursal", "talla", "minimo", "desde", "hasta")
TRANSFER_COLUMNS = (
    ("id_transferencia", "Transferencia"), ("origen", "Origen"), ("destino", "Destino"),
    ("fecha", "Fecha"), ("estado", "Estado"),
)
LINE_COLUMNS = (("producto", "Producto"), ("modelo", "Modelo"), ("talla", "Talla"), ("pares", "Pares"))


def choose_nodes():
    key = request.args.get("sucursal", "")
    if not key:
        return NODES
    if key not in NODE_BY_KEY:
        abort(400, description="Selecciona una sucursal de la lista.")
    return (NODE_BY_KEY[key],)


def search_arg():
    search = request.args.get("q", "").strip()
    if len(search) > 100:
        abort(400, description="La búsqueda admite hasta 100 caracteres.")
    return search


def number_arg(name, minimum, maximum, default=None):
    value = request.args.get(name, "").strip()
    if not value:
        return default
    if not re.fullmatch(r"[0-9]{1,10}", value) or not minimum <= int(value) <= maximum:
        abort(400, description=f"El valor de {name} debe ser un entero de {minimum} a {maximum}.")
    return int(value)


def date_arg(name):
    value = request.args.get(name, "").strip()
    if not value:
        return None
    try:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except ValueError:
        abort(400, description="Selecciona una fecha válida.")


def cell(value, key):
    if value is None or value == "":
        return "—"
    if key in {"total", "ingresos", "precio", "precio_unitario", "subtotal"}:
        return f"${value:,.2f}"
    if key in {"fecha", "actualizado"}:
        return value.strftime("%d/%m/%Y %H:%M:%S")
    if key in {"talla", "numero_talla"}:
        return f"{value:.1f}"
    if key == "estado":
        return value.replace("_", " ").capitalize()
    return value


def create_app(db=None):
    app = Flask(__name__)
    app.config["TRUSTED_HOSTS"] = ["127.0.0.1", "localhost"]
    db = db if db is not None else Database()
    app.jinja_env.filters["cell"] = cell
    app.jinja_env.filters["digits"] = lambda value: "—" if value is None else f"{value:,}"

    @app.after_request
    def keep_queries_private(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.context_processor
    def interface():
        endpoint = request.endpoint or ""
        active = {"sale_detail": "sales", "transfer_detail": "transfers"}.get(endpoint, endpoint)

        def page_url(number):
            values = {key: request.args[key] for key in PAGE_FILTERS if key in request.args}
            values.update(request.view_args or {})
            values["pagina"] = number
            return url_for(endpoint, **values)

        return {"navigation": NAVIGATION, "active": active, "nodes": NODES, "page_url": page_url}

    @app.get("/")
    def dashboard():
        status, catalog, operations = reports.dashboard(db)
        catalog_node = next(iter(catalog.values), None)
        counts = catalog.values.get(catalog_node, {})
        totals = {}
        if operations.complete:
            for key in ("pares", "ventas", "ingresos", "transferencias"):
                totals[key] = sum(row[key] for row in operations.values.values())
        setup_nodes = [node for node in NODES if status.errors.get(node) == MISSING_CREDENTIALS]
        node_issues = {}
        for node in NODES:
            messages = (batch.errors.get(node) for batch in (status, catalog, operations))
            node_issues[node] = tuple(dict.fromkeys(
                message for message in messages if message and message != MISSING_CREDENTIALS
            ))
        return render_template(
            "dashboard.html", title="Panel general", status=status, catalog_node=catalog_node,
            operations=operations, totals=totals | counts, setup_nodes=setup_nodes, node_issues=node_issues,
        )

    @app.get("/inventario")
    def inventory():
        nodes = choose_nodes()
        search = search_arg()
        size = request.args.get("talla", "").strip().replace(",", ".")
        if size and not re.fullmatch(r"[0-9]{1,3}(\.[0-9])?", size):
            abort(400, description="Ingresa una talla válida, por ejemplo 26 o 26.5.")
        minimum = number_arg("minimo", 0, 2147483647)
        page, batch = reports.paginated(
            db, nodes, lambda n: q.inventory(n, search, Decimal(size) if size else None, minimum),
            number_arg("pagina", 1, 1000000, 1),
            lambda row: (row["nodo_id"], row["id_producto"], row["id_talla"]),
        )
        return render_template("inventory.html", title="Inventario", page=page, batch=batch,
                               columns=INVENTORY_COLUMNS)

    @app.get("/ventas")
    def sales():
        nodes = choose_nodes()
        start, end = date_arg("desde"), date_arg("hasta")
        if start and end and start > end:
            abort(400, description="La fecha inicial debe ser anterior o igual a la fecha final.")
        effective_end = None if end == date.max else end
        page, batch = reports.paginated(
            db, nodes, lambda n: q.sales(n, start, effective_end), number_arg("pagina", 1, 1000000, 1),
            lambda row: q.by_date(row, "id_venta"), descending=True,
        )
        summary = reports.sales_report(db, nodes, start, effective_end)
        ranking = reports.product_totals(row["ranking"] for row in summary.values.values()) if summary.complete else []
        return render_template("sales.html", title="Ventas", page=page, batch=batch, selected=nodes,
                               columns=SALE_COLUMNS, summary=summary, ranking=ranking[:10])

    @app.get("/transferencias")
    def transfers():
        page, batch = reports.paginated(
            db, choose_nodes(), q.transfers, number_arg("pagina", 1, 1000000, 1),
            lambda row: q.by_date(row, "id_transferencia"), descending=True,
        )
        for row in page.rows:
            row.update(origen=q.branch_name(row["id_sucursal_origen"]),
                       destino=q.branch_name(row["id_sucursal_destino"]))
        return render_template("transfers.html", title="Transferencias", page=page,
                               batch=batch, columns=TRANSFER_COLUMNS)

    def detail(key, record_id, header, lines, columns, kind):
        node = NODE_BY_KEY.get(key)
        if not node:
            abort(404)
        id_field = "v.id_venta" if kind == "venta" else "t.id_transferencia"

        def read(node, cursor):
            rows = header(node).where(f"{id_field} = %s", record_id).read(cursor)
            return (rows[0], lines(record_id).read(cursor)) if rows else None

        batch = db.run((node,), read)
        if not batch.complete:
            abort(503, description=f"{node.name}. {batch.errors[node]}")
        result = batch.values[node]
        if not result:
            abort(404, description="No se encontró el registro en esta sucursal.")
        row, details = result
        if kind == "transferencia":
            row.update(origen=q.branch_name(row["id_sucursal_origen"]),
                       destino=q.branch_name(row["id_sucursal_destino"]))
        return render_template("detail.html", title=f"{kind.capitalize()} #{record_id}", node=node,
                               row=row, details=details, columns=columns, kind=kind)

    @app.get("/ventas/<key>/<int:record_id>")
    def sale_detail(key, record_id):
        return detail(key, record_id, q.sales, q.sale_lines,
                      (*LINE_COLUMNS, ("precio_unitario", "Precio unitario"), ("subtotal", "Subtotal")), "venta")

    @app.get("/transferencias/<key>/<int:record_id>")
    def transfer_detail(key, record_id):
        return detail(key, record_id, q.transfers, q.transfer_lines, LINE_COLUMNS, "transferencia")

    @app.get("/catalogos")
    @app.get("/catalogos/<name>")
    def catalogs(name="productos"):
        if name not in q.CATALOGS:
            abort(404)
        selected = choose_nodes() if name == "empleados" else NODES
        page, batch = reports.catalog_page(
            db, name, selected, number_arg("pagina", 1, 1000000, 1), search_arg(),
        )
        label, _, _, columns = q.CATALOGS[name]
        return render_template("catalogs.html", title="Catálogos", name=name, label=label,
                               catalogs=q.CATALOGS, page=page, batch=batch, columns=columns)

    @app.get("/estadisticas")
    def statistics():
        batch = reports.statistics(db)
        ranking = reports.product_totals(row["ranking"] for row in batch.values.values())[:10] if batch.complete else []
        stock = reports.product_totals(row["existencias"] for row in batch.values.values())
        by_node = {node: {row["id_producto"]: int(row["pares"]) for row in value["existencias"]}
                   for node, value in batch.values.items()}
        products = [{
            "id": row["id_producto"],
            "label": product_label(row),
            "values": [by_node[node].get(row["id_producto"], 0) if node in by_node else None for node in NODES],
        } for row in stock]
        return render_template("statistics.html", title="Estadísticas", batch=batch,
                               ranking=ranking, products=products, product_label=product_label)

    @app.get("/consultas-distribuidas")
    def distributed():
        key = request.args.get("consulta", "")
        branch = request.args.get("sucursal") or NODES[0].key
        if key and (key not in reports.DEMOS or branch not in NODE_BY_KEY):
            abort(400, description="Selecciona una consulta y una sucursal de las listas.")
        result = reports.academic(db, key, NODE_BY_KEY[branch]) if key else None
        return render_template("distributed.html", title="Consultas distribuidas", demos=reports.DEMOS,
                               selection=key, result=result)

    @app.errorhandler(SecurityError)
    def invalid_host(error):
        return "Abre la aplicación desde 127.0.0.1 o localhost.", 400

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(503)
    def render_error(error):
        titles = {400: "Revisa los filtros", 404: "Página o registro no encontrado", 503: "Consulta no disponible"}
        return render_template("error.html", title=titles[error.code], message=error.description), error.code

    @app.cli.command("verificar-conexion")
    def verify_connection():
        """Comprueba la cuenta de lectura y la identidad de cada nodo."""
        result = db.check()
        for node in NODES:
            status = result.errors.get(node, "Conexión de lectura disponible")
            click.echo(f"{node.name} ({node.port}) · {status}")
        if not result.complete:
            raise click.ClickException("Faltan conexiones para completar las consultas globales.")

    return app


def product_label(row):
    name = row["producto"] or f"Producto #{row['id_producto']}"
    return f"{name} · {row['modelo']}" if row["modelo"] else name


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False, load_dotenv=False)
