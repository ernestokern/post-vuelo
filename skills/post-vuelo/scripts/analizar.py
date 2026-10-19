"""Paso 2 · Analizar una salida: inventario, medidas por segundo y hojas de contacto.

Uso:  python analizar.py <carpeta_salida> [--crudo <carpeta>]

Deja en <salida>/analisis/:
- inventario.json  fotos (hora, GPS, altura, orientación) y videos (resolución, fps, color, ISO...)
- metricas.json    por video y por segundo: brillo, nitidez, movimiento; tramos quietos
- hojas/<video>.jpg  grilla de cuadros con la hora, para revisarlos de un vistazo

Los cuadros (1 por segundo, 320 px) quedan en la caché local, no en la salida.
"""
import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from comun import (VIDEOS, cargar_config, carpeta_cache, carpeta_crudo, chequear_herramientas, exif_foto,
                   ffmpeg, guardar_json, leer_srt, mmss, probe, xmp_dji)

QUIETO = 3.0        # movimiento medio por debajo de esto = imagen casi igual al segundo anterior
TRAMO_QUIETO = 8    # segundos seguidos quietos para marcarlo


def extraer(video: Path, cache: Path) -> list[Path]:
    carpeta = cache / video.stem
    if not any(carpeta.glob("*.jpg")):
        carpeta.mkdir(parents=True, exist_ok=True)
        ffmpeg("-i", str(video), "-vf", "fps=1,scale=320:-2", "-q:v", "4", str(carpeta / "%05d.jpg"))
    return sorted(carpeta.glob("*.jpg"))


def medir(cuadros: list[Path]) -> list[dict]:
    filas, previo = [], None
    for i, c in enumerate(cuadros):
        g = np.asarray(Image.open(c).convert("L"), dtype=np.float32)
        lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
        mov = float(np.abs(g - previo).mean()) if previo is not None and previo.shape == g.shape else 0.0
        filas.append({"t": i, "brillo": round(float(g.mean()), 1), "contraste": round(float(g.std()), 1),
                      "nitidez": round(float(lap.var()), 1), "movimiento": round(mov, 1)})
        previo = g
    return filas


def tramos_quietos(filas: list[dict]) -> list[list[int]]:
    tramos, ini = [], None
    for f in filas[1:] + [{"t": len(filas), "movimiento": 99}]:
        if f["movimiento"] < QUIETO:
            ini = f["t"] if ini is None else ini
        else:
            if ini is not None and f["t"] - ini >= TRAMO_QUIETO:
                tramos.append([ini, f["t"]])
            ini = None
    return tramos


def hoja(nombre: str, cuadros: list[Path], destino: Path) -> int:
    paso = max(1, math.ceil(len(cuadros) / 40))
    elegidos = cuadros[::paso]
    ancho, cols = 200, 8
    alto = round(ancho * 9 / 16)
    lienzo = Image.new("RGB", (cols * ancho, math.ceil(len(elegidos) / cols) * alto), "black")
    d = ImageDraw.Draw(lienzo)
    for k, c in enumerate(elegidos):
        x, y = (k % cols) * ancho, (k // cols) * alto
        lienzo.paste(Image.open(c).resize((ancho, alto)), (x, y))
        d.rectangle([x, y, x + 42, y + 14], fill="black")
        d.text((x + 3, y + 1), mmss(k * paso), fill="yellow")
    destino.mkdir(parents=True, exist_ok=True)
    lienzo.save(destino / f"{nombre}.jpg", quality=82)
    return paso


def main():
    ap = argparse.ArgumentParser(description="Analizar los videos y fotos de una salida.")
    ap.add_argument("salida", help="carpeta de la salida (la que tiene crudo/)")
    ap.add_argument("--crudo", help="carpeta con los archivos, si no es <salida>/crudo")
    ap.add_argument("--config")
    args = ap.parse_args()
    chequear_herramientas()

    salida = Path(args.salida).resolve()
    crudo = carpeta_crudo(salida, args.crudo)
    analisis = salida / "analisis"
    cache = carpeta_cache(cargar_config(args.config)) / "cuadros" / salida.name

    inventario = {"fotos": [], "videos": {}}
    for p in sorted(crudo.glob("DJI_*")):
        if p.suffix.upper() in (".JPG", ".JPEG"):
            ex, x = exif_foto(p), xmp_dji(p)
            inventario["fotos"].append({
                "archivo": p.name, "hora": ex["hora"].isoformat() if ex["hora"] else None,
                "modelo": ex["modelo"], "tamano": ex["tamano"],
                "lat": x.get("Latitude"), "lon": x.get("Longitude"), "altura": x.get("RelativeAltitude"),
                "rumbo": x.get("GimbalYawDegree", x.get("FlightYawDegree")), "camara": x.get("GimbalPitchDegree"),
                "raw": p.with_suffix(".DNG").exists(),
            })

    metricas = {}
    for v in sorted(p for p in crudo.glob("DJI_*") if p.suffix.upper() in VIDEOS):
        pr, srt = probe(v), leer_srt(v.with_suffix(".SRT"), todo=True)
        inicio = srt.get("inicio") or pr["creacion"]
        cuadros = extraer(v, cache)
        filas = medir(cuadros)
        quietos = tramos_quietos(filas)
        paso = hoja(v.stem, cuadros, analisis / "hojas")
        inventario["videos"][v.stem] = {
            "archivo": v.name, "inicio": inicio.isoformat() if inicio else None,
            "segundos": round(pr["segundos"], 2), "ancho": pr["ancho"], "alto": pr["alto"], "fps": pr["fps"],
            "color": srt.get("color"), "iso": srt.get("iso"), "obturador": srt.get("obturador"),
            "temp_color": srt.get("temp_color"), "mb": round(v.stat().st_size / 1e6),
        }
        metricas[v.stem] = {"quietos": quietos, "paso_hoja": paso, "por_segundo": filas}
        seg_q = sum(b - a for a, b in quietos)
        print(f"{v.stem}: {pr['ancho']}x{pr['alto']} · {mmss(pr['segundos'])} · quieto {mmss(seg_q)}"
              + (f" en {len(quietos)} tramos" if quietos else ""), flush=True)

    guardar_json(analisis / "inventario.json", inventario)
    guardar_json(analisis / "metricas.json", metricas, indent=None)
    bajas = [k for k, v in inventario["videos"].items() if (v["alto"] or 0) < 2160]
    print(f"\n{len(inventario['fotos'])} fotos, {len(metricas)} videos. Hojas de contacto en {analisis / 'hojas'}")
    if bajas:
        print(f"⚠ {len(bajas)} videos están por debajo de 4K: sirven para elegir, no para cortes verticales finales.")


if __name__ == "__main__":
    main()
