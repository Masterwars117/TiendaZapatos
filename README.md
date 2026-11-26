# TiendaZapatos · Zapatería Distribuida

Sistema universitario de consulta para una cadena de zapaterías con tres nodos MariaDB. La aplicación Flask permite revisar el panel, el inventario, las ventas, las transferencias, los catálogos, las estadísticas y las consultas distribuidas.

La instalación de este README crea un entorno de demostración con datos ficticios, cuentas de lectura y volúmenes propios. Docker ejecuta tanto la base de datos como la aplicación.

## Ejecutar en otra PC

### 1. Inicia Docker Desktop

Usa Docker Desktop con el motor de contenedores Linux. En Linux también puedes usar Docker Engine con el complemento Docker Compose. La primera ejecución necesita Internet para descargar las imágenes y las dependencias. [Instalación de Docker Desktop](https://docs.docker.com/desktop/)

### 2. Clona el repositorio

Una vez publicado el proyecto, abre la terminal en la carpeta donde quieras guardarlo. [Git para Windows](https://gitforwindows.org/)

```powershell
git clone https://github.com/Masterwars117/TiendaZapatos.git
cd TiendaZapatos
```

También puedes descargar el ZIP desde GitHub, extraerlo y abrir una terminal en la carpeta extraída.

### 3. Instala y arranca con un solo comando

Desde la carpeta del proyecto, ejecuta lo siguiente.

```bash
docker compose -f compose.demo.yml up -d --build
```

El comando descarga y construye las imágenes, genera las contraseñas en volúmenes locales, carga los datos de ejemplo en los tres nodos MariaDB y arranca Flask. También configura las réplicas y la vista de inventario global. Python y sus dependencias se instalan dentro de Docker.

Cuando termine, abre el panel en el navegador. Debe mostrar tres sucursales disponibles para consulta, seis productos, 288 pares de inventario y tres ventas de ejemplo. En **Consultas distribuidas**, elige la vista global para ver su consulta SQL y plan de ejecución. [Abrir TiendaZapatos](http://127.0.0.1:8080)

## Verificar, detener y reanudar el demo

Para revisar el estado de los servicios y ejecutar pruebas, usa estos comandos.

```bash
docker compose -f compose.demo.yml ps -a
docker compose -f compose.demo.yml exec web python -m flask --app app verificar-conexion
docker compose -f compose.demo.yml exec -e ZAPATERIA_LIVE_TESTS=1 web python -m unittest discover -s tests -v
```

`credentials` y `bootstrap` aparecen como `Exited (0)` al terminar su trabajo. Los tres nodos deben estar `healthy` y la web debe estar en ejecución.

Para detenerlo y conservar sus datos, ejecuta lo siguiente.

```bash
docker compose -f compose.demo.yml stop
```

Para reanudarlo después, vuelve a iniciar Docker Desktop y ejecuta lo siguiente desde el repositorio.

```bash
docker compose -f compose.demo.yml up -d
```

## Subir el proyecto a GitHub

Para publicar por primera vez en el repositorio vacío [Masterwars117/TiendaZapatos](https://github.com/Masterwars117/TiendaZapatos), abre PowerShell en tu carpeta original del proyecto. El archivo `.gitignore` excluye las credenciales, el entorno virtual y el Compose y volcado SQL de uso local. La instalación compartida usa `compose.demo.yml` y `demo/init.sql`.

### 1. Prepara el primer commit

```powershell
if (-not (Test-Path -LiteralPath .git)) {
    git init -b main
}
git add .
git diff --cached --name-only
```

En la lista deben aparecer `README.md`, `compose.demo.yml`, `demo/`, `web/` y los archivos `.env.example`. Comprueba que tus archivos `.env`, `web/.env`, `docker-compose.yml` y `zapateria_distribuida.sql` estén fuera de la lista.

Si Git pide una identidad para el commit, configura tu nombre y el correo asociado a tu cuenta.

```powershell
git config user.name "Tu nombre"
git config user.email "correo-asociado-a-github"
```

### 2. Comprueba el repositorio de destino

```powershell
if ((git remote) -notcontains "origin") {
    git remote add origin https://github.com/Masterwars117/TiendaZapatos.git
}
git remote get-url origin
```

La dirección debe ser `https://github.com/Masterwars117/TiendaZapatos.git`.

### 3. Crea el commit y envíalo

```powershell
git commit -m "Prepara TiendaZapatos para ejecutar con Docker"
git push -u origin main
```

Autoriza el inicio de sesión en GitHub si Git abre el navegador y comprueba que el sitio muestre el README. Comparte el enlace del repositorio para que otra persona siga la sección **Ejecutar en otra PC**. [Guía de publicación de GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github?platform=windows)

## Cómo funciona la demostración

| Servicio | Función | Puerto dentro de Docker |
| --- | --- | --- |
| Villahermosa | Nodo principal, catálogos y vista global | `3307` |
| Cárdenas | Fragmento local y réplica de catálogos | `3308` |
| Cunduacán | Fragmento local y réplica de catálogos | `3309` |
| Web | Flask con una cuenta de consulta en cada nodo | `5000` |

El inventario, las ventas, los empleados y las transferencias quedan en el nodo que los registra. La vista `inventario_global` reúne las existencias de los tres nodos mediante tablas federadas. Villahermosa replica los cambios de sucursales, proveedores, productos y tallas hacia los otros dos nodos. El navegador entra por el puerto web en la PC anfitriona.

Si ya tienes nodos MariaDB configurados y quieres conectar Flask directamente desde Windows, sigue la [guía de conexión a nodos existentes](web/README.md).

## Si algo falla al arrancar

| Qué ves | Qué revisar |
| --- | --- |
| Docker dice que no puede conectar con el servidor | Abre Docker Desktop, espera a que inicie el motor Linux y ejecuta `docker version`. |
| El puerto `8080` está ocupado | Crea `.env` en la raíz con la línea `DEMO_WEB_PORT=8081` y vuelve a ejecutar `docker compose -f compose.demo.yml up -d --build`. Abre el puerto nuevo en el navegador. |
| `credentials` terminó con un error | Ejecuta `docker compose -f compose.demo.yml logs --tail 80 credentials`. |
| `bootstrap` terminó con un error | Ejecuta `docker compose -f compose.demo.yml logs --tail 80 bootstrap villahermosa cardenas cunduacan`. |
| El navegador muestra un error de conexión | Comprueba `docker compose -f compose.demo.yml ps -a` y `docker compose -f compose.demo.yml logs --tail 80 web`. |
