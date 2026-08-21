#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generar.py - Motor de reels de Lavandera Design.

Crea un reel 1080x1920 listo para Instagram a partir del metraje real de la
carpeta fuentes/, con el dominio lavanderadesign.com quemado en pantalla y una
llamada a la accion clara.

Uso:
    python generar.py --slot 12h --out videos/ --fecha 2026-08-22
    python generar.py --slot 16h --preview      (no escribe caption)

Requisitos: ffmpeg en el PATH y Pillow.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import shutil
from datetime import date, datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# --------------------------------------------------------------------------
# Constantes de marca
# --------------------------------------------------------------------------
W, H = 1080, 1920
FPS = 30
DUR = 18.0                     # duracion del reel en segundos
DOMINIO = "lavanderadesign.com"

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES_DIR = os.path.join(AQUI, "fuentes")
ASSETS = os.path.join(AQUI, "assets")
F_BOLD = os.path.join(ASSETS, "Outfit-Bold.ttf")
F_REG = os.path.join(ASSETS, "Outfit-Regular.ttf")

TINTA = (255, 255, 255)
TENUE = (183, 190, 201)
FONDO = (9, 11, 15)

# Momentos clave (segundos)
T_HOOK_FIN = 3.4
T_MARCA_INI = 3.5
T_FINAL_INI = DUR - 3.4

# Layout del formato escritorio: la captura 16:9 se amplia 1.3x y se recorta a
# los lados para que el texto de la web se lea de verdad en un movil.
MARCO_Y = 660          # y donde empieza el chrome del navegador
CHROME_H = 108         # alto de la barra del navegador
CAP_W_VIRTUAL = 1231   # ancho virtual (1080 * 1.14) antes de recortar
CAP_H = 692            # alto de la captura ya recortada

# --------------------------------------------------------------------------
# Banco de contenido
# --------------------------------------------------------------------------
# tipo: "cliente" = encargo real de un cliente.
#       "demo"    = proyecto propio de muestra (marca y textos inventados).
# El tipo se ROTULA en pantalla. Nunca presentamos una demo como cliente real.
PROYECTOS = [
    {
        "id": "ocean-fisher", "nombre": "The Ocean's Fisher",
        "sector": "pesca deportiva", "tipo": "cliente", "acento": (56, 189, 248),
        "movil": None, "escritorio": "Ocean-Fisher-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "motion-rent", "nombre": "Motion Rent",
        "sector": "alquiler de vehículos", "tipo": "cliente", "acento": (255, 138, 61),
        "movil": None, "escritorio": "Motion-Rent-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "villa-sol-y-luna", "nombre": "Villa Sol y Luna",
        "sector": "alojamiento", "tipo": "cliente", "acento": (233, 184, 114),
        "movil": None, "escritorio": "Villa-Sol-y-Luna-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "anfora-charter", "nombre": "Ánfora Charter",
        "sector": "charter náutico", "tipo": "cliente", "acento": (125, 211, 252),
        "movil": "anfora-charter-movil.mp4", "escritorio": "anfora-charter-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "ebano-motors", "nombre": "Ébano Motors",
        "sector": "concesionario", "tipo": "cliente", "acento": (212, 175, 111),
        "movil": "ebano-motors-movil.mp4", "escritorio": "ebano-motors-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "solera-retreats", "nombre": "Solera Retreats",
        "sector": "retiros y bienestar", "tipo": "demo", "acento": (196, 168, 122),
        "movil": "solera-retreats-movil.mp4", "escritorio": "solera-retreats-escritorio.mp4",
        "url": DOMINIO,
    },
]

GANCHOS = [
    "Esto no es\nuna plantilla.",
    "Tu competencia\nya tiene una\nweb así.",
    "Mira lo que ve\ntu cliente\nen el móvil.",
    "Tienes 3 segundos\npara convencer.",
    "Una web no es\nun folleto.",
    "Sin plantillas.\nDiseñada\ndesde cero.",
    "El 75% te juzga\npor tu web.",
    "Así se ve una web\nhecha a medida.",
]

CTAS = [
    "Te revisamos tu web gratis",
    "Pide tu demo gratis",
    "Demo gratis para tu negocio",
    "Te decimos qué falla en tu web",
]

# Frases de apoyo del cierre
REMATES = [
    "Webs, tiendas, reservas, SEO y automatizaciones",
    "Diseño propio de arriba abajo. Sin plantillas.",
    "Respondemos en menos de 24 h",
    "Webs a medida para negocios de Canarias",
]

HASHTAGS = ("#diseñoweb #paginasweb #diseñowebprofesional #webdesign #negociolocal "
            "#marketingdigital #emprendedores #tiendaonline #branding #canarias "
            "#reels #webpremium #presenciaonline #negociosdelujo #pymes "
            "#emprenderespaña #seo #automatización #turismocanarias #lavanderadesign")


# --------------------------------------------------------------------------
# Utilidades de dibujo
# --------------------------------------------------------------------------
def fuente(path, size):
    return ImageFont.truetype(path, size)


def medir(draw, texto, font, spacing=0):
    caja = draw.multiline_textbbox((0, 0), texto, font=font, spacing=spacing)
    return caja[2] - caja[0], caja[3] - caja[1]


def scrim_vertical(size, color, desde_alpha, hasta_alpha, arriba=True):
    """Degradado vertical translucido."""
    w, h = size
    capa = Image.new("L", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        if arriba:
            a = desde_alpha + (hasta_alpha - desde_alpha) * t
        else:
            a = hasta_alpha + (desde_alpha - hasta_alpha) * (1 - t)
        capa.putpixel((0, y), int(max(0, min(255, a))))
    capa = capa.resize((w, h))
    out = Image.new("RGBA", (w, h), color + (0,))
    out.putalpha(capa)
    return out


def redondear(img, radio):
    mascara = Image.new("L", img.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1],
                                              radius=radio, fill=255)
    out = img.copy().convert("RGBA")
    out.putalpha(mascara)
    return out


# --------------------------------------------------------------------------
# Capas
# --------------------------------------------------------------------------
def capa_gancho(gancho, proyecto):
    """Texto de gancho arriba, sobre un degradado oscuro."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    scrim = scrim_vertical((W, 900), (0, 0, 0), 232, 0, arriba=True)
    capa.alpaste = None
    capa.paste(scrim, (0, 0), scrim)
    d = ImageDraw.Draw(capa)

    f = fuente(F_BOLD, 108)
    tw, th = medir(d, gancho, f, spacing=14)
    x, y = 72, 232
    d.multiline_text((x, y), gancho, font=f, fill=TINTA, spacing=14)

    # Barrita de acento sobre el titular
    d.rounded_rectangle([x, y - 54, x + 132, y - 42], radius=6, fill=proyecto["acento"])

    # Etiqueta discreta arriba del todo
    fe = fuente(F_REG, 34)
    etiqueta = "LAVANDERA DESIGN  ·  CANARIAS"
    d.text((x + 2, 128), etiqueta, font=fe, fill=(255, 255, 255, 170))
    return capa


def capa_marca(proyecto, formato="movil"):
    """Pildora discreta con el dominio, abajo, presente casi todo el video."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)

    f = fuente(F_BOLD, 44)
    texto = DOMINIO
    tw = d.textlength(texto, font=f)
    pad_x, alto = 40, 96
    ancho = int(tw) + pad_x * 2 + 34
    x = (W - ancho) // 2
    y = H - 250

    d.rounded_rectangle([x, y, x + ancho, y + alto], radius=alto // 2,
                        fill=(9, 11, 15, 212))
    d.rounded_rectangle([x, y, x + ancho, y + alto], radius=alto // 2,
                        outline=proyecto["acento"] + (150,), width=3)
    punto_x = x + pad_x - 4
    d.ellipse([punto_x, y + alto // 2 - 8, punto_x + 16, y + alto // 2 + 8],
              fill=proyecto["acento"])
    d.text((punto_x + 32, y + alto // 2 - 30), texto, font=f, fill=TINTA)

    # Rotulo del proyecto, justo encima del dominio: honesto cliente vs demo.
    fp = fuente(F_REG, 31)
    if proyecto["tipo"] == "cliente":
        rotulo = f"{proyecto['nombre']}  ·  proyecto real de cliente"
    else:
        rotulo = f"{proyecto['nombre']}  ·  proyecto propio de muestra"
    rw = d.textlength(rotulo, font=fp)
    rx = (W - int(rw) - 52) // 2
    ry = y - 76
    d.rounded_rectangle([rx, ry, rx + int(rw) + 52, ry + 58], radius=29,
                        fill=(9, 11, 15, 195))
    d.text((rx + 26, ry + 12), rotulo, font=fp, fill=(214, 221, 231))

    # En formato escritorio queda hueco arriba: lo ocupamos con la ficha del
    # proyecto en lugar de dejar un degradado vacio 13 segundos.
    if formato == "escritorio":
        ft = fuente(F_BOLD, 88)
        nombre = proyecto["nombre"].upper()
        nw = d.textlength(nombre, font=ft)
        d.text(((W - nw) / 2, 300), nombre, font=ft, fill=TINTA)

        d.rounded_rectangle([W // 2 - 58, 424, W // 2 + 58, 431], radius=4,
                            fill=proyecto["acento"])

        fs = fuente(F_REG, 42)
        sub = f"{proyecto['sector'].capitalize()}  ·  {DOMINIO}"
        sw = d.textlength(sub, font=fs)
        d.text(((W - sw) / 2, 470), sub, font=fs, fill=TENUE)

        fe = fuente(F_REG, 32)
        et = "DISEÑO Y DESARROLLO WEB  ·  LAVANDERA DESIGN"
        ew = d.textlength(et, font=fe)
        d.text(((W - ew) / 2, 208), et, font=fe, fill=(255, 255, 255, 155))
    return capa


def capa_cierre(proyecto, cta, remate):
    """Cierre a pantalla completa: dominio grande + llamada a la accion."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fondo = Image.new("RGBA", (W, H), FONDO + (255,))
    capa.paste(fondo, (0, 0), fondo)
    d = ImageDraw.Draw(capa)

    ac = proyecto["acento"]

    # Halo de acento detras del bloque central
    halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    hd.ellipse([W // 2 - 470, H // 2 - 430, W // 2 + 470, H // 2 + 180], fill=ac + (46,))
    halo = halo.filter(ImageFilter.GaussianBlur(140))
    capa = Image.alpha_composite(capa, halo)
    d = ImageDraw.Draw(capa)

    cy = 700

    # Antetitulo
    fa = fuente(F_REG, 40)
    ante = "TU NEGOCIO MERECE UNA WEB ASÍ"
    aw = d.textlength(ante, font=fa)
    d.text(((W - aw) / 2, cy), ante, font=fa, fill=(255, 255, 255, 205))

    # Llamada a la accion, grande
    fc = fuente(F_BOLD, 92)
    lineas = envolver(d, cta, fc, W - 190)
    y = cy + 96
    for ln in lineas:
        lw = d.textlength(ln, font=fc)
        d.text(((W - lw) / 2, y), ln, font=fc, fill=TINTA)
        y += 108

    # Separador
    y += 40
    d.rounded_rectangle([W // 2 - 70, y, W // 2 + 70, y + 8], radius=4, fill=ac)
    y += 76

    # EL DOMINIO: lo mas grande y legible del cierre
    fd = fuente(F_BOLD, 82)
    dw = d.textlength(DOMINIO, font=fd)
    caja_w = int(dw) + 128
    caja_x = (W - caja_w) // 2
    d.rounded_rectangle([caja_x, y, caja_x + caja_w, y + 152], radius=32,
                        fill=(255, 255, 255, 250))
    d.text(((W - dw) / 2, y + 32), DOMINIO, font=fd, fill=(9, 11, 15))
    y += 152 + 60

    # Remate
    fr = fuente(F_REG, 44)
    for ln in envolver(d, remate, fr, W - 200):
        lw = d.textlength(ln, font=fr)
        d.text(((W - lw) / 2, y), ln, font=fr, fill=TENUE)
        y += 60

    # Firma abajo
    ff = fuente(F_REG, 34)
    firma = "LAVANDERA DESIGN  ·  DISEÑO Y DESARROLLO WEB  ·  CANARIAS"
    fw = d.textlength(firma, font=ff)
    d.text(((W - fw) / 2, H - 260), firma, font=ff, fill=(255, 255, 255, 165))
    return capa


def envolver(d, texto, font, max_w):
    palabras = texto.split()
    lineas, actual = [], ""
    for p in palabras:
        prueba = (actual + " " + p).strip()
        if d.textlength(prueba, font=font) <= max_w:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def marco_navegador(proyecto):
    """Fondo + chrome de navegador para el formato de escritorio."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ac = proyecto["acento"]

    fondo = Image.new("RGBA", (W, H), FONDO + (255,))
    bd = ImageDraw.Draw(fondo)
    bd.ellipse([-420, 420, W + 420, 1640], fill=ac + (38,))
    fondo = fondo.filter(ImageFilter.GaussianBlur(190))
    capa.paste(fondo, (0, 0))

    d = ImageDraw.Draw(capa)
    # Barra superior del navegador, a todo el ancho
    my = MARCO_Y
    d.rounded_rectangle([0, my, W, my + CHROME_H + 40], radius=30,
                        fill=(24, 27, 34, 255))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([46 + i * 42, my + 34, 68 + i * 42, my + 56], fill=c)
    fu = fuente(F_REG, 34)
    url = proyecto["url"]
    uw = d.textlength(url, font=fu)
    px = (W - int(uw) - 96) // 2
    d.rounded_rectangle([px, my + 20, px + int(uw) + 96, my + 70], radius=25,
                        fill=(13, 15, 20, 255))
    d.text((px + 48, my + 29), url, font=fu, fill=(163, 171, 184))
    return capa


def borde_captura(proyecto):
    """Filo fino alrededor de la captura, se pinta ENCIMA del video."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    y0 = MARCO_Y + CHROME_H
    d.rectangle([0, y0, W - 1, y0 + CAP_H], outline=(255, 255, 255, 28), width=2)
    # sombra suave bajo el bloque
    sombra = scrim_vertical((W, 150), (0, 0, 0), 120, 0, arriba=True)
    capa.paste(sombra, (0, y0 + CAP_H), sombra)
    return capa



# --------------------------------------------------------------------------
# Seleccion determinista de contenido
# --------------------------------------------------------------------------
SLOTS = ["12h", "16h", "21h"]


def elegir(fecha, slot):
    """Rotacion determinista: mismo dia+pase => mismo contenido reproducible.

    Reglas que cumple:
      - los 3 pases de un mismo dia son de 3 negocios DISTINTOS;
      - cada negocio sale exactamente 3 veces cada 6 dias (reparto uniforme);
      - un mismo pase no repite negocio hasta 6 dias despues;
      - gancho, llamada a la accion y tramo del metraje rotan por separado.
    """
    dia = fecha.toordinal()
    si = SLOTS.index(slot) if slot in SLOTS else 0
    npro = len(PROYECTOS)

    # (dia + 2*si) mod 6 -> dentro de un dia da 3 indices distintos (0,2,4 de
    # separacion) y a lo largo de los dias recorre los 6 negocios por igual.
    proyecto = PROYECTOS[(dia + 2 * si) % npro]

    # Vertical siempre que ese negocio tenga metraje vertical; si no, escritorio.
    if proyecto["movil"] and (dia + si) % 2 == 0:
        formato = "movil"
    else:
        formato = "escritorio"

    gancho = GANCHOS[(dia * 3 + si * 5) % len(GANCHOS)]
    cta = CTAS[(dia * 3 + si * 2) % len(CTAS)]
    remate = REMATES[(dia * 5 + si * 3) % len(REMATES)]
    arranque = ((dia + si) % 3) * 2.0
    return proyecto, formato, gancho, cta, remate, arranque


def construir_caption(proyecto, cta, remate):
    if proyecto["tipo"] == "cliente":
        linea_proy = (f"{proyecto['nombre']} ({proyecto['sector']}) es un encargo real "
                      f"diseñado y desarrollado por nosotros.")
    else:
        linea_proy = (f"AVISO: {proyecto['nombre']} es un proyecto propio de muestra. "
                      f"La marca, los textos y las imágenes son inventados por nosotros "
                      f"para enseñar cómo trabajamos; no es un negocio real.")

    return (
        f"{cta}.\n\n"
        f"{linea_proy}\n\n"
        f"Qué hacemos: webs a medida sin plantillas, tiendas online y sistemas de "
        f"reservas, chatbots y automatizaciones con IA, SEO y paneles internos.\n\n"
        f"{remate.rstrip(chr(46))}.\n\n"
        f"Entra en {DOMINIO} y te decimos gratis qué le falta a tu web. "
        f"El enlace también está en la bio.\n\n"
        f"{HASHTAGS}"
    )


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------
def duracion_de(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def render(proyecto, formato, gancho, cta, remate, salida, tmp, arranque=0.0):
    os.makedirs(tmp, exist_ok=True)
    archivo = proyecto[formato]
    src = os.path.join(FUENTES_DIR, archivo)
    if not os.path.exists(src):
        raise SystemExit(f"[ERROR] No encuentro el metraje: {src}")

    p_gancho = os.path.join(tmp, "gancho.png")
    p_marca = os.path.join(tmp, "marca.png")
    p_cierre = os.path.join(tmp, "cierre.png")
    capa_gancho(gancho, proyecto).save(p_gancho)
    capa_marca(proyecto, formato).save(p_marca)
    capa_cierre(proyecto, cta, remate).save(p_cierre)

    # Solo arrancamos mas adelante si al metraje le sobra metraje de verdad.
    sobra = duracion_de(src) - DUR
    ini = arranque if sobra >= arranque else 0.0
    entradas = ["-stream_loop", "-1"]
    if ini > 0:
        entradas += ["-ss", f"{ini:.2f}"]
    entradas += ["-i", src]

    if formato == "movil":
        base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},fps={FPS},setsar=1[base];")
    else:
        p_marco = os.path.join(tmp, "marco.png")
        p_borde = os.path.join(tmp, "borde.png")
        marco_navegador(proyecto).save(p_marco)
        borde_captura(proyecto).save(p_borde)
        entradas += ["-loop", "1", "-i", p_marco, "-loop", "1", "-i", p_borde]
        cap_y = MARCO_Y + CHROME_H
        base = (
            f"[0:v]scale={CAP_W_VIRTUAL}:{CAP_H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{CAP_H},fps={FPS},setsar=1[cap];"
            f"[1:v]format=rgba,fps={FPS},setsar=1[marco];"
            f"[marco][cap]overlay=0:{cap_y}:format=auto[conmarco];"
            f"[2:v]format=rgba,fps={FPS},setsar=1[borde];"
            f"[conmarco][borde]overlay=0:0:format=auto[base];"
        )

    # indices de las capas png
    i_gancho = 1 if formato == "movil" else 3
    i_marca = i_gancho + 1
    i_cierre = i_gancho + 2
    entradas += ["-loop", "1", "-i", p_gancho,
                 "-loop", "1", "-i", p_marca,
                 "-loop", "1", "-i", p_cierre]
    entradas += ["-f", "lavfi", "-i",
                 "anullsrc=channel_layout=stereo:sample_rate=44100"]
    i_audio = i_cierre + 1

    fc = base + (
        f"[{i_gancho}:v]format=rgba,fps={FPS},"
        f"fade=t=in:st=0.10:d=0.45:alpha=1,"
        f"fade=t=out:st={T_HOOK_FIN - 0.5:.2f}:d=0.45:alpha=1[g];"
        f"[base][g]overlay=0:0:enable='between(t,0,{T_HOOK_FIN})'[v1];"

        f"[{i_marca}:v]format=rgba,fps={FPS},"
        f"fade=t=in:st={T_MARCA_INI:.2f}:d=0.45:alpha=1,"
        f"fade=t=out:st={T_FINAL_INI - 0.6:.2f}:d=0.45:alpha=1[m];"
        f"[v1][m]overlay=0:0:enable='between(t,{T_MARCA_INI},{T_FINAL_INI})'[v2];"

        f"[{i_cierre}:v]format=rgba,fps={FPS},"
        f"fade=t=in:st={T_FINAL_INI:.2f}:d=0.55:alpha=1[c];"
        f"[v2][c]overlay=0:0:enable='gte(t,{T_FINAL_INI})'[vout]"
    )

    cmd = (["ffmpeg", "-y", "-loglevel", "error"] + entradas +
           ["-filter_complex", fc,
            "-map", "[vout]", "-map", f"{i_audio}:a",
            "-t", str(DUR),
            "-c:v", "libx264", "-preset", "fast", "-crf", "21",
            "-profile:v", "high", "-level", "4.0", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-g", str(FPS * 2),
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", salida])

    subprocess.run(cmd, check=True)
    return salida


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="12h", choices=SLOTS)
    ap.add_argument("--out", default=os.path.join(AQUI, "videos"))
    ap.add_argument("--fecha", default=None, help="YYYY-MM-DD")
    ap.add_argument("--nombre", default=None)
    ap.add_argument("--json", action="store_true",
                    help="imprime {file, caption} en JSON por stdout")
    args = ap.parse_args()

    fecha = (datetime.strptime(args.fecha, "%Y-%m-%d").date()
             if args.fecha else date.today())

    proyecto, formato, gancho, cta, remate, arranque = elegir(fecha, args.slot)
    os.makedirs(args.out, exist_ok=True)
    nombre = args.nombre or f"reel-{fecha.isoformat()}-{args.slot}-{proyecto['id']}-{formato}.mp4"
    salida = os.path.join(args.out, nombre)

    tmp = tempfile.mkdtemp(prefix="reel-", dir=os.path.join(AQUI, "tmp")
                           if os.path.isdir(os.path.join(AQUI, "tmp")) else None)
    try:
        render(proyecto, formato, gancho, cta, remate, salida, tmp, arranque)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    caption = construir_caption(proyecto, cta, remate)

    if args.json:
        print(json.dumps({"file": nombre, "caption": caption, "posted": False},
                         ensure_ascii=False))
    else:
        print(f"[OK] {salida}")
        print(f"     proyecto: {proyecto['nombre']} ({proyecto['tipo']}) · formato {formato}")
        print(f"     gancho  : {gancho.replace(chr(10), ' / ')}")
        print(f"     cta     : {cta}")


if __name__ == "__main__":
    main()
