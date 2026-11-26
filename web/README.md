# Zapatería Distribuida

Esta guía conecta Flask con una instalación existente de los tres nodos. Para preparar un clon desde cero con Docker y datos de muestra, usa el [README del proyecto](../README.md).

Aplicación universitaria de consulta para el Sistema de Base de Datos Distribuida para la Gestión de Ventas e Inventario de una Cadena de Zapaterías. Flask se ejecuta en Windows y lee las instancias de MariaDB 11.4 existentes. Bootstrap 5.3.8 y Chart.js 4.5.1 se sirven desde archivos locales.

## Instalación en Windows

Desde la raíz del proyecto, abre PowerShell. Inicia Docker Desktop y reutiliza los tres contenedores existentes.

```powershell
docker compose start
docker compose ps
Set-Location web
py -3.13 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

Usa Python 3.13 si está disponible. El entorno virtual se puede ejecutar directamente desde PowerShell sin activar scripts. Completa `.env` con las credenciales de lectura de cada nodo. Conserva el archivo fuera del control de versiones. Si la contraseña contiene caracteres especiales, enciérrala entre comillas dobles y escapa las comillas dobles y las barras invertidas con una barra invertida.

| Nodo | Host y puerto desde Windows | Cuenta de consulta |
| --- | --- | --- |
| Villahermosa | `127.0.0.1:3307` | `zapateria_lectura`, a crear manualmente |
| Cárdenas | `127.0.0.1:3308` | `consultas`, disponible en la instalación revisada |
| Cunduacán | `127.0.0.1:3309` | `consultas`, disponible en la instalación revisada |

## Usuarios de solo lectura

Recupera las contraseñas de `consultas` desde el lugar donde las guardaste al configurar la replicación o las tablas federadas. Cada nodo admite una contraseña distinta en `.env`. Para Villahermosa, abre una sesión administrativa desde la raíz del proyecto.

```powershell
docker compose exec villahermosa mariadb -u root -p
```

Si la cuenta falta, elige una contraseña y ejecuta manualmente el siguiente SQL. Usa la cuenta administrativa únicamente para gestionar permisos. `%` permite que el servidor acepte la cuenta a través de la red Docker. Los puertos publicados en el Compose original están vinculados al loopback de Windows.

```sql
CREATE USER 'zapateria_lectura'@'%' IDENTIFIED BY 'SUSTITUYE_ESTA_CONTRASEÑA';
GRANT SELECT ON zapateria_distribuida.* TO 'zapateria_lectura'@'%';
GRANT SHOW VIEW ON zapateria_distribuida.inventario_global TO 'zapateria_lectura'@'%';
```

Si necesitas una cuenta separada en Cárdenas o Cunduacán, entra al servicio correspondiente con `docker compose exec cardenas mariadb -u root -p` o `docker compose exec cunduacan mariadb -u root -p`. Aplica `CREATE USER` y `GRANT SELECT` y actualiza los nombres de usuario en `.env`. La vista existe en Villahermosa. Los permisos se comprueban por nodo. [Documentación de GRANT en MariaDB](https://mariadb.com/docs/server/reference/sql-statements/account-management-sql-statements/grant)

## Ejecutar

Desde `web`, comprueba los tres accesos y arranca Flask.

```powershell
& .\.venv\Scripts\python.exe -m flask --app app verificar-conexion
& .\.venv\Scripts\python.exe app.py
```

Abre [el panel local](http://127.0.0.1:5000). Después de guardar cambios en el archivo de configuración, usa **Actualizar** en el panel para comprobarlos. Detén Flask con **Ctrl+C**. Si un nodo falla, revisa su mensaje en el panel y su estado con `docker compose ps` desde la raíz.

## Integración con MariaDB

| Datos | Integración |
| --- | --- |
| Inventario | Lee `inventario` en el nodo propietario, une por `id_producto` y `id_talla` y presenta la sucursal indicada por `id_sucursal`. |
| Ventas | Lee `venta` y `detalle_venta` en el nodo que registró la venta. Los ingresos provienen de `venta.total` y el ranking suma `detalle_venta.cantidad`. |
| Transferencias | Lee `transferencia` y `detalle_transferencia` en el nodo de origen. La transferencia histórica presente en los tres nodos se cuenta una vez. El identificador se interpreta junto con su nodo. |
| Productos, tallas, proveedores y sucursales | Lee una sola copia por consulta. Prefiere Villahermosa y muestra el nombre de la réplica si usa un respaldo. Una réplica puede llevar retraso. |
| Clientes | Consulta la copia de Villahermosa. Se verificaron copias iguales en las tres sucursales, y los filtros de replicación de Compose no incluyen `cliente`. El detalle de venta usa el cliente referenciado dentro del nodo de esa venta. |
| Empleados | Lee el fragmento de cada nodo filtrado por su `id_sucursal`. |
| Vista global | Villahermosa expone `inventario_global`, que combina `inventario`, `inventario_cardenas` e `inventario_cunduacan` mediante `UNION ALL`. El módulo académico contrasta sus referencias y pares con lecturas directas de los tres fragmentos. |

El YAML y el volcado SQL originales se conservan. La vista y sus tablas federadas se verificaron en la instalación en ejecución. Una instalación que solo importe el volcado necesitará recuperar por separado los objetos distribuidos de su puesta en marcha.

Una interrupción se identifica por nodo. Las listas pueden mostrar las filas disponibles con un aviso de alcance parcial. Los totales operativos globales y los rankings globales requieren todos los fragmentos correspondientes. En las gráficas, un nodo ausente se indica como **Sin datos**.

Las lecturas se ejecutan en paralelo cuando intervienen varios nodos, con transacciones de solo lectura independientes, tiempos límite de conexión y E/S y verificación de `server_id`. El tiempo por nodo del módulo académico incluye la ejecución y la recepción de filas del SELECT. El tiempo total incluye conexiones, verificaciones y EXPLAIN. Los resultados entre nodos se observan durante la consulta y pueden reflejar cambios concurrentes. [Transacciones de MariaDB](https://mariadb.com/docs/server/reference/sql-statements/transactions/start-transaction) · [EXPLAIN en MariaDB](https://mariadb.com/docs/server/reference/sql-statements/administrative-sql-statements/analyze-and-explain-statements/explain)

## Pruebas

Desde `web`, ejecuta las pruebas de filtros, paginación, consultas académicas y disponibilidad parcial.

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Con los tres nodos accesibles y `.env` configurado, activa las pruebas contra MariaDB. Comprueban conexiones, páginas, catálogos, detalles disponibles y la consulta académica de la vista global. Las pruebas realizan lecturas.

```powershell
$env:ZAPATERIA_LIVE_TESTS = '1'
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:ZAPATERIA_LIVE_TESTS
```

Para observar la degradación sin interrumpir MariaDB, inicia Flask con una configuración de prueba que deje sin contraseña un nodo. El panel mostrará la incidencia y ocultará los totales globales afectados.

## Archivos principales

- `app.py` contiene las rutas, la validación de filtros y el comando de verificación.
- `database.py` gestiona configuración, conexiones, tiempos límite y errores.
- `queries.py` define las consultas parametrizadas y los catálogos.
- `reports.py` combina resultados, conserva su origen y ejecuta las demostraciones.
- `templates/` y `static/` contienen la interfaz y sus dependencias.
