#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar.py · versión «lote» · 5 de septiembre de 2026

Ya no dibuja nada. Los vídeos los hace el motor de Lavandera Design en el
ordenador de Jorge (nueva web lavandera/herramientas/videos/motor.mjs) sobre
las grabaciones REALES de las doce demos y de The Ocean's Fisher, y llegan al
repositorio ya montados: la carpeta lote/ con los .mp4 y lote/cola.json con el
texto de cada uno.

Este archivo sólo ELIGE la pieza que toca y la deja donde el bot la espera.
encolar.py lo llama igual que llamaba al generador antiguo
(--slot, --variante, --out, --json) y recibe el mismo JSON {file, caption,
posted}. pase.py, publish.py, comprobar_url.py y el workflow no cambian.

Cómo elige:
  1. la pieza de HOY (hora de Canarias) y de ESTE pase: reel-AAAA-MM-DD-NNh-…;
  2. si no existe, la más antigua del lote que aún no esté en posts.json, para
     que un pase perdido no deje un vídeo huérfano;
  3. si el lote está vacío, error claro: toca generar y subir el siguiente.

    python generar.py --slot 12h --out videos --json
    python generar.py --slot 16h --fecha 2026-09-10        (probar en local)
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

AQUI = os.path.dirname(os.path.abspath(__file__))
LOTE = os.path.join(AQUI, "lote")
COLA = os.path.join(LOTE, "cola.json")
POSTS = os.path.join(AQUI, "posts.json")
FUENTES = os.path.join(AQUI, "fuentes")
SLOTS = ["09h", "12h", "16h", "19h", "21h"]
AVISAR_CUANDO_QUEDEN = 10

# encolar.purgar_fuentes() borra de fuentes/ el metraje que ningún PROYECTO use.
# Aquí se declara todo lo que hay para que NO borre nada: el metraje del
# generador antiguo (generar_pillow.py) se queda por si hace falta volver.
PROYECTOS = [
    {"id": f, "nombre": f, "movil": f, "escritorio": None}
    for f in (sorted(os.listdir(FUENTES)) if os.path.isdir(FUENTES) else [])
    if f.lower().endswith(".mp4")
]


def cargar(ruta, por_defecto):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return por_defecto


def resumen(texto):
    """Deja una línea en el resumen del job de GitHub Actions, que sí se lee
    aunque encolar.py capture la salida de este proceso."""
    ruta = os.environ.get("GITHUB_STEP_SUMMARY")
    if ruta:
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(texto + "\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="12h", choices=SLOTS)
    ap.add_argument("--out", default=os.path.join(AQUI, "videos"))
    ap.add_argument("--fecha", default=None, help="AAAA-MM-DD; por defecto, hoy en Canarias")
    # Estos tres se admiten por compatibilidad con encolar.py; aquí no hacen nada.
    ap.add_argument("--variante", default="instagram")
    ap.add_argument("--apertura", default="directo")
    ap.add_argument("--nombre", default=None)
    ap.add_argument("--json", action="store_true", help="imprime {file, caption, posted}")
    args = ap.parse_args()

    hoy = args.fecha or datetime.now(ZoneInfo("Atlantic/Canary")).date().isoformat()

    cola = cargar(COLA, [])
    posts = cargar(POSTS, [])
    if not isinstance(posts, list):
        posts = posts.get("posts", [])
    usados = {p.get("file") for p in posts}

    disponibles = [
        e for e in cola
        if e.get("file") and e["file"] not in usados
        and os.path.exists(os.path.join(LOTE, e["file"]))
    ]
    if not disponibles:
        resumen("### ⚠️ Lote agotado\nNo queda ninguna pieza en `lote/`. Genera el "
                "siguiente lote en el ordenador y súbelo con publicar.mjs.")
        raise SystemExit(
            "[ERROR] LOTE AGOTADO: no queda ninguna pieza en lote/. En el ordenador: "
            "node herramientas/videos/motor.mjs cola AAAA-MM-DD  y después  "
            "node herramientas/videos/publicar.mjs")

    prefijo = f"reel-{hoy}-{args.slot}-"
    eleccion = next((e for e in disponibles if e["file"].startswith(prefijo)), None)
    motivo = "la pieza de hoy y de este pase"
    if eleccion is None:
        disponibles.sort(key=lambda e: e["file"])
        eleccion = disponibles[0]
        motivo = f"no había pieza {prefijo}*: sale la más antigua sin publicar"

    os.makedirs(args.out, exist_ok=True)
    destino = os.path.join(args.out, eleccion["file"])
    if not os.path.exists(destino):
        shutil.copyfile(os.path.join(LOTE, eleccion["file"]), destino)

    quedan = len(disponibles) - 1
    if quedan < AVISAR_CUANDO_QUEDEN:
        resumen(f"### ⚠️ Quedan {quedan} piezas en el lote\nGenera y sube el siguiente "
                f"antes de que se acabe (`motor.mjs cola` + `publicar.mjs`).")
    resumen(f"Pieza: `{eleccion['file']}` · {motivo} · quedan {quedan} en el lote.")

    salida = {"file": eleccion["file"], "caption": eleccion.get("caption", ""), "posted": False}
    if args.json:
        print(json.dumps(salida, ensure_ascii=False))
    else:
        print(f"[OK] {destino}")
        print(f"     {motivo}")
        print(f"     quedan {quedan} piezas en el lote")


if __name__ == "__main__":
    main()
