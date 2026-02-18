# 🏪 KIOSCO POS v5.0 - Sistema de Gestión de Ventas e Inventario

![Python](https://img.shields.io/badge/python-3.8%2B-green)
![SQLite](https://img.shields.io/badge/database-SQLite-blue)
![License](https://img.shields.io/badge/license-MIT-orange)

**KIOSCO POS** es una solución integral desarrollada en Python para la administración de pequeños comercios. Este proyecto nació durante mi formación en la "Semana de Python en la Práctica", evolucionando desde un gestor de stock básico hasta un sistema de punto de venta robusto con interfaz gráfica profesional.

---

## ✨ Características Destacadas

### 💳 Ventas POS y Facturación
- **Interfaz Ágil:** Carrito de compras con cálculo automático de totales y vuelto en tiempo real.
- **Comprobantes Profesionales:** Generación de tickets con diseño corporativo, incluyendo logo y detalles de la transacción, listos para guardar en PDF.
- **Atajos de Teclado:** Optimizado para la velocidad del negocio (`F12` para pagar, `ENTER` para agregar).

### 📦 Gestión de Inventario (Semáforo de Stock)
- **Alertas Visuales:** Implementación de un sistema de colores para reposición inmediata:
  - ⚫ **AGOTADO:** Stock en cero.
  - 🔴 **CRÍTICO:** Stock igual o menor al mínimo establecido.
  - 🟡 **BAJO:** Stock próximo a agotarse (menor al doble del mínimo).
  - 🟢 **NORMAL:** Stock suficiente para la venta.
- **Ordenamiento Dinámico:** Filtros para ver productos por stock bajo o alfabéticamente.
- **Edición Rápida:** Panel inferior para actualizar precios y cantidades sin cambiar de ventana.

### 💰 Control de Caja
- Registro de ingresos por ventas y egresos por retiros de caja.
- Reportes diarios para el cierre de jornada.

---


## 🛠️ Tecnologías Utilizadas
- **Lenguaje:** Python 3.x
- **Interfaz Gráfica:** Tkinter (Tema 'clam' para personalización avanzada)
- **Base de Datos:** SQLite (Persistencia de datos en `eco_stock.db`)
- **Librerías Extra:** `fpdf2` (para la generación de comprobantes PDF).

---

## 🚀 Cómo empezar

1. Cloná el repositorio:
   ```bash
   git clone [https://github.com/Cristofer1210/kiosco-pos.git](https://github.com/Cristofer1210/kiosco-pos.git)

2. Instalá las dependencias:

  pip install fpdf2

3. Ejecutá la aplicación:

  python src/kiosco_pos.py
  
📬 Contacto
Desarrollador: Cristofer

Estado: Aprendiendo y construyendo día a día 🚀

LinkedIn: (https://www.linkedin.com/in/cristofer-gallay-080577264/)
