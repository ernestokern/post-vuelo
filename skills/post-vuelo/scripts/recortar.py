"""Paso 4b · Recortar las tomas elegidas en máxima calidad para Instagram.

Uso:  python recortar.py <salida> [--solo t01,t03] [--formatos 9x16,4x5,16x9] [--crudo <carpeta>]

Por cada toma elegida (analisis/eleccion.json, o --solo) hace:
- 9x16  1080×1920  historias y reels
- 4x5   1080×1350  feed y carrusel
- 16x9  la resolución del original (4K si se grabó en 4K), para pasar entera; nunca se agranda

Vertical (9x16 y 4x5), --vertical auto|recorte|relleno:
- recorte: una franja del cuadro. Solo queda nítida si el original es 4K.
- relleno: el cuadro entero, nítido, al centro, y el mismo video desenfocado arriba y abajo.
  Es lo que usa "auto" cuando el original no alcanza para recortar sin estirar.

Encuadre: en analisis/notas.json cada toma puede tener "encuadre": {"x": 0.5} (0 = borde izquierdo,
1 = borde derecho) o {"x": [0.2, 0.7]} para un paneo suave de un lado al otro durante la toma.
Color: si el video está en D-Cinelike aplica una curva de contraste y saturación; si la
configuración tiene "lut": "<archivo .cube>", usa ese LUT.
Calidad: H.264 CRF 18 (a la vista, igual al original), sin audio, sin metadatos (no lleva GPS). Si la franja recortada tiene
menos píxeles que la salida, el archivo termina en -BORRADOR y queda anotado en cortes.json.
"""
import argparse
import re
from pathlib import Path

from comun import cargar_config, carpeta_crudo, chequear_herramientas, ffmpeg, guardar_json, leer_json, probe

FORMATOS = {"9x16": (9, 16, 1080, 1920), "4x5": (4, 5, 1080, 1350), "16x9": (16, 9, None, None)}
CURVA_DCINELIKE = "curves=master='0/0 0.18/0.13 0.5/0.5 0.82/0.88 1/1',eq=saturation=1.28"


def slug(s: str) -> str:
    s = s.lower()
    for a, b in zip("áéíóúñü", "aeiounu"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40]


def par(n: float) -> int:
    return int(n) // 2 * 2


def filtro_color(color: str | None, lut: str | None) -> str | None:
    if lut:
        return f"lut3d=file='{Path(lut).as_posix().replace(':', chr(92) + ':')}'"
    if color and "cin" in color.lower():
        return CURVA_DCINELIKE
    return None


def main():
    ap = argparse.ArgumentParser(description="Recortar tomas elegidas para Instagram")
    ap.add_argument("salida")
    ap.add_argument("--crudo")
    ap.add_argument("--solo", help="ids separados por coma (si no, las de eleccion.json)")
    ap.add_argument("--formatos", default="9x16,4x5,16x9")
    ap.add_argument("--vertical", choices=["auto", "recorte", "relleno"], default="auto",
                    help="9:16 y 4:5: recortar una franja, o cuadro entero con fondo desenfocado. "
                         "auto = recorte si el original alcanza (4K), si no relleno")
    ap.add_argument("--config")
    args = ap.parse_args()
    chequear_herramientas()

    salida = Path(args.salida).resolve()
    crudo = carpeta_crudo(salida, args.crudo)
    cfg = cargar_config(args.config)
    inv = leer_json(salida / "analisis" / "inventario.json")
    notas = leer_json(salida / "analisis" / "notas.json")
    ids = args.solo.split(",") if args.solo else leer_json(salida / "analisis" / "eleccion.json", {}).get("elegidas", [])
    if not ids:
        raise SystemExit("No hay tomas elegidas: usá --solo o corré eleccion.py.")
    tomas = {t["id"]: t for t in notas["tomas"]}
    destino = salida / "instagram"
    destino.mkdir(parents=True, exist_ok=True)
    listado = [c for c in leer_json(destino / "cortes.json", []) if c["toma"] not in ids]

    for i in ids:
        t = tomas[i]
        v = inv["videos"][t["video"]]
        src = crudo / v["archivo"]
        pr = probe(src)
        iw, ih = pr["ancho"], pr["alto"]
        dur = t["fin"] - t["ini"]
        enc = (t.get("encuadre") or {}).get("x", 0.5)
        x0, x1 = (enc, enc) if not isinstance(enc, list) else enc
        color = filtro_color(v.get("color"), cfg.get("lut"))
        for fmt in args.formatos.split(","):
            pw, ph, ow, oh = FORMATOS[fmt]
            modo = "entero"
            if fmt == "16x9":
                # Nunca se agranda: 4K queda en 4K, 1080p en 1080p, 720p en 720p
                cw, ch = iw, ih
                ow, oh = (3840, 2160) if ih >= 2160 else (par(ih * 16 / 9), ih)
                cadena = f"scale={ow}:{oh}:flags=lanczos"
            else:
                ch, cw = ih, par(ih * pw / ph)
                modo = args.vertical if args.vertical != "auto" else ("recorte" if ow / cw <= 1.0 else "relleno")
                if modo == "recorte":
                    # franja vertical; x fijo o moviéndose de x0 a x1 a lo largo de la toma
                    mov = f"({x0}+({x1}-{x0})*t/{dur:.2f})" if x0 != x1 else f"{x0}"
                    cadena = f"crop={cw}:{ch}:'(iw-{cw})*{mov}':0,scale={ow}:{oh}:flags=lanczos"
                else:
                    # cuadro entero nítido al centro, y el mismo video desenfocado de fondo
                    cw, ch = iw, ih
                    bw, bh = ow // 8, oh // 8
                    cadena = (f"split=2[a][b];[a]scale={bw}:{bh}:force_original_aspect_ratio=increase,"
                              f"crop={bw}:{bh},boxblur=6:2,scale={ow}:{oh}:flags=bicubic,eq=brightness=-0.07[fondo];"
                              f"[b]scale={ow}:-2:flags=lanczos[frente];[fondo][frente]overlay=(W-w)/2:(H-h)/2")
            escala = round(ow / cw, 2)
            cadena = ",".join(f for f in (cadena, color, "format=yuv420p") if f)
            borrador = escala > 1.0
            nombre = f"{i}-{slug(t['titulo'])}-{fmt}{'-BORRADOR' if borrador else ''}.mp4"
            detalle = f", estirado {escala}×" if borrador else (", con relleno" if modo == "relleno" else "")
            print(f"{nombre}  ({cw}×{ch} → {ow}×{oh}{detalle})", flush=True)
            ffmpeg("-ss", f"{t['ini']:.2f}", "-to", f"{t['fin']:.2f}", "-i", str(src), "-filter_complex", cadena,
                   "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
                   "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                   "-an", "-map_metadata", "-1", "-movflags", "+faststart", str(destino / nombre))
            listado.append({"toma": i, "titulo": t["titulo"], "formato": fmt, "archivo": nombre, "modo": modo,
                            "ancho": ow, "alto": oh, "recorte": [cw, ch], "escala": escala,
                            "segundos": round(dur), "fuente": f"{iw}x{ih}"})

    guardar_json(destino / "cortes.json", listado)
    malos = [c for c in listado if c["escala"] > 1.0]
    rellenos = [c for c in listado if c.get("modo") == "relleno"]
    print(f"\n{len(listado)} cortes en {destino}")
    if rellenos:
        print(f"{len(rellenos)} verticales van con relleno: el video no tiene resolución para recortar una franja "
              "sin estirarla (hace falta 4K). Para forzar el recorte: --vertical recorte.")
    if malos:
        print(f"⚠ {len(malos)} son BORRADOR: se estiraron más allá de la resolución del original.")


if __name__ == "__main__":
    main()
