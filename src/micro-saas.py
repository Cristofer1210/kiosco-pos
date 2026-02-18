#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KIOSCO POS v5.0 - Sistema Profesional de Punto de Venta
Arquitectura Escalable - Clean Architecture

Características:
✅ Gestión completa de categorías (CRUD)
✅ SKU automático basado en categoría
✅ Búsqueda inteligente por palabras clave
✅ Interfaz optimizada para kioscos
✅ Reportes y cierre de caja
"""

import sqlite3
import csv
import os
from datetime import datetime, date
from typing import List, Tuple, Optional, Dict, Any
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import re
from dataclasses import dataclass
from contextlib import contextmanager

# ============================================================================
# MODELOS DE DOMINIO (Capas de abstracción)
# ============================================================================

@dataclass
class Categoria:
    """Modelo de categoría de productos."""
    id: Optional[int]
    nombre: str
    prefijo: str
    descripcion: str
    activo: bool = True
    creado_en: Optional[str] = None


@dataclass
class Producto:
    """Modelo de producto - Versión SIMPLE (usando categoria como string)."""
    id: Optional[int]
    sku: str
    nombre: str
    descripcion: str
    cantidad: int
    precio: float
    stock_minimo: int
    categoria: str  # ← Usamos string, no ID
    creado_en: Optional[str] = None
    actualizado_en: Optional[str] = None

    @property
    def tiene_stock_bajo(self) -> bool:
        return self.cantidad <= self.stock_minimo


@dataclass
class ItemCarrito:
    """Item en carrito de compras."""
    producto_id: int
    sku: str
    nombre: str
    cantidad: int
    precio_unitario: float
    subtotal: float


@dataclass
class MovimientoCaja:
    """Movimiento de caja."""
    id: Optional[int]
    fecha: str
    tipo: str
    monto: float
    concepto: str
    usuario: str


# ============================================================================
# REPOSITORIOS (Capa de acceso a datos)
# ============================================================================

class ConexionBaseDatos:
    """Context manager para conexiones de base de datos."""
    
    def __init__(self, db_name: str = "kiosco_pos.db"):
        self.db_name = db_name
        self.connection = None
    
    def __enter__(self):
        self.connection = sqlite3.connect(self.db_name)
        self.connection.row_factory = sqlite3.Row
        return self.connection
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.connection:
            if exc_type:
                self.connection.rollback()
            else:
                self.connection.commit()
            self.connection.close()


class RepositorioCategoria:
    """Repositorio para categorías."""
    
    def __init__(self, db_path: str = "kiosco_pos.db"):
        self.db_path = db_path
    
    @contextmanager
    def _conexion(self):
        with ConexionBaseDatos(self.db_path) as conn:
            yield conn
    
    def crear_tabla(self):
        """Crea tabla de categorías."""
        with self._conexion() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS categorias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre TEXT UNIQUE NOT NULL,
                    prefijo TEXT UNIQUE NOT NULL,
                    descripcion TEXT,
                    activo BOOLEAN DEFAULT 1,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def obtener_todas(self, solo_activas: bool = True) -> List[Categoria]:
        """Obtiene todas las categorías."""
        with self._conexion() as conn:
            query = "SELECT * FROM categorias"
            if solo_activas:
                query += " WHERE activo = 1"
            query += " ORDER BY nombre"
            
            cursor = conn.execute(query)
            return [self._fila_a_categoria(row) for row in cursor.fetchall()]
    
    def obtener_por_id(self, categoria_id: int) -> Optional[Categoria]:
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT * FROM categorias WHERE id = ?",
                (categoria_id,)
            )
            row = cursor.fetchone()
            return self._fila_a_categoria(row) if row else None
    
    def obtener_por_prefijo(self, prefijo: str) -> Optional[Categoria]:
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT * FROM categorias WHERE prefijo = ?",
                (prefijo.upper(),)
            )
            row = cursor.fetchone()
            return self._fila_a_categoria(row) if row else None
    
    def agregar(self, categoria: Categoria) -> int:
        with self._conexion() as conn:
            cursor = conn.execute("""
                INSERT INTO categorias (nombre, prefijo, descripcion)
                VALUES (?, ?, ?)
            """, (
                categoria.nombre.upper(),
                categoria.prefijo.upper(),
                categoria.descripcion
            ))
            return cursor.lastrowid
    
    def actualizar(self, categoria: Categoria) -> bool:
        with self._conexion() as conn:
            cursor = conn.execute("""
                UPDATE categorias 
                SET nombre = ?, prefijo = ?, descripcion = ?
                WHERE id = ?
            """, (
                categoria.nombre.upper(),
                categoria.prefijo.upper(),
                categoria.descripcion,
                categoria.id
            ))
            return cursor.rowcount > 0
    
    def eliminar(self, categoria_id: int) -> bool:
        """Eliminación lógica (desactiva)."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                UPDATE categorias 
                SET activo = 0 
                WHERE id = ?
            """, (categoria_id,))
            return cursor.rowcount > 0
    
    def _fila_a_categoria(self, row) -> Categoria:
        return Categoria(
            id=row['id'],
            nombre=row['nombre'],
            prefijo=row['prefijo'],
            descripcion=row['descripcion'],
            activo=bool(row['activo']),
            creado_en=row['creado_en']
        )


class RepositorioProducto:
    """Repositorio para productos - Versión SIMPLE."""
    
    def __init__(self, db_path: str = "kiosco_pos.db"):
        self.db_path = db_path
    
    @contextmanager
    def _conexion(self):
        with ConexionBaseDatos(self.db_path) as conn:
            yield conn
    
    def crear_tabla(self):
        """Crea la tabla de productos."""
        with self._conexion() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS productos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sku TEXT UNIQUE NOT NULL,
                    nombre TEXT NOT NULL,
                    descripcion TEXT,
                    cantidad INTEGER DEFAULT 0,
                    precio REAL DEFAULT 0.0,
                    stock_minimo INTEGER DEFAULT 5,
                    categoria TEXT,
                    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
    
    def agregar(self, producto: Producto) -> int:
        """Agrega un nuevo producto."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                INSERT INTO productos 
                (sku, nombre, descripcion, cantidad, precio, stock_minimo, categoria)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                producto.sku.upper(),
                producto.nombre,
                producto.descripcion,
                producto.cantidad,
                producto.precio,
                producto.stock_minimo,
                producto.categoria
            ))
            return cursor.lastrowid
    
    def obtener_todos(self) -> List[Producto]:
        """Obtiene todos los productos."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                SELECT * FROM productos 
                ORDER BY nombre
            """)
            return [self._fila_a_producto(row) for row in cursor.fetchall()]
    
    def buscar_para_venta(self, termino: str) -> List[Producto]:
        """Búsqueda optimizada para POS."""
        with self._conexion() as conn:
            patron = f"%{termino}%"
            try:
                cursor = conn.execute("""
                    SELECT id, sku, nombre, precio, cantidad, categoria
                    FROM productos 
                    WHERE LOWER(nombre) LIKE LOWER(?)
                       OR LOWER(sku) LIKE LOWER(?)
                       OR LOWER(categoria) LIKE LOWER(?)
                    ORDER BY 
                        CASE 
                            WHEN LOWER(sku) = LOWER(?) THEN 0
                            WHEN LOWER(nombre) LIKE LOWER(?) THEN 1
                            ELSE 2
                        END,
                        nombre
                    LIMIT 10
                """, (patron, patron, patron, termino.lower(), patron))
            except sqlite3.OperationalError:
                # Si no existe columna categoria, buscar solo por nombre y sku
                cursor = conn.execute("""
                    SELECT id, sku, nombre, precio, cantidad
                    FROM productos 
                    WHERE LOWER(nombre) LIKE LOWER(?)
                       OR LOWER(sku) LIKE LOWER(?)
                    ORDER BY 
                        CASE 
                            WHEN LOWER(sku) = LOWER(?) THEN 0
                            WHEN LOWER(nombre) LIKE LOWER(?) THEN 1
                            ELSE 2
                        END,
                        nombre
                    LIMIT 10
                """, (patron, patron, termino.lower(), patron))
            
            productos = []
            for row in cursor.fetchall():
                categoria = row['categoria'] if 'categoria' in row.keys() else ''
                productos.append(Producto(
                    id=row['id'],
                    sku=row['sku'],
                    nombre=row['nombre'],
                    descripcion="",
                    cantidad=row['cantidad'],
                    precio=row['precio'],
                    stock_minimo=5,
                    categoria=categoria
                ))
            return productos
    
    def obtener_por_id(self, producto_id: int) -> Optional[Producto]:
        """Obtiene producto por ID."""
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT * FROM productos WHERE id = ?",
                (producto_id,)
            )
            row = cursor.fetchone()
            return self._fila_a_producto(row) if row else None
    
    def obtener_por_sku(self, sku: str) -> Optional[Producto]:
        """Obtiene producto por SKU."""
        with self._conexion() as conn:
            cursor = conn.execute(
                "SELECT * FROM productos WHERE sku = ?",
                (sku.upper(),)
            )
            row = cursor.fetchone()
            return self._fila_a_producto(row) if row else None
    
    def obtener_siguiente_numero_sku(self, prefijo: str) -> int:
        """Obtiene el próximo número disponible para SKU."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) as total 
                FROM productos 
                WHERE sku LIKE ?
            """, (f"{prefijo}%",))
            row = cursor.fetchone()
            return (row['total'] or 0) + 1
    
    def actualizar_stock(self, producto_id: int, cantidad_vendida: int) -> bool:
        """Actualiza el stock después de una venta."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                UPDATE productos 
                SET cantidad = cantidad - ?, 
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id=? AND cantidad >= ?
            """, (cantidad_vendida, producto_id, cantidad_vendida))
            return cursor.rowcount > 0
    
    def actualizar(self, producto: Producto) -> bool:
        """Actualiza un producto existente."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                UPDATE productos 
                SET nombre = ?, descripcion = ?, cantidad = ?, 
                    precio = ?, stock_minimo = ?, categoria = ?,
                    actualizado_en = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (
                producto.nombre,
                producto.descripcion,
                producto.cantidad,
                producto.precio,
                producto.stock_minimo,
                producto.categoria,
                producto.id
            ))
            return cursor.rowcount > 0
    
    def eliminar(self, producto_id: int) -> bool:
        """Elimina un producto."""
        with self._conexion() as conn:
            cursor = conn.execute(
                "DELETE FROM productos WHERE id = ?",
                (producto_id,)
            )
            return cursor.rowcount > 0
    
    def _fila_a_producto(self, row) -> Producto:
        """Convierte una fila de la BD a objeto Producto."""
        return Producto(
            id=row['id'],
            sku=row['sku'],
            nombre=row['nombre'],
            descripcion=row['descripcion'] if 'descripcion' in row.keys() else '',
            cantidad=row['cantidad'],
            precio=row['precio'],
            stock_minimo=row['stock_minimo'] if 'stock_minimo' in row.keys() else 5,
            categoria=row['categoria'] if 'categoria' in row.keys() else '',
            creado_en=row['creado_en'] if 'creado_en' in row.keys() else None,
            actualizado_en=row['actualizado_en'] if 'actualizado_en' in row.keys() else None
        )


class RepositorioVenta:
    """Repositorio para ventas."""
    
    def __init__(self, db_path: str = "kiosco_pos.db"):
        self.db_path = db_path
    
    @contextmanager
    def _conexion(self):
        with ConexionBaseDatos(self.db_path) as conn:
            yield conn
    
    def crear_tablas(self):
        """Crea las tablas de ventas."""
        with self._conexion() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ventas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total REAL NOT NULL,
                    metodo_pago TEXT NOT NULL,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    usuario TEXT DEFAULT 'CAJERO'
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detalles_venta (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    venta_id INTEGER NOT NULL,
                    producto_id INTEGER NOT NULL,
                    sku TEXT NOT NULL,
                    nombre_producto TEXT NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unitario REAL NOT NULL,
                    subtotal REAL NOT NULL,
                    FOREIGN KEY (venta_id) REFERENCES ventas(id),
                    FOREIGN KEY (producto_id) REFERENCES productos(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS movimientos_caja (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tipo TEXT NOT NULL,
                    monto REAL NOT NULL,
                    concepto TEXT NOT NULL,
                    usuario TEXT DEFAULT 'CAJERO',
                    CHECK (tipo IN ('RETIRO', 'INGRESO'))
                )
            """)
    
    def registrar_venta(self, items: List[ItemCarrito], total: float, metodo_pago: str) -> int:
        """Registra una venta completa."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                INSERT INTO ventas (total, metodo_pago)
                VALUES (?, ?)
            """, (total, metodo_pago))
            
            venta_id = cursor.lastrowid
            
            for item in items:
                conn.execute("""
                    INSERT INTO detalles_venta 
                    (venta_id, producto_id, sku, nombre_producto, cantidad, precio_unitario, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    venta_id, item.producto_id, item.sku, item.nombre,
                    item.cantidad, item.precio_unitario, item.subtotal
                ))
            
            return venta_id
    
    def obtener_ventas_dia(self) -> List[Dict]:
        """Obtiene ventas del día."""
        with self._conexion() as conn:
            hoy = date.today().strftime('%Y-%m-%d')
            cursor = conn.execute("""
                SELECT * FROM ventas 
                WHERE DATE(fecha) = ?
                ORDER BY fecha DESC
            """, (hoy,))
            return [dict(row) for row in cursor.fetchall()]
    
    def registrar_retiro(self, monto: float, concepto: str) -> int:
        """Registra un retiro de efectivo."""
        with self._conexion() as conn:
            cursor = conn.execute("""
                INSERT INTO movimientos_caja (tipo, monto, concepto)
                VALUES ('RETIRO', ?, ?)
            """, (monto, concepto))
            return cursor.lastrowid
    
    def obtener_retiros_dia(self) -> List[Dict]:
        """Obtiene retiros del día."""
        with self._conexion() as conn:
            hoy = date.today().strftime('%Y-%m-%d')
            cursor = conn.execute("""
                SELECT * FROM movimientos_caja 
                WHERE DATE(fecha) = ? AND tipo = 'RETIRO'
                ORDER BY fecha DESC
            """, (hoy,))
            return [dict(row) for row in cursor.fetchall()]
    
    def total_retiros_dia(self) -> float:
        """Calcula total de retiros del día."""
        with self._conexion() as conn:
            hoy = date.today().strftime('%Y-%m-%d')
            cursor = conn.execute("""
                SELECT COALESCE(SUM(monto), 0) as total 
                FROM movimientos_caja 
                WHERE DATE(fecha) = ? AND tipo = 'RETIRO'
            """, (hoy,))
            row = cursor.fetchone()
            return row['total']


# ============================================================================
# SERVICIOS (Capa de lógica de negocio)
# ============================================================================

class ServicioCategoria:
    """Servicio para gestión de categorías."""
    
    def __init__(self):
        self.repo = RepositorioCategoria()
        self.repo.crear_tabla()
    
    def obtener_todas(self) -> List[Categoria]:
        return self.repo.obtener_todas()
    
    def obtener_por_id(self, categoria_id: int) -> Optional[Categoria]:
        return self.repo.obtener_por_id(categoria_id)
    
    def validar_prefijo(self, prefijo: str) -> Tuple[bool, str]:
        """Valida que el prefijo sea válido y único."""
        if not prefijo:
            return False, "El prefijo es obligatorio"
        
        prefijo = prefijo.upper()
        if len(prefijo) > 5:
            return False, "El prefijo no puede tener más de 5 caracteres"
        
        if not prefijo.isalpha():
            return False, "El prefijo solo puede contener letras"
        
        existente = self.repo.obtener_por_prefijo(prefijo)
        if existente:
            return False, f"Ya existe una categoría con prefijo '{prefijo}'"
        
        return True, ""
    
    def agregar(self, categoria: Categoria) -> Tuple[bool, str]:
        """Agrega una nueva categoría."""
        # Validar nombre único
        existentes = self.repo.obtener_todas(solo_activas=False)
        for c in existentes:
            if c.nombre.upper() == categoria.nombre.upper():
                return False, f"Ya existe una categoría '{categoria.nombre}'"
        
        # Validar prefijo
        valido, msg = self.validar_prefijo(categoria.prefijo)
        if not valido:
            return False, msg
        
        try:
            categoria_id = self.repo.agregar(categoria)
            return True, f"Categoría '{categoria.nombre}' creada"
        except Exception as e:
            return False, f"Error: {e}"
    
    def actualizar(self, categoria: Categoria) -> Tuple[bool, str]:
        """Actualiza una categoría."""
        try:
            if self.repo.actualizar(categoria):
                return True, "Categoría actualizada"
            return False, "No se pudo actualizar"
        except Exception as e:
            return False, f"Error: {e}"
    
    def eliminar(self, categoria_id: int) -> Tuple[bool, str]:
        """Elimina una categoría."""
        try:
            if self.repo.eliminar(categoria_id):
                return True, "Categoría eliminada"
            return False, "No se pudo eliminar"
        except Exception as e:
            return False, f"Error: {e}"


class ServicioProducto:
    """Servicio para gestión de productos - Versión SIMPLE."""
    
    def __init__(self):
        self.repo = RepositorioProducto()
        self.repo.crear_tabla()
        self.servicio_categoria = ServicioCategoria()
    
    def obtener_todos(self) -> List[Producto]:
        """Obtiene todos los productos."""
        return self.repo.obtener_todos()
    
    def buscar(self, termino: str) -> List[Producto]:
        """Busca productos por término."""
        if len(termino) < 2:
            return []
        return self.repo.buscar_para_venta(termino)
    
    def generar_sku_sugerido(self, categoria_id: int) -> str:
        """Genera un SKU sugerido basado en la categoría."""
        categoria = self.servicio_categoria.obtener_por_id(categoria_id)
        if not categoria:
            return ""
        
        numero = self.repo.obtener_siguiente_numero_sku(categoria.prefijo)
        return f"{categoria.prefijo}{numero:03d}"
    
    def agregar(self, producto: Producto) -> Tuple[bool, str]:
        """Agrega un nuevo producto."""
        # Validar SKU único
        existente = self.repo.obtener_por_sku(producto.sku)
        if existente:
            return False, f"Ya existe un producto con SKU '{producto.sku}'"
        
        # Validar campos
        if not producto.nombre:
            return False, "El nombre es obligatorio"
        
        if producto.precio <= 0:
            return False, "El precio debe ser mayor a cero"
        
        if producto.cantidad < 0:
            return False, "La cantidad no puede ser negativa"
        
        try:
            producto_id = self.repo.agregar(producto)
            return True, f"Producto '{producto.nombre}' agregado"
        except Exception as e:
            return False, f"Error: {e}"
    
    def actualizar(self, producto: Producto) -> Tuple[bool, str]:
        """Actualiza un producto existente."""
        try:
            if self.repo.actualizar(producto):
                return True, "Producto actualizado"
            return False, "No se pudo actualizar"
        except Exception as e:
            return False, f"Error: {e}"
    
    def eliminar(self, producto_id: int) -> Tuple[bool, str]:
        """Elimina un producto."""
        try:
            if self.repo.eliminar(producto_id):
                return True, "Producto eliminado"
            return False, "No se pudo eliminar"
        except Exception as e:
            return False, f"Error: {e}"
    
    def actualizar_stock(self, producto_id: int, cantidad: int) -> bool:
        """Actualiza el stock de un producto."""
        return self.repo.actualizar_stock(producto_id, cantidad)
    
    def contar_por_categoria(self, categoria_nombre):
        """Esto permite contar cuantos productos pertenecen a una categoria"""
        try:
            todos = self.obtener_todos()
            return sum(1 for p in todos if p.categoria == categoria_nombre)
        except:
            return 0


class ServicioVenta:
    """Servicio para ventas y caja."""
    
    def __init__(self):
        self.repo = RepositorioVenta()
        self.repo.crear_tablas()
    
    def procesar_venta(self, items: List[ItemCarrito], metodo_pago: str) -> Tuple[bool, str, Optional[int]]:
        """Procesa una venta."""
        if not items:
            return False, "Carrito vacío", None
        
        total = sum(item.subtotal for item in items)
        
        try:
            venta_id = self.repo.registrar_venta(items, total, metodo_pago)
            return True, f"Venta #{venta_id} completada", venta_id
        except Exception as e:
            return False, f"Error: {e}", None
    
    def obtener_ventas_dia(self) -> List[Dict]:
        """Obtiene ventas del día."""
        return self.repo.obtener_ventas_dia()
    
    def registrar_retiro(self, monto: float, concepto: str, disponible: float) -> Tuple[bool, str]:
        """Registra un retiro de efectivo."""
        if monto <= 0:
            return False, "El monto debe ser positivo"
        
        if monto > disponible:
            return False, f"Fondos insuficientes. Disponible: ${disponible:.2f}"
        
        try:
            self.repo.registrar_retiro(monto, concepto)
            return True, f"Retiro de ${monto:.2f} registrado"
        except Exception as e:
            return False, f"Error: {e}"
    
    def obtener_retiros_dia(self) -> List[Dict]:
        """Obtiene retiros del día."""
        return self.repo.obtener_retiros_dia()
    
    def total_retiros_dia(self) -> float:
        """Total de retiros del día."""
        return self.repo.total_retiros_dia()


class ServicioPOS:
    """Servicio principal que coordina todo."""
    
    def __init__(self):
        self.repo_producto = RepositorioProducto()
        self.repo_venta = RepositorioVenta()
        self._inicializar_base_datos()
        self._inicializar_datos_ejemplo()
    
    def _inicializar_base_datos(self):
        """Inicializa las tablas."""
        self.repo_producto.crear_tabla()
        self.repo_venta.crear_tablas()
    
    def _inicializar_datos_ejemplo(self):
        """Crea datos de ejemplo si la BD está vacía."""
        if not self.repo_producto.obtener_todos():
            productos = [
                Producto(None, 'BEB001', 'Coca-Cola 600ml', 'Gaseosa', 50, 25.00, 10, 'Bebidas'),
                Producto(None, 'BEB002', 'Sprite 600ml', 'Gaseosa', 40, 25.00, 8, 'Bebidas'),
                Producto(None, 'BEB003', 'Agua 500ml', 'Agua mineral', 100, 15.00, 20, 'Bebidas'),
                Producto(None, 'SNA001', 'Lays 60g', 'Papas fritas', 75, 20.00, 15, 'Snacks'),
                Producto(None, 'SNA002', 'Doritos 70g', 'Nachos', 80, 20.00, 15, 'Snacks'),
                Producto(None, 'GOL001', 'Chocolate 50g', 'Chocolate con leche', 100, 30.00, 20, 'Golosinas'),
            ]
            for p in productos:
                self.repo_producto.agregar(p)
    
    def obtener_todos_productos(self) -> List[Producto]:
        """Obtiene todos los productos."""
        return self.repo_producto.obtener_todos()
    
    def buscar_productos(self, termino: str) -> List[Producto]:
        """Busca productos para la venta."""
        if len(termino) < 2:
            return []
        return self.repo_producto.buscar_para_venta(termino)
    
    def procesar_venta(self, items: List[ItemCarrito], metodo_pago: str) -> Tuple[bool, str, Optional[int]]:
        """Procesa una venta completa."""
        if not items:
            return False, "Carrito vacío", None
        
        for item in items:
            producto = self.repo_producto.obtener_por_id(item.producto_id)
            if not producto or producto.cantidad < item.cantidad:
                return False, f"Stock insuficiente para {item.nombre}", None
        
        total = sum(item.subtotal for item in items)
        
        try:
            venta_id = self.repo_venta.registrar_venta(items, total, metodo_pago)
            
            for item in items:
                self.repo_producto.actualizar_stock(item.producto_id, item.cantidad)
            
            return True, f"Venta #{venta_id} completada", venta_id
        except Exception as e:
            return False, f"Error: {e}", None
    
    def obtener_ventas_dia(self) -> List[Dict]:
        """Obtiene ventas del día."""
        return self.repo_venta.obtener_ventas_dia()
    
    def obtener_retiros_dia(self) -> List[Dict]:
        """Obtiene retiros del día."""
        return self.repo_venta.obtener_retiros_dia()
    
    def total_retiros_dia(self) -> float:
        """Total de retiros del día."""
        return self.repo_venta.total_retiros_dia()
    
    def efectivo_disponible(self) -> float:
        """Calcula el efectivo disponible en caja."""
        ventas = self.obtener_ventas_dia()
        total_ventas = sum(v['total'] for v in ventas) if ventas else 0
        retiros = self.total_retiros_dia()
        return total_ventas - retiros
    
    def registrar_retiro(self, monto: float, concepto: str) -> Tuple[bool, str]:
        """Registra un retiro de efectivo."""
        if monto <= 0:
            return False, "El monto debe ser positivo"
        
        disponible = self.efectivo_disponible()
        if monto > disponible:
            return False, f"Fondos insuficientes. Disponible: ${disponible:.2f}"
        
        try:
            self.repo_venta.registrar_retiro(monto, concepto)
            return True, f"Retiro de ${monto:.2f} registrado"
        except Exception as e:
            return False, f"Error: {e}"


# ============================================================================
# INTERFAZ DE USUARIO - COMPONENTES REUTILIZABLES
# ============================================================================

class DialogoBase(tk.Toplevel):
    """Clase base para diálogos con tamaño óptimo."""
    
    def __init__(self, parent, titulo, ancho=500, alto=400):
        super().__init__(parent)
        self.title(titulo)
        self.geometry(f"{ancho}x{alto}")
        self.minsize(ancho, alto)
        self.transient(parent)
        self.grab_set()
        self.centrar()
    
    def centrar(self):
        """Centra la ventana en la pantalla."""
        self.update_idletasks()
        x = self.master.winfo_rootx() + (self.master.winfo_width() // 2) - (self.winfo_width() // 2)
        y = self.master.winfo_rooty() + (self.master.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
    
    def crear_botones(self, parent, texto_aceptar="Aceptar", comando_aceptar=None):
        """Crea botones estándar."""
        btn_frame = tk.Frame(parent)
        btn_frame.pack(pady=20)
        
        tk.Button(
            btn_frame,
            text=texto_aceptar,
            font=('Helvetica', 11, 'bold'),
            bg='#27ae60',
            fg='white',
            command=comando_aceptar or self.destroy,
            width=15,
            height=2
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Button(
            btn_frame,
            text="Cancelar",
            font=('Helvetica', 11),
            bg='#e74c3c',
            fg='white',
            command=self.destroy,
            width=15,
            height=2
        ).pack(side=tk.LEFT, padx=10)


# ============================================================================
# PESTAÑA DE CATEGORÍAS
# ============================================================================

class PestañaCategorias:
    """Pestaña para gestión de categorías."""
    
    def __init__(self, parent, servicio_categoria, servicio_producto, callback_estado):
        self.parent = parent
        self.servicio = servicio_categoria
        self.servicio_producto = servicio_producto  # ← NUEVO
        self.callback_estado = callback_estado
        
        self._crear_widgets()
        self.cargar_categorias()
    
    def _crear_widgets(self):
        toolbar = tk.Frame(self.parent, bg='#34495e', height=60)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        toolbar.pack_propagate(False)
        
        tk.Button(
            toolbar,
            text="➕ NUEVA CATEGORÍA",
            font=('Helvetica', 10, 'bold'),
            bg='#27ae60',
            fg='white',
            command=self.nueva_categoria,
            padx=15
        ).pack(side=tk.LEFT, padx=5, pady=10)
        
        tk.Button(
            toolbar,
            text="🔄 ACTUALIZAR",
            font=('Helvetica', 10, 'bold'),
            bg='#3498db',
            fg='white',
            command=self.cargar_categorias,
            padx=15
        ).pack(side=tk.LEFT, padx=5, pady=10)
        
        tree_frame = tk.Frame(self.parent, bg='white')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columnas = [
            ('ID', 50, 'center'),
            ('Nombre', 150, 'w'),
            ('Prefijo', 80, 'center'),
            ('Descripción', 300, 'w'),
            ('Productos', 100, 'center')
        ]
        
        self.tree = ttk.Treeview(tree_frame, columns=[c[0] for c in columnas], show='headings', height=15)
        
        for col, ancho, alineacion in columnas:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=ancho, anchor=alineacion)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        action_frame = tk.Frame(self.parent, bg='#ecf0f1', height=60)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        action_frame.pack_propagate(False)
        
        tk.Button(
            action_frame,
            text="✏️ Editar",
            bg='#3498db',
            fg='white',
            command=self.editar_categoria,
            width=15,
            height=2
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        tk.Button(
            action_frame,
            text="🗑️ Eliminar",
            bg='#e74c3c',
            fg='white',
            command=self.eliminar_categoria,
            width=15,
            height=2
        ).pack(side=tk.LEFT, padx=10, pady=10)
        
        self.tree.bind('<Double-Button-1>', lambda e: self.editar_categoria())
    
    def cargar_categorias(self):
        """Carga las categorías en la tabla con el conteo real de productos."""
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        categorias = self.servicio.obtener_todas()
        total_productos = 0  # Variable para acumular el total
        
        for cat in categorias:
            # Contar productos reales de esta categoría
            cantidad_productos = self.servicio_producto.contar_por_categoria(cat.nombre)
            total_productos += cantidad_productos  # Sumar al total
            
            self.tree.insert('', tk.END, values=(
                cat.id,
                cat.nombre,
                cat.prefijo,
                cat.descripcion[:50] + '...' if len(cat.descripcion) > 50 else cat.descripcion,
                cantidad_productos  # ✅ MUESTRA EL NÚMERO REAL
            ))
        
        # ✅ CORREGIDO: Usar len() en lugar de sum()
        self.callback_estado(f"{len(categorias)} categorías - {total_productos} productos totales")
    
    def nueva_categoria(self):
        """Crea una nueva categoría."""
        dialogo = DialogoBase(self.parent, "Nueva Categoría", 500, 350)
        
        tk.Label(
            dialogo,
            text="➕ NUEVA CATEGORÍA",
            font=('Helvetica', 14, 'bold'),
            bg='#27ae60',
            fg='white'
        ).pack(fill=tk.X, pady=10, ipady=10)
        
        frame = tk.Frame(dialogo, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="Nombre *:", font=('Helvetica', 10, 'bold')).pack(anchor='w')
        entry_nombre = tk.Entry(frame, font=('Helvetica', 12))
        entry_nombre.pack(fill=tk.X, pady=5)
        
        tk.Label(frame, text="Prefijo *:", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(10,0))
        entry_prefijo = tk.Entry(frame, font=('Helvetica', 12), width=10)
        entry_prefijo.pack(anchor='w', pady=5)
        
        tk.Label(frame, text="Descripción:", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(10,0))
        entry_desc = tk.Entry(frame, font=('Helvetica', 12))
        entry_desc.pack(fill=tk.X, pady=5)
        
        def guardar():
            nombre = entry_nombre.get().strip()
            prefijo = entry_prefijo.get().strip().upper()
            desc = entry_desc.get().strip()
            
            if not nombre or not prefijo:
                messagebox.showerror("Error", "Nombre y prefijo son obligatorios")
                return
            
            categoria = Categoria(
                id=None,
                nombre=nombre,
                prefijo=prefijo,
                descripcion=desc
            )
            
            exito, msg = self.servicio.agregar(categoria)
            
            if exito:
                messagebox.showinfo("Éxito", msg)
                dialogo.destroy()
                self.cargar_categorias()
                self.callback_estado(msg)
            else:
                messagebox.showerror("Error", msg)
        
        dialogo.crear_botones(frame, "Guardar Categoría", guardar)
    
    def editar_categoria(self):
        """Edita categoría seleccionada."""
        seleccion = self.tree.selection()
        if not seleccion:
            messagebox.showwarning("Seleccionar", "Seleccione una categoría")
            return
        
        item = self.tree.item(seleccion[0])
        cat_id = item['values'][0]
        
        categoria = self.servicio.obtener_por_id(cat_id)
        if not categoria:
            messagebox.showerror("Error", "Categoría no encontrada")
            return
        
        dialogo = DialogoBase(self.parent, "Editar Categoría", 500, 350)
        
        tk.Label(
            dialogo,
            text="✏️ EDITAR CATEGORÍA",
            font=('Helvetica', 14, 'bold'),
            bg='#3498db',
            fg='white'
        ).pack(fill=tk.X, pady=10, ipady=10)
        
        frame = tk.Frame(dialogo, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="Nombre:", font=('Helvetica', 10, 'bold')).pack(anchor='w')
        entry_nombre = tk.Entry(frame, font=('Helvetica', 12))
        entry_nombre.insert(0, categoria.nombre)
        entry_nombre.pack(fill=tk.X, pady=5)
        
        tk.Label(frame, text="Prefijo:", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(10,0))
        entry_prefijo = tk.Entry(frame, font=('Helvetica', 12), width=10)
        entry_prefijo.insert(0, categoria.prefijo)
        entry_prefijo.pack(anchor='w', pady=5)
        
        tk.Label(frame, text="Descripción:", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(10,0))
        entry_desc = tk.Entry(frame, font=('Helvetica', 12))
        entry_desc.insert(0, categoria.descripcion)
        entry_desc.pack(fill=tk.X, pady=5)
        
        def actualizar():
            categoria.nombre = entry_nombre.get().strip()
            categoria.prefijo = entry_prefijo.get().strip().upper()
            categoria.descripcion = entry_desc.get().strip()
            
            exito, msg = self.servicio.actualizar(categoria)
            
            if exito:
                messagebox.showinfo("Éxito", msg)
                dialogo.destroy()
                self.cargar_categorias()
                self.callback_estado(msg)
            else:
                messagebox.showerror("Error", msg)
        
        dialogo.crear_botones(frame, "Actualizar", actualizar)
    
    def eliminar_categoria(self):
        """Elimina categoría seleccionada."""
        seleccion = self.tree.selection()
        if not seleccion:
            messagebox.showwarning("Seleccionar", "Seleccione una categoría")
            return
        
        item = self.tree.item(seleccion[0])
        cat_id = item['values'][0]
        cat_nombre = item['values'][1]
        
        if messagebox.askyesno("Confirmar", f"¿Eliminar categoría '{cat_nombre}'?"):
            exito, msg = self.servicio.eliminar(cat_id)
            if exito:
                self.cargar_categorias()
                self.callback_estado(msg)
            else:
                messagebox.showerror("Error", msg)

# ============================================================================
# PESTAÑA DE PRODUCTOS - VERSIÓN MEJORADA (CON SEMÁFORO Y ORDENAMIENTO)
# ============================================================================

class PestañaProductos:
    """Pestaña de administración de productos con semáforo de stock y ordenamiento."""
    
    def __init__(self, parent, servicio_producto: ServicioProducto, servicio_categoria: ServicioCategoria, callback_estado):
        self.parent = parent
        self.servicio_producto = servicio_producto
        self.servicio_categoria = servicio_categoria
        self.callback_estado = callback_estado
        self.busqueda_var = tk.StringVar()
        self.orden_actual = "defecto"  # defecto, stock_bajo, alfabetico
        
        self._crear_widgets()
        self.actualizar_tabla_productos()
        
        # Vincular evento de cambio de pestaña para actualizar automáticamente
        parent.bind("<Map>", lambda e: self.actualizar_tabla_productos())
    
    
    def _crear_widgets(self):
        # ============================================================
        # TOOLBAR PRINCIPAL
        # ============================================================
        toolbar = tk.Frame(self.parent, bg='#34495e', height=60)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        toolbar.pack_propagate(False)
        
        # Botones de acción
        tk.Button(
            toolbar,
            text="➕ NUEVO PRODUCTO",
            font=('Helvetica', 10, 'bold'),
            bg='#27ae60',
            fg='white',
            command=self.nuevo_producto,
            padx=15
        ).pack(side=tk.LEFT, padx=5, pady=10)
        
        tk.Button(
            toolbar,
            text="📤 IMPORTAR CSV",
            font=('Helvetica', 10, 'bold'),
            bg='#3498db',
            fg='white',
            command=self.importar_csv,
            padx=15
        ).pack(side=tk.LEFT, padx=5, pady=10)
        
        tk.Button(
            toolbar,
            text="📥 EXPORTAR CSV",
            font=('Helvetica', 10, 'bold'),
            bg='#9b59b6',
            fg='white',
            command=self.exportar_csv,
            padx=15
        ).pack(side=tk.LEFT, padx=5, pady=10)
        
        # Buscador
        tk.Label(toolbar, text="🔍 Buscar:", bg='#34495e', fg='white').pack(side=tk.RIGHT, padx=5)
        self.busqueda_var.trace_add('write', lambda *args: self.actualizar_tabla_productos(self.busqueda_var.get()))
        
        tk.Entry(
            toolbar,
            textvariable=self.busqueda_var,
            font=('Helvetica', 10),
            width=25,
            bg='white'
        ).pack(side=tk.RIGHT, padx=10)
        
        # ============================================================
        # BOTONERA DE ORDENAMIENTO
        # ============================================================
        orden_frame = tk.Frame(self.parent, bg='#ecf0f1', height=40)
        orden_frame.pack(fill=tk.X, padx=5, pady=5)
        orden_frame.pack_propagate(False)
        
        tk.Label(orden_frame, text="Ordenar por:", font=('Helvetica', 9, 'bold'), 
                bg='#ecf0f1', fg='#2c3e50').pack(side=tk.LEFT, padx=10)
        
        # Botón: Por Defecto
        self.btn_defecto = tk.Button(
            orden_frame,
            text="📊 Por Defecto",
            font=('Helvetica', 9),
            bg='#3498db',
            fg='white',
            command=lambda: self.cambiar_orden("defecto"),
            padx=10,
            relief=tk.SUNKEN  # Marcado como activo por defecto
        )
        self.btn_defecto.pack(side=tk.LEFT, padx=5)
        
        # Botón: Stock Bajo
        self.btn_stock_bajo = tk.Button(
            orden_frame,
            text="⚠️ Stock Bajo",
            font=('Helvetica', 9),
            bg='#95a5a6',
            fg='white',
            command=lambda: self.cambiar_orden("stock_bajo"),
            padx=10
        )
        self.btn_stock_bajo.pack(side=tk.LEFT, padx=5)
        
        # Botón: Alfabético
        self.btn_alfabetico = tk.Button(
            orden_frame,
            text="🔤 Alfabético",
            font=('Helvetica', 9),
            bg='#95a5a6',
            fg='white',
            command=lambda: self.cambiar_orden("alfabetico"),
            padx=10
        )
        self.btn_alfabetico.pack(side=tk.LEFT, padx=5)
        
        # ============================================================
        # TABLA DE PRODUCTOS (Treeview)
        # ============================================================
        tree_frame = tk.Frame(self.parent, bg='white')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Configurar columnas (AGREGAMOS "ESTADO")
        columnas = [
            ('ID', 50, 'center'),
            ('SKU', 100, 'center'),
            ('Nombre', 200, 'w'),
            ('Categoría', 120, 'w'),
            ('Precio', 80, 'center'),
            ('Stock', 80, 'center'),
            ('Stock Mín', 80, 'center'),
            ('Estado', 100, 'center'),
            ('Descripción', 250, 'w')
        ]

        self.tree = ttk.Treeview(tree_frame, columns=[c[0] for c in columnas], show='headings', height=20)

        # 🔴 NUEVO: Configurar estilo para que los colores de fondo funcionen
        style = ttk.Style()
        style.theme_use('clam')  # El tema 'clam' permite colores de fondo
        style.configure("Treeview", background="white", fieldbackground="white")

        for col, ancho, alineacion in columnas:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=ancho, anchor=alineacion)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Grid layout
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Configurar tags para colores (semáforo)
        self.tree.tag_configure('agotado', background='#cccccc')      # Gris
        self.tree.tag_configure('critico', background='#ffcccc')      # Rojo claro
        self.tree.tag_configure('bajo', background='#fff2cc')         # Amarillo claro
        self.tree.tag_configure('normal', background='#ffffff')       # Blanco
        
        # ============================================================
        # PANEL DE EDICIÓN RÁPIDA
        # ============================================================
        edit_frame = tk.Frame(self.parent, bg='#ecf0f1', height=60)
        edit_frame.pack(fill=tk.X, padx=5, pady=5)
        edit_frame.pack_propagate(False)
        
        tk.Label(edit_frame, text="✏️ Edición Rápida:", font=('Helvetica', 10, 'bold'), 
                bg='#ecf0f1').pack(side=tk.LEFT, padx=10)
        
        tk.Label(edit_frame, text="Precio:", bg='#ecf0f1').pack(side=tk.LEFT, padx=5)
        self.edit_precio = tk.Entry(edit_frame, width=10)
        self.edit_precio.pack(side=tk.LEFT, padx=5)
        
        tk.Label(edit_frame, text="Stock:", bg='#ecf0f1').pack(side=tk.LEFT, padx=5)
        self.edit_stock = tk.Entry(edit_frame, width=8)
        self.edit_stock.pack(side=tk.LEFT, padx=5)
        
        tk.Button(
            edit_frame,
            text="Actualizar",
            bg='#3498db',
            fg='white',
            command=self.actualizar_producto
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Button(
            edit_frame,
            text="🗑️ Eliminar",
            bg='#e74c3c',
            fg='white',
            command=self.eliminar_producto
        ).pack(side=tk.LEFT, padx=5)
        
        # Vincular selección
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        
        # Configurar tags para colores (semáforo)
        self.tree.tag_configure('agotado', background='#cccccc')      # Gris
        self.tree.tag_configure('critico', background='#ffcccc')      # Rojo claro
        self.tree.tag_configure('bajo', background='#fff2cc')         # Amarillo claro
        self.tree.tag_configure('normal', background='#ffffff')       # Blanco

        # ============================================================
        # LEYENDA DE COLORES (CON CUADROS DE COLOR REALES)
        # ============================================================
        leyenda_frame = tk.Frame(self.parent, bg='#ecf0f1', height=35)
        leyenda_frame.pack(fill=tk.X, padx=5, pady=5)
        leyenda_frame.pack_propagate(False)

        inner_frame = tk.Frame(leyenda_frame, bg='#ecf0f1')
        inner_frame.pack(expand=True)

        # Crítico - Cuadro rojo
        cuadro_critico = tk.Frame(inner_frame, bg='#ffcccc', width=20, height=20, relief=tk.RAISED, bd=1)
        cuadro_critico.pack(side=tk.LEFT, padx=(0,5))
        cuadro_critico.pack_propagate(False)

        tk.Label(inner_frame, text="Crítico", font=('Helvetica', 9), 
                bg='#ecf0f1').pack(side=tk.LEFT, padx=(0,15))

        # Bajo - Cuadro amarillo
        cuadro_bajo = tk.Frame(inner_frame, bg='#fff2cc', width=20, height=20, relief=tk.RAISED, bd=1)
        cuadro_bajo.pack(side=tk.LEFT, padx=(0,5))
        cuadro_bajo.pack_propagate(False)

        tk.Label(inner_frame, text="Bajo", font=('Helvetica', 9), 
                bg='#ecf0f1').pack(side=tk.LEFT, padx=(0,15))

        # Agotado - Cuadro gris
        cuadro_agotado = tk.Frame(inner_frame, bg='#cccccc', width=20, height=20, relief=tk.RAISED, bd=1)
        cuadro_agotado.pack(side=tk.LEFT, padx=(0,5))
        cuadro_agotado.pack_propagate(False)

        tk.Label(inner_frame, text="Agotado", font=('Helvetica', 9), 
                bg='#ecf0f1').pack(side=tk.LEFT, padx=(0,15))

        # Normal - Cuadro blanco con borde
        cuadro_normal = tk.Frame(inner_frame, bg='#ffffff', width=20, height=20, relief=tk.RAISED, bd=1)
        cuadro_normal.pack(side=tk.LEFT, padx=(0,5))
        cuadro_normal.pack_propagate(False)

        tk.Label(inner_frame, text="Normal", font=('Helvetica', 9), 
                bg='#ecf0f1').pack(side=tk.LEFT)
    
    def on_select(self, event):
        """Carga datos del producto seleccionado."""
        seleccion = self.tree.selection()
        if seleccion:
            item = self.tree.item(seleccion[0])
            valores = item['values']
            self.edit_precio.delete(0, tk.END)
            self.edit_precio.insert(0, str(valores[4]).replace('$', ''))
            self.edit_stock.delete(0, tk.END)
            self.edit_stock.insert(0, valores[5])
    
    def cambiar_orden(self, orden):
        """Cambia el orden de visualización de la tabla."""
        self.orden_actual = orden
        
        # Actualizar estilos de botones
        for btn in [self.btn_defecto, self.btn_stock_bajo, self.btn_alfabetico]:
            btn.config(bg='#95a5a6', relief=tk.RAISED)
        
        if orden == "defecto":
            self.btn_defecto.config(bg='#3498db', relief=tk.SUNKEN)
        elif orden == "stock_bajo":
            self.btn_stock_bajo.config(bg='#3498db', relief=tk.SUNKEN)
        elif orden == "alfabetico":
            self.btn_alfabetico.config(bg='#3498db', relief=tk.SUNKEN)
        
        # Recargar tabla con nuevo orden
        self.actualizar_tabla_productos(self.busqueda_var.get())
    
    def actualizar_tabla_productos(self, filtro=""):
        """
        Actualiza la tabla con los productos desde la BD.
        Se llama automáticamente al entrar a la pestaña y después de cada venta.
        """
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Obtener productos según filtro
        if filtro:
            productos = self.servicio_producto.buscar(filtro)
        else:
            productos = self.servicio_producto.obtener_todos()
        
        # Aplicar ordenamiento
        if self.orden_actual == "stock_bajo":
            # Ordenar: primero los más críticos
            productos.sort(key=lambda p: (
                0 if p.cantidad == 0 else
                1 if p.cantidad <= p.stock_minimo else
                2 if p.cantidad <= p.stock_minimo * 2 else 3,
                p.nombre
            ))
        elif self.orden_actual == "alfabetico":
            productos.sort(key=lambda p: p.nombre.lower())
        else:  # defecto - por ID
            productos.sort(key=lambda p: p.id if p.id else 0)
        
        # Insertar productos con colores según stock
        for p in productos:
            # Determinar estado y color (SIN EMOJIS)
            if p.cantidad == 0:
                estado = "AGOTADO"
                tag = 'agotado'
            elif p.cantidad <= p.stock_minimo:
                estado = "CRÍTICO"
                tag = 'critico'
            elif p.cantidad <= p.stock_minimo * 2:
                estado = "BAJO"
                tag = 'bajo'
            else:
                estado = "NORMAL"
                tag = 'normal'
            
            valores = (
                p.id,
                p.sku,
                p.nombre,
                p.categoria,
                f"${p.precio:.2f}",
                p.cantidad,
                p.stock_minimo,
                estado,  # 🔴 SOLO TEXTO, SIN EMOJIS
                p.descripcion[:50] + '...' if len(p.descripcion) > 50 else p.descripcion
            )
            
            self.tree.insert('', tk.END, values=valores, tags=(tag,))
        
        # Actualizar barra de estado
        if self.callback_estado:
            try:
                self.callback_estado(f"{len(productos)} productos - Última actualización: {datetime.now().strftime('%H:%M:%S')}")
            except:
                pass
    
    # ============================================================
    # MÉTODOS EXISTENTES (sin cambios)
    # ============================================================
    
    def nuevo_producto(self):
        """Diálogo para nuevo producto - Versión SIMPLE."""
        categorias = self.servicio_categoria.obtener_todas()
        
        if not categorias:
            messagebox.showwarning("Sin categorías", "Primero debe crear una categoría")
            return
        
        dialogo = DialogoBase(self.parent, "Nuevo Producto", 600, 650)
        
        tk.Label(
            dialogo,
            text="➕ NUEVO PRODUCTO",
            font=('Helvetica', 16, 'bold'),
            bg='#27ae60',
            fg='white'
        ).pack(fill=tk.X, pady=10, ipady=10)
        
        frame = tk.Frame(dialogo, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="Categoría *:", font=('Helvetica', 10, 'bold')).pack(anchor='w')
        categoria_var = tk.StringVar()
        categoria_combo = ttk.Combobox(
            frame,
            textvariable=categoria_var,
            values=[f"{c.nombre} ({c.prefijo})" for c in categorias],
            state='readonly',
            font=('Helvetica', 11)
        )
        categoria_combo.pack(fill=tk.X, pady=5)
        
        tk.Label(frame, text="SKU (generado automáticamente):", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(10,0))
        sku_var = tk.StringVar()
        sku_entry = tk.Entry(frame, textvariable=sku_var, font=('Helvetica', 12, 'bold'), 
                            bg='#ecf0f1', state='readonly')
        sku_entry.pack(fill=tk.X, pady=5)
        
        tk.Label(frame, text="Nombre *:", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(10,0))
        entry_nombre = tk.Entry(frame, font=('Helvetica', 12))
        entry_nombre.pack(fill=tk.X, pady=5)
        
        tk.Label(frame, text="Descripción:", font=('Helvetica', 10, 'bold')).pack(anchor='w', pady=(10,0))
        entry_desc = tk.Entry(frame, font=('Helvetica', 12))
        entry_desc.pack(fill=tk.X, pady=5)
        
        precio_stock_frame = tk.Frame(frame)
        precio_stock_frame.pack(fill=tk.X, pady=10)
        
        tk.Label(precio_stock_frame, text="Precio *:", font=('Helvetica', 10, 'bold')).pack(anchor='w')
        entry_precio = tk.Entry(precio_stock_frame, font=('Helvetica', 12), width=15, justify='right')
        entry_precio.pack(side=tk.LEFT, padx=5)
        
        tk.Label(precio_stock_frame, text="Stock *:", font=('Helvetica', 10, 'bold')).pack(side=tk.LEFT, padx=(20,5))
        entry_stock = tk.Entry(precio_stock_frame, font=('Helvetica', 12), width=10, justify='right')
        entry_stock.pack(side=tk.LEFT, padx=5)
        
        tk.Label(frame, text="Stock Mínimo:", font=('Helvetica', 10, 'bold')).pack(anchor='w')
        entry_stock_min = tk.Entry(frame, font=('Helvetica', 12), width=10, justify='right')
        entry_stock_min.insert(0, "5")
        entry_stock_min.pack(anchor='w', pady=5)
        
        def actualizar_sku(*args):
            if categoria_var.get():
                seleccion = categoria_var.get()
                prefijo = seleccion.split('(')[-1].replace(')', '')
                
                for c in categorias:
                    if c.prefijo == prefijo:
                        sku_sugerido = self.servicio_producto.generar_sku_sugerido(c.id)
                        sku_var.set(sku_sugerido)
                        break
        
        categoria_combo.bind('<<ComboboxSelected>>', actualizar_sku)
        
        def guardar():
            if not categoria_var.get():
                messagebox.showerror("Error", "Seleccione una categoría")
                return
            
            seleccion = categoria_var.get()
            prefijo = seleccion.split('(')[-1].replace(')', '')
            categoria = None
            for c in categorias:
                if c.prefijo == prefijo:
                    categoria = c
                    break
            
            nombre = entry_nombre.get().strip()
            if not nombre:
                messagebox.showerror("Error", "El nombre es obligatorio")
                return
            
            try:
                precio = float(entry_precio.get() or 0)
                stock = int(entry_stock.get() or 0)
                stock_min = int(entry_stock_min.get() or 5)
            except ValueError:
                messagebox.showerror("Error", "Precio y stock deben ser números")
                return
            
            if precio <= 0:
                messagebox.showerror("Error", "El precio debe ser mayor a cero")
                return
            
            producto = Producto(
                id=None,
                sku=sku_var.get(),
                nombre=nombre,
                descripcion=entry_desc.get(),
                cantidad=stock,
                precio=precio,
                stock_minimo=stock_min,
                categoria=categoria.nombre
            )
            
            exito, msg = self.servicio_producto.agregar(producto)
            
            if exito:
                messagebox.showinfo("Éxito", msg)
                dialogo.destroy()
                self.actualizar_tabla_productos()
                if self.callback_estado:
                    self.callback_estado(msg)
            else:
                messagebox.showerror("Error", msg)
        
        dialogo.crear_botones(frame, "Guardar Producto", guardar)
    
    def actualizar_producto(self):
        """Actualiza producto seleccionado."""
        seleccion = self.tree.selection()
        if not seleccion:
            messagebox.showwarning("Seleccionar", "Seleccione un producto")
            return
        
        try:
            item = self.tree.item(seleccion[0])
            prod_id = item['values'][0]
            
            precio = float(self.edit_precio.get())
            stock = int(self.edit_stock.get())
            
            producto = self.servicio_producto.repo.obtener_por_id(prod_id)
            if not producto:
                messagebox.showerror("Error", "Producto no encontrado")
                return
            
            producto.precio = precio
            producto.cantidad = stock
            
            exito, msg = self.servicio_producto.actualizar(producto)
            
            if exito:
                self.actualizar_tabla_productos(self.busqueda_var.get())
                if self.callback_estado:
                    self.callback_estado(msg)
            else:
                messagebox.showerror("Error", msg)
                
        except ValueError:
            messagebox.showerror("Error", "Precio y stock deben ser números")
        except Exception as e:
            messagebox.showerror("Error", str(e))
    
    def eliminar_producto(self):
        """Elimina producto seleccionado."""
        seleccion = self.tree.selection()
        if not seleccion:
            messagebox.showwarning("Seleccionar", "Seleccione un producto")
            return
        
        item = self.tree.item(seleccion[0])
        prod_id = item['values'][0]
        nombre = item['values'][2]
        
        if messagebox.askyesno("Confirmar", f"¿Eliminar '{nombre}'?"):
            exito, msg = self.servicio_producto.eliminar(prod_id)
            if exito:
                self.actualizar_tabla_productos(self.busqueda_var.get())
                if self.callback_estado:
                    self.callback_estado(msg)
            else:
                messagebox.showerror("Error", msg)
    
    def importar_csv(self):
        """Importa productos desde CSV."""
        filename = filedialog.askopenfilename(
            title="Seleccionar CSV",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")]
        )
        
        if not filename:
            return
        
        try:
            importados = 0
            errores = 0
            
            with open(filename, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    try:
                        categoria_nombre = row.get('Categoría', '').strip()
                        
                        producto = Producto(
                            id=None,
                            sku=row.get('SKU', '').upper(),
                            nombre=row.get('Nombre', ''),
                            descripcion=row.get('Descripción', ''),
                            cantidad=int(row.get('Stock', 0)),
                            precio=float(row.get('Precio', 0)),
                            stock_minimo=int(row.get('Stock_Minimo', 5)),
                            categoria=categoria_nombre
                        )
                        
                        exito, _ = self.servicio_producto.agregar(producto)
                        if exito:
                            importados += 1
                        else:
                            errores += 1
                            
                    except Exception:
                        errores += 1
            
            messagebox.showinfo("Importación", f"✅ Importados: {importados}\n❌ Errores: {errores}")
            self.actualizar_tabla_productos()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al importar: {e}")
    
    def exportar_csv(self):
        """Exporta productos a CSV."""
        filename = filedialog.asksaveasfilename(
            title="Guardar CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        
        if not filename:
            return
        
        try:
            productos = self.servicio_producto.obtener_todos()
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['SKU', 'Nombre', 'Descripción', 'Categoría', 'Precio', 'Stock', 'Stock_Minimo', 'Estado'])
                
                for p in productos:
                    # Determinar estado para el CSV
                    if p.cantidad == 0:
                        estado = "AGOTADO"
                    elif p.cantidad <= p.stock_minimo:
                        estado = "CRÍTICO"
                    elif p.cantidad <= p.stock_minimo * 2:
                        estado = "BAJO"
                    else:
                        estado = "NORMAL"
                    
                    writer.writerow([
                        p.sku, p.nombre, p.descripcion, 
                        p.categoria, p.precio, p.cantidad, p.stock_minimo,
                        estado
                    ])
            
            messagebox.showinfo("Éxito", f"Exportados {len(productos)} productos")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al exportar: {e}")


# ============================================================================
# PESTAÑA DE VENTAS POS
# ============================================================================

class CarritoWidget(tk.Frame):
    """Widget del carrito de compras."""
    
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.items = []
        self.total_var = tk.StringVar(value="$0.00")
        self._crear_widgets()
    
    def _crear_widgets(self):
        tk.Label(
            self,
            text="🛒 VENTA ACTUAL",
            font=('Helvetica', 14, 'bold'),
            bg='#2c3e50',
            fg='white'
        ).pack(fill=tk.X, pady=(0, 10))
        
        list_frame = tk.Frame(self, bg='white')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.lista = tk.Listbox(
            list_frame,
            font=('Courier', 10),
            height=15,
            bg='white',
            relief=tk.SUNKEN,
            bd=1
        )
        scrollbar = tk.Scrollbar(list_frame)
        self.lista.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.lista.yview)
        
        self.lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        total_frame = tk.Frame(self, bg='#34495e', height=60)
        total_frame.pack(fill=tk.X, pady=5)
        total_frame.pack_propagate(False)
        
        tk.Label(
            total_frame,
            text="TOTAL:",
            font=('Helvetica', 16, 'bold'),
            bg='#34495e',
            fg='white'
        ).pack(side=tk.LEFT, padx=10)
        
        tk.Label(
            total_frame,
            textvariable=self.total_var,
            font=('Helvetica', 20, 'bold'),
            bg='#34495e',
            fg='#27ae60'
        ).pack(side=tk.RIGHT, padx=10)
        
        btn_frame = tk.Frame(self, bg='#ecf0f1')
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.btn_eliminar = tk.Button(
            btn_frame,
            text="🗑️ Eliminar",
            font=('Helvetica', 10),
            bg='#e74c3c',
            fg='white',
            command=self.eliminar_seleccionado,
            state=tk.DISABLED
        )
        self.btn_eliminar.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        tk.Button(
            btn_frame,
            text="🔄 Limpiar",
            font=('Helvetica', 10),
            bg='#95a5a6',
            fg='white',
            command=self.limpiar
        ).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        
        self.lista.bind('<<ListboxSelect>>', self._on_seleccion)
    
    def _on_seleccion(self, event):
        self.btn_eliminar.config(state=tk.NORMAL if self.lista.curselection() else tk.DISABLED)
    
    def agregar(self, producto: Producto, cantidad: int) -> Tuple[bool, str]:
        for item in self.items:
            if item.producto_id == producto.id:
                nueva_cantidad = item.cantidad + cantidad
                if nueva_cantidad > producto.cantidad:
                    return False, f"Stock insuficiente. Máx: {producto.cantidad}"
                
                item.cantidad = nueva_cantidad
                item.subtotal = item.cantidad * item.precio_unitario
                self._actualizar()
                return True, f"Cantidad actualizada: {item.nombre} x{item.cantidad}"
        
        if cantidad > producto.cantidad:
            return False, f"Stock insuficiente. Máx: {producto.cantidad}"
        
        item = ItemCarrito(
            producto_id=producto.id,
            sku=producto.sku,
            nombre=producto.nombre,
            cantidad=cantidad,
            precio_unitario=producto.precio,
            subtotal=cantidad * producto.precio
        )
        
        self.items.append(item)
        self._actualizar()
        return True, f"Agregado: {producto.nombre} x{cantidad}"
    
    def eliminar_seleccionado(self):
        seleccion = self.lista.curselection()
        if seleccion:
            self.items.pop(seleccion[0])
            self._actualizar()
            self.btn_eliminar.config(state=tk.DISABLED)
    
    def limpiar(self):
        self.items.clear()
        self._actualizar()
        self.btn_eliminar.config(state=tk.DISABLED)
    
    def _actualizar(self):
        self.lista.delete(0, tk.END)
        total = 0
        
        for i, item in enumerate(self.items):
            linea = f"{i+1:2d}. {item.nombre[:20]:20} x{item.cantidad:2d}  ${item.precio_unitario:6.2f}  ${item.subtotal:7.2f}"
            self.lista.insert(tk.END, linea)
            total += item.subtotal
        
        self.total_var.set(f"${total:.2f}")
    
    def obtener_items(self) -> List[ItemCarrito]:
        return self.items.copy()
    
    def obtener_total(self) -> float:
        return sum(item.subtotal for item in self.items)


class BuscadorPOS(tk.Frame):
    """Buscador inteligente para POS."""
    
    def __init__(self, master, servicio_producto: ServicioProducto, carrito: CarritoWidget, callback_estado, **kwargs):
        super().__init__(master, **kwargs)
        self.servicio_producto = servicio_producto
        self.carrito = carrito
        self.callback_estado = callback_estado
        self.resultados = []
        self.configure(bg='white')
        self._crear_widgets()
    
    def _crear_widgets(self):
        tk.Label(
            self,
            text="🔍 Buscar Producto:",
            font=('Helvetica', 12, 'bold'),
            bg='white'
        ).pack(anchor='w', padx=10, pady=(10,0))
        
        self.entry_busqueda = tk.Entry(
            self,
            font=('Helvetica', 14),
            bg='#ecf0f1',
            relief=tk.SUNKEN,
            bd=2
        )
        self.entry_busqueda.pack(fill=tk.X, padx=10, pady=5, ipady=5)
        self.entry_busqueda.focus_set()
        
        tk.Label(
            self,
            text="Resultados:",
            font=('Helvetica', 11, 'bold'),
            bg='white'
        ).pack(anchor='w', padx=10)
        
        list_frame = tk.Frame(self, bg='white')
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        self.lista = tk.Listbox(
            list_frame,
            font=('Courier', 11),
            height=8,
            bg='white',
            selectbackground='#3498db',
            selectforeground='white'
        )
        scrollbar = tk.Scrollbar(list_frame)
        self.lista.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.lista.yview)
        
        self.lista.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        cant_frame = tk.Frame(self, bg='white')
        cant_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(cant_frame, text="Cantidad:", font=('Helvetica', 11), bg='white').pack(side=tk.LEFT, padx=5)
        
        self.entry_cantidad = tk.Entry(
            cant_frame,
            font=('Helvetica', 14),
            width=8,
            bg='#ecf0f1',
            justify='center'
        )
        self.entry_cantidad.pack(side=tk.LEFT, padx=5)
        self.entry_cantidad.insert(0, "1")
        
        self.btn_agregar = tk.Button(
            cant_frame,
            text="➕ AGREGAR (ENTER)",
            font=('Helvetica', 12, 'bold'),
            bg='#27ae60',
            fg='white',
            command=self.agregar_al_carrito
        )
        self.btn_agregar.pack(side=tk.LEFT, padx=10, fill=tk.X, expand=True, ipady=5)
        
        self.entry_busqueda.bind('<KeyRelease>', self._buscar)
        self.entry_busqueda.bind('<Return>', lambda e: self.entry_cantidad.focus())
        self.entry_cantidad.bind('<Return>', lambda e: self.agregar_al_carrito())
        self.lista.bind('<Double-Button-1>', lambda e: self.entry_cantidad.focus())
    
    def _buscar(self, event):
        termino = self.entry_busqueda.get().strip()
        
        if len(termino) < 2:
            self.lista.delete(0, tk.END)
            self.resultados = []
            return
        
        self.resultados = self.servicio_producto.buscar(termino)
        
        self.lista.delete(0, tk.END)
        for p in self.resultados:
            # Indicador de stock más visible
            if p.cantidad <= 0:
                stock_icon = "🔴 SIN STOCK"
            elif p.cantidad <= p.stock_minimo:
                stock_icon = f"🟡 BAJO ({p.cantidad})"
            else:
                stock_icon = f"🟢 OK ({p.cantidad})"
            
            linea = f"{p.nombre[:25]:25} ${p.precio:6.2f}  {stock_icon}"
            self.lista.insert(tk.END, linea)
    
    def agregar_al_carrito(self):
        if not self.resultados:
            messagebox.showwarning("Sin resultados", "No hay productos para agregar")
            return
        
        seleccion = self.lista.curselection()
        if not seleccion:
            messagebox.showwarning("Sin selección", "Seleccione un producto")
            return
        
        try:
            cantidad = int(self.entry_cantidad.get())
            if cantidad <= 0:
                messagebox.showerror("Error", "La cantidad debe ser positiva")
                return
        except ValueError:
            messagebox.showerror("Error", "Cantidad inválida")
            return
        
        producto = self.resultados[seleccion[0]]
        exito, msg = self.carrito.agregar(producto, cantidad)
        
        if exito:
            self.entry_busqueda.delete(0, tk.END)
            self.lista.delete(0, tk.END)
            self.entry_cantidad.delete(0, tk.END)
            self.entry_cantidad.insert(0, "1")
            self.entry_busqueda.focus()
            self.resultados = []
            if self.callback_estado:
                self.callback_estado(msg)
        else:
            messagebox.showerror("Error", msg)


class DialogoPago(tk.Toplevel):
    """Diálogo de pago con vuelto y tamaño automático."""
    
    def __init__(self, parent, total):
        super().__init__(parent)
        self.total = total
        self.resultado = None
        self.monto_pagado = None
        
        self.title("Pago en Efectivo")
        self.transient(parent)
        self.grab_set()
        self.configure(bg='white')
        
        self._crear_widgets()
        self._ajustar_tamano()
    
    def _crear_widgets(self):
        # ============================================================
        # TÍTULO (siempre visible)
        # ============================================================
        titulo_frame = tk.Frame(self, bg='#2c3e50', height=60)
        titulo_frame.pack(fill=tk.X)
        titulo_frame.pack_propagate(False)
        
        tk.Label(
            titulo_frame,
            text="💵 PAGO EN EFECTIVO",
            font=('Helvetica', 16, 'bold'),
            bg='#2c3e50',
            fg='white'
        ).pack(expand=True)
        
        # ============================================================
        # TOTAL A PAGAR (destacado)
        # ============================================================
        total_frame = tk.Frame(self, bg='#3498db', height=100)
        total_frame.pack(fill=tk.X, padx=20, pady=15)
        total_frame.pack_propagate(False)
        
        tk.Label(
            total_frame,
            text="TOTAL A PAGAR",
            font=('Helvetica', 12),
            bg='#3498db',
            fg='white'
        ).pack(pady=(15,5))
        
        tk.Label(
            total_frame,
            text=f"${self.total:.2f}",
            font=('Helvetica', 28, 'bold'),
            bg='#3498db',
            fg='white'
        ).pack()
        
        # ============================================================
        # CAMPO PARA INGRESAR MONTO
        # ============================================================
        entrada_frame = tk.Frame(self, bg='white')
        entrada_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(
            entrada_frame,
            text="¿CON CUÁNTO PAGA?",
            font=('Helvetica', 12, 'bold'),
            bg='white'
        ).pack(pady=5)
        
        self.entry_monto = tk.Entry(
            entrada_frame,
            font=('Helvetica', 20, 'bold'),
            bg='#ecf0f1',
            justify='center',
            relief=tk.SUNKEN,
            bd=3
        )
        self.entry_monto.pack(fill=tk.X, pady=10, ipady=8)
        self.entry_monto.focus_set()
        
        # ============================================================
        # VUELTO (se actualiza dinámicamente)
        # ============================================================
        self.vuelto_frame = tk.Frame(self, bg='#27ae60', height=100)
        self.vuelto_frame.pack(fill=tk.X, padx=20, pady=10)
        self.vuelto_frame.pack_propagate(False)
        
        tk.Label(
            self.vuelto_frame,
            text="VUELTO",
            font=('Helvetica', 12, 'bold'),
            bg='#27ae60',
            fg='white'
        ).pack(pady=(15,5))
        
        self.label_vuelto = tk.Label(
            self.vuelto_frame,
            text="$0.00",
            font=('Helvetica', 24, 'bold'),
            bg='#27ae60',
            fg='white'
        )
        self.label_vuelto.pack()
        
        # ============================================================
        # BOTONES DE ACCIÓN
        # ============================================================
        btn_frame = tk.Frame(self, bg='white')
        btn_frame.pack(fill=tk.X, padx=20, pady=15)
        
        tk.Button(
            btn_frame,
            text="Cancelar (ESC)",
            font=('Helvetica', 11),
            bg='#e74c3c',
            fg='white',
            command=self.cancelar,
            width=15,
            height=2
        ).pack(side=tk.LEFT, padx=5, expand=True)
        
        self.btn_confirmar = tk.Button(
            btn_frame,
            text="Confirmar (ENTER)",
            font=('Helvetica', 11, 'bold'),
            bg='#95a5a6',
            fg='white',
            width=15,
            height=2,
            state=tk.DISABLED,
            command=self.confirmar
        )
        self.btn_confirmar.pack(side=tk.LEFT, padx=5, expand=True)
        
        # ============================================================
        # EVENTOS
        # ============================================================
        self.entry_monto.bind('<KeyRelease>', self._calcular_vuelto)
        self.bind('<Return>', lambda e: self.confirmar() if self.btn_confirmar['state'] == tk.NORMAL else None)
        self.bind('<Escape>', lambda e: self.cancelar())
    
    def _ajustar_tamano(self):
        """Calcula el tamaño necesario y centra la ventana."""
        self.update_idletasks()
        
        # Calcular dimensiones requeridas
        ancho = max(450, self.winfo_reqwidth() + 40)
        alto = self.winfo_reqheight() + 20
        
        # Obtener posición del padre para centrar
        x = self.master.winfo_rootx() + (self.master.winfo_width() // 2) - (ancho // 2)
        y = self.master.winfo_rooty() + (self.master.winfo_height() // 2) - (alto // 2)
        
        # Aplicar geometría
        self.geometry(f"{ancho}x{alto}+{x}+{y}")
        self.minsize(ancho, alto)
        self.resizable(False, False)  # Bloquear redimensionado manual
    
    def _calcular_vuelto(self, event):
        """Calcula el vuelto en tiempo real."""
        try:
            monto = float(self.entry_monto.get())
            if monto >= self.total:
                vuelto = monto - self.total
                self.label_vuelto.config(text=f"${vuelto:.2f}")
                self.btn_confirmar.config(state=tk.NORMAL, bg='#27ae60')
                self.vuelto_frame.config(bg='#27ae60')
            else:
                self.label_vuelto.config(text="MONTO INSUFICIENTE")
                self.btn_confirmar.config(state=tk.DISABLED, bg='#95a5a6')
                self.vuelto_frame.config(bg='#e74c3c')
        except ValueError:
            self.label_vuelto.config(text="$0.00")
            self.btn_confirmar.config(state=tk.DISABLED, bg='#95a5a6')
            self.vuelto_frame.config(bg='#27ae60')
    
    def confirmar(self):
        """Confirma el pago."""
        try:
            self.monto_pagado = float(self.entry_monto.get())
            self.resultado = "efectivo"
            self.destroy()
        except ValueError:
            messagebox.showerror("Error", "Monto inválido")
    
    def cancelar(self):
        """Cancela el pago."""
        self.resultado = None
        self.destroy()

# ============================================================================
# TICKET PROFESIONAL - VERSIÓN MEJORADA (NUEVO CÓDIGO)
# ============================================================================

class TicketProfesional:
    """Ticket profesional con ventana de tamaño automático."""
    
    @staticmethod
    def mostrar_ticket(parent, venta_id, total, pagado, vuelto, items=None):
        """Muestra ticket en ventana con tamaño automático."""
        
        ticket = tk.Toplevel(parent)
        ticket.title(f"Comprobante de Venta #{venta_id}")
        ticket.transient(parent)
        ticket.grab_set()
        ticket.configure(bg='white')
        
        # ============================================================
        # ENCABEZADO PROFESIONAL (CORREGIDO)
        # ============================================================
        header_frame = tk.Frame(ticket, bg='#2c3e50')
        header_frame.pack(fill=tk.X, padx=0, pady=0)

        # Configurar que el frame se expanda pero no limite el texto
        header_frame.pack_propagate(False)  # Mantener tamaño fijo
        header_frame.configure(height=120)  # Altura fija suficiente

        tk.Label(
            header_frame,
            text="🏪",
            font=('Helvetica', 30),
            bg='#2c3e50',
            fg='white'
        ).pack(pady=(10,0))

        tk.Label(
            header_frame,
            text="KIOSCO POS",
            font=('Helvetica', 18, 'bold'),
            bg='#2c3e50',
            fg='white'
        ).pack()

        # 🔴 CORREGIDO: Label con wraplength para que el texto no se corte
        tk.Label(
            header_frame,
            text="Sistema Administrador de Ventas",
            font=('Helvetica', 10),
            bg='#2c3e50',
            fg='#ecf0f1',
            wraplength=350,  # ✅ Ancho máximo antes de saltar línea
            justify='center'
        ).pack(pady=(0,5))
        
        # ============================================================
        # INFORMACIÓN DE LA VENTA
        # ============================================================
        info_frame = tk.Frame(ticket, bg='white')
        info_frame.pack(fill=tk.X, padx=20, pady=10)
        
        fecha_actual = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        
        # Usamos grid para alineación perfecta
        info_frame.columnconfigure(0, weight=1, minsize=100)
        info_frame.columnconfigure(1, weight=2)
        
        tk.Label(info_frame, text="Fecha:", font=('Helvetica', 10, 'bold'), bg='white', anchor='w').grid(row=0, column=0, sticky='w', pady=2)
        tk.Label(info_frame, text=fecha_actual, font=('Helvetica', 10), bg='white', anchor='w').grid(row=0, column=1, sticky='w', pady=2)
        
        tk.Label(info_frame, text="Comprobante:", font=('Helvetica', 10, 'bold'), bg='white', anchor='w').grid(row=1, column=0, sticky='w', pady=2)
        tk.Label(info_frame, text=f"N° {venta_id:06d}", font=('Helvetica', 10, 'bold'), bg='white', fg='#3498db', anchor='w').grid(row=1, column=1, sticky='w', pady=2)
        
        tk.Label(info_frame, text="Cajero:", font=('Helvetica', 10, 'bold'), bg='white', anchor='w').grid(row=2, column=0, sticky='w', pady=2)
        tk.Label(info_frame, text="PRINCIPAL", font=('Helvetica', 10), bg='white', anchor='w').grid(row=2, column=1, sticky='w', pady=2)
        
        # Línea separadora
        tk.Frame(ticket, bg='#bdc3c7', height=1).pack(fill=tk.X, padx=20, pady=5)
        
        # ============================================================
        # TABLA DE PRODUCTOS (ahora usa grid para ancho fijo)
        # ============================================================
        productos_label = tk.Label(ticket, text="DETALLE DE PRODUCTOS", 
                                   font=('Helvetica', 11, 'bold'), 
                                   bg='white', fg='#2c3e50', anchor='w')
        productos_label.pack(fill=tk.X, padx=20, pady=(10,5))
        
        # Frame contenedor para la tabla con ancho fijo
        table_container = tk.Frame(ticket, bg='white')
        table_container.pack(fill=tk.X, padx=20, pady=5)
        
        # Configurar grid para la tabla
        table_container.columnconfigure(0, weight=3, minsize=200)  # Producto
        table_container.columnconfigure(1, weight=1, minsize=60)   # Cantidad
        table_container.columnconfigure(2, weight=1, minsize=80)   # P.Unit
        table_container.columnconfigure(3, weight=1, minsize=80)   # Total
        
        # Encabezados
        tk.Label(table_container, text="Producto", font=('Helvetica', 9, 'bold'), 
                bg='#34495e', fg='white', anchor='w').grid(row=0, column=0, sticky='nsew', padx=1, pady=1, ipady=3)
        tk.Label(table_container, text="Cant.", font=('Helvetica', 9, 'bold'), 
                bg='#34495e', fg='white', anchor='center').grid(row=0, column=1, sticky='nsew', padx=1, pady=1, ipady=3)
        tk.Label(table_container, text="P.Unit", font=('Helvetica', 9, 'bold'), 
                bg='#34495e', fg='white', anchor='center').grid(row=0, column=2, sticky='nsew', padx=1, pady=1, ipady=3)
        tk.Label(table_container, text="Total", font=('Helvetica', 9, 'bold'), 
                bg='#34495e', fg='white', anchor='center').grid(row=0, column=3, sticky='nsew', padx=1, pady=1, ipady=3)
        
        # Productos
        if items:
            for i, item in enumerate(items):
                row = i + 1
                bg_color = '#f8f9fa' if i % 2 == 0 else 'white'
                
                # Nombre del producto (con wrap automático)
                nombre_text = item.nombre
                tk.Label(table_container, text=nombre_text, font=('Helvetica', 9), 
                        bg=bg_color, anchor='w', wraplength=200, justify='left').grid(
                        row=row, column=0, sticky='nsew', padx=1, pady=1, ipady=2)
                
                tk.Label(table_container, text=str(item.cantidad), font=('Helvetica', 9), 
                        bg=bg_color, anchor='center').grid(
                        row=row, column=1, sticky='nsew', padx=1, pady=1, ipady=2)
                
                tk.Label(table_container, text=f"${item.precio_unitario:.2f}", font=('Helvetica', 9), 
                        bg=bg_color, anchor='center').grid(
                        row=row, column=2, sticky='nsew', padx=1, pady=1, ipady=2)
                
                tk.Label(table_container, text=f"${item.subtotal:.2f}", font=('Helvetica', 9, 'bold'), 
                        bg=bg_color, anchor='center').grid(
                        row=row, column=3, sticky='nsew', padx=1, pady=1, ipady=2)
        else:
            tk.Label(table_container, text="No hay productos", font=('Helvetica', 9), 
                    bg='white').grid(row=1, column=0, columnspan=4, pady=10)
        
        # ============================================================
        # TOTALES
        # ============================================================
        totales_frame = tk.Frame(ticket, bg='white')
        totales_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Configurar grid para totales
        totales_frame.columnconfigure(0, weight=1)
        totales_frame.columnconfigure(1, weight=1)
        
        # Subtotal
        tk.Label(totales_frame, text="Subtotal:", font=('Helvetica', 10), 
                bg='white', anchor='w').grid(row=0, column=0, sticky='w', pady=2)
        tk.Label(totales_frame, text=f"${total:.2f}", font=('Helvetica', 10), 
                bg='white', anchor='e').grid(row=0, column=1, sticky='e', pady=2)
        
        # Total destacado
        tk.Label(totales_frame, text="TOTAL:", font=('Helvetica', 14, 'bold'), 
                bg='white', fg='#2c3e50', anchor='w').grid(row=1, column=0, sticky='w', pady=2)
        tk.Label(totales_frame, text=f"${total:.2f}", font=('Helvetica', 14, 'bold'), 
                bg='white', fg='#27ae60', anchor='e').grid(row=1, column=1, sticky='e', pady=2)
        
        # Pagó
        tk.Label(totales_frame, text="Pagó:", font=('Helvetica', 11), 
                bg='white', anchor='w').grid(row=2, column=0, sticky='w', pady=2)
        tk.Label(totales_frame, text=f"${pagado:.2f}", font=('Helvetica', 11), 
                bg='white', anchor='e').grid(row=2, column=1, sticky='e', pady=2)
        
        # Vuelto (destacado)
        vuelto_frame = tk.Frame(ticket, bg='#27ae60')
        vuelto_frame.pack(fill=tk.X, padx=20, pady=10)
        
        tk.Label(vuelto_frame, text="VUELTO:", font=('Helvetica', 14, 'bold'), 
                bg='#27ae60', fg='white').pack(side=tk.LEFT, padx=15, pady=10)
        tk.Label(vuelto_frame, text=f"${vuelto:.2f}", font=('Helvetica', 20, 'bold'), 
                bg='#27ae60', fg='white').pack(side=tk.RIGHT, padx=15, pady=10)
        
        # ============================================================
        # PIE DE PÁGINA CON BOTONES
        # ============================================================
        footer_frame = tk.Frame(ticket, bg='#ecf0f1')
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        tk.Label(footer_frame, text="¡GRACIAS POR SU COMPRA!", 
                font=('Helvetica', 11, 'bold'), bg='#ecf0f1', fg='#2c3e50').pack(pady=5)
        
        btn_frame = tk.Frame(footer_frame, bg='#ecf0f1')
        btn_frame.pack(pady=5)
        
        # ============================================================
        # FUNCIÓN PARA GENERAR PDF
        # ============================================================
        def generar_pdf():
            try:
                from fpdf import FPDF
                from fpdf.enums import XPos, YPos
                import subprocess
                import sys
                import os
                
                pdf = FPDF()
                pdf.add_page()
                
                # Encabezado PDF
                pdf.set_font('Helvetica', 'B', 16)
                pdf.cell(0, 10, 'KIOSCO POS', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                
                pdf.set_font('Helvetica', '', 10)
                pdf.cell(0, 10, 'Comprobante de Venta', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                pdf.ln(5)
                
                # Información
                pdf.set_font('Helvetica', '', 10)
                pdf.cell(0, 6, f"Fecha: {fecha_actual}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.cell(0, 6, f"Comprobante N°: {venta_id:06d}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(5)
                
                # Productos - Encabezados
                pdf.set_font('Helvetica', 'B', 10)
                pdf.cell(80, 8, 'Producto', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(20, 8, 'Cant', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(30, 8, 'P.Unit', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                pdf.cell(40, 8, 'Total', border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
                
                # Productos - Detalle
                pdf.set_font('Helvetica', '', 9)
                if items:
                    for item in items:
                        pdf.cell(80, 6, item.nombre[:30], border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L')
                        pdf.cell(20, 6, str(item.cantidad), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
                        pdf.cell(30, 6, f"${item.precio_unitario:.2f}", border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
                        pdf.cell(40, 6, f"${item.subtotal:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
                
                # Totales
                pdf.ln(5)
                pdf.set_font('Helvetica', 'B', 12)
                pdf.cell(130, 8, 'TOTAL:', new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
                pdf.cell(40, 8, f"${total:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
                
                pdf.set_font('Helvetica', '', 10)
                pdf.cell(130, 6, 'Pagó:', new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
                pdf.cell(40, 6, f"${pagado:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
                
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(39, 174, 96)
                pdf.cell(130, 8, 'VUELTO:', new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
                pdf.cell(40, 8, f"${vuelto:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')
                
                # Guardar
                os.makedirs("comprobantes", exist_ok=True)
                fecha_file = datetime.now().strftime("%Y%m%d_%H%M%S")
                nombre_archivo = f"venta_{venta_id:06d}_{fecha_file}.pdf"
                ruta_completa = os.path.join("comprobantes", nombre_archivo)
                
                pdf.output(ruta_completa)
                
                if os.path.exists(ruta_completa):
                    messagebox.showinfo("PDF Generado", f"✅ Comprobante guardado en:\n{ruta_completa}")
                    if messagebox.askyesno("Abrir PDF", "¿Desea abrir el archivo?"):
                        try:
                            if sys.platform == 'win32':
                                os.startfile(ruta_completa)
                            else:
                                subprocess.run(['xdg-open', ruta_completa])
                        except:
                            messagebox.showinfo("Ubicación", f"El archivo está en:\n{ruta_completa}")
                else:
                    messagebox.showerror("Error", "No se pudo crear el archivo")
                    
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo generar PDF:\n{str(e)}")
        
        # ============================================================
        # BOTONES
        # ============================================================
        tk.Button(btn_frame, text="📄 Guardar PDF", font=('Helvetica', 9, 'bold'),
                 bg='#e67e22', fg='white', command=generar_pdf, width=12).pack(side=tk.LEFT, padx=5)
        
        tk.Button(btn_frame, text="✅ Cerrar", font=('Helvetica', 9, 'bold'),
                 bg='#3498db', fg='white', command=ticket.destroy, width=12).pack(side=tk.LEFT, padx=5)
        
        # ============================================================
        # AJUSTE AUTOMÁTICO DE TAMAÑO
        # ============================================================
        ticket.update_idletasks()  # Actualizar geometría
        
        # Calcular tamaño necesario
        ancho = ticket.winfo_reqwidth() + 50  # Añadir margen
        alto = ticket.winfo_reqheight() + 20
        
        # Centrar con el nuevo tamaño
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (ancho // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (alto // 2)
        
        ticket.geometry(f"{ancho}x{alto}+{x}+{y}")
        ticket.minsize(ancho, alto)  # Tamaño mínimo = tamaño necesario


# ============================================================================
# PESTAÑA DE VENTAS POS (RECUPERADA - NO SE DEBE DE BORRAR)
# ============================================================================

class PestañaVentas:
    """Pestaña de ventas POS."""
    
    def __init__(self, parent, servicio_producto: ServicioProducto, servicio_venta: ServicioVenta, callback_estado):
        self.parent = parent
        self.servicio_producto = servicio_producto
        self.servicio_venta = servicio_venta
        self.callback_estado = callback_estado
        
        panel = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg='#ecf0f1', sashwidth=5)
        panel.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        izq = tk.Frame(panel, bg='white')
        panel.add(izq, width=600)
        
        der = tk.Frame(panel, bg='white', width=400)
        panel.add(der)
        
        self.carrito = CarritoWidget(der, bg='white')
        self.carrito.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.btn_pagar = tk.Button(
            der,
            text="💳 PROCESAR PAGO (F12)",
            font=('Helvetica', 14, 'bold'),
            bg='#3498db',
            fg='white',
            command=self.procesar_pago,
            height=2
        )
        self.btn_pagar.pack(fill=tk.X, padx=10, pady=5)
        
        self.buscador = BuscadorPOS(izq, servicio_producto, self.carrito, callback_estado, bg='white')
        self.buscador.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        parent.bind_all('<F12>', lambda e: self.procesar_pago())
    
    def procesar_pago(self):
        items = self.carrito.obtener_items()
        if not items:
            messagebox.showwarning("Carrito vacío", "No hay productos en el carrito")
            return
        
        # Verificar stock nuevamente
        for item in items:
            producto = self.servicio_producto.repo.obtener_por_id(item.producto_id)
            if not producto or producto.cantidad < item.cantidad:
                messagebox.showerror("Error", f"Stock insuficiente para {item.nombre}")
                return
        
        total = self.carrito.obtener_total()
        dialogo = DialogoPago(self.parent, total)
        self.parent.wait_window(dialogo)
        
        if dialogo.resultado:
            # ✅ ACTUALIZAR STOCK - Esta línea es clave
            for item in items:
                self.servicio_producto.actualizar_stock(item.producto_id, item.cantidad)
            
            # Registrar venta
            exito, msg, venta_id = self.servicio_venta.procesar_venta(items, dialogo.resultado)
            
            if exito:
                vuelto = dialogo.monto_pagado - total
                TicketProfesional.mostrar_ticket(self.parent, venta_id, total, dialogo.monto_pagado, vuelto, items)
                self.carrito.limpiar()
                
                # 🔴 ACTUALIZAR TABLA DE PRODUCTOS
                self._actualizar_tabla_productos()
                
                if self.callback_estado:
                    self.callback_estado(f"Venta #{venta_id} - Vuelto: ${vuelto:.2f}")
            else:
                messagebox.showerror("Error", msg)

    def _actualizar_tabla_productos(self):
        """Busca la pestaña de productos y actualiza su tabla."""
        try:
            # Obtener el notebook (padre de esta pestaña)
            notebook = self.parent.master
            
            # Buscar en todas las pestañas del notebook
            for tab_id in range(notebook.index("end")):
                tab = notebook.nametowidget(notebook.tabs()[tab_id])
                # Buscar dentro de la pestaña algún widget con el método
                for child in tab.winfo_children():
                    if hasattr(child, 'actualizar_tabla_productos'):
                        child.actualizar_tabla_productos()
                        return
        except Exception as e:
            print(f"Error actualizando tabla de productos: {e}")


# ============================================================================
# PESTAÑA DE CAJA
# ============================================================================

class PestañaCaja:
    """Pestaña de gestión de caja."""
    
    def __init__(self, parent, servicio_venta: ServicioVenta, callback_estado):
        self.parent = parent
        self.servicio_venta = servicio_venta
        self.callback_estado = callback_estado
        
        self._crear_widgets()
        self.actualizar()
    
    def _crear_widgets(self):
        superior = tk.Frame(self.parent, bg='white', relief=tk.RAISED, bd=1)
        superior.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(
            superior,
            text="💰 ESTADO DE CAJA",
            font=('Helvetica', 14, 'bold'),
            bg='#2c3e50',
            fg='white'
        ).pack(fill=tk.X, pady=5)
        
        metrics = tk.Frame(superior, bg='white')
        metrics.pack(padx=20, pady=15)
        
        self.label_ventas = tk.Label(metrics, text="Total Ventas: $0.00", font=('Helvetica', 12), bg='white')
        self.label_ventas.pack(anchor='w', pady=2)
        
        self.label_retiros = tk.Label(metrics, text="Total Retiros: $0.00", font=('Helvetica', 12), bg='white', fg='#e67e22')
        self.label_retiros.pack(anchor='w', pady=2)
        
        self.label_efectivo = tk.Label(metrics, text="Efectivo en Caja: $0.00", font=('Helvetica', 14, 'bold'), bg='white', fg='#27ae60')
        self.label_efectivo.pack(anchor='w', pady=5)
        
        btn_frame = tk.Frame(superior, bg='white')
        btn_frame.pack(pady=10)
        
        tk.Button(
            btn_frame,
            text="💸 REGISTRAR RETIRO",
            font=('Helvetica', 11, 'bold'),
            bg='#e67e22',
            fg='white',
            command=self.registrar_retiro,
            width=20,
            height=2
        ).pack(side=tk.LEFT, padx=5)
        
        notebook = ttk.Notebook(superior)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        ventas_frame = tk.Frame(notebook, bg='white')
        notebook.add(ventas_frame, text="📊 Ventas del Día")
        self._crear_tabla_ventas(ventas_frame)
        
        retiros_frame = tk.Frame(notebook, bg='white')
        notebook.add(retiros_frame, text="💸 Retiros del Día")
        self._crear_tabla_retiros(retiros_frame)
        
        tk.Button(superior, text="🔄 Actualizar", command=self.actualizar).pack(pady=5)
    
    def _crear_tabla_ventas(self, parent):
        tree_frame = tk.Frame(parent, bg='white')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tree_ventas = ttk.Treeview(
            tree_frame,
            columns=('ID', 'Hora', 'Total', 'Método'),
            show='headings',
            height=8
        )
        
        self.tree_ventas.heading('ID', text='Venta #')
        self.tree_ventas.heading('Hora', text='Hora')
        self.tree_ventas.heading('Total', text='Total')
        self.tree_ventas.heading('Método', text='Método')
        
        for col in ['ID', 'Hora', 'Total', 'Método']:
            self.tree_ventas.column(col, width=100, anchor='center')
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_ventas.yview)
        self.tree_ventas.configure(yscrollcommand=vsb.set)
        
        self.tree_ventas.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
    
    def _crear_tabla_retiros(self, parent):
        tree_frame = tk.Frame(parent, bg='white')
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tree_retiros = ttk.Treeview(
            tree_frame,
            columns=('Hora', 'Monto', 'Concepto'),
            show='headings',
            height=8
        )
        
        self.tree_retiros.heading('Hora', text='Hora')
        self.tree_retiros.heading('Monto', text='Monto')
        self.tree_retiros.heading('Concepto', text='Concepto')
        
        self.tree_retiros.column('Hora', width=120, anchor='center')
        self.tree_retiros.column('Monto', width=100, anchor='center')
        self.tree_retiros.column('Concepto', width=200, anchor='w')
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree_retiros.yview)
        self.tree_retiros.configure(yscrollcommand=vsb.set)
        
        self.tree_retiros.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
    
    def actualizar(self):
        ventas = self.servicio_venta.obtener_ventas_dia()
        retiros = self.servicio_venta.obtener_retiros_dia()
        
        for item in self.tree_ventas.get_children():
            self.tree_ventas.delete(item)
        
        for item in self.tree_retiros.get_children():
            self.tree_retiros.delete(item)
        
        total_ventas = sum(v['total'] for v in ventas) if ventas else 0
        total_retiros = self.servicio_venta.total_retiros_dia()
        efectivo = total_ventas - total_retiros
        
        self.label_ventas.config(text=f"Total Ventas: ${total_ventas:.2f}")
        self.label_retiros.config(text=f"Total Retiros: ${total_retiros:.2f}")
        self.label_efectivo.config(text=f"Efectivo en Caja: ${efectivo:.2f}")
        
        for v in ventas:
            hora = datetime.strptime(v['fecha'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
            self.tree_ventas.insert('', tk.END, values=(
                f"#{v['id']:06d}",
                hora,
                f"${v['total']:.2f}",
                v['metodo_pago'].upper()
            ))
        
        for r in retiros:
            hora = datetime.strptime(r['fecha'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M')
            self.tree_retiros.insert('', tk.END, values=(
                hora,
                f"${r['monto']:.2f}",
                r['concepto']
            ))
    
    def registrar_retiro(self):
        dialogo = tk.Toplevel(self.parent)
        dialogo.title("Registrar Retiro")
        dialogo.geometry("400x300")
        dialogo.transient(self.parent)
        dialogo.grab_set()
        
        dialogo.update_idletasks()
        x = self.parent.winfo_rootx() + (self.parent.winfo_width() // 2) - (dialogo.winfo_width() // 2)
        y = self.parent.winfo_rooty() + (self.parent.winfo_height() // 2) - (dialogo.winfo_height() // 2)
        dialogo.geometry(f"+{x}+{y}")
        
        tk.Label(
            dialogo,
            text="RETIRO DE EFECTIVO",
            font=('Helvetica', 14, 'bold'),
            bg='#e67e22',
            fg='white'
        ).pack(fill=tk.X, pady=10, ipady=10)
        
        frame = tk.Frame(dialogo, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(frame, text="Monto a retirar:", font=('Helvetica', 11)).pack(anchor='w')
        entry_monto = tk.Entry(frame, font=('Helvetica', 14), justify='right')
        entry_monto.pack(fill=tk.X, pady=5)
        entry_monto.focus_set()
        
        tk.Label(frame, text="Concepto:", font=('Helvetica', 11)).pack(anchor='w', pady=(10,0))
        entry_concepto = tk.Entry(frame, font=('Helvetica', 12))
        entry_concepto.pack(fill=tk.X, pady=5)
        
        disponible = self.servicio_venta.total_retiros_dia()  # Simplificado
        
        tk.Label(frame, text=f"Disponible: ${disponible:.2f}", font=('Helvetica', 10), fg='#27ae60').pack(pady=10)
        
        def confirmar():
            try:
                monto = float(entry_monto.get())
                concepto = entry_concepto.get().strip()
                
                if not concepto:
                    messagebox.showerror("Error", "Ingrese un concepto")
                    return
                
                exito, msg = self.servicio_venta.registrar_retiro(monto, concepto, disponible)
                
                if exito:
                    messagebox.showinfo("Éxito", msg)
                    dialogo.destroy()
                    self.actualizar()
                    if self.callback_estado:
                        self.callback_estado(msg)
                else:
                    messagebox.showerror("Error", msg)
                    
            except ValueError:
                messagebox.showerror("Error", "Monto inválido")
        
        tk.Button(
            dialogo,
            text="Confirmar Retiro",
            font=('Helvetica', 12, 'bold'),
            bg='#e67e22',
            fg='white',
            command=confirmar,
            height=2
        ).pack(pady=10)


# ============================================================================
# APLICACIÓN PRINCIPAL
# ============================================================================

class KioscoPOSApp:
    """Aplicación principal."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("KIOSCO POS v5.0 - Sistema Profesional de Punto de Venta")
        self.root.geometry("1400x800")
        self.root.minsize(1200, 600)
        
        self.servicio_categoria = ServicioCategoria()
        self.servicio_producto = ServicioProducto()
        self.servicio_venta = ServicioVenta()
        
        self._inicializar_categorias_default()
        
        self.colores = {
            'primary': '#2c3e50',
            'secondary': '#34495e',
            'accent': '#3498db',
            'success': '#27ae60',
            'warning': '#e67e22',
            'danger': '#e74c3c',
            'light': '#ecf0f1'
        }
        
        self.root.configure(bg=self.colores['light'])
        
        self._crear_header()
        self._crear_statusbar()
        self._crear_notebook()
        self._centrar()
        
        self._actualizar_estado("✅ Sistema listo")
    
    def _inicializar_categorias_default(self):
        """Crea categorías por defecto si no existen."""
        if not self.servicio_categoria.obtener_todas():
            categorias_default = [
                Categoria(None, "BEBIDAS", "BEB", "Gaseosas, aguas, jugos"),
                Categoria(None, "SNACKS", "SNA", "Papas fritas, nachos, palitos"),
                Categoria(None, "GOLOSINAS", "GOL", "Chocolates, caramelos, chicles"),
                Categoria(None, "CIGARRILLOS", "CIG", "Marlboro, Parliament, Chesterfield"),
                Categoria(None, "ALMACÉN", "ALM", "Productos de almacén básicos"),
            ]
            
            for cat in categorias_default:
                self.servicio_categoria.agregar(cat)
    
    def _centrar(self):
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (w // 2)
        y = (self.root.winfo_screenheight() // 2) - (h // 2)
        self.root.geometry(f'{w}x{h}+{x}+{y}')
    
    def _crear_header(self):
        header = tk.Frame(self.root, bg=self.colores['primary'], height=80)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="🏪 KIOSCO POS v5.0",
            font=('Helvetica', 24, 'bold'),
            bg=self.colores['primary'],
            fg='white'
        ).pack(side=tk.LEFT, padx=30, pady=15)
        
        tk.Label(
            header,
            text="Sistema Profesional de Punto de Venta",
            font=('Helvetica', 12),
            bg=self.colores['primary'],
            fg='white'
        ).pack(side=tk.LEFT, padx=10, pady=20)
        
        self.label_hora = tk.Label(
            header,
            text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            font=('Helvetica', 11, 'bold'),
            bg=self.colores['primary'],
            fg='white'
        )
        self.label_hora.pack(side=tk.RIGHT, padx=30, pady=25)
        self._actualizar_hora()
    
    def _actualizar_hora(self):
        self.label_hora.config(text=datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        self.root.after(1000, self._actualizar_hora)
    
    def _crear_statusbar(self):
        status = tk.Frame(self.root, bg=self.colores['secondary'], height=30)
        status.pack(fill=tk.X, side=tk.BOTTOM)
        status.pack_propagate(False)
        
        self.label_estado = tk.Label(
            status,
            text="Iniciando...",
            bg=self.colores['secondary'],
            fg='white',
            font=('Helvetica', 9)
        )
        self.label_estado.pack(side=tk.LEFT, padx=10, pady=5)
        
        atajos = tk.Label(
            status,
            text="⚡ F1:Ayuda  F12:Pagar  ENTER:Agregar  |  📦 Categorías → Productos → Ventas",
            bg=self.colores['secondary'],
            fg='white',
            font=('Helvetica', 9)
        )
        atajos.pack(side=tk.RIGHT, padx=10, pady=5)
    
    def _crear_notebook(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TNotebook', background=self.colores['light'])
        style.configure('TNotebook.Tab', padding=[20, 8], font=('Helvetica', 11, 'bold'))
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        frame_categorias = ttk.Frame(self.notebook)
        self.notebook.add(frame_categorias, text="📁 CATEGORÍAS")
        self.pestana_categorias = PestañaCategorias(frame_categorias, self.servicio_categoria, self.servicio_producto,  # ← NUEVO PARÁMETRO
                                                    self._actualizar_estado
                                                    )
        
        frame_productos = ttk.Frame(self.notebook)
        self.notebook.add(frame_productos, text="📦 PRODUCTOS")
        self.pestana_productos = PestañaProductos(frame_productos, self.servicio_producto, self.servicio_categoria, self._actualizar_estado)
        
        frame_ventas = ttk.Frame(self.notebook)
        self.notebook.add(frame_ventas, text="💳 VENTAS POS")
        self.pestana_ventas = PestañaVentas(frame_ventas, self.servicio_producto, self.servicio_venta, self._actualizar_estado)
        
        frame_caja = ttk.Frame(self.notebook)
        self.notebook.add(frame_caja, text="💰 CAJA")
        self.pestana_caja = PestañaCaja(frame_caja, self.servicio_venta, self._actualizar_estado)
    
    def _actualizar_estado(self, msg):
        if hasattr(self, 'label_estado') and self.label_estado:
            self.label_estado.config(text=f"✅ {msg}")


# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

def main():
    root = tk.Tk()
    app = KioscoPOSApp(root)
    
    def al_cerrar():
        if messagebox.askokcancel("Salir", "¿Cerrar sistema POS?"):
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", al_cerrar)
    root.mainloop()

if __name__ == "__main__":
    main()