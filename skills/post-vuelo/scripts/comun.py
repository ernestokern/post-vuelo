"""Piezas compartidas por los scripts de post-vuelo: configuración, metadatos DJI y ffmpeg."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# La consola de Windows no siempre usa UTF-8; evita que los acentos rompan la salida.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

FOTOS = {".JPG", ".JPEG", ".DNG"}
VIDEOS = {".MP4", ".MOV"}
EXT_DRON = FOTOS | VIDEOS | {".SRT"}

CONFIG_POR_DEFECTO = {
    "destino": None,          # carpeta raíz de las salidas (ej. la de Google Drive)
    "corte_horas": 3,         # más de esto sin archivos = otra salida
    "margen_libre_gb": 5,
    "lugares": [],            # [{"nombre", "lat", "lon", "radio_km"}]
    "lut": None,              # archivo .cube opcional para corregir color
    "cache": None,            # dónde guardar cuadros temporales (por defecto ~/.cache/post-vuelo)
}


def buscar_config(explicita: str | None = None) -> Path | None:
    candidatos = [explicita, os.environ.get("POST_VUELO_CONFIG"),
                  Path.cwd() / "post-vuelo.json", Path.home() / ".post-vuelo.json"]
    for c in candidatos:
        if c and Path(c).is_file():
            return Path(c)
    return None


def cargar_config(explicita: str | None = None) -> dict:
    ruta = buscar_config(explicita)
    cfg = dict(CONFIG_POR_DEFECTO)
    if ruta:
        cfg.update(json.loads(ruta.read_text(encoding="utf-8")))
        cfg["_ruta"] = str(ruta)
    cfg["lugares"] = [l for l in cfg.get("lugares") or [] if not str(l.get("nombre", "")).startswith("Ejemplo")]
    return cfg


def carpeta_cache(cfg: dict) -> Path:
    base = Path(cfg.get("cache") or Path.home() / ".cache" / "post-vuelo")
    base.mkdir(parents=True, exist_ok=True)
    return base


def carpeta_crudo(salida: Path, crudo: str | None = None) -> Path:
    """Los archivos del dron: <salida>/crudo si existe, si no la carpeta misma."""
    if crudo:
        return Path(crudo)
    return salida / "crudo" if (salida / "crudo").is_dir() else salida


def leer_json(ruta: Path, defecto=None):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else defecto


def guardar_json(ruta: Path, datos, indent=2):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, indent=indent, ensure_ascii=False, default=str), encoding="utf-8")


# ---------- metadatos DJI ----------

XMP_CAMPOS = ["Latitude", "Longitude", "RelativeAltitude", "GimbalPitchDegree", "GimbalYawDegree", "FlightYawDegree"]


def xmp_dji(p: Path) -> dict:
    """DJI guarda posición, altura y orientación como texto XMP al principio del JPG."""
    cabeza = p.read_bytes()[:200_000]
    datos = {}
    for k in XMP_CAMPOS:
        m = re.search(rb'drone-dji:' + k.encode() + rb'="([-+0-9.]+)"', cabeza)
        if m:
            datos[k] = float(m.group(1))
    alt = datos.get("RelativeAltitude")
    if alt is not None and not (-50 < alt < 500):  # algunos firmwares graban alturas absurdas
        datos["RelativeAltitude"] = None
    return datos


def exif_foto(p: Path) -> dict:
    from PIL import Image
    try:
        im = Image.open(p)
        ex = im.getexif()
        txt = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        hora = datetime.strptime(txt.strip("\x00"), "%Y:%m:%d %H:%M:%S") if txt else None
        modelo = (ex.get(272) or "").strip("\x00 ")
        return {"hora": hora, "modelo": modelo, "tamano": im.size}
    except Exception:
        return {"hora": None, "modelo": "", "tamano": None}


def leer_srt(srt: Path, todo: bool = False) -> dict:
    """Hora de inicio y ajustes de cámara del SRT de un video DJI (si existe)."""
    if not srt.exists():
        return {}
    with open(srt, encoding="utf-8", errors="ignore") as f:
        texto = f.read() if todo else f.read(6000)
    m = re.search(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", texto)
    color = re.search(r"\[color_md\s*:\s*(\w+)\]", texto)
    isos = [int(x) for x in re.findall(r"\[iso\s*:\s*(\d+)\]", texto)]
    obt = re.findall(r"\[shutter\s*:\s*1/([0-9.]+)\]", texto)
    ct = [int(x) for x in re.findall(r"\[ct\s*:\s*(\d+)\]", texto)]
    lat = re.search(r"\[latitude\s*:\s*([-0-9.]+)\]", texto)
    lon = re.search(r"\[long(?:i)?tude\s*:\s*([-0-9.]+)\]", texto)
    return {
        "inicio": datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") if m else None,
        "color": color.group(1) if color else None,
        "iso": [min(isos), max(isos)] if isos else None,
        "obturador": [f"1/{min(obt, key=float)}", f"1/{max(obt, key=float)}"] if obt else None,
        "temp_color": [min(ct), max(ct)] if ct else None,
        "gps": (float(lat.group(1)), float(lon.group(1))) if lat and lon and float(lat.group(1)) != 0 else None,
    }


def probe(p: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate:format=duration:format_tags=creation_time",
         "-of", "json", str(p)], capture_output=True, text=True).stdout
    d = json.loads(out or "{}")
    s = (d.get("streams") or [{}])[0]
    num, _, den = (s.get("r_frame_rate") or "30/1").partition("/")
    creacion = (d.get("format", {}).get("tags") or {}).get("creation_time")
    return {
        "ancho": s.get("width"), "alto": s.get("height"),
        "fps": round(float(num) / float(den or 1), 3),
        "segundos": float(d.get("format", {}).get("duration") or 0),
        "creacion": datetime.fromisoformat(creacion[:19]) if creacion else None,
    }


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def chequear_herramientas():
    faltan = []
    for prog in ("ffmpeg", "ffprobe"):
        try:
            subprocess.run([prog, "-version"], capture_output=True, check=True)
        except Exception:
            faltan.append(prog)
    for mod in ("PIL", "numpy"):
        try:
            __import__(mod)
        except ImportError:
            faltan.append({"PIL": "Pillow", "numpy": "numpy"}[mod] + " (pip install -r requirements.txt)")
    if faltan:
        sys.exit("Faltan herramientas: " + ", ".join(faltan))


def mmss(seg: float) -> str:
    seg = int(round(seg))
    return f"{seg // 60}:{seg % 60:02d}"
