#!/usr/bin/env python3
"""
CLIENTE DE ORBIT — para la Raspberry Pi del robot
==================================================
Envía cada consulta del robot al colador del dashboard (POST /api/interacciones).

Características:
 - Solo usa la biblioteca estándar (no instala nada en la Pi).
 - Si el servidor no responde (sin internet/red), guarda la consulta en
   cola_envio.json y la reenvía después con --reintentar. ¡Nunca se pierde nada!

Uso desde la línea de comandos:
    python orbit_enviar.py "¿Dónde hay un supermercado cerca?"
    python orbit_enviar.py --robot orbit_2 "¿Qué museos hay en Barcelona?"
    python orbit_enviar.py --url http://192.168.1.50:5000 "¿Buenos restaurantes?"
    python orbit_enviar.py --reintentar          # envía todo lo pendiente

Uso desde TU CÓDIGO DEL ROBOT:
    from orbit_enviar import enviar_consulta
    enviar_consulta("¿Dónde puedo comer arepas?", robot_id="orbit_1")
"""

import sys
import os
import json
import argparse
import datetime
import urllib.request
import urllib.error

# La consola de Windows/terminal puede tronar con acentos: forzamos UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Dirección del dashboard: se puede cambiar con --url o la variable ORBIT_API_URL
URL_POR_DEFECTO = os.environ.get("ORBIT_API_URL", "http://127.0.0.1:5000")
ARCHIVO_COLA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cola_envio.json")


def enviar_consulta(texto, robot_id="orbit_1", categoria=None, url=None, timeout=6):
    """
    Envía una consulta al colador del dashboard.
    Devuelve (exito: bool, respuesta: dict | str).
    """
    destino = (url or URL_POR_DEFECTO).rstrip("/") + "/api/interacciones"
    cuerpo = {"robot_id": robot_id, "texto": texto}
    if categoria:
        cuerpo["categoria"] = categoria

    req = urllib.request.Request(
        destino,
        data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------
# COLA OFFLINE: si el servidor no está disponible, la consulta
# se guarda en disco y se reenvía luego (nada se pierde).
# ---------------------------------------------------------------
def _cargar_cola():
    if os.path.exists(ARCHIVO_COLA):
        try:
            with open(ARCHIVO_COLA, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _guardar_cola(cola):
    with open(ARCHIVO_COLA, "w", encoding="utf-8") as f:
        json.dump(cola, f, ensure_ascii=False, indent=2)


def encolar(texto, robot_id="orbit_1", categoria=None):
    cola = _cargar_cola()
    cola.append({
        "texto": texto,
        "robot_id": robot_id,
        "categoria": categoria,
        "fecha": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _guardar_cola(cola)
    print(f"📴 Sin conexión: consulta guardada en cola (pendientes: {len(cola)})")


def reintentar_cola(url=None):
    """Reenvía todas las consultas pendientes. Devuelve (enviadas, fallidas)."""
    cola = _cargar_cola()
    if not cola:
        print("✅ No hay consultas pendientes en la cola.")
        return 0, 0

    print(f"🔁 Reintentando enviar {len(cola)} consultas pendientes...")
    pendientes = []
    enviadas = 0
    for item in cola:
        ok, resp = enviar_consulta(item["texto"], item["robot_id"],
                                   item.get("categoria"), url=url)
        if ok:
            enviadas += 1
        else:
            pendientes.append(item)

    _guardar_cola(pendientes)
    print(f"   ✔ Enviadas: {enviadas}   ❌ Aún pendientes: {len(pendientes)}")
    return enviadas, len(pendientes)


def main():
    parser = argparse.ArgumentParser(description="Envía consultas de ORBIT al colador")
    parser.add_argument("textos", nargs="*", help="Consulta(s) a enviar")
    parser.add_argument("--robot", default="orbit_1", help="ID del robot (orbit_1...orbit_4)")
    parser.add_argument("--url", default=None, help="URL del dashboard, ej: http://192.168.1.50:5000")
    parser.add_argument("--categoria", default=None, help="Categoría sugerida (opcional)")
    parser.add_argument("--reintentar", action="store_true", help="Reenviar la cola offline")
    args = parser.parse_args()

    if args.reintentar:
        reintentar_cola(args.url)
        return

    if not args.textos:
        parser.print_help()
        return

    for texto in args.textos:
        ok, resp = enviar_consulta(texto, args.robot, args.categoria, url=args.url)
        if ok:
            estado = resp.get("resultado", "?")
            icono = {"guardada": "✅", "duplicada": "⏭️", "ruido": "🗑️"}.get(estado, "ℹ️")
            print(f"{icono} '{texto[:60]}' -> {estado}"
                  + (f" ({resp.get('categoria')})" if resp.get("categoria") else ""))
        else:
            print(f"❌ No se pudo conectar al dashboard: {resp}")
            encolar(texto, args.robot, args.categoria)
            print("   Usa 'python orbit_enviar.py --reintentar' cuando vuelva la conexión.")


if __name__ == "__main__":
    main()
