"""Paso 3 · Armar la página para elegir tomas (y ver los cortes terminados).

Uso:  python pagina.py <carpeta_salida> [--pagina <carpeta>] [--sin-ubicacion] [--titulo "..."]

Lee <salida>/analisis/ (inventario, metricas, notas) y, si existen, los cortes de <salida>/instagram/.
Deja una página autocontenida (index.html + media/) que se puede:
- publicar como artifact de Claude: las elecciones se guardan solas y Claude las lee;
- subir a cualquier hosting estático, o abrir local: cada uno elige y toca "Copiar mi elección".

--sin-ubicacion  no incluye mapa, coordenadas ni metadatos en fotos y videos. Usalo cuando
                 la página la va a ver gente de afuera.
"""
import argparse
import io
import json
import math
import urllib.request
from pathlib import Path

from PIL import Image, ImageStat

from comun import carpeta_crudo, ffmpeg, guardar_json, leer_json

AQUI = Path(__file__).resolve().parent
TILE = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"


def imagen_limpia(src: Path, dst: Path, lado: int):
    """Miniatura sin EXIF ni XMP: la foto nueva no lleva GPS ni datos del aparato."""
    im = Image.open(src).convert("RGB")
    im.thumbnail((lado, lado))
    limpia = Image.new("RGB", im.size)
    limpia.paste(im)
    dst.parent.mkdir(parents=True, exist_ok=True)
    limpia.save(dst, quality=76)


def vista_previa(video: Path, ini: float, fin: float, dst: Path, ancho: int = 480):
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-ss", f"{ini:.2f}", "-to", f"{fin:.2f}", "-i", str(video), "-vf", f"scale={ancho}:-2",
           "-c:v", "libx264", "-crf", "30", "-preset", "veryfast", "-an", "-map_metadata", "-1",
           "-movflags", "+faststart", str(dst))


def poster(video: Path, t: float, dst: Path, ancho: int = 480):
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", "-vf", f"scale={ancho}:-2",
           "-map_metadata", "-1", "-q:v", "5", str(dst))


# ---------- mapa satelital estático ----------

def px(lat, lon, z):
    n = 2 ** z * 256
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def bajar_tile(z, x, y) -> Image.Image:
    req = urllib.request.Request(TILE.format(z=z, x=x, y=y), headers={"User-Agent": "post-vuelo/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def mapa(nombre: str, fotos: list[dict], media: Path) -> dict | None:
    fotos = [f for f in fotos if f.get("lat") is not None]
    if not fotos:
        return None
    lats, lons = [f["lat"] for f in fotos], [f["lon"] for f in fotos]
    z = 18
    while z > 14:
        x0, y1 = px(min(lats), min(lons), z)
        x1, y0 = px(max(lats), max(lons), z)
        if x1 - x0 < 600 and y1 - y0 < 380:
            break
        z -= 1
    # En zonas rurales no hay imagen en los zooms más cercanos (llega un gris liso): alejarse
    while z > 14:
        cx, cy = px(sum(lats) / len(lats), sum(lons) / len(lons), z)
        if ImageStat.Stat(bajar_tile(z, int(cx // 256), int(cy // 256)).convert("L")).stddev[0] > 18:
            break
        z -= 1
    x0, y1 = px(min(lats), min(lons), z)
    x1, y0 = px(max(lats), max(lons), z)
    w, h = 960, 600
    left, top = (x0 + x1) / 2 - w / 2, (y0 + y1) / 2 - h / 2
    lienzo = Image.new("RGB", (w, h))
    for tx in range(int(left // 256), int((left + w) // 256) + 1):
        for ty in range(int(top // 256), int((top + h) // 256) + 1):
            lienzo.paste(bajar_tile(z, tx, ty), (int(tx * 256 - left), int(ty * 256 - top)))
    dst = media / "mapas" / f"{nombre}.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    lienzo.save(dst, quality=80)
    for f in fotos:
        x, y = px(f["lat"], f["lon"], z)
        f["x"], f["y"] = round((x - left) / w * 100, 2), round((y - top) / h * 100, 2)
    metros_px = 156543.03 * math.cos(math.radians(sum(lats) / len(lats))) / 2 ** z
    return {"imagen": f"media/mapas/{nombre}.jpg", "metros_por_100px": round(metros_px * 100)}


def main():
    ap = argparse.ArgumentParser(description="Armar la página de elección de tomas.")
    ap.add_argument("salida")
    ap.add_argument("--crudo")
    ap.add_argument("--pagina", help="carpeta de salida de la página (por defecto ./pagina/<salida>)")
    ap.add_argument("--sin-ubicacion", action="store_true", help="sin mapa, sin coordenadas, sin nombre del lugar")
    ap.add_argument("--titulo", help="título visible (por defecto, el nombre de la salida)")
    ap.add_argument("--descargas", help="link a la carpeta con los cortes en alta (ej. Google Drive)")
    args = ap.parse_args()

    salida = Path(args.salida).resolve()
    crudo = carpeta_crudo(salida, args.crudo)
    analisis = salida / "analisis"
    inv = leer_json(analisis / "inventario.json")
    notas = leer_json(analisis / "notas.json")
    if not inv or not notas:
        raise SystemExit("Falta analisis/inventario.json o analisis/notas.json: corré analizar.py y escribí las notas.")
    metricas = leer_json(analisis / "metricas.json", {})
    pagina = Path(args.pagina or Path.cwd() / "pagina" / salida.name).resolve()
    media = pagina / "media"

    fecha = salida.name[:10]
    titulo = args.titulo or (f"Salida del {fecha}" if args.sin_ubicacion else salida.name)

    videos = {}
    for k, v in inv["videos"].items():
        videos[k] = {"inicio": v["inicio"], "segundos": round(v["segundos"]), "ancho": v["ancho"], "alto": v["alto"],
                     "quietos": metricas.get(k, {}).get("quietos", [])}

    tomas = []
    for t in notas["tomas"]:
        src = crudo / inventario_archivo(inv, t["video"])
        vista_previa(src, t["ini"], t["fin"], media / "clips" / f"{t['id']}.mp4")
        poster(src, t["ini"] + (t["fin"] - t["ini"]) * 0.6, media / "clips" / f"{t['id']}.jpg")
        inicio = videos[t["video"]]["inicio"] or ""
        tomas.append({**t, "dia": inicio[:10], "hora": inicio[11:16]})

    # Cortes terminados (recortar.py los deja en <salida>/instagram con un listado)
    listas = []
    for c in leer_json(salida / "instagram" / "cortes.json", []):
        archivo = salida / "instagram" / c["archivo"]
        if not archivo.exists():
            continue
        ancho = 360 if c["formato"] != "16x9" else 480
        prev = media / "listas" / f"{Path(c['archivo']).stem}.mp4"
        if not prev.exists():
            prev.parent.mkdir(parents=True, exist_ok=True)
            ffmpeg("-i", str(archivo), "-vf", f"scale={ancho}:-2", "-c:v", "libx264", "-crf", "30",
                   "-preset", "veryfast", "-an", "-map_metadata", "-1", "-movflags", "+faststart", str(prev))
        listas.append({**c, "vista": f"media/listas/{prev.name}"})

    fotos, mapas = [], {}
    for f in inv["fotos"]:
        imagen_limpia(crudo / f["archivo"], media / "fotos" / f["archivo"], 720)
        fotos.append({k: f.get(k) for k in ("archivo", "hora", "altura", "rumbo", "camara", "lat", "lon")})
    dias = sorted({(v["inicio"] or "")[:10] for v in videos.values()} | {(f["hora"] or "")[:10] for f in fotos})
    if args.sin_ubicacion:
        for f in fotos:
            f.pop("lat"), f.pop("lon")
    else:
        for d in dias:
            mapas[d] = mapa(d, [f for f in fotos if (f["hora"] or "").startswith(d)], media)
        for f in fotos:
            f.pop("lat"), f.pop("lon")  # ya quedaron como posición x/y sobre la imagen

    datos = {
        "salida": salida.name if not args.sin_ubicacion else fecha,
        "titulo": titulo, "revisado": notas.get("revisado"), "sin_ubicacion": args.sin_ubicacion,
        "tomas": tomas, "descartes": notas.get("descartes", []), "videos": videos,
        "fotos": fotos, "mapas": mapas, "listas": listas, "descargas": args.descargas,
    }
    plantilla = (AQUI.parent / "plantillas" / "pagina.html").read_text(encoding="utf-8")
    html = plantilla.replace("/*DATOS*/{}", json.dumps(datos, ensure_ascii=False)).replace("{{TITULO}}", titulo)
    (pagina / "index.html").write_text(html, encoding="utf-8")  # para artifact: el visor agrega el esqueleto
    (pagina / "sitio.html").write_text(  # para cualquier hosting estático o abrir con doble clic
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        f"</head><body>{html}</body></html>", encoding="utf-8")
    archivos = sorted(str(p.relative_to(pagina)).replace("\\", "/") for p in media.rglob("*") if p.is_file())
    guardar_json(pagina / "archivos.json", archivos)
    peso = sum(p.stat().st_size for p in pagina.rglob("*") if p.is_file())
    print(f"{len(tomas)} tomas, {len(listas)} cortes listos, {len(fotos)} fotos · {peso / 1e6:.1f} MB")
    print(f"PAGINA: {pagina / 'index.html'}")


def inventario_archivo(inv: dict, video: str) -> str:
    return inv["videos"][video]["archivo"]


if __name__ == "__main__":
    main()
