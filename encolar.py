#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encolar.py - Prepara los dos videos de cada pase.

INSTAGRAM: si posts.json no tiene ningun video pendiente, genera uno nuevo y lo
anade a la cola para que publish.py lo publique. Cinco pases al dia: 09h, 12h,
16h, 19h y 21h, hora de Canarias.

Los videos de TikTok NO salen de aqui: los hace lote.py, 10 al dia.

Ademas limpia del repositorio los .mp4 antiguos para que no crezca sin control.

Uso:
    python encolar.py --slot 16h
    python encolar.py --slot 12h --forzar     (regenera aunque ya haya cola)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import date

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(AQUI, "fuentes")
POSTS = os.path.join(AQUI, "posts.json")
VIDEOS = os.path.join(AQUI, "videos")

# Cuantos videos conservamos en el repo antes de borrar los .mp4 mas antiguos.
CONSERVAR = 6


def cargar(ruta, por_defecto):
    if not os.path.exists(ruta):
        return por_defecto
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return por_defecto


def guardar(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)


def generar(slot, variante, destino):
    """Llama a generar.py y devuelve el dict con file y caption."""
    proc = subprocess.run(
        [sys.executable, os.path.join(AQUI, "generar.py"),
         "--slot", slot, "--variante", variante, "--out", destino, "--json"],
        capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(f"[ERROR] generar.py fallo con la variante {variante}.")

    lineas = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if not lineas:
        sys.stdout.write(proc.stdout)
        raise SystemExit(f"[ERROR] generar.py no devolvio JSON ({variante}).")

    entrada = json.loads(lineas[-1])
    ruta = os.path.join(destino, entrada["file"])
    if not os.path.exists(ruta):
        raise SystemExit(f"[ERROR] El video no existe: {ruta}")

    tam = os.path.getsize(ruta) / 1_000_000
    if tam > 90:
        raise SystemExit(f"[ERROR] {entrada['file']} pesa {tam:.1f} MB; GitHub no "
                         f"admite archivos de mas de 100 MB.")
    entrada["_mb"] = round(tam, 1)
    return entrada


def limpiar(lista, carpeta, conservar, clave_hecho=None):
    """Borra los .mp4 mas antiguos. Las entradas se conservan en el JSON para
    no repetir contenido; lo que desaparece es solo el archivo."""
    if clave_hecho:
        candidatos = [e for e in lista if e.get(clave_hecho)]
    else:
        candidatos = list(lista)
    if len(candidatos) <= conservar:
        return 0
    borrados = 0
    for e in candidatos[:-conservar]:
        ruta = os.path.join(carpeta, e["file"])
        if os.path.exists(ruta):
            os.remove(ruta)
            borrados += 1
    if borrados:
        print(f"[LIMPIEZA] {borrados} mp4 antiguos eliminados de {os.path.basename(carpeta)}/")
    return borrados


def purgar_fuentes():
    """Borra de fuentes/ cualquier .mp4 que ya no use ningun proyecto.

    Sirve para que el metraje retirado (por ejemplo, marcas de las que no
    tenemos permiso) desaparezca del repositorio solo, sin borrarlo a mano.
    """
    if not os.path.isdir(FUENTES):
        return 0
    sys.path.insert(0, AQUI)
    import generar
    usados = set()
    for pr in generar.PROYECTOS:
        for k in ("movil", "escritorio"):
            if pr.get(k):
                usados.add(pr[k])
    borrados = []
    for f in sorted(os.listdir(FUENTES)):
        if f.lower().endswith(".mp4") and f not in usados:
            os.remove(os.path.join(FUENTES, f))
            borrados.append(f)
    if borrados:
        print(f"[LIMPIEZA] {len(borrados)} metrajes retirados de fuentes/: "
              + ", ".join(borrados[:4]) + (" ..." if len(borrados) > 4 else ""))
    return len(borrados)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="12h",
                    choices=["09h", "12h", "16h", "19h", "21h"])
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()

    os.makedirs(VIDEOS, exist_ok=True)
    hoy = date.today().isoformat()

    # Lo primero: quitar metraje que ya no se usa.
    purgar_fuentes()

    # ---------------- INSTAGRAM ----------------
    posts = cargar(POSTS, [])
    pendientes = [p for p in posts if not p.get("posted")]

    if pendientes and not args.forzar:
        print(f"[IG] Ya hay {len(pendientes)} video(s) en cola. No genero otro.")
    else:
        print(f"[IG] Generando el reel del pase {args.slot}...")
        e = generar(args.slot, "instagram", VIDEOS)
        mb = e.pop("_mb")
        posts.append(e)
        print(f"[IG] Encolado: {e['file']} ({mb} MB)")

    limpiar(posts, VIDEOS, CONSERVAR, clave_hecho="posted")
    guardar(POSTS, posts)

    # La parte de TikTok se quito a proposito. Los videos de TikTok salen
    # ahora de lote.py (10 al dia, con las cuatro aperturas y los cupos de
    # reparto). Tener aqui un segundo generador solo duplicaba contenido peor
    # y hacia crecer el repositorio sin motivo.


if __name__ == "__main__":
    main()
