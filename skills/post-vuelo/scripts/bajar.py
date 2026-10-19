"""Paso 1 · Bajar la tarjeta: copia los archivos del dron, los agrupa por salida y los verifica.

Uso:
  python bajar.py                       # busca la tarjeta y SOLO muestra qué haría
  python bajar.py --copiar              # copia de verdad
  python bajar.py --origen <carpeta>    # leer una carpeta en vez de la tarjeta
  python bajar.py --lugar "Chacra"      # nombre para las salidas sin lugar conocido

Qué hace:
- Toma solo archivos del dron (DJI_*): fotos JPG/DNG, videos MP4/MOV y sus SRT.
- Agrupa en salidas: misma fecha y sin cortes de más de `corte_horas`.
- Nombra cada salida con fecha y lugar (lugares de la configuración, por GPS de las fotos).
- Copia a  <destino>/<AAAA-MM-DD lugar>/crudo/  y crea instagram/ vacía.
- Verifica cada copia releyéndola y comparando la huella (hash SHA-1).
- Recuerda lo importado en <destino>/_importados.json: correrlo dos veces no duplica nada.
- La tarjeta NO se toca: borrarla o formatearla queda a cargo de quien vuela.
"""
import argparse
import hashlib
import math
import os
import platform
import re
import shutil
import string
import sys
from datetime import datetime
from pathlib import Path

from comun import (EXT_DRON, FOTOS, VIDEOS, cargar_config, exif_foto, guardar_json, leer_json,
                   leer_srt, probe, xmp_dji)

BLOQUE = 8 * 1024 * 1024


# ---------- dónde buscar ----------

def buscar_tarjetas() -> list[Path]:
    """Unidades extraíbles con carpeta DCIM (tarjeta SD, lector USB, el dron por cable)."""
    sistema = platform.system()
    candidatas: list[Path] = []
    if sistema == "Windows":
        import ctypes
        for letra in string.ascii_uppercase:
            raiz = f"{letra}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(raiz) == 2:
                candidatas.append(Path(raiz))
    elif sistema == "Darwin":
        candidatas = [p for p in Path("/Volumes").glob("*") if p.is_dir()]
    else:
        usuario = os.environ.get("USER", "")
        for base in (Path("/media") / usuario, Path("/run/media") / usuario, Path("/media")):
            if base.is_dir():
                candidatas += [p for p in base.glob("*") if p.is_dir()]
    return [c for c in candidatas if (c / "DCIM").is_dir()]


def archivos_dron(origen: Path) -> tuple[list[Path], int]:
    elegidos, ignorados = [], 0
    for p in origen.rglob("*"):
        if not p.is_file():
            continue
        if p.name.upper().startswith("DJI_") and p.suffix.upper() in EXT_DRON:
            elegidos.append(p)
        else:
            ignorados += 1
    return sorted(elegidos), ignorados


# ---------- datos de cada archivo ----------

def huella_rapida(p: Path) -> str:
    """Tamaño + primer y último MB: alcanza para reconocer duplicados sin leer 4 GB."""
    tam = p.stat().st_size
    h = hashlib.sha1(str(tam).encode())
    with open(p, "rb") as f:
        h.update(f.read(1 << 20))
        if tam > 2 << 20:
            f.seek(-(1 << 20), os.SEEK_END)
            h.update(f.read(1 << 20))
    return h.hexdigest()


def describir(archivos: list[Path]) -> list[dict]:
    """Agrupa por 'tallo' (DJI_0501.MP4 + DJI_0501.SRT) y le pone hora y GPS a cada grupo."""
    por_tallo: dict[tuple[Path, str], list[Path]] = {}
    for p in archivos:
        por_tallo.setdefault((p.parent, p.stem.upper()), []).append(p)
    grupos = []
    for (_, tallo), ps in por_tallo.items():
        exts = {p.suffix.upper(): p for p in ps}
        hora, gps, tipo = None, None, "otro"
        foto = next((exts[e] for e in (".JPG", ".JPEG", ".DNG") if e in exts), None)
        video = exts.get(".MP4") or exts.get(".MOV")
        if foto:
            tipo = "foto"
            hora = exif_foto(foto)["hora"]
            x = xmp_dji(foto) if foto.suffix.upper() != ".DNG" else {}
            if "Latitude" in x:
                gps = (x["Latitude"], x["Longitude"])
        if video:
            tipo = "video"
            srt = leer_srt(video.with_suffix(".SRT")) or leer_srt(exts.get(".SRT", Path("-")))
            hora = srt.get("inicio") or probe(video)["creacion"]
            gps = gps or srt.get("gps")
        elif ".SRT" in exts and not hora:
            hora = leer_srt(exts[".SRT"]).get("inicio")
        if not hora:  # último recurso: fecha del archivo
            hora = datetime.fromtimestamp(min(p.stat().st_mtime for p in ps))
        grupos.append({"tallo": tallo, "tipo": tipo, "hora": hora, "gps": gps, "archivos": ps})
    return sorted(grupos, key=lambda g: g["hora"])


# ---------- salidas y lugares ----------

def km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def nombre_lugar(centro, lugares, por_defecto):
    if centro:
        cerca = [(km(centro, (l["lat"], l["lon"])), l) for l in lugares]
        cerca = [(d, l) for d, l in cerca if d <= l.get("radio_km", 2)]
        if cerca:
            return min(cerca, key=lambda x: x[0])[1]["nombre"]
    return por_defecto


def limpiar(nombre: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "-", nombre).strip() or "sin-lugar"


def armar_salidas(grupos, corte_horas, lugares, lugar_cli):
    salidas, actual = [], []
    for g in grupos:
        if actual:
            prev = actual[-1]["hora"]
            if g["hora"].date() != prev.date() or (g["hora"] - prev).total_seconds() > corte_horas * 3600:
                salidas.append(actual)
                actual = []
        actual.append(g)
    if actual:
        salidas.append(actual)

    resultado = []
    for gs in salidas:
        puntos = [g["gps"] for g in gs if g["gps"]]
        centro = None
        if puntos:
            lats, lons = sorted(p[0] for p in puntos), sorted(p[1] for p in puntos)
            centro = (lats[len(lats) // 2], lons[len(lons) // 2])  # mediana: ignora una foto lejana
        lugar = nombre_lugar(centro, lugares, lugar_cli or "sin-lugar")
        resultado.append({
            "carpeta": limpiar(f"{gs[0]['hora']:%Y-%m-%d} {lugar}"),
            "lugar": lugar, "centro": centro,
            "inicio": gs[0]["hora"], "fin": gs[-1]["hora"], "grupos": gs,
        })
    return resultado


# ---------- copiar ----------

def copiar_verificado(src: Path, dst: Path) -> str:
    tmp = dst.with_name(dst.name + ".parcial")
    h = hashlib.sha1()
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        while chunk := fi.read(BLOQUE):
            h.update(chunk)
            fo.write(chunk)
    h2 = hashlib.sha1()
    with open(tmp, "rb") as f:
        while chunk := f.read(BLOQUE):
            h2.update(chunk)
    if h.hexdigest() != h2.hexdigest():
        tmp.unlink(missing_ok=True)
        raise IOError(f"La copia de {src.name} no coincide con el original")
    os.replace(tmp, dst)
    shutil.copystat(src, dst)
    return h.hexdigest()


def gb(n):
    return f"{n / 1e9:.1f} GB"


def main():
    ap = argparse.ArgumentParser(description="Bajar archivos del dron y ordenarlos por salida.")
    ap.add_argument("--origen", help="carpeta a leer (por defecto, la tarjeta del dron)")
    ap.add_argument("--destino", help="carpeta raíz de las salidas (por defecto, la de la configuración)")
    ap.add_argument("--lugar", help="nombre para salidas cuyo lugar no está en la configuración")
    ap.add_argument("--config", help="archivo de configuración (por defecto post-vuelo.json o ~/.post-vuelo.json)")
    ap.add_argument("--copiar", action="store_true", help="copiar de verdad (sin esto, solo simula)")
    args = ap.parse_args()

    cfg = cargar_config(args.config)
    if not (args.destino or cfg.get("destino")):
        sys.exit("Falta el destino. Creá post-vuelo.json (ver config.ejemplo.json) o usá --destino <carpeta>.")
    destino = Path(args.destino or cfg["destino"])

    if args.origen:
        origen = Path(args.origen).resolve()
    else:
        tarjetas = buscar_tarjetas()
        if not tarjetas:
            sys.exit("No encontré ninguna tarjeta con carpeta DCIM. Conectala o usá --origen <carpeta>.")
        if len(tarjetas) > 1:
            sys.exit(f"Hay varias tarjetas conectadas ({', '.join(map(str, tarjetas))}). Elegí una con --origen.")
        origen = tarjetas[0]
    print(f"Origen:  {origen}\nDestino: {destino}\n")

    archivos, ignorados = archivos_dron(origen)
    if not archivos:
        sys.exit("No hay archivos del dron (DJI_*) en el origen.")

    registro_path = destino / "_importados.json"
    registro = leer_json(registro_path, {})

    # Duplicados: lo que ya se importó antes y lo repetido dentro del mismo origen
    vistos, nuevos, ya, repetidos = set(), [], 0, 0
    for p in archivos:
        clave = huella_rapida(p)
        if clave in registro:
            ya += 1
        elif clave in vistos:
            repetidos += 1
        else:
            vistos.add(clave)
            nuevos.append((p, clave))
    claves = dict(nuevos)

    print(f"Archivos del dron: {len(archivos)}  ·  ya importados antes: {ya}  ·  "
          f"repetidos en el origen: {repetidos}  ·  nuevos: {len(nuevos)}")
    if ignorados:
        print(f"Ignorados (no son DJI_*): {ignorados}")
    if not nuevos:
        print("\nNo hay nada nuevo para bajar.")
        return

    salidas = armar_salidas(describir([p for p, _ in nuevos]), cfg.get("corte_horas", 3), cfg["lugares"], args.lugar)
    total = sum(p.stat().st_size for p, _ in nuevos)

    # Resolución de los videos: avisa si son copias livianas (no alcanzan para cortes verticales nítidos)
    resoluciones = {}
    for s in salidas:
        for g in s["grupos"]:
            v = next((p for p in g["archivos"] if p.suffix.upper() in VIDEOS), None)
            if v:
                pr = probe(v)
                clave = f"{pr['ancho']}x{pr['alto']}"
                resoluciones[clave] = resoluciones.get(clave, 0) + 1

    print(f"\n{'Salida':32} {'Horario':13} {'Fotos':>5} {'Videos':>6} {'Peso':>9}")
    for s in salidas:
        fotos = sum(1 for g in s["grupos"] if g["tipo"] == "foto")
        videos = sum(1 for g in s["grupos"] if g["tipo"] == "video")
        peso = sum(p.stat().st_size for g in s["grupos"] for p in g["archivos"])
        estado = " (se suma a la existente)" if (destino / s["carpeta"]).exists() else ""
        print(f"{s['carpeta'][:32]:32} {s['inicio']:%H:%M}–{s['fin']:%H:%M}   {fotos:>5} {videos:>6} {gb(peso):>9}{estado}")
    print(f"\nTotal a copiar: {gb(total)}")
    if resoluciones:
        print("Resolución de los videos: " + ", ".join(f"{k} ({n})" for k, n in resoluciones.items()))
        if any(int(k.split("x")[1] or 0) < 2160 for k in resoluciones):
            print("  ⚠ Hay videos por debajo de 4K: los recortes verticales 9:16 van a salir blandos.")

    for s in salidas:
        if s["lugar"] == "sin-lugar":
            donde = f"GPS {s['centro'][0]:.5f}, {s['centro'][1]:.5f}" if s["centro"] else "sin GPS"
            print(f"  · {s['carpeta']}: lugar desconocido ({donde}). Agregalo a la configuración o usá --lugar.")

    # Espacio: Google Drive para escritorio guarda en el disco local lo que sube hasta terminar
    libre = min(shutil.disk_usage(destino if destino.exists() else destino.anchor).free,
                shutil.disk_usage(Path.home()).free)
    margen = cfg.get("margen_libre_gb", 5) * 1e9
    if total + margen > libre:
        sys.exit(f"\nNo alcanza el espacio: hacen falta {gb(total)} + {gb(margen)} de margen y hay {gb(libre)} libres.")

    if not args.copiar:
        print("\nSimulación: no se copió nada. Para copiar de verdad, repetí con --copiar.")
        return

    print()
    hechos = 0
    try:
        for s in salidas:
            carpeta = destino / s["carpeta"]
            crudo = carpeta / "crudo"
            for sub in ("crudo", "instagram"):
                (carpeta / sub).mkdir(parents=True, exist_ok=True)
            copiados = []
            for g in s["grupos"]:
                for p in g["archivos"]:
                    dst = crudo / p.name
                    n = 2
                    while dst.exists():  # mismo nombre pero otro archivo (ej. de otra tarjeta)
                        dst = crudo / f"{p.stem}_{n}{p.suffix}"
                        n += 1
                    print(f"  {s['carpeta']}/crudo/{dst.name}  ({gb(p.stat().st_size)})", flush=True)
                    copiar_verificado(p, dst)
                    registro[claves[p]] = f"{s['carpeta']}/crudo/{dst.name}"
                    copiados.append(dst.name)
                    hechos += 1
                    if hechos % 10 == 0:
                        guardar_json(registro_path, registro, indent=1)

            ficha_path = carpeta / "salida.json"
            ficha = leer_json(ficha_path) or {"fecha": f"{s['inicio']:%Y-%m-%d}", "lugar": s["lugar"],
                                               "notas": "", "importaciones": []}
            ficha["importaciones"].append({
                "cuando": datetime.now().isoformat(timespec="seconds"),
                "origen": str(origen),
                "horario": f"{s['inicio']:%H:%M}–{s['fin']:%H:%M}",
                "centro_gps": s["centro"],
                "archivos": copiados,
            })
            guardar_json(ficha_path, ficha)
    finally:
        destino.mkdir(parents=True, exist_ok=True)
        guardar_json(registro_path, registro, indent=1)

    print(f"\nListo: {hechos} archivos copiados y verificados en {destino}.")
    print("La tarjeta quedó intacta. Formateala desde el dron cuando veas que la copia terminó de subir.")
    for s in salidas:
        print(f"SALIDA: {destino / s['carpeta']}")


if __name__ == "__main__":
    main()
