-- Esquema y datos ficticios para un volumen nuevo del entorno demo.
SET NAMES utf8mb4;
USE zapateria_distribuida;

CREATE TABLE sucursal (
    id_sucursal INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    municipio VARCHAR(100) NOT NULL,
    direccion VARCHAR(200),
    telefono VARCHAR(20)
) ENGINE=InnoDB;

CREATE TABLE proveedor (
    id_proveedor INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    telefono VARCHAR(20),
    correo VARCHAR(100),
    direccion VARCHAR(200)
) ENGINE=InnoDB;

CREATE TABLE producto (
    id_producto INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    modelo VARCHAR(100),
    marca VARCHAR(100),
    categoria VARCHAR(100),
    color VARCHAR(50),
    precio DECIMAL(10,2) NOT NULL,
    id_proveedor INT,
    FOREIGN KEY (id_proveedor) REFERENCES proveedor (id_proveedor)
) ENGINE=InnoDB;

CREATE TABLE talla (
    id_talla INT AUTO_INCREMENT PRIMARY KEY,
    numero_talla DECIMAL(4,1) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE cliente (
    id_cliente INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellidos VARCHAR(100),
    telefono VARCHAR(20),
    correo VARCHAR(100)
) ENGINE=InnoDB;

CREATE TABLE empleado (
    id_empleado INT AUTO_INCREMENT PRIMARY KEY,
    id_sucursal INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellidos VARCHAR(100),
    puesto VARCHAR(100),
    FOREIGN KEY (id_sucursal) REFERENCES sucursal (id_sucursal)
) ENGINE=InnoDB;

CREATE TABLE inventario (
    id_inventario INT AUTO_INCREMENT PRIMARY KEY,
    id_sucursal INT NOT NULL,
    id_producto INT NOT NULL,
    id_talla INT NOT NULL,
    cantidad INT NOT NULL DEFAULT 0,
    fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id_sucursal, id_producto, id_talla),
    FOREIGN KEY (id_sucursal) REFERENCES sucursal (id_sucursal),
    FOREIGN KEY (id_producto) REFERENCES producto (id_producto),
    FOREIGN KEY (id_talla) REFERENCES talla (id_talla)
) ENGINE=InnoDB;

CREATE TABLE venta (
    id_venta INT AUTO_INCREMENT PRIMARY KEY,
    id_sucursal INT NOT NULL,
    id_empleado INT NOT NULL,
    id_cliente INT,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    total DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (id_sucursal) REFERENCES sucursal (id_sucursal),
    FOREIGN KEY (id_empleado) REFERENCES empleado (id_empleado),
    FOREIGN KEY (id_cliente) REFERENCES cliente (id_cliente)
) ENGINE=InnoDB;

CREATE TABLE detalle_venta (
    id_detalle_venta INT AUTO_INCREMENT PRIMARY KEY,
    id_venta INT NOT NULL,
    id_producto INT NOT NULL,
    id_talla INT NOT NULL,
    cantidad INT NOT NULL,
    precio_unitario DECIMAL(10,2) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (id_venta) REFERENCES venta (id_venta),
    FOREIGN KEY (id_producto) REFERENCES producto (id_producto),
    FOREIGN KEY (id_talla) REFERENCES talla (id_talla)
) ENGINE=InnoDB;

CREATE TABLE transferencia (
    id_transferencia INT AUTO_INCREMENT PRIMARY KEY,
    id_sucursal_origen INT NOT NULL,
    id_sucursal_destino INT NOT NULL,
    fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
    estado VARCHAR(30) DEFAULT 'PENDIENTE',
    FOREIGN KEY (id_sucursal_origen) REFERENCES sucursal (id_sucursal),
    FOREIGN KEY (id_sucursal_destino) REFERENCES sucursal (id_sucursal)
) ENGINE=InnoDB;

CREATE TABLE detalle_transferencia (
    id_detalle_transferencia INT AUTO_INCREMENT PRIMARY KEY,
    id_transferencia INT NOT NULL,
    id_producto INT NOT NULL,
    id_talla INT NOT NULL,
    cantidad INT NOT NULL,
    FOREIGN KEY (id_transferencia) REFERENCES transferencia (id_transferencia),
    FOREIGN KEY (id_producto) REFERENCES producto (id_producto),
    FOREIGN KEY (id_talla) REFERENCES talla (id_talla)
) ENGINE=InnoDB;

START TRANSACTION;

-- Los catálogos tienen la misma base inicial en los tres nodos.
INSERT INTO sucursal (id_sucursal, nombre, municipio) VALUES
    (1, 'Villahermosa', 'Centro'),
    (2, 'Cárdenas', 'Cárdenas'),
    (3, 'Cunduacán', 'Cunduacán');

INSERT INTO proveedor (id_proveedor, nombre) VALUES
    (1, 'Calzado de Muestra'),
    (2, 'Muestrario del Sureste');

INSERT INTO producto (id_producto, nombre, modelo, marca, categoria, color, precio, id_proveedor) VALUES
    (1, 'Tenis urbanos', 'URB-101', 'Marca Demo', 'Casual', 'Blanco', 899.90, 1),
    (2, 'Botas de senderismo', 'BOT-202', 'Marca Demo', 'Exterior', 'Marrón', 1299.50, 1),
    (3, 'Tenis ligeros', 'TEN-303', 'Marca Demo', 'Deportivo', 'Azul', 749.90, 2),
    (4, 'Zapatos de vestir', 'VES-404', 'Marca Demo', 'Formal', 'Negro', 1099.00, 2),
    (5, 'Sandalias', 'SAN-505', 'Marca Demo', 'Casual', 'Arena', 429.00, 1),
    (6, 'Mocasines', 'MOC-606', 'Marca Demo', 'Casual', 'Gris', 849.00, 2);

INSERT INTO talla (id_talla, numero_talla) VALUES
    (1, 24), (2, 25), (3, 26), (4, 27), (5, 28), (6, 29);

INSERT INTO cliente (id_cliente, nombre) VALUES
    (1, 'Cliente de muestra 1'),
    (2, 'Cliente de muestra 2'),
    (3, 'Cliente de muestra 3');

-- Cada nodo conserva su fragmento de datos operativos.
SET @sucursal_demo = @@server_id;

INSERT INTO empleado (id_empleado, id_sucursal, nombre, apellidos, puesto)
SELECT id_sucursal, id_sucursal, 'Equipo de muestra', nombre, 'Ventas'
FROM sucursal WHERE id_sucursal = @sucursal_demo;

INSERT INTO inventario (id_inventario, id_sucursal, id_producto, id_talla, cantidad)
SELECT @sucursal_demo * 100 + id_producto, @sucursal_demo, id_producto, id_producto,
       15 + id_producto * 2 - @sucursal_demo * 3
FROM producto;

SET @pares_venta = 4 - @sucursal_demo;

INSERT INTO venta (id_venta, id_sucursal, id_empleado, id_cliente, fecha, total)
SELECT @sucursal_demo, @sucursal_demo, @sucursal_demo, @sucursal_demo,
       DATE_ADD('2026-01-10 12:00:00', INTERVAL @sucursal_demo DAY), precio * @pares_venta
FROM producto WHERE id_producto = @sucursal_demo;

INSERT INTO detalle_venta (id_detalle_venta, id_venta, id_producto, id_talla,
                          cantidad, precio_unitario, subtotal)
SELECT @sucursal_demo, @sucursal_demo, id_producto, id_producto,
       @pares_venta, precio, precio * @pares_venta
FROM producto WHERE id_producto = @sucursal_demo;

INSERT INTO transferencia (id_transferencia, id_sucursal_origen, id_sucursal_destino, fecha, estado)
VALUES (@sucursal_demo, @sucursal_demo, MOD(@sucursal_demo, 3) + 1,
        DATE_ADD('2026-01-12 10:00:00', INTERVAL @sucursal_demo DAY),
        CASE @sucursal_demo WHEN 1 THEN 'RECIBIDA' WHEN 2 THEN 'EN TRÁNSITO' ELSE 'PENDIENTE' END);

INSERT INTO detalle_transferencia (id_detalle_transferencia, id_transferencia, id_producto, id_talla, cantidad)
VALUES (@sucursal_demo, @sucursal_demo, @sucursal_demo, @sucursal_demo, 2);

COMMIT;
