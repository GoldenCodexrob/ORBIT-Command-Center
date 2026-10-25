"""
COLADOR DE TEXTO DE ORBIT
=========================
Módulo de limpieza y filtrado básico de texto (sin dependencias externas).
Pasa cada texto por un embudo:
   1. limpiar_texto()  -> quita HTML, URLs, caracteres de control, normaliza espacios
   2. es_ruido()       -> detecta textos vacíos, demasiado cortos o sin palabras
   3. clasificar()     -> asigna categoría por palabras clave
   4. hash_texto()     -> huella para detectar duplicados exactos
"""

import re
import unicodedata

# ---------------------------------------------------------------
# PALABRAS CLAVE POR CATEGORÍA (lo básico que Orbit debe saber colar)
# El orden importa: gana la primera categoría que aparezca en el texto.
# Puedes agregar/quitar palabras libremente para "enseñarle" al colador.
# ---------------------------------------------------------------
PALABRAS_CLAVE = {
    "Comida": ["comida", "comer", "restaurante", "restorán", "asado", "arepa", "cachapa",
               "sopa", "desayuno", "almuerzo", "cena", "café", "cerveza", "mariscos",
               "menú", "menu", "pizza", "hamburguesa", "pollo", "pescado", "postre",
               "desayunar", "almorzar", "cenar", "comer", "helado", "jugo", "tragos"],

    "Supermercados": ["supermercado", "supermercados", "super", "mercado", "abastos",
                      "tienda", "tiendas", "panadería", "panaderia", "carnicería",
                      "carniceria", "verduras", "frutas", "compras", "carrito",
                      "carrito de compra", "económico", "economico", "precio", "oferta"],

    "Cultura": ["cultura", "museo", "museos", "teatro", "biblioteca", "música", "musica",
                "fiesta", "carnaval", "tradición", "tradicional", "artesanía", "artesania",
                "iglesia", "catedral", "festival", "galería", "galeria", "exposición",
                "exposicion", "historia", "monumento", "cultura", "danza", "folklore",
                "feria", "eventos", "celebración", "celebracion"],

    "Turismo": ["turismo", "tour", "tours", "playa", "playas", "mirador", "atracción",
                "atraccion", "visita", "visitas", "excursión", "excursion", "paseo",
                "parque", "parques", "natural", "naturaleza", "playa", "montaña",
                "montana", "camino", "conocer", "recomendar", "recomienda", "lugar",
                "sitios", "qué ver", "que ver"],

    "Transporte": ["transporte", "taxi", "bus", "autobus", "autobús", "metro", "cable",
                   "carro", "alquiler", "rentar", "gasolina", "ruta", "pasaje",
                   "caminar", "llegar", "cómo llego", "como llego", "parada", "terminal"],

    "Hoteles": ["hotel", "hoteles", "alojamiento", "hospedaje", "posada", "hostal",
                "resort", "habitación", "habitacion", "check-in", "reservar", "dormir",
                "pasar la noche", "alojarse"],

    "Vuelos": ["vuelo", "vuelos", "aeropuerto", "aerolinea", "aerolínea", "despegue",
               "aterrizaje", "boleto", "pasaje aéreo", "maiquetia", "maiquetía",
               "terminal aérea", "volar", "avión", "avion"],

    "Salud": ["farmacia", "médico", "medico", "hospital", "clínica", "clinica", "salud",
              "dolor", "emergencia", "ambulancia", "doctor", "medicinas", "pastillas"],
}

# Frases que suelen ser ruido en un robot (comandos internos, saludos vacíos, etc.)
IGNORAR_EXACTO = {
    "si", "sí", "no", "ok", "hola", "adios", "adiós", "gracias", "hello", "test", "prueba",
}

URL_REGEX = re.compile(r"https?://\S+|www\.\S+")
HTML_REGEX = re.compile(r"<[^>]+>")
CONTROL_REGEX = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def limpiar_texto(texto):
    """Limpieza básica: quita HTML, URLs, caracteres raros y normaliza espacios."""
    if not isinstance(texto, str):
        return ""

    texto = HTML_REGEX.sub(" ", texto)          # 1. etiquetas HTML
    texto = URL_REGEX.sub(" ", texto)           # 2. enlaces
    texto = unicodedata.normalize("NFC", texto)  # 3. normalizar tildes/letras
    texto = CONTROL_REGEX.sub(" ", texto)        # 4. caracteres de control
    texto = texto.lower()
    texto = re.sub(r"\s+", " ", texto).strip()   # 5. espacios múltiples -> uno
    return texto


def es_ruido(texto_limpio):
    """Devuelve True si el texto no aporta información útil."""
    if len(texto_limpio) < 3:
        return True
    if texto_limpio in IGNORAR_EXACTO:
        return True
    # Si no contiene ninguna letra (solo números o símbolos), es ruido
    if not re.search(r"[a-záéíóúñ]", texto_limpio):
        return True
    return False


def clasificar(texto_limpio, categoria_sugerida=None):
    """Asigna categoría por palabras clave. Si el usuario ya dio una, la respeta."""
    if categoria_sugerida:
        return categoria_sugerida

    for categoria, palabras in PALABRAS_CLAVE.items():
        for palabra in palabras:
            if palabra in texto_limpio:
                return categoria
    return "General"


def hash_texto(texto_limpio):
    """Huella del texto para detectar duplicados exactos."""
    import hashlib
    return hashlib.sha256(texto_limpio.encode("utf-8")).hexdigest()


def colar(texto_crudo, categoria_sugerida=None):
    """
    El colador completo. Devuelve un dict con el veredicto:
      {'estado': 'aprobado'|'ruido', 'texto': ..., 'categoria': ..., 'hash': ...}
    """
    texto = limpiar_texto(texto_crudo)

    if es_ruido(texto):
        return {"estado": "ruido", "texto": texto, "categoria": None, "hash": None}

    return {
        "estado": "aprobado",
        "texto": texto,
        "categoria": clasificar(texto, categoria_sugerida),
        "hash": hash_texto(texto),
    }


# ---------------------------------------------------------------
# PRUEBA RÁPIDA:  python filtro_texto.py
# ---------------------------------------------------------------
if __name__ == "__main__":
    pruebas = [
        "<p>¿Dónde puedo comer el mejor asado cerca del aeropuerto?</p>",
        "   ¿Qué   horario tiene   el vuelo a Maiquetía?  ",
        "http://spam.ejemplo.com mira esta oferta",
        "hola",
        "12345",
        "<b>Hoteles</b> buenos en Margarita para la próxima semana",
        "¿Cómo llego en bus a la playa?",
    ]
    for t in pruebas:
        print(colar(t))
