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
# Las 12 son maquetas PROPIAS: marca, textos e imagenes inventados por
# nosotros, con fotos de licencia libre. Ninguna pertenece a un negocio real,
# asi que ninguna puede rotularse como cliente. El tipo se rotula en pantalla.
PROYECTOS = [
    {
        "id": "marea-viva", "nombre": "Marea Viva",
        "sector": "charter náutico", "tipo": "demo", "acento": (79, 195, 232),
        "movil": "01-charter-nautico-marea-viva-movil.mp4",
        "escritorio": "01-charter-nautico-marea-viva-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "casa-timanfaya", "nombre": "Casa Timanfaya",
        "sector": "villa vacacional", "tipo": "demo", "acento": (194, 114, 74),
        "movil": "02-villa-vacacional-casa-timanfaya-movil.mp4",
        "escritorio": "02-villa-vacacional-casa-timanfaya-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "salitre", "nombre": "Salitre",
        "sector": "restaurante", "tipo": "demo", "acento": (224, 160, 48),
        "movil": "03-restaurante-salitre-movil.mp4",
        "escritorio": "03-restaurante-salitre-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "vega-motor", "nombre": "Vega Motor",
        "sector": "concesionario", "tipo": "demo", "acento": (217, 84, 31),
        "movil": "04-concesionario-vega-motor-movil.mp4",
        "escritorio": "04-concesionario-vega-motor-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "clinica-aran", "nombre": "Clínica Arán",
        "sector": "medicina estética", "tipo": "demo", "acento": (63, 148, 110),
        "movil": "05-clinica-estetica-aran-movil.mp4",
        "escritorio": "05-clinica-estetica-aran-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "malvasia-alta", "nombre": "Bodega Malvasía Alta",
        "sector": "bodega", "tipo": "demo", "acento": (201, 162, 75),
        "movil": "06-bodega-malvasia-alta-movil.mp4",
        "escritorio": "06-bodega-malvasia-alta-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "casona-del-risco", "nombre": "Casona del Risco",
        "sector": "hotel rural", "tipo": "demo", "acento": (200, 155, 90),
        "movil": "07-hotel-rural-casona-del-risco-movil.mp4",
        "escritorio": "07-hotel-rural-casona-del-risco-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "taller-tosca", "nombre": "Taller Tosca",
        "sector": "reformas e interiorismo", "tipo": "demo", "acento": (227, 181, 5),
        "movil": "08-reformas-taller-tosca-movil.mp4",
        "escritorio": "08-reformas-taller-tosca-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "cardon", "nombre": "Cardón Propiedades",
        "sector": "inmobiliaria", "tipo": "demo", "acento": (143, 179, 160),
        "movil": "09-inmobiliaria-cardon-propiedades-movil.mp4",
        "escritorio": "09-inmobiliaria-cardon-propiedades-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "basalto", "nombre": "Basalto Performance",
        "sector": "centro de rendimiento", "tipo": "demo", "acento": (180, 255, 58),
        "movil": "10-centro-rendimiento-basalto-movil.mp4",
        "escritorio": "10-centro-rendimiento-basalto-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "bruma-banos", "nombre": "Bruma Baños",
        "sector": "spa y baños", "tipo": "demo", "acento": (110, 140, 160),
        "movil": "11-spa-bruma-banos-movil.mp4",
        "escritorio": "11-spa-bruma-banos-escritorio.mp4",
        "url": DOMINIO,
    },
    {
        "id": "corriente-norte", "nombre": "Corriente Norte",
        "sector": "escuela de surf", "tipo": "demo", "acento": (255, 107, 44),
        "movil": "12-escuela-surf-corriente-norte-movil.mp4",
        "escritorio": "12-escuela-surf-corriente-norte-escritorio.mp4",
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

HASHTAGS_TIKTOK = ("#diseñoweb #paginaweb #negociolocal #canarias #emprendedores "
                   "#pymes #webdesign #marketingdigital #tenerife #laspalmas "
                   "#lanzarote #fuerteventura #emprenderespaña #negocios #seo "
                   "#parati #fyp")

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


def elegir(fecha, slot, variante="instagram"):
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

    # Desplazamiento de la variante. Con 6 negocios, sumar 3 garantiza que el
    # video de TikTok NUNCA cae en el mismo negocio que el de Instagram.
    dv = 3 if variante == "tiktok" else 0

    # (dia + 2*si) mod 6 -> dentro de un dia da 3 indices distintos (0,2,4 de
    # separacion) y a lo largo de los dias recorre los 6 negocios por igual.
    proyecto = PROYECTOS[(dia + 2 * si + dv) % npro]

    # Vertical siempre que ese negocio tenga metraje vertical; si no, escritorio.
    par = (dia + si + (1 if variante == "tiktok" else 0)) % 2
    if proyecto["movil"] and par == 0:
        formato = "movil"
    else:
        formato = "escritorio"

    dg = 4 if variante == "tiktok" else 0
    dc = 2 if variante == "tiktok" else 0
    gancho = GANCHOS[(dia * 3 + si * 5 + dg) % len(GANCHOS)]
    cta = CTAS[(dia * 3 + si * 2 + dc) % len(CTAS)]
    remate = REMATES[(dia * 5 + si * 3 + dc) % len(REMATES)]
    arranque = ((dia + si + dv) % 3) * 2.0

    # Tipo de anuncio. El desplazamiento de 2 hace que el de TikTok NUNCA
    # tenga la misma forma que el de Instagram del mismo pase, y dentro de un
    # mismo dia los tres pases tampoco se repiten.
    dt = 2 if variante == "tiktok" else 0
    tipo = TIPOS[(dia * 5 + si * 3 + dt) % len(TIPOS)]
    dato = DATOS[(dia * 3 + si + dt) % len(DATOS)]
    serie = SERIES[(dia * 7 + si * 2 + dt) % len(SERIES)]
    return proyecto, formato, gancho, cta, remate, arranque, tipo, dato, serie


def construir_caption(proyecto, cta, remate, variante="instagram"):
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
        f"{HASHTAGS_TIKTOK if variante == 'tiktok' else HASHTAGS}"
    )


# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Tipos de anuncio
# --------------------------------------------------------------------------
# Cuatro maneras distintas de abrir el mismo metraje. Rotan para que dos
# anuncios seguidos nunca tengan la misma forma, no solo distinto negocio.
TIPOS = ["escaparate", "dato", "ficha", "lista"]

# Datos NUESTROS, comprobables en lavanderadesign.com. No usamos estadisticas
# de terceros: si lo decimos en un anuncio, tiene que ser algo que cumplimos.
DATOS = [
    ("24 h", "es lo que tardamos en contestarte"),
    ("0 €", "cuesta que te digamos qué falla en tu web"),
    ("3 días", "es nuestro plazo de entrega más corto"),
    ("12", "sectores distintos diseñados desde cero"),
]

SERIES = [
    ["Sin plantillas", "Diseño propio", "Tuya de verdad"],
    ["Se ve bien en el móvil", "Carga rápido", "Y además vende"],
    ["Web a medida", "Tienda y reservas", "SEO y automatización"],
    ["Lo diseñamos", "Lo programamos", "Lo mantenemos"],
]


def capa_dato(dato, proyecto):
    """Apertura con una cifra grande a pantalla completa."""
    cifra, linea = dato
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fondo = Image.new("RGBA", (W, H), FONDO + (250,))
    capa.paste(fondo, (0, 0), fondo)
    d = ImageDraw.Draw(capa)
    ac = proyecto["acento"]

    fe = fuente(F_REG, 34)
    d.text((72, 300), "LAVANDERA DESIGN  ·  CANARIAS", font=fe, fill=(255, 255, 255, 170))

    fc = fuente(F_BOLD, 300)
    d.text((66, 380), cifra, font=fc, fill=ac)

    fl = fuente(F_REG, 62)
    y = 760
    for ln in envolver(d, linea, fl, W - 150):
        d.text((72, y), ln, font=fl, fill=TINTA)
        y += 78
    d.rounded_rectangle([72, y + 30, 204, y + 42], radius=6, fill=ac)
    return capa


def capa_ficha(proyecto):
    """Apertura tipo portafolio: sector y aviso de maqueta."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fondo = Image.new("RGBA", (W, H), FONDO + (248,))
    capa.paste(fondo, (0, 0), fondo)
    d = ImageDraw.Draw(capa)
    ac = proyecto["acento"]

    fe = fuente(F_REG, 36)
    et = proyecto["sector"].upper()
    ew = d.textlength(et, font=fe)
    d.text(((W - ew) / 2, 640), et, font=fe, fill=ac + (230,))

    fn = fuente(F_BOLD, 104)
    for i, ln in enumerate(envolver(d, proyecto["nombre"], fn, W - 160)):
        lw = d.textlength(ln, font=fn)
        d.text(((W - lw) / 2, 720 + i * 118), ln, font=fn, fill=TINTA)

    d.rounded_rectangle([W // 2 - 70, 960, W // 2 + 70, 968], radius=4, fill=ac)

    fs = fuente(F_REG, 40)
    sub = "Diseñada y desarrollada por nosotros"
    sw = d.textlength(sub, font=fs)
    d.text(((W - sw) / 2, 1010), sub, font=fs, fill=TENUE)

    fa = fuente(F_REG, 30)
    av = "MAQUETA DE MUESTRA · NO ES UN NEGOCIO REAL"
    aw = d.textlength(av, font=fa)
    d.text(((W - aw) / 2, 1110), av, font=fa, fill=(255, 255, 255, 130))
    return capa


def capa_frase(texto, proyecto):
    """Banda inferior con una frase corta, para el tipo 'lista'."""
    capa = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(capa)
    f = fuente(F_BOLD, 76)
    lineas = envolver(d, texto, f, W - 200)
    alto = 60 + len(lineas) * 92
    y0 = H - 250 - alto - 40
    d.rounded_rectangle([56, y0, W - 56, y0 + alto], radius=34, fill=(9, 11, 15, 224))
    d.rounded_rectangle([56, y0, 68, y0 + alto], radius=6, fill=proyecto["acento"])
    y = y0 + 30
    for ln in lineas:
        d.text((104, y), ln, font=f, fill=TINTA)
        y += 92
    return capa


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


def render(proyecto, formato, gancho, cta, remate, salida, tmp,
           arranque=0.0, tipo="escaparate", dato=None, serie=None):
    os.makedirs(tmp, exist_ok=True)
    archivo = proyecto[formato]
    src = os.path.join(FUENTES_DIR, archivo)
    if not os.path.exists(src):
        raise SystemExit(f"[ERROR] No encuentro el metraje: {src}")

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

    # Capas: (ruta, t_inicio, t_fin, fundido_entrada, fundido_salida)
    capas = []
    n = 0

    def guardar(img, sufijo):
        nonlocal n
        r = os.path.join(tmp, f"capa_{n}_{sufijo}.png")
        n += 1
        img.save(r)
        return r

    if tipo == "dato":
        capas.append((guardar(capa_dato(dato, proyecto), "dato"), 0.0, 3.0, 0.10, 0.45))
        t_marca = 3.1
    elif tipo == "ficha":
        capas.append((guardar(capa_ficha(proyecto), "ficha"), 0.0, 2.8, 0.10, 0.45))
        t_marca = 2.9
    elif tipo == "lista":
        for i, frase in enumerate(serie):
            a = 1.2 + i * 4.6
            capas.append((guardar(capa_frase(frase, proyecto), f"f{i}"),
                          a, a + 3.0, 0.35, 0.35))
        t_marca = 0.6
    else:  # escaparate
        capas.append((guardar(capa_gancho(gancho, proyecto), "gancho"),
                      0.0, T_HOOK_FIN, 0.10, 0.45))
        t_marca = T_MARCA_INI

    # En el tipo 'lista' la pildora del dominio comparte sitio con las frases,
    # asi que la marca va solo cuando no hay frase en pantalla.
    if tipo != "lista":
        capas.append((guardar(capa_marca(proyecto, formato), "marca"),
                      t_marca, T_FINAL_INI, 0.45, 0.45))
    else:
        ultima = 1.2 + (len(serie) - 1) * 4.6 + 3.0
        capas.append((guardar(capa_marca(proyecto, formato), "marca"),
                      ultima + 0.4, T_FINAL_INI, 0.45, 0.45))

    capas.append((guardar(capa_cierre(proyecto, cta, remate), "cierre"),
                  T_FINAL_INI, DUR + 1, 0.55, None))

    # Cadena de superposiciones
    idx0 = 1 if formato == "movil" else 3
    fc = base
    etiqueta = "base"
    for k, (ruta, t0, t1, fin_, fout) in enumerate(capas):
        entradas += ["-loop", "1", "-i", ruta]
        i = idx0 + k
        fundidos = f"fade=t=in:st={t0 + 0.05:.2f}:d={fin_:.2f}:alpha=1"
        if fout:
            fundidos += f",fade=t=out:st={t1 - fout - 0.05:.2f}:d={fout:.2f}:alpha=1"
        siguiente = f"v{k}"
        fc += (f"[{i}:v]format=rgba,fps={FPS},{fundidos}[c{k}];"
               f"[{etiqueta}][c{k}]overlay=0:0:"
               f"enable='between(t,{t0:.2f},{t1:.2f})'[{siguiente}];")
        etiqueta = siguiente
    fc = fc.rstrip(";").replace(f"[{etiqueta}];", f"[{etiqueta}]")
    if fc.endswith(f"[{etiqueta}]") is False:
        fc += f"[{etiqueta}]"

    i_audio = idx0 + len(capas)
    entradas += ["-f", "lavfi", "-i",
                 "anullsrc=channel_layout=stereo:sample_rate=44100"]

    cmd = (["ffmpeg", "-y", "-loglevel", "error"] + entradas +
           ["-filter_complex", fc,
            "-map", f"[{etiqueta}]", "-map", f"{i_audio}:a",
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
    ap.add_argument("--variante", default="instagram",
                    choices=["instagram", "tiktok"],
                    help="tiktok elige SIEMPRE otro negocio y otro gancho")
    ap.add_argument("--json", action="store_true",
                    help="imprime {file, caption} en JSON por stdout")
    args = ap.parse_args()

    fecha = (datetime.strptime(args.fecha, "%Y-%m-%d").date()
             if args.fecha else date.today())

    proyecto, formato, gancho, cta, remate, arranque, tipo, dato, serie = elegir(
        fecha, args.slot, args.variante)
    os.makedirs(args.out, exist_ok=True)
    prefijo = "tiktok" if args.variante == "tiktok" else "reel"
    nombre = (args.nombre or
              f"{prefijo}-{fecha.isoformat()}-{args.slot}-{proyecto['id']}"
              f"-{formato}-{tipo}.mp4")
    salida = os.path.join(args.out, nombre)

    tmp = tempfile.mkdtemp(prefix="reel-", dir=os.path.join(AQUI, "tmp")
                           if os.path.isdir(os.path.join(AQUI, "tmp")) else None)
    try:
        render(proyecto, formato, gancho, cta, remate, salida, tmp,
               arranque, tipo, dato, serie)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    caption = construir_caption(proyecto, cta, remate, args.variante)

    if args.json:
        salida_json = {"file": nombre, "caption": caption}
        if args.variante == "tiktok":
            salida_json.update({"fecha": fecha.isoformat(), "slot": args.slot,
                                "negocio": proyecto["nombre"], "formato": formato,
                                "tipo_anuncio": tipo})
        else:
            salida_json["posted"] = False
        print(json.dumps(salida_json, ensure_ascii=False))
    else:
        print(f"[OK] {salida}")
        print(f"     variante: {args.variante} · anuncio tipo {tipo}")
        print(f"     proyecto: {proyecto['nombre']} ({proyecto['tipo']}) · formato {formato}")
        print(f"     gancho  : {gancho.replace(chr(10), ' / ')}")
        print(f"     cta     : {cta}")


if __name__ == "__main__":
    main()
