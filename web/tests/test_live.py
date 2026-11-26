"""Pruebas optativas con las cuentas de solo lectura configuradas en .env."""

import os
import unittest

from app import create_app
from database import Database, NODES
import queries as q
import reports


@unittest.skipUnless(os.getenv("ZAPATERIA_LIVE_TESTS") == "1", "requiere cuentas de lectura en los tres nodos")
class LiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database()
        cls.app = create_app(cls.db)
        cls.app.testing = True
        cls.client = cls.app.test_client()

    def test_connections_and_fragment_queries(self):
        status = self.db.check()
        self.assertEqual(status.errors, {})
        self.assertEqual(tuple(status.values), NODES)
        _, catalog, operations = reports.dashboard(self.db)
        self.assertEqual(catalog.errors, {})
        self.assertEqual(operations.errors, {})
        self.assertEqual(reports.statistics(self.db).errors, {})

    def test_modules_and_academic_plans(self):
        paths = ["/", "/inventario", "/ventas", "/transferencias", "/estadisticas",
                 *[f"/catalogos/{name}" for name in q.CATALOGS],
                 *[f"/consultas-distribuidas?consulta={key}" for key in reports.DEMOS]]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                page = response.get_data(as_text=True)
                self.assertNotIn("notice-amber", page)
                if "consulta=" in path:
                    self.assertIn("SQL ejecutado", page)
                    self.assertIn("Plan de ejecución (EXPLAIN)", page)
                    self.assertNotIn("MariaDB no devolvió el plan", page)
                    self.assertNotIn("El resumen de la vista difiere", page)

    def test_sale_and_transfer_details_when_present(self):
        for build, endpoint, id_field in [(q.sales, "ventas", "id_venta"),
                                           (q.transfers, "transferencias", "id_transferencia")]:
            with self.subTest(endpoint=endpoint):
                batch = self.db.run(NODES, lambda node, cursor: build(node).read(cursor, 1))
                self.assertEqual(batch.errors, {})
                for node, rows in batch.values.items():
                    if rows:
                        response = self.client.get(f"/{endpoint}/{node.key}/{rows[0][id_field]}")
                        self.assertEqual(response.status_code, 200)
                        self.assertIn("Productos", response.get_data(as_text=True))
