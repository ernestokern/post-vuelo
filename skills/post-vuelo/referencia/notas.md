# Formato de `analisis/notas.json`

Lo escribe Claude después de mirar las hojas de contacto. Los tiempos son segundos desde el
inicio del video y valen igual para la copia liviana y el original.

```json
{
  "revisado": "2026-10-18",
  "metodo": "Hojas de contacto + medidas de movimiento y nitidez.",
  "tomas": [
    {
      "id": "t01",
      "video": "DJI_0468",
      "ini": 0,
      "fin": 38,
      "puntaje": 5,
      "titulo": "Del muelle a los cerros",
      "tipo": "revelación",
      "formato": ["reel", "historia"],
      "por_que": "Arranca con el grupo en el muelle y se aleja hasta mostrar el lago y los cerros.",
      "encuadre": {"x": 0.45}
    }
  ],
  "descartes": [
    {"video": "DJI_0501", "ini": 44, "fin": 867, "motivo": "Cámara en el piso después de aterrizar."}
  ]
}
```

| Campo | Qué va |
|---|---|
| `id` | `t01`, `t02`... en orden de puntaje, de mayor a menor |
| `video` | nombre del archivo sin extensión |
| `ini`, `fin` | segundos; la toma debería durar entre 8 y 60 s |
| `puntaje` | 1 a 5 (ver `criterios.md`) |
| `titulo` | corto y descriptivo, sin nombres de personas |
| `tipo` | `revelación`, `alejamiento`, `acercamiento`, `cenital`, `órbita`, `paisaje`, `seguimiento` |
| `formato` | uno o más de `historia`, `reel`, `carrusel` |
| `por_que` | una o dos oraciones: qué se ve y para qué sirve |
| `encuadre` | opcional. `{"x": 0.5}` fijo o `{"x": [0.2, 0.7]}` paneo; 0 = izquierda, 1 = derecha |
| `descartes` | tramos para tirar, con el motivo en lenguaje llano |
