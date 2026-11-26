"""Comprueba las reglas de lectura y los estados de las páginas sin tocar MariaDB."""

import json
import os
import re
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from app import create_app
from database import Batch, Database, MISSING_CREDENTIALS, NODES
import queries as q
import reports

NO_CREDENTIALS = {
    f"DB_{node.key.upper()}_{setting}": ""
    for node in NODES
    for setting in ("PASSWORD", "PASSWORD_FILE")
}


class AppTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.testing = True
        self.client = self.app.test_client()

    def test_modules_without_credentials(self):
        paths = ["/", "/inventario", "/ventas", "/transferencias", "/estadisticas",
                 "/consultas-distribuidas?consulta=vista-global",
                 *[f"/catalogos/{name}" for name in q.CATALOGS]]
        with patch.dict(os.environ, NO_CREDENTIALS):
            for path in paths:
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn("Faltan las credenciales", response.get_data(as_text=True))

    def test_dashboard_groups_pending_setup(self):
        with patch.dict(os.environ, NO_CREDENTIALS):
            page = self.client.get("/").get_data(as_text=True)
        self.assertEqual(page.count("Faltan las credenciales"), 1)
        self.assertEqual(page.count("Por configurar"), len(NODES))
        self.assertNotIn("Sin conexión", page)
        self.assertIn("Ver pasos de configuración", page)

    def test_rejects_non_local_host(self):
        response = self.client.get("/", base_url="http://host.invalid:5000")
        self.assertEqual(response.status_code, 400)
        self.assertIn("127.0.0.1", response.get_data(as_text=True))

    def test_rejects_invalid_filters_before_connecting(self):
        paths = ["/inventario?talla=26.55", "/inventario?minimo=-1",
                 "/ventas?desde=2026-11-27&hasta=2026-11-26",
                 "/ventas?hasta=2026-02-30", "/transferencias?sucursal=otra",
                 "/consultas-distribuidas?consulta=aparte", "/catalogos/clientes?pagina=0"]
        with patch.object(Database, "run") as database:
            for path in paths:
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path).status_code, 400)
            database.assert_not_called()

    def test_partial_dashboard_hides_totals_but_shows_connected_node(self):
        central, cardenas, cunduacan = NODES
        issue = {cunduacan: "Tiempo límite agotado."}
        metrics = {"pares": 98, "ventas": 2, "ingresos": Decimal("560.00"), "transferencias": 1}
        with patch.object(reports, "dashboard", return_value=(
            Batch({central: True, cardenas: True}, issue),
            Batch({central: {"productos": 10, "sucursales": 3}}, {}),
            Batch({central: metrics, cardenas: metrics}, issue),
        )):
            page = self.client.get("/").get_data(as_text=True)
            self.assertIn("2 de 3 disponibles", page)
            self.assertIn("Sin datos completos", page)
            self.assertIn('"values": [98, 98, null]', page)
            self.assertNotIn("$1,120.00", page)

    def test_statistics_distinguishes_absence_from_zero(self):
        central, cardenas, cunduacan = NODES
        stock = {"id_producto": 3, "producto": "Prueba", "modelo": "T-3", "pares": 2}
        base = {"ventas": 0, "ingresos": Decimal("0"), "ranking": []}
        with patch.object(reports, "statistics", return_value=Batch({
            central: dict(base, existencias=[stock], pares=2),
            cardenas: dict(base, existencias=[], pares=0),
        }, {cunduacan: "Sin acceso."})):
            response = self.client.get("/estadisticas")
            self.assertEqual(response.status_code, 200)
            page = response.get_data(as_text=True)
            data = re.search(r'id="stock-data">([^<]+)</script>', page)
            self.assertEqual(json.loads(data[1])[0]["values"], [2, 0, None])
            self.assertIn("El ranking requiere datos de los tres nodos.", page)

    def test_sale_details_are_addressed_by_node(self):
        central, cardenas, _ = NODES
        row = {"id_venta": 7, "nodo_id": cardenas.id, "nodo_key": cardenas.key,
               "nodo_nombre": cardenas.name, "fecha": None, "empleado": None,
               "cliente": None, "total": Decimal("12.00")}
        with patch.object(reports, "paginated", return_value=(
            reports.Page([row], 1, 1), Batch({cardenas: True}, {central: "Sin conexión."}),
        )), patch.object(reports, "sales_report", return_value=Batch(
            {cardenas: {"ingresos": row["total"], "ranking": []}}, {central: "Sin conexión."},
        )):
            page = self.client.get("/ventas").get_data(as_text=True)
            self.assertIn("/ventas/cardenas/7", page)
            self.assertIn("registros en los nodos consultados", page)

    def test_view_coverage_mismatch_hides_results(self):
        central = NODES[0]
        local = {"id_sucursal": 1, "pares": 4, "referencias": 1}
        remote = dict(local, pares=3)
        execution = {"rows": [remote], "sql": q.GLOBAL_INVENTORY.sql, "elapsed": 1,
                     "plan": [{"table": "inventario"}], "plan_error": False}
        db = MagicMock()
        db.run.side_effect = [
            Batch({central: [local], NODES[1]: [], NODES[2]: []}, {}),
            Batch({central: execution}, {}),
        ]
        client = create_app(db).test_client()
        page = client.get("/consultas-distribuidas?consulta=vista-global").get_data(as_text=True)
        self.assertIn("El resumen de la vista difiere", page)
        self.assertIn("SQL ejecutado", page)
        self.assertIn("Plan de ejecución (EXPLAIN)", page)
        self.assertNotIn("ID sucursal", page)

    def test_detail_errors_distinguish_missing_rows_and_unavailable_node(self):
        central = NODES[0]
        db = MagicMock()
        client = create_app(db).test_client()
        db.run.return_value = Batch({central: None}, {})
        self.assertEqual(client.get("/ventas/villahermosa/7").status_code, 404)
        db.run.return_value = Batch({}, {central: "Sin conexión."})
        self.assertEqual(client.get("/transferencias/villahermosa/7").status_code, 503)


class QueryTest(unittest.TestCase):
    def test_fragment_filters_are_bound(self):
        node = NODES[1]
        query = q.inventory(node, "RUN_100%", Decimal("26.5"), 2)
        self.assertNotIn("RUN_100", query.sql)
        self.assertEqual(query.args, (2, *("%RUN!_100!%%",) * 4, Decimal("26.5"), 2))
        self.assertEqual(q.transfers(node).args, (2,))
        self.assertIn("id_sucursal_origen = %s", q.transfers(node).sql)

    def test_merges_chronologically_before_paginating(self):
        central, cardenas, _ = NODES

        def cursor(node):
            result = MagicMock()
            result.fetchone.return_value = {"total": 2}
            result.fetchall.return_value = [
                {"fecha": datetime(2026, 11, day), "id_venta": record_id}
                for record_id, day in ((2, node.id + 2), (1, node.id))
            ]
            return result

        db = MagicMock()
        db.run.side_effect = lambda nodes, read: Batch({node: read(node, cursor(node)) for node in nodes}, {})
        with patch.object(reports, "PAGE_SIZE", 2):
            page, batch = reports.paginated(db, (central, cardenas), q.sales, 2,
                                            lambda row: q.by_date(row, "id_venta"), descending=True)
            self.assertTrue(batch.complete)
            self.assertEqual(page.known_total, 4)
            self.assertEqual(page.last, 2)
            self.assertEqual([(row["id_venta"], row["nodo_id"]) for row in page.rows], [(1, 2), (1, 1)])

    def test_connection_enforces_read_only_and_server_identity(self):
        node = NODES[0]
        with patch.dict(os.environ, {"DB_VILLAHERMOSA_USER": "lector", "DB_VILLAHERMOSA_PASSWORD": "prueba"}):
            with patch("database.pymysql.connect") as connect:
                cursor = connect.return_value.cursor.return_value.__enter__.return_value
                cursor.fetchone.return_value = {"servidor": 2}
                batch = Database().run((node,), lambda n, c: self.fail("El nodo no corresponde"))
                self.assertIn("otro servidor", batch.errors[node])
                cursor.execute.assert_any_call("START TRANSACTION READ ONLY")

    def test_env_file_is_reloaded_between_reads(self):
        node = NODES[0]
        with TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=True):
            env_file = Path(folder) / ".env"
            env_file.write_text("DB_VILLAHERMOSA_USER=lector\nDB_VILLAHERMOSA_PASSWORD=\n", encoding="utf-8")
            db = Database(env_file)
            operation = lambda node, cursor: True
            self.assertEqual(db.run((node,), operation).errors[node], MISSING_CREDENTIALS)

            env_file.write_text("DB_VILLAHERMOSA_USER=lector\nDB_VILLAHERMOSA_PASSWORD=prueba\n", encoding="utf-8")
            with patch("database.pymysql.connect") as connect:
                cursor = connect.return_value.cursor.return_value.__enter__.return_value
                cursor.fetchone.return_value = {"servidor": node.id}
                self.assertEqual(db.run((node,), operation).values, {node: True})
                self.assertEqual(connect.call_args.kwargs["user"], "lector")

    def test_root_is_rejected_without_network(self):
        with patch.dict(os.environ, {"DB_VILLAHERMOSA_USER": "root", "DB_VILLAHERMOSA_PASSWORD": "prueba"}):
            with patch("database.pymysql.connect") as connect:
                batch = Database().run((NODES[0],), lambda n, c: None)
                self.assertIn("cuenta de solo lectura", batch.errors[NODES[0]])
                connect.assert_not_called()
