#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
encolar.py - Rellena la cola de publicacion.

Si posts.json no tiene ningun video pendiente, genera uno nuevo con generar.py
y lo anade a la cola. Ademas limpia del repositorio los .mp4 ya publicados
antiguos para que el repo no crezca sin control.

Uso:
    python encolar.py --slot 16h
    python encolar.py --slot 12h --forzar     (encola aunque ya haya cola)
"""

import argparse
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(AQUI, "posts.json")
VIDEOS = os.path.join(AQUI, "videos")

# Cuantos videos ya publicados conservamos en el repo antes de borrar los .mp4.
CONSERVAR = 6


def cargar():
    if not os.path.exists(POSTS):
        return []
    with open(POSTS, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar(posts):
    with open(POSTS, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)


def limpiar_antiguos(posts):
    """Borra el .mp4 de los publicados mas antiguos. La entrada se conserva
    en posts.json para no repetir contenido; solo desaparece el archivo."""
    publicados = [p for p in posts if p.get("posted")]
    if len(publicados) <= CONSERVAR:
        return 0
    borrados = 0
    for p in publicados[:-CONSERVAR]:
        ruta = os.path.join(VIDEOS, p["file"])
        if os.path.exists(ruta):
            os.remove(ruta)
            borrados += 1
    if borrados:
        print(f"[LIMPIEZA] {borrados} mp4 antiguos eliminados del repositorio.")
    return borrados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="12h", choices=["12h", "16h", "21h"])
    ap.add_argument("--forzar", action="store_true")
    args = ap.parse_args()

    posts = cargar()
    pendientes = [p for p in posts if not p.get("posted")]

    if pendientes and not args.forzar:
        print(f"[INFO] Ya hay {len(pendientes)} video(s) en cola. No genero nada.")
        limpiar_antiguos(posts)
        guardar(posts)
        return

    print(f"[1/2] Generando el reel del pase {args.slot}...")
    proc = subprocess.run(
        [sys.executable, os.path.join(AQUI, "generar.py"),
         "--slot", args.slot, "--out", VIDEOS, "--json"],
        capture_output=True, text=True)

    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit("[ERROR] generar.py no pudo crear el video.")

    linea = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if not linea:
        sys.stdout.write(proc.stdout)
        raise SystemExit("[ERROR] generar.py no devolvio JSON.")

    entrada = json.loads(linea[-1])
    ruta = os.path.join(VIDEOS, entrada["file"])
    if not os.path.exists(ruta):
        raise SystemExit(f"[ERROR] El video no existe: {ruta}")

    tam = os.path.getsize(ruta) / 1_000_000
    if tam > 90:
        raise SystemExit(f"[ERROR] El video pesa {tam:.1f} MB; GitHub no admite "
                         f"archivos de mas de 100 MB.")

    posts.append(entrada)
    limpiar_antiguos(posts)
    guardar(posts)
    print(f"[2/2] Encolado: {entrada['file']} ({tam:.1f} MB)")


if __name__ == "__main__":
    main()
