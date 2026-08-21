#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

BASE = "https://graph.instagram.com"
POSTS_FILE = "posts.json"

IG_USER_ID = os.environ.get("IG_USER_ID", "").strip()
IG_TOKEN = os.environ.get("IG_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "").strip()
BRANCH = os.environ.get("GITHUB_REF_NAME", "main").strip() or "main"
# Si el workflow nos pasa el SHA del commit recien subido usamos ese, porque la
# URL por rama puede tardar en refrescarse en la CDN de GitHub.
VIDEO_REF = os.environ.get("VIDEO_REF", "").strip() or BRANCH


def _request(method, path, params):
    url = f"{BASE}/{path}"
    data = urllib.parse.urlencode(params).encode()
    if method == "GET":
        url = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"[ERROR API] {e.code} en {path}: {detail}")


def verify_token():
    me = _request("GET", "me", {"fields": "id,username,account_type",
                                "access_token": IG_TOKEN})
    print(f"[OK] Token valido. Cuenta: @{me.get('username')} (id {me.get('id')})")
    return me


def load_posts():
    if not os.path.exists(POSTS_FILE):
        raise SystemExit(f"[ERROR] No encuentro {POSTS_FILE}.")
    with open(POSTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_posts(posts):
    with open(POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)


def publish_next():
    if not IG_USER_ID or not IG_TOKEN:
        raise SystemExit("[ERROR] Faltan los secretos IG_USER_ID o IG_TOKEN.")
    verify_token()
    posts = load_posts()
    pending = [p for p in posts if not p.get("posted")]
    if not pending:
        print("[INFO] No hay videos pendientes.")
        return
    post = pending[0]
    if not REPO:
        raise SystemExit("[ERROR] No detecto el repositorio.")

    # Si el archivo ya no esta en el repo (limpieza antigua, borrado a mano),
    # no tiene sentido reintentarlo cada pase: se marca y se sigue.
    ruta_local = os.path.join("videos", post["file"])
    if not os.path.exists(ruta_local):
        print(f"[AVISO] {ruta_local} no existe en el repositorio. "
              f"Lo marco como hecho para no bloquear la cola.")
        post["posted"] = True
        save_posts(posts)
        return

    video_url = f"https://raw.githubusercontent.com/{REPO}/{VIDEO_REF}/videos/{post['file']}"
    caption = post.get("caption", "")
    print(f"[1/3] Preparando: {post['file']}")
    print(f"      URL: {video_url}")
    container = _request("POST", f"{IG_USER_ID}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "access_token": IG_TOKEN,
    })
    cid = container.get("id")
    if not cid:
        raise SystemExit(f"[ERROR] No se creo el contenedor: {container}")
    print(f"[2/3] Contenedor {cid}. Esperando a que Instagram procese el video...")
    for intento in range(30):
        estado = _request("GET", cid, {"fields": "status_code",
                                       "access_token": IG_TOKEN})
        sc = estado.get("status_code")
        if sc == "FINISHED":
            print("      Video procesado.")
            break
        if sc == "ERROR":
            raise SystemExit(f"[ERROR] Instagram no pudo procesar el video: {estado}")
        print(f"      ...{sc} ({intento + 1}/30)")
        time.sleep(10)
    else:
        raise SystemExit("[ERROR] El video tardo demasiado en procesarse.")
    result = _request("POST", f"{IG_USER_ID}/media_publish", {
        "creation_id": cid,
        "access_token": IG_TOKEN,
    })
    print(f"[3/3] PUBLICADO. ID: {result.get('id')}")
    post["posted"] = True
    save_posts(posts)
    restantes = len([p for p in posts if not p.get("posted")])
    print(f"[INFO] Quedan {restantes} videos en la cola.")


if __name__ == "__main__":
    if "--verify" in sys.argv:
        if not IG_TOKEN:
            raise SystemExit("[ERROR] Falta el secreto IG_TOKEN.")
        verify_token()
    else:
        publish_next()
