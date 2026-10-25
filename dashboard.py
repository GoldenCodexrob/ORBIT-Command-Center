import sys
import collections
import random
from datetime import datetime, timedelta

# Consolas de Windows usan cp1252 y truenan con emojis/UTF-8: forzamos UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from flask import Flask, jsonify, request, send_from_directory
from db_local import OrbitLocalDB

app = Flask(__name__)

# ---------------------------------------------------------------
# BASE DE DATOS REAL (SQLite local, funciona sin internet ni credenciales)
# ---------------------------------------------------------------
orbit_db = OrbitLocalDB("orbit_history.db")

# Firebase queda como opcional para el futuro
try:
    from orbit_db import OrbitCloudDB
    orbit_cloud = OrbitCloudDB("firebase_credentials.json")
    print("☁️  Firebase conectado. También se replicarán las consultas aprobadas.")
except Exception:
    orbit_cloud = None
    print("ℹ️  Modo local: usando SQLite (orbit_history.db). Firebase desactivado.")

# ---------------------------------------------------------------
# DATOS SIMULADOS (solo hardware: baterías, QRs...)
# El HISTORIAL de consultas viene 100% de la base de datos real
# ---------------------------------------------------------------
FLOTA = {
    "orbit_1": {"nombre": "Orbit 1 - Maiquetía", "color": "#10B981", "bateria": 85, "estado": "Activo", "qrs": 1420, "csat": 4.8},
    "orbit_2": {"nombre": "Orbit 2 - Barcelona", "color": "#06B6D4", "bateria": 92, "estado": "Activo", "qrs": 840, "csat": 4.9},
    "orbit_3": {"nombre": "Orbit 3 - Margarita", "color": "#F59E0B", "bateria": 45, "estado": "Cargando", "qrs": 2150, "csat": 4.7},
    "orbit_4": {"nombre": "Orbit 4 - Puerto Rico", "color": "#8B5CF6", "bateria": 100, "estado": "Desplegando", "qrs": 120, "csat": 5.0}
}

PATROCINADORES = {
    "orbit_1": [{"id": 1, "nombre": "Conviasa", "activo": True, "vistas": 450}, {"id": 2, "nombre": "Café Amanecer", "activo": True, "vistas": 890}],
    "orbit_2": [{"id": 3, "nombre": "Avior", "activo": True, "vistas": 320}],
    "orbit_3": [{"id": 4, "nombre": "Hotel Lidotel", "activo": True, "vistas": 1200}, {"id": 5, "nombre": "Ferrys", "activo": False, "vistas": 50}],
    "orbit_4": [{"id": 6, "nombre": "Turismo PR", "activo": True, "vistas": 80}]
}


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


# ===============================================================
# ENDPOINT DE INGESTA: el robot envía cada consulta por aquí.
# El texto SIEMPRE pasa por el colador antes de guardarse.
# ===============================================================
@app.route('/api/interacciones', methods=['POST'])
def recibir_interaccion():
    datos = request.get_json(silent=True) or {}
    texto = datos.get('texto') or datos.get('pregunta') or ''
    robot_id = datos.get('robot_id', 'orbit_1')
    categoria = datos.get('categoria')

    if not texto:
        return jsonify({"error": "Falta el campo 'texto'"}), 400

    resultado = orbit_db.guardar_interaccion(texto, robot_id, categoria, origen="robot")

    # Si hay Firebase conectado, replicamos solo lo que el colador aprobó
    if orbit_cloud and resultado.get("resultado") == "guardada":
        try:
            orbit_cloud.registrar_pregunta(resultado["categoria"], texto)
        except Exception as e:
            print(f"⚠️  No se pudo replicar a Firebase: {e}")

    estado_http = 201 if resultado["resultado"] == "guardada" else 200
    return jsonify({"robot_id": robot_id, **resultado}), estado_http


# ===============================================================
# HISTORIAL FILTRADO
# ===============================================================
@app.route('/api/historial')
def historial():
    robot_id = request.args.get('robot_id')
    limite = request.args.get('limite', 50, type=int)
    return jsonify(orbit_db.historial(robot_id, limite))


# ===============================================================
# ESTADO DEL COLADOR
# ===============================================================
@app.route('/api/colador')
def estado_colador():
    return jsonify(orbit_db.resumen_colador())


# ===============================================================
# DATOS DEL DASHBOARD
# ===============================================================
@app.route('/api/flota')
def datos_flota():
    total_qrs = sum(r["qrs"] for r in FLOTA.values())
    bateria_promedio = sum(r["bateria"] for r in FLOTA.values()) // len(FLOTA)
    activos = sum(1 for r in FLOTA.values() if r["estado"] == "Activo")

    analytics = {}
    for oid in FLOTA.keys():
        historial_robot = [
            {"categoria": h["categoria"], "pregunta": h["texto"], "fecha": h["fecha_hora"]}
            for h in orbit_db.historial(robot_id=oid, limite=8)
        ]
        conteo = orbit_db.conteo_categorias(robot_id=oid)
        analytics[oid] = {
            "historial": historial_robot,
            "grafica": {
                "labels": [c["categoria"] for c in conteo],
                "valores": [c["total"] for c in conteo]
            }
        }

    return jsonify({
        "global": {
            "total_qrs": total_qrs,
            "bateria_promedio": bateria_promedio,
            "robots_activos": activos,
            "total_robots": len(FLOTA),
            "consultas_reales": orbit_db.total_interacciones()
        },
        "robots": FLOTA,
        "patrocinadores": PATROCINADORES,
        "analytics": analytics,
        "colador": orbit_db.resumen_colador(),
        "fuente": "base_datos_local"
    })


if __name__ == '__main__':
    print("=" * 50)
    print("🌐 FLEET COMMAND CENTER DE ORBIT")
    print("=" * 50)
    print(f"📊 Consultas aprobadas en la base: {orbit_db.total_interacciones()}")
    print(f"🧹 Colador: {orbit_db.resumen_colador()['aprobados']} aprobadas / {orbit_db.resumen_colador()['rechazados']} descartadas")
    print("📮 Robot -> POST http://127.0.0.1:5000/api/interacciones")
    print("🌍 Web   -> http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True, port=5000)
