#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
musica.py - Sintetiza la banda sonora de cada reel.

La musica se GENERA aqui con codigo, nota a nota. No viene de ningun banco de
sonido, asi que no hay licencia de terceros ni riesgo de que Instagram la
silencie por deteccion de contenido.

Cada proyecto suena distinto: la tonalidad, el tempo y el timbre salen del
indice del negocio, y la intensidad del tipo de anuncio.

    python musica.py --salida /tmp/x.wav --semilla 3 --tipo dato --segundos 18
"""

import argparse
import math

import numpy as np

SR = 44100

# Escalas pentatonicas (semitonos desde la tonica). La menor suena seria; la
# mayor, luminosa. Se elige segun el sector para que pegue con la imagen.
PENTA_MENOR = [0, 3, 5, 7, 10]
PENTA_MAYOR = [0, 2, 4, 7, 9]

# Tonicas en Hz (C2..B2 aprox). Doce, una por proyecto.
TONICAS = [65.41, 69.30, 73.42, 77.78, 82.41, 87.31,
           92.50, 98.00, 103.83, 110.00, 116.54, 123.47]


def nota(f, dur, sr=SR):
    return np.arange(int(dur * sr)) / sr, f


def env_adsr(n, a, d, s, r, sr=SR):
    """Envolvente clasica ataque-caida-sostenido-relajacion."""
    na, nd, nr = int(a * sr), int(d * sr), int(r * sr)
    ns = max(0, n - na - nd - nr)
    partes = [
        np.linspace(0, 1, na, endpoint=False) if na else np.array([]),
        np.linspace(1, s, nd, endpoint=False) if nd else np.array([]),
        np.full(ns, s),
        np.linspace(s, 0, nr) if nr else np.array([]),
    ]
    e = np.concatenate([p for p in partes if p.size])
    if e.size < n:
        e = np.pad(e, (0, n - e.size))
    return e[:n]


def pad(frecs, dur, sr=SR):
    """Acorde sostenido, con voces ligeramente desafinadas para dar cuerpo."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    for f in frecs:
        for det in (-0.35, 0.0, 0.35):          # centesimas de desafinacion
            ff = f * (2 ** (det / 1200.0))
            out += np.sin(2 * np.pi * ff * t) / len(frecs)
            out += 0.22 * np.sin(4 * np.pi * ff * t) / len(frecs)
    out *= env_adsr(n, 2.2, 1.2, 0.85, 2.5, sr)
    return out * 0.16


def pluck(f, dur, sr=SR):
    """Nota corta con caida exponencial: el punteo que marca el pulso."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    cuerpo = (np.sin(2 * np.pi * f * t)
              + 0.35 * np.sin(4 * np.pi * f * t)
              + 0.12 * np.sin(6 * np.pi * f * t))
    return cuerpo * np.exp(-t * 6.5) * 0.28


def sub(f, dur, sr=SR):
    """Grave suave que sujeta la mezcla."""
    n = int(dur * sr)
    t = np.arange(n) / sr
    return np.sin(2 * np.pi * f * t) * env_adsr(n, 1.5, 1.0, 0.9, 2.0, sr) * 0.30


def barrido(dur, subiendo=True, sr=SR):
    """Whoosh de aire para las transiciones."""
    n = int(dur * sr)
    t = np.linspace(0, 1, n)
    ruido = np.random.default_rng(7).normal(0, 1, n)
    # Filtro de un polo con corte que se mueve: barrido de brillo.
    corte = (0.02 + 0.35 * t) if subiendo else (0.37 - 0.35 * t)
    y = np.zeros(n)
    z = 0.0
    for i in range(n):
        a = corte[i]
        z += a * (ruido[i] - z)
        y[i] = z
    forma = np.sin(np.pi * t) ** 1.5
    return y * forma * 0.16


def eco(x, retardo=0.28, realim=0.28, mezcla=0.24, sr=SR):
    d = int(retardo * sr)
    y = x.copy()
    buf = np.zeros(len(x) + d)
    buf[:len(x)] = x
    for i in range(len(x)):
        if i >= d:
            buf[i] += realim * buf[i - d]
    return (1 - mezcla) * y + mezcla * buf[:len(x)]


def paso_bajo(x, corte=0.35):
    y = np.zeros_like(x)
    z = 0.0
    for i in range(len(x)):
        z += corte * (x[i] - z)
        y[i] = z
    return y


# Intensidad por tipo de anuncio: el que abre con gancho pide mas pulso; el
# de spa o el de ficha piden mas aire.
INTENSIDAD = {"escaparate": 1.00, "dato": 0.92, "ficha": 0.80, "lista": 1.05}


def componer(semilla, tipo, segundos, t_cierre=None, sr=SR):
    rng = np.random.default_rng(1000 + semilla)
    n = int(segundos * sr)
    mezcla = np.zeros(n)

    tonica = TONICAS[semilla % len(TONICAS)]
    escala = PENTA_MENOR if semilla % 2 == 0 else PENTA_MAYOR
    bpm = 84 + (semilla % 5) * 6
    paso = 60.0 / bpm / 2.0                      # corcheas
    fuerza = INTENSIDAD.get(tipo, 1.0)

    # 1 · Colchon armonico: tonica, quinta y decima
    acorde = [tonica * 2, tonica * 2 * 2 ** (escala[2] / 12),
              tonica * 4 * 2 ** (escala[1] / 12)]
    capa = pad(acorde, segundos, sr)
    mezcla[:len(capa)] += capa[:n]

    # 2 · Grave
    g = sub(tonica, segundos, sr)
    mezcla[:len(g)] += g[:n]

    # 3 · Punteo pentatonico. Deja huecos: menos notas suena mas caro.
    t = 0.6
    while t < segundos - 1.2:
        if rng.random() < 0.62:
            grado = escala[rng.integers(0, len(escala))]
            octava = 4 if rng.random() < 0.7 else 8
            f = tonica * octava * 2 ** (grado / 12)
            p = pluck(f, min(1.1, segundos - t), sr) * fuerza
            i = int(t * sr)
            mezcla[i:i + len(p)] += p[:max(0, n - i)]
        t += paso * (1 if rng.random() < 0.75 else 2)

    # 4 · Transiciones
    b = barrido(1.1, subiendo=True, sr=sr)
    mezcla[:len(b)] += b[:n]
    if t_cierre:
        i = max(0, int((t_cierre - 0.7) * sr))
        b2 = barrido(1.3, subiendo=False, sr=sr)
        mezcla[i:i + len(b2)] += b2[:max(0, n - i)]

    # 5 · Color y espacio
    mezcla = paso_bajo(mezcla, corte=0.30)
    mezcla = eco(mezcla, sr=sr)

    # 6 · El cierre baja un poco para que se lea el dominio en silencio relativo
    if t_cierre:
        i = int(t_cierre * sr)
        if i < n:
            mezcla[i:] *= np.linspace(1.0, 0.55, n - i)

    # 7 · Entrada y salida
    ent, sal = int(0.9 * sr), int(0.8 * sr)
    mezcla[:ent] *= np.linspace(0, 1, ent)
    mezcla[-sal:] *= np.linspace(1, 0, sal)

    # 8 · Nivel: pico a -1.5 dBFS, sin comprimir de mas
    pico = np.max(np.abs(mezcla)) or 1.0
    mezcla = mezcla / pico * 0.84
    return mezcla


def guardar_wav(ruta, mono, sr=SR):
    # Estereo con una pizca de anchura: el eco va mas a un lado.
    izq = mono
    der = np.concatenate([np.zeros(int(0.012 * sr)), mono])[:len(mono)]
    est = np.stack([izq, der * 0.97], axis=1)
    datos = np.clip(est, -1, 1)
    pcm = (datos * 32767).astype("<i2")

    import struct
    bloque = pcm.tobytes()
    with open(ruta, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(bloque)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 2, sr, sr * 4, 4, 16))
        f.write(b"data" + struct.pack("<I", len(bloque)) + bloque)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--tipo", default="escaparate")
    ap.add_argument("--segundos", type=float, default=18.0)
    ap.add_argument("--cierre", type=float, default=None)
    a = ap.parse_args()
    guardar_wav(a.salida, componer(a.semilla, a.tipo, a.segundos, a.cierre))
    print(f"[OK] {a.salida}")


if __name__ == "__main__":
    main()
