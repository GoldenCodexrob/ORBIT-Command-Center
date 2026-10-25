"""
BASE DE DATOS LOCAL DE ORBIT (SQLite)
=====================================
Guarda las interacciones del robot en un archivo local (orbit_history.db).
No requiere instalar nada: SQLite viene con Python.

Flujo: texto crudo -> filtro_texto.colar() -> aquí.
 - Aprobados  -> tabla 'interacciones'
 - Ruidosos   -> tabla 'rechazados' (por si quieres auditar qué se descarta)
 - Duplicados -> se contabilizan pero no se guardan dos veces
"""

import sqlite3
import datetime
from filtro_texto import colar


class OrbitLocalDB:
    def __init__(self, db_path="orbit_history.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._crear_tablas()

    def _crear_tablas(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS interacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                robot_id TEXT NOT NULL,
                texto TEXT NOT NULL,
                categoria TEXT NOT NULL,
                origen TEXT DEFAULT 'api',
                hash_texto TEXT UNIQUE,
                fecha_hora TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS rechazados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                robot_id TEXT,
                texto TEXT,
                motivo TEXT,
                fecha_hora TEXT NOT NULL
            )
        """)
        # Telemetría real que envía la Raspberry Pi 4 (batería, temp, etc.)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS telemetria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                robot_id TEXT NOT NULL,
                bateria REAL,
                temp_procesador REAL,
                sensores TEXT,
                motores TEXT,
                estado TEXT,
                csat REAL,
                qrs INTEGER,
                fecha_hora TEXT NOT NULL
            )
        """)
        self.conn.commit()

    # ----------------------------------------------------------
    # TELEMETRÍA (lo que mide la IA en la Raspberry Pi 4)
    # ----------------------------------------------------------
    def guardar_telemetria(self, robot_id, campos):
        """Guarda un reporte de la Pi. `campos` solo trae los datos enviados."""
        ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        columnas = list(campos.keys())
        valores = [campos[c] for c in columnas] + [robot_id, ahora]
        placeholders = ",".join("?" * len(columnas))
        self.conn.execute(
            f"INSERT INTO telemetria ({','.join(columnas)}, robot_id, fecha_hora)"
            f" VALUES ({placeholders},?,?)",
            valores)
        self.conn.commit()
        return {"resultado": "guardada", "robot_id": robot_id, "fecha_hora": ahora}

    def ultima_telemetria(self, robot_id=None):
        """Último reporte de telemetría recibido ({} si aún no hay ninguno)."""
        cur = self.conn.cursor()
        if robot_id:
            cur.execute(
                "SELECT bateria, temp_procesador, sensores, motores, estado,"
                " csat, qrs, fecha_hora FROM telemetria"
                " WHERE robot_id=? ORDER BY id DESC LIMIT 1", (robot_id,))
        else:
            cur.execute(
                "SELECT robot_id, bateria, temp_procesador, sensores, motores,"
                " estado, csat, qrs, fecha_hora FROM telemetria"
                " ORDER BY id DESC LIMIT 4")
        if robot_id:
            fila = cur.fetchone()
            return dict(fila) if fila else {}
        return [dict(fila) for fila in cur.fetchall()]

    # ----------------------------------------------------------
    # GUARDAR (pasando SIEMPRE por el colador)
    # ----------------------------------------------------------
    def guardar_interaccion(self, texto_crudo, robot_id="orbit_1", categoria=None, origen="api"):
        """
        Pasa el texto por el colador y lo guarda si es válido.
        Devuelve: {'resultado': 'guardada'|'duplicada'|'ruido', 'categoria': ...}
        """
        veredicto = colar(texto_crudo, categoria)
        ahora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if veredicto["estado"] == "ruido":
            self.conn.execute(
                "INSERT INTO rechazados (robot_id, texto, motivo, fecha_hora) VALUES (?,?,?,?)",
                (robot_id, veredicto["texto"], "texto_ruidoso_o_vacio", ahora)
            )
            self.conn.commit()
            return {"resultado": "ruido", "categoria": None}

        try:
            self.conn.execute(
                "INSERT INTO interacciones (robot_id, texto, categoria, origen, hash_texto, fecha_hora)"
                " VALUES (?,?,?,?,?,?)",
                (robot_id, veredicto["texto"], veredicto["categoria"], origen,
                 veredicto["hash"], ahora)
            )
            self.conn.commit()
            return {"resultado": "guardada", "categoria": veredicto["categoria"]}
        except sqlite3.IntegrityError:
            # hash duplicado: ya existe esa misma pregunta
            self.conn.execute(
                "INSERT INTO rechazados (robot_id, texto, motivo, fecha_hora) VALUES (?,?,?,?)",
                (robot_id, veredicto["texto"], "duplicado", ahora)
            )
            self.conn.commit()
            return {"resultado": "duplicada", "categoria": veredicto["categoria"]}

    # ----------------------------------------------------------
    # CONSULTAS PARA EL DASHBOARD
    # ----------------------------------------------------------
    def historial(self, robot_id=None, limite=50):
        """Últimas consultas aprobadas, opcionalmente de un robot."""
        cur = self.conn.cursor()
        if robot_id:
            cur.execute(
                "SELECT robot_id, texto, categoria, fecha_hora FROM interacciones"
                " WHERE robot_id=? ORDER BY id DESC LIMIT ?", (robot_id, limite))
        else:
            cur.execute(
                "SELECT robot_id, texto, categoria, fecha_hora FROM interacciones"
                " ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(fila) for fila in cur.fetchall()]

    def conteo_categorias(self, robot_id=None):
        """Conteo de consultas por categoría (para la gráfica)."""
        cur = self.conn.cursor()
        if robot_id:
            cur.execute(
                "SELECT categoria, COUNT(*) AS total FROM interacciones"
                " WHERE robot_id=? GROUP BY categoria ORDER BY total DESC", (robot_id,))
        else:
            cur.execute(
                "SELECT categoria, COUNT(*) AS total FROM interacciones"
                " GROUP BY categoria ORDER BY total DESC")
        return [dict(fila) for fila in cur.fetchall()]

    def total_interacciones(self, robot_id=None):
        cur = self.conn.cursor()
        if robot_id:
            cur.execute("SELECT COUNT(*) FROM interacciones WHERE robot_id=?", (robot_id,))
        else:
            cur.execute("SELECT COUNT(*) FROM interacciones")
        return cur.fetchone()[0]

    def resumen_colador(self):
        """Estadísticas del filtrado: cuántos entraron, cuántos pasaron, cuántos no."""
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM interacciones")
        aprobados = cur.fetchone()[0]
        cur.execute("SELECT motivo, COUNT(*) FROM rechazados GROUP BY motivo")
        rechazados = {fila[0]: fila[1] for fila in cur.fetchall()}
        total_rechazados = sum(rechazados.values())
        return {
            "aprobados": aprobados,
            "rechazados": total_rechazados,
            "detalle_rechazos": rechazados,
            "procesados": aprobados + total_rechazados,
        }

    def reclasificar_todo(self):
        """
        Vuelve a pasar todos los textos ya guardados por el colador.
        Útil cuando agregas nuevas categorías/palabras clave a filtro_texto.py
        y quieres que los datos viejos se reagrupen sin reimportar nada.
        """
        cur = self.conn.cursor()
        cur.execute("SELECT id, texto FROM interacciones")
        filas = cur.fetchall()
        cambios = 0
        for fila in filas:
            veredicto = colar(fila["texto"])   # ya está limpio, solo re-clasifica
            if veredicto["estado"] == "aprobado" and veredicto["categoria"]:
                cur.execute("UPDATE interacciones SET categoria=? WHERE id=?",
                            (veredicto["categoria"], fila["id"]))
                cambios += 1
        self.conn.commit()
        return {"textos_revisados": len(filas), "categorias_reasignadas": cambios}

    def cerrar(self):
        self.conn.close()


# ---------------------------------------------------------------
# USOS POR LÍNEA DE COMANDOS:
#   python db_local.py                 -> prueba rápida
#   python db_local.py reclasificar    -> re-agrupa todo con las categorías actuales
# ---------------------------------------------------------------
if __name__ == "__main__":
    import sys
    db = OrbitLocalDB("orbit_history.db")

    if len(sys.argv) > 1 and sys.argv[1] == "reclasificar":
        print("🔄 Reclasificando historial con las categorías actuales...")
        print(db.reclasificar_todo())
    else:
        print(db.guardar_interaccion("¿Dónde hay buenos hoteles en Margarita?", "orbit_1"))
        print(db.guardar_interaccion("¿Dónde hay buenos hoteles en Margarita?", "orbit_1"))  # duplicada
        print(db.guardar_interaccion("hola", "orbit_1"))                                    # ruido
        print("Historial:", db.historial())
        print("Resumen:", db.resumen_colador())

    db.cerrar()
