#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
comprobar_url.py - Verifica que el proximo video de la cola ya se puede
descargar desde raw.githubusercontent.com antes de pedirle a Instagram que lo
publique. Si Instagram intenta bajar un video que aun no esta servido, devuelve
un error y se pierde el pase.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
POSTS = os.path.join(AQUI, "posts.json")

REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
REF = (os.environ.get("VIDEO_REF") or
       os.environ.get("GITHUB_REF_NAME") or "main").strip()

INTENTOS = 10
ESPERA = 6


def main():
    if not os.path.exists(POSTS):
        raise SystemExit("[ERROR] No encuentro posts.json.")
    with open(POSTS, "r", encoding="utf-8") as f:
        posts = json.load(f)

    pendientes = [p for p in posts if not p.get("posted")]
    if not pendientes:
        print("[INFO] No hay nada en cola; nada que comprobar.")
        return

    fichero = pendientes[0]["file"]
    url = f"https://raw.githubusercontent.com/{REPO}/{REF}/videos/{fichero}"
    print(f"[INFO] Comprobando {url}")

    for intento in range(1, INTENTOS + 1):
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as r:
                tam = r.headers.get("Content-Length", "?")
                print(f"[OK] Disponible ({r.status}, {tam} bytes).")
                return
        except urllib.error.HTTPError as e:
            print(f"      intento {intento}/{INTENTOS}: HTTP {e.code}")
        except Exception as e:  # noqa: BLE001
            print(f"      intento {intento}/{INTENTOS}: {e}")
        time.sleep(ESPERA)

    raise SystemExit(f"[ERROR] {fichero} no esta accesible en GitHub. "
                     f"Instagram no podria descargarlo.")


if __name__ == "__main__":
    main()
