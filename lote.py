#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lote.py - Genera de golpe el lote de videos de TikTok de un dia.

Lo lanza Jorge cuando quiere: no tiene horario propio. Elige N combinaciones
DISTINTAS entre si, las renderiza y deja al lado un archivo con los textos
listos para copiar y la hora sugerida de cada uno.

    python lote.py                       # 10 videos para hoy
    python lote.py --n 6                 # 6 videos
    python lote.py --fecha 2026-08-25    # los de un dia concreto
    python lote.py --simular --dias 30   # comprobar el reparto sin renderizar

Metraje propio
--------------
Todo .mp4 que Jorge deje en  fuentes/propios/  entra solo en la rotacion y se
monta A SANGRE (sin marco de navegador), porque son grabaciones suyas: manos
sujetando un iPad, la pantalla del movil, etc. El nombre del archivo se
convierte en el rotulo; si quieres otro, ponlo en fuentes/propios/titulos.json
como {"archivo.mp4": "Rotulo bonito"}.
"""

import argparse
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import generar as g  # noqa: E402

PROPIOS_DIR = os.path.join(g.FUENTES_DIR, "propios")

# Horas sugeridas. Las seis primeras van separadas >= 2,5 h, que es lo que pide
# TikTok para que un video no le robe el alcance inicial al anterior. Las
# cuatro ultimas son relleno para dias en que quieras apretar de verdad.
HORAS_BASE = ["08:00", "11:00", "14:00", "17:00", "20:00", "22:30"]
HORAS_EXTRA = ["09:30", "12:30", "15:30", "18:30"]

# Paleta para el metraje propio (los proyectos de muestra ya traen la suya).
ACENTOS_PROPIOS = [
    (79, 195, 232), (232, 168, 79), (152, 196, 122), (214, 122, 196),
    (120, 152, 240), (236, 132, 108),
]


# --------------------------------------------------------------------------
# Metraje propio
# --------------------------------------------------------------------------
def titulo_desde_archivo(nombre):
    base = os.path.splitext(nombre)[0]
    base = base.replace("_", " ").replace("-", " ").strip()
    return base[:1].upper() + base[1:] if base else "Nuestro trabajo"


def cargar_propios():
    """Devuelve los proyectos que salen del metraje grabado por Jorge."""
    if not os.path.isdir(PROPIOS_DIR):
        return []

    titulos = {}
    ruta_t = os.path.join(PROPIOS_DIR, "titulos.json")
    if os.path.exists(ruta_t):
        try:
            with open(ruta_t, "r", encoding="utf-8") as f:
                titulos = json.load(f)
        except (json.JSONDecodeError, OSError):
            titulos = {}

    salida = []
    for i, nombre in enumerate(sorted(os.listdir(PROPIOS_DIR))):
        if not nombre.lower().endswith(".mp4"):
            continue
        rel = os.path.join("propios", nombre)
        salida.append({
            "id": "propio-" + os.path.splitext(nombre)[0].lower(),
            "nombre": titulos.get(nombre) or titulo_desde_archivo(nombre),
            "sector": "Lavandera Design",
            "tipo": "propio",
            "acento": ACENTOS_PROPIOS[i % len(ACENTOS_PROPIOS)],
            "movil": rel,          # se monta a sangre, da igual la orientacion
            "escritorio": None,
            "url": g.DOMINIO,
            "marco": False,
        })
    return salida


# --------------------------------------------------------------------------
# Universo de combinaciones y reparto
# --------------------------------------------------------------------------
def universo():
    """Todas las combinaciones posibles negocio x formato x tipo de anuncio."""
    combos = []
    for pr in g.PROYECTOS + cargar_propios():
        for fmt in ("movil", "escritorio"):
            if not pr.get(fmt):
                continue
            for tipo in g.TIPOS:
                for ap in g.APERTURAS:
                    combos.append((pr, fmt, tipo, ap))
    return combos


def baraja(m, semilla=20260824):
    """Orden fijo y bien mezclado de las m combinaciones.

    Antes esto era un salto de razon aurea sobre el indice plano, y tenia un
    fallo que solo se ve mirando los numeros: con 416 combinaciones el salto
    sale 257, que es 1 modulo 32, o sea que cada paso movia SOLO la apertura y
    dejaba formato y tipo quietos. Habia dias con ocho de diez en movil.

    Una permutacion fija no tiene estructura que pueda alinearse con los ejes:
    mezcla igual de bien el negocio, el formato, el tipo y la apertura, y
    sigue sin repetir hasta agotar las m.
    """
    orden = list(range(m))
    random.Random(semilla).shuffle(orden)
    return orden


def elegir_lote(fecha, n):
    """N combinaciones distintas para ese dia, sin repetir en muchos dias."""
    combos = universo()
    m = len(combos)
    if m == 0:
        raise SystemExit("[ERROR] No hay metraje en fuentes/.")
    n = min(n, m)

    orden = baraja(m)
    base = fecha.toordinal() * n

    # Una permutacion reparte bien A LA LARGA, pero un dia suelto puede salir
    # con nueve de diez en movil por pura casualidad, y eso es justo lo que se
    # ve como "todos los videos son iguales". Asi que el dia tambien lleva
    # cupos: se recorre la baraja y se acepta cada candidato solo si no
    # revienta el reparto del dia.
    import math as _m
    cupo_fmt = max(2, _m.ceil(n * 0.60))
    cupo_tipo = max(1, _m.ceil(n * 0.30))
    cupo_ap = max(1, _m.ceil(n * 0.30))
    cupo_neg = max(1, _m.ceil(n * 0.20))

    elegidos = []
    usados = {"fmt": {}, "tipo": {}, "ap": {}, "neg": {}}

    def cabe(pr, fmt, tipo, ap, holgura):
        return (usados["fmt"].get(fmt, 0) < cupo_fmt + holgura
                and usados["tipo"].get(tipo, 0) < cupo_tipo + holgura
                and usados["ap"].get(ap, 0) < cupo_ap + holgura
                and usados["neg"].get(pr["id"], 0) < cupo_neg + holgura)

    holgura = 0
    i = 0
    while len(elegidos) < n:
        if i >= m * 2:                     # nada encaja: se afloja el cupo
            holgura += 1
            i = 0
            if holgura > n:
                break
        combo = combos[orden[(base + i) % m]]
        pr, fmt, tipo, ap = combo
        if combo not in elegidos and cabe(pr, fmt, tipo, ap, holgura):
            elegidos.append(combo)
            usados["fmt"][fmt] = usados["fmt"].get(fmt, 0) + 1
            usados["tipo"][tipo] = usados["tipo"].get(tipo, 0) + 1
            usados["ap"][ap] = usados["ap"].get(ap, 0) + 1
            usados["neg"][pr["id"]] = usados["neg"].get(pr["id"], 0) + 1
        i += 1

    plan = []
    for k in range(len(elegidos)):
        c = base + k
        proyecto, formato, tipo, apertura = elegidos[k]

        gancho = g.GANCHOS[(c * 5 + 1) % len(g.GANCHOS)]
        cta = g.CTAS[(c * 3) % len(g.CTAS)]
        remate = g.REMATES[(c * 5 + 2) % len(g.REMATES)]
        dato = g.DATOS[(c * 3 + 1) % len(g.DATOS)]
        serie = g.SERIES[(c * 3 + 2) % len(g.SERIES)]
        arranque = (c % 4) * 2.0

        plan.append({
            "n": k + 1,
            "proyecto": proyecto, "formato": formato, "tipo": tipo,
            "apertura": apertura,
            "gancho": gancho, "cta": cta, "remate": remate,
            "dato": dato, "serie": serie, "arranque": arranque,
        })

    # El primer video del dia es SIEMPRE nuestra propia web. Es el unico
    # metraje sin aviso de maqueta, el que ensena de verdad como trabajamos, y
    # el que mejor abre: marmol y luz en el primer fotograma.
    propios_reales = [pr for pr in g.PROYECTOS if pr.get("tipo") == "propio"]
    if propios_reales and plan:
        dia = fecha.toordinal()
        pr = propios_reales[dia % len(propios_reales)]
        fmt = "movil" if (dia % 2 == 0 and pr.get("movil")) else "escritorio"
        if not pr.get(fmt):
            fmt = "movil" if pr.get("movil") else "escritorio"
        plan[0]["proyecto"] = pr
        plan[0]["formato"] = fmt
        plan[0]["tipo"] = g.TIPOS[dia % len(g.TIPOS)]
        plan[0]["apertura"] = g.APERTURAS[dia % len(g.APERTURAS)]

    horas = HORAS_BASE + HORAS_EXTRA
    orden = sorted(range(len(plan)), key=lambda i: horas[i] if i < len(horas) else "23:59")
    for pos, i in enumerate(orden):
        plan[i]["hora"] = horas[pos] if pos < len(horas) else "—"
        plan[i]["prioritario"] = pos < len(HORAS_BASE)
    plan.sort(key=lambda e: e["hora"])
    for k, e in enumerate(plan):
        e["n"] = k + 1
    return plan


# --------------------------------------------------------------------------
# Renderizado
# --------------------------------------------------------------------------
def nombre_archivo(fecha, e):
    return (f"tt-{fecha.isoformat()}-{e['n']:02d}-{e['proyecto']['id']}"
            f"-{e['formato']}-{e['tipo']}-{e['apertura']}.mp4")


def renderizar_uno(fecha, e, destino):
    nombre = nombre_archivo(fecha, e)
    salida = os.path.join(destino, nombre)
    tmp = tempfile.mkdtemp(prefix="lote-")
    try:
        g.render(e["proyecto"], e["formato"], e["gancho"], e["cta"],
                 e["remate"], salida, tmp, e["arranque"], e["tipo"],
                 e["dato"], e["serie"], e["apertura"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return nombre, salida


def escribir_textos(fecha, entradas, destino):
    """Documento con los 10 textos listos para copiar y pegar en TikTok."""
    lineas = [
        f"# Lote de TikTok · {fecha.strftime('%d/%m/%Y')}",
        "",
        f"{len(entradas)} vídeos. Cada bloque tiene el nombre del archivo, la hora "
        "sugerida y el texto listo para copiar.",
        "",
        "**Los marcados con ★ son los seis que sí o sí**: van separados más de "
        "2,5 h, que es lo que pide TikTok para que un vídeo no le robe el alcance "
        "al anterior. Los demás son relleno para días en que quieras apretar; si "
        "un día vas corto de tiempo, publica solo los seis con estrella.",
        "",
        "---",
        "",
    ]
    for e in entradas:
        estrella = "★ " if e["prioritario"] else ""
        lineas += [
            f"## {estrella}{e['n']:02d} · {e['hora']} · {e['proyecto']['nombre']}",
            "",
            f"- **Archivo:** `{e['file']}`",
            f"- **Tipo de anuncio:** {e['tipo']}  ·  **Abre con:** {e['apertura']}"
            f"  ·  **Formato:** {e['formato']}",
            "",
            "```",
            e["caption"],
            "```",
            "",
        ]
    lineas += [
        "---",
        "",
        "## Cómo medirlo",
        "",
        "En las analíticas de TikTok mira **tiempo medio de visualización** y "
        "**% que lo vio entero**, no las visitas. Un vídeo con 400 visitas y 45 % "
        "de retención vale más que uno con 2.000 y 8 %.",
        "",
        "Y lo que de verdad cuenta para el negocio: **cuántos mensajes y clics al "
        "enlace** te llegan desde Canarias. Las visitas solas no pagan facturas.",
        "",
    ]
    ruta = os.path.join(destino, f"textos-{fecha.isoformat()}.md")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(lineas))
    return ruta


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="cuantos videos")
    ap.add_argument("--fecha", default=None, help="YYYY-MM-DD")
    ap.add_argument("--out", default=os.path.join(AQUI, "lote"))
    ap.add_argument("--trabajadores", type=int, default=2)
    ap.add_argument("--desde", type=int, default=1,
                    help="primer video del lote a renderizar (1 = el primero)")
    ap.add_argument("--hasta", type=int, default=0,
                    help="ultimo video a renderizar (0 = hasta el final)")
    ap.add_argument("--simular", action="store_true",
                    help="solo imprime el plan, no renderiza")
    ap.add_argument("--dias", type=int, default=1,
                    help="con --simular, cuantos dias comprobar")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    fecha = (datetime.strptime(args.fecha, "%Y-%m-%d").date()
             if args.fecha else date.today())

    # ---------------- Modo comprobacion ----------------
    if args.simular:
        vistos, choques, dias_sin_repe = {}, 0, 0
        for d in range(args.dias):
            f = date.fromordinal(fecha.toordinal() + d)
            plan = elegir_lote(f, args.n)
            claves = [(e["proyecto"]["id"], e["formato"], e["tipo"], e["apertura"])
                      for e in plan]
            if len(set(claves)) == len(claves):
                dias_sin_repe += 1
            negocios = [e["proyecto"]["nombre"] for e in plan]
            for c in claves:
                vistos[c] = vistos.get(c, 0) + 1
                if vistos[c] > 1:
                    choques += 1
            if d < 3:
                print(f"\n--- {f} ---")
                for e in plan:
                    est = "★" if e["prioritario"] else " "
                    print(f" {est} {e['hora']}  {e['proyecto']['nombre']:<22}"
                          f"{e['formato']:<11}{e['tipo']:<11}{e['apertura']}")
                print(f"   negocios distintos en el dia: "
                      f"{len(set(negocios))}/{len(plan)}")
        total = len(universo())
        print(f"\nUniverso: {total} combinaciones.")
        print(f"Dias comprobados: {args.dias}  ·  sin repetir dentro del dia: "
              f"{dias_sin_repe}/{args.dias}")
        print(f"Primera repeticion global tras {total / args.n:.1f} dias "
              f"(repeticiones acumuladas en {args.dias} dias: {choques})")
        if vistos:
            print(f"Reparto: cada combinacion sale entre {min(vistos.values())} "
                  f"y {max(vistos.values())} veces")
        return

    # ---------------- Renderizado ----------------
    os.makedirs(args.out, exist_ok=True)
    plan = elegir_lote(fecha, args.n)

    # Los textos no dependen de renderizar: se calculan del plan. Asi cada
    # llamada deja el documento completo aunque solo renderice un tramo.
    for e in plan:
        e["file"] = nombre_archivo(fecha, e)
        e["caption"] = g.construir_caption(e["proyecto"], e["cta"],
                                           e["remate"], "tiktok")

    hasta = args.hasta or len(plan)
    tramo = [e for e in plan if args.desde <= e["n"] <= hasta]

    print(f"[LOTE] {len(tramo)} de {len(plan)} videos para el "
          f"{fecha.isoformat()} ({args.trabajadores} en paralelo)")

    def tarea(e):
        nombre, ruta = renderizar_uno(fecha, e, args.out)
        e["ruta"] = ruta
        e["mb"] = round(os.path.getsize(ruta) / 1_000_000, 1)
        print(f"   [{e['n']:02d}/{len(plan)}] {nombre}  ({e['mb']} MB)")
        return e

    with ThreadPoolExecutor(max_workers=max(1, args.trabajadores)) as ex:
        list(ex.map(tarea, tramo))

    plan.sort(key=lambda e: e["n"])
    ruta_textos = escribir_textos(fecha, plan, args.out)

    resumen = {
        "fecha": fecha.isoformat(),
        "textos": os.path.basename(ruta_textos),
        "videos": [
            {"n": e["n"], "hora": e["hora"], "prioritario": e["prioritario"],
             "file": e["file"], "negocio": e["proyecto"]["nombre"],
             "formato": e["formato"], "tipo_anuncio": e["tipo"],
             "apertura": e["apertura"],
             "mb": e.get("mb"),
             "renderizado": os.path.exists(os.path.join(args.out, e["file"])),
             "caption": e["caption"]}
            for e in plan
        ],
    }
    with open(os.path.join(args.out, f"lote-{fecha.isoformat()}.json"),
              "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)

    if args.json:
        print(json.dumps(resumen, ensure_ascii=False))
    else:
        print(f"[OK] {len(tramo)} videos renderizados en {args.out}")
        print(f"[OK] textos en {ruta_textos}")


if __name__ == "__main__":
    main()
