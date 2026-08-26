#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pase.py - Decide QUE pase toca publicar, y lo decide bien.

POR QUE EXISTE ESTE ARCHIVO
---------------------------
La version anterior de esta decision vivia dentro de publish.yml y era esta:

    slot = {9: "09h", 12: "12h", 16: "16h", 19: "19h", 21: "21h"}.get(ahora.hour)

O sea: el pase solo salia si el trabajo ARRANCABA dentro de la hora exacta. Eso
da una ventana de 60 minutos. Y los cron de GitHub Actions no son puntuales: en
este mismo repositorio, entre el 24 y el 26 de agosto de 2026, los disparos
llegaron con 15, 18, 19, 34, 35, 36, 39, 46 y 51 minutos de retraso. La mediana
esta en 35 minutos. GitHub avisa en su documentacion de que los cron pueden
retrasarse "durante periodos de mucha carga" y de que incluso pueden perderse.

Con una ventana de 60 minutos y un retraso mediano de 35, el margen real son 25
minutos. El 26 de agosto de 2026 el disparo de las 15:00 UTC llego pasada la
hora, la guarda dijo "no toca" y el pase de las 16:00 de Canarias se perdio. Y
como no habia nada que reintentara, se perdio PARA SIEMPRE.

QUE HACE AHORA
--------------
No mira el reloj para preguntarse "¿es justo mi hora?". Mira lo que se DEBE:

    de los cinco pases de hoy, ¿cuales ya han pasado de hora y siguen sin
    publicar? Publica el mas antiguo de esos.

Con eso, un disparo que llega tarde sigue haciendo el trabajo que debia, y un
disparo que GitHub se coma directamente lo recoge el siguiente. Deja de importar
si GitHub es puntual, que es justo lo que no podemos controlar.

Reglas:
  1. Un pase se debe si su hora de Canarias ya ha pasado hoy y no hay ninguna
     entrada de hoy con ese pase marcada como publicada.
  2. Si hay algo en la cola sin publicar, eso va primero: se termina lo empezado
     antes de generar nada nuevo.
  3. Se publica UN pase por disparo. Si se deben dos, el otro sale en el
     siguiente. Asi un dia de recuperacion no suelta tres reels de golde.
  4. Un pase con mas de MAX_RETRASO horas de retraso ya no se publica: colgar el
     reel de las 9 de la manana a las 9 de la noche es peor que no colgarlo. Se
     avisa en el registro, en alto, para que se vea. No se pierde en silencio.

Uso:
    python pase.py                      -> decide solo
    python pase.py --manual 16h         -> lo fuerza (workflow_dispatch)
    python pase.py --ahora 2026-08-26T17:15   -> simula una hora (para pruebas)
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(AQUI, "posts.json")
CANARIAS = ZoneInfo("Atlantic/Canary")

# Pase -> hora de Canarias a la que le toca.
HORAS = {"09h": 9, "12h": 12, "16h": 16, "19h": 19, "21h": 21}

# Cuantas horas de retraso admitimos antes de dar un pase por perdido.
MAX_RETRASO = 3

PATRON = re.compile(r"^reel-(\d{4}-\d{2}-\d{2})-(\d{2}h)-")


def cargar_posts():
    if not os.path.exists(POSTS):
        return []
    try:
        with open(POSTS, "r", encoding="utf-8") as f:
            datos = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Un posts.json roto no puede tumbar el pase: se trata como cola vacia
        # y el resto del flujo generara uno nuevo.
        return []
    return datos if isinstance(datos, list) else datos.get("posts", [])


def decidir(ahora, posts):
    """Devuelve (seguir, slot, motivo, perdidos). No toca nada de fuera."""
    hoy = ahora.date().isoformat()

    publicados, en_cola = set(), []
    for e in posts:
        m = PATRON.match(e.get("file", "") or "")
        if not m or m.group(1) != hoy:
            continue
        if e.get("posted"):
            publicados.add(m.group(2))
        else:
            en_cola.append(m.group(2))

    # Regla 2: lo que ya esta generado y sin publicar va primero.
    if en_cola:
        slot = sorted(en_cola, key=lambda s: HORAS.get(s, 99))[0]
        return True, slot, f"hay un video de las {slot} en la cola sin publicar; se termina eso", []

    # Regla 1: pases de hoy cuya hora ya paso y que no estan publicados.
    debidos = []
    for slot, hora in sorted(HORAS.items(), key=lambda kv: kv[1]):
        if slot in publicados:
            continue
        toca = ahora.replace(hour=hora, minute=0, second=0, microsecond=0)
        if ahora >= toca:
            debidos.append((slot, ahora - toca))

    if not debidos:
        return False, "", f"en Canarias son las {ahora:%H:%M} y no hay ningun pase pendiente", []

    # Regla 4: los que llevan demasiado retraso se descartan, pero en alto.
    vivos = [(s, r) for s, r in debidos if r <= timedelta(hours=MAX_RETRASO)]
    # Solo se avisa de un pase perdido en la hora siguiente a que cruce el
    # limite. Si no, un pase perdido por la manana llena el registro de avisos
    # el resto del dia y se deja de leer, que es como se pierden los avisos que
    # si importan.
    perdidos = [(s, r) for s, r in debidos
                if timedelta(hours=MAX_RETRASO) < r <= timedelta(hours=MAX_RETRASO + 1)]

    if not vivos:
        return False, "", (f"en Canarias son las {ahora:%H:%M}; todo lo pendiente "
                           f"lleva mas de {MAX_RETRASO} h de retraso"), perdidos

    # Regla 3: uno solo, el mas antiguo de los que siguen a tiempo.
    slot, retraso = vivos[0]
    mins = int(retraso.total_seconds() // 60)
    if mins < 60:
        motivo = f"toca el pase de las {slot} (son las {ahora:%H:%M} de Canarias)"
    else:
        motivo = (f"RECUPERANDO el pase de las {slot}: lleva {mins // 60} h "
                  f"{mins % 60} min de retraso y no se habia publicado")
    if len(vivos) > 1:
        motivo += f". Tambien se deben {', '.join(s for s, _ in vivos[1:])}: saldran en los siguientes disparos"
    return True, slot, motivo, perdidos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", default="", help="pase forzado desde workflow_dispatch")
    ap.add_argument("--ahora", default="", help="hora simulada ISO, solo para pruebas")
    args = ap.parse_args()

    if args.ahora:
        ahora = datetime.fromisoformat(args.ahora).replace(tzinfo=CANARIAS)
    else:
        ahora = datetime.now(CANARIAS)

    if args.manual:
        seguir, slot, motivo, perdidos = True, args.manual, "lanzado a mano", []
    else:
        seguir, slot, motivo, perdidos = decidir(ahora, cargar_posts())

    for s, r in perdidos:
        mins = int(r.total_seconds() // 60)
        print(f"::warning title=Pase perdido::El pase de las {s} de hoy lleva "
              f"{mins // 60} h {mins % 60} min sin publicar. Se descarta: "
              f"colgarlo ya seria peor que no colgarlo.")

    salida = os.environ.get("GITHUB_OUTPUT")
    lineas = [f"seguir={'si' if seguir else 'no'}", f"slot={slot}", f"motivo={motivo}"]
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write("\n".join(lineas) + "\n")
    print(motivo)
    for l in lineas:
        print(f"  {l}")


if __name__ == "__main__":
    main()
