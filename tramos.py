#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tramos.py - Elige el TRAMO MAS ATRACTIVO de cada metraje.

Regla de Jorge: "siempre escoge que se vea el apartado mas atractivo de las
paginas web". Antes el arranque se elegia por una formula de rotacion, sin
mirar el video, y salian anuncios que empezaban en una franja de texto plano o
directamente en un hueco en blanco.

Aqui se MIDE. Se muestrea el video cada medio segundo y cada muestra recibe
dos notas:

  detalle  desviacion tipica de la luminancia. Un hueco en blanco da casi 0.
  color    colorido (Hasler-Susstrunk simplificado). Un muro de texto gris da
           poco; una foto grande da mucho.

Despues se recorre el video con una ventana del largo del anuncio y se elige
la de mejor nota media, PENALIZANDO fuerte que dentro haya alguna muestra
sosa: mas vale un tramo bueno entero que uno excelente con un bache.

    python herramientas/tramos.py                  # mide todo fuentes/
    python herramientas/tramos.py --ventana 15     # para anuncios de 15 s

Escribe fuentes/tramos.json, que es lo que lee generar.py.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

# Funciona tanto si este archivo vive en herramientas/ como en la raiz del
# proyecto: se busca la carpeta que tenga fuentes/ al lado o un nivel arriba.
_aqui = os.path.dirname(os.path.abspath(__file__))
AQUI = _aqui if os.path.isdir(os.path.join(_aqui, "fuentes")) else os.path.dirname(_aqui)
FUENTES = os.path.join(AQUI, "fuentes")
SALIDA = os.path.join(FUENTES, "tramos.json")

PASO = 0.5          # cada cuanto se muestrea, en segundos
ANCHO = 160         # las muestras se sacan pequenas: sobra para medir
SOSO = 0.34         # por debajo de esto la muestra se considera sosa


def duracion(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def muestrear(path, tmp):
    """Saca un fotograma cada PASO segundos, pequeno, y devuelve las rutas."""
    patron = os.path.join(tmp, "m_%05d.jpg")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", path,
         "-vf", f"fps={1/PASO},scale={ANCHO}:-1", "-q:v", "4", patron],
        check=True)
    return sorted(os.path.join(tmp, f) for f in os.listdir(tmp)
                  if f.startswith("m_"))


def notas(ruta):
    """Devuelve (detalle, colorido) SIN normalizar. La escala absoluta no dice
    nada -una web clara y una oscura no son comparables-, asi que despues se
    normaliza dentro de cada metraje."""
    im = Image.open(ruta).convert("RGB")
    w, h = im.size
    b = im.tobytes()
    n = w * h

    sl = sr = sg = sb = 0.0
    sl2 = 0.0
    srg = srg2 = syb = syb2 = 0.0
    for i in range(0, len(b), 3):
        r, g, bl = b[i], b[i + 1], b[i + 2]
        lum = 0.299 * r + 0.587 * g + 0.114 * bl
        sl += lum
        sl2 += lum * lum
        rg = r - g
        yb = 0.5 * (r + g) - bl
        srg += rg
        srg2 += rg * rg
        syb += yb
        syb2 += yb * yb

    def desv(suma, suma2):
        m = suma / n
        return max(0.0, suma2 / n - m * m) ** 0.5

    detalle = desv(sl, sl2)
    colorido = ((desv(srg, srg2) ** 2 + desv(syb, syb2) ** 2) ** 0.5
                + 0.3 * (((srg / n) ** 2 + (syb / n) ** 2) ** 0.5))
    return detalle, colorido


def normalizar(valores):
    """Cada metraje se mide contra SI MISMO: lo que importa no es si esta web
    es mas colorida que otra, sino que tramo de ESTA es el bueno."""
    if not valores:
        return []
    orden = sorted(valores)
    p90 = orden[min(len(orden) - 1, int(len(orden) * 0.9))]
    if p90 <= 0:
        return [0.0] * len(valores)
    return [min(1.0, v / p90) for v in valores]


def mejor_ventana(puntos, ventana_s, dur):
    """Devuelve (inicio, nota, peor) de la mejor ventana.

    Los puntos ya vienen normalizados 0-1 dentro del propio metraje, asi que
    SOSO significa "flojo PARA ESTE VIDEO", que es lo que queremos.
    """
    por_ventana = max(1, int(round(ventana_s / PASO)))
    if len(puntos) <= por_ventana:
        return 0.0, (sum(puntos) / len(puntos) if puntos else 0.0), \
               (min(puntos) if puntos else 0.0)

    mejor = (0.0, -9.9, 0.0)
    for i in range(len(puntos) - por_ventana + 1):
        tramo = puntos[i:i + por_ventana]
        media = sum(tramo) / len(tramo)
        peor = min(tramo)
        sosas = sum(1 for v in tramo if v < SOSO) / len(tramo)
        # El bache pesa, pero no tanto como para tirar por tierra un tramo
        # que por lo demas es el mejor del video.
        nota = media - 0.8 * sosas - 0.4 * max(0.0, SOSO - peor)
        if nota > mejor[1]:
            mejor = (i * PASO, nota, peor)
    tope = max(0.0, dur - ventana_s)
    if mejor[0] > tope:
        mejor = (tope, mejor[1], mejor[2])
    return mejor


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ventana", type=float, default=15.0)
    ap.add_argument("--dir", default=FUENTES)
    ap.add_argument("--salida", default=SALIDA)
    args = ap.parse_args()

    archivos = []
    for raiz, _, files in os.walk(args.dir):
        for f in sorted(files):
            if f.lower().endswith(".mp4"):
                archivos.append(os.path.relpath(os.path.join(raiz, f), args.dir))

    if not archivos:
        raise SystemExit(f"[ERROR] No hay .mp4 en {args.dir}")

    datos = {}
    for rel in archivos:
        path = os.path.join(args.dir, rel)
        dur = duracion(path)
        tmp = tempfile.mkdtemp(prefix="tramos-")
        try:
            marcos = muestrear(path, tmp)
            det = []
            col = []
            for m in marcos:
                d, c = notas(m)
                det.append(d)
                col.append(c)
            det = normalizar(det)
            col = normalizar(col)
            puntos = [0.62 * d + 0.38 * c for d, c in zip(det, col)]
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        ini, nota, peor = mejor_ventana(puntos, args.ventana, dur)
        datos[rel.replace("\\", "/")] = {
            "inicio": round(ini, 2),
            "nota": round(nota, 3),
            "peor": round(peor, 3),
            "duracion": round(dur, 2),
            "muestras": len(puntos),
        }
        aviso = "  <-- tiene algun bache" if peor < SOSO else ""
        print(f"  {rel:<48} inicio {ini:5.1f}s  nota {nota:.3f}  "
              f"peor {peor:.3f}{aviso}")

    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    buenos = sum(1 for v in datos.values() if v["peor"] >= SOSO)
    print(f"\n[OK] {len(datos)} metrajes medidos · {buenos} sin ningun bache")
    print(f"[OK] {args.salida}")


if __name__ == "__main__":
    main()
