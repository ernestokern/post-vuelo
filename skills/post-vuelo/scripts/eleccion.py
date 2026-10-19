"""Paso 4a · Juntar las elecciones de la página en <salida>/analisis/eleccion.json.

Uso:
  python eleccion.py <salida> --votos votos.json      # lo que guardó la página (lista de documentos)
  python eleccion.py <salida> --texto mensajes.txt    # mensajes pegados con "Copiar mi elección"
  (se pueden combinar y repetir)

Cada mensaje copiado termina con una línea  PV1|<salida>|<nombre>|t01+,t02-,...
Resultado: por persona, qué quiso y qué no; y "elegidas" = tomas que alguien quiso y nadie
del dueño descartó. Claude puede editar eleccion.json a mano antes de recortar.
"""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote

from comun import guardar_json, leer_json


def de_votos(ruta: Path) -> dict:
    """Acepta una lista de documentos ({id, data}) o un dict {uid: {nombre, elecciones}}."""
    crudo = json.loads(ruta.read_text(encoding="utf-8"))
    docs = crudo if isinstance(crudo, list) else [{"id": k, "data": v} for k, v in crudo.items()]
    personas = {}
    for d in docs:
        data = d.get("data", d)
        nombre = (data.get("nombre") or d.get("id") or "sin nombre").strip()
        personas[nombre] = {k: v for k, v in (data.get("elecciones") or {}).items() if isinstance(v, dict)}
    return personas


def de_texto(ruta: Path) -> dict:
    personas = {}
    texto = ruta.read_text(encoding="utf-8")
    for m in re.finditer(r"PV1\|([^|\n]*)\|([^|\n]*)\|([^\n]*)", texto):
        nombre = unquote(m.group(2)).strip() or "sin nombre"
        elecciones = {}
        for item in filter(None, m.group(3).strip().split(",")):
            item = item.strip()
            if item[-1:] in "+-" and len(item) > 1:
                elecciones[item[:-1]] = {"voto": "si" if item.endswith("+") else "no", "nota": ""}
        # notas escritas en el mismo mensaje: "• t01: texto"
        bloque = texto[:m.start()].rsplit("Elección de", 1)[-1]
        for n in re.finditer(r"•\s*(t\d+):\s*(.+)", bloque.split("Notas:", 1)[-1] if "Notas:" in bloque else ""):
            elecciones.setdefault(n.group(1), {"voto": ""})["nota"] = n.group(2).strip()
        personas[nombre] = elecciones
    return personas


def main():
    ap = argparse.ArgumentParser(description="Juntar elecciones en eleccion.json")
    ap.add_argument("salida")
    ap.add_argument("--votos", action="append", default=[], help="JSON con los documentos de la colección votos")
    ap.add_argument("--texto", action="append", default=[], help="texto con mensajes copiados de la página")
    ap.add_argument("--duenio", help="nombre de quien voló: su 'Descartar' saca la toma aunque otros la quieran")
    args = ap.parse_args()

    salida = Path(args.salida).resolve()
    destino = salida / "analisis" / "eleccion.json"
    actual = leer_json(destino, {"personas": {}})
    personas = actual.get("personas", {})
    for r in args.votos:
        personas.update(de_votos(Path(r)))
    for r in args.texto:
        personas.update(de_texto(Path(r)))

    notas = leer_json(salida / "analisis" / "notas.json", {"tomas": []})
    orden = [t["id"] for t in notas["tomas"]]
    quieren = {i for p in personas.values() for i, e in p.items() if e.get("voto") == "si"}
    vetadas = {i for i, e in personas.get(args.duenio or "", {}).items() if e.get("voto") == "no"}
    elegidas = [i for i in orden if i in quieren and i not in vetadas]
    guardar_json(destino, {"personas": personas, "elegidas": elegidas})

    print(f"{len(personas)} personas: " + ", ".join(personas))
    for i in elegidas:
        quienes = [n for n, p in personas.items() if p.get(i, {}).get("voto") == "si"]
        print(f"  {i}: {', '.join(quienes)}")
    print(f"ELEGIDAS: {','.join(elegidas)}")


if __name__ == "__main__":
    main()
