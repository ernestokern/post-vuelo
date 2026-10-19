# Cómo elegir tomas mirando las hojas de contacto

Cada hoja es una grilla de cuadros de un video con la hora (minuto:segundo) en la esquina.
`paso_hoja` en `metricas.json` dice cada cuántos segundos hay un cuadro.

## Qué vale

| Tipo | Cómo se reconoce | Sirve para |
|---|---|---|
| Revelación | arranca cerca de algo (gente, árboles, un borde) y se aleja o lo pasa hasta mostrar un paisaje amplio | reel; es la que más funciona |
| Alejamiento (dronie) | arranca en una persona o grupo y se aleja subiendo | reel, arranque de historia |
| Cenital | cámara mirando hacia abajo, sube o gira sobre algo | historia: se recorta a vertical sin perder nada |
| Acercamiento | lo inverso: de lo amplio a un detalle | reel, cierre |
| Órbita | gira alrededor de un punto | reel |
| Paisaje | movimiento lento, horizonte estable | relleno, plano de ubicación |
| Seguimiento | acompaña algo que se mueve | reel |

## Puntaje

- **5**: movimiento limpio, algo lindo al final (paisaje, agua, cerros) y algo humano al principio.
- **4**: buena, pero repite otra o el final es menos lindo.
- **3**: correcta, sirve de relleno o transición.
- **2 o menos**: no la incluyas en `tomas`; si es mala, va a `descartes`.

Entre dos tomas parecidas, la mejor se lleva el puntaje alto y la otra baja un punto.

## Qué se tira

- **Dron en el piso**: cuadros iguales con piedras o pasto muy cerca. Coincide con `quietos`.
- **Despegue y aterrizaje**: imagen que se acerca al piso o al piloto con el control en la mano.
- **Quieto en el aire**: flotando sin intención más de 10 s.
- **Giros bruscos, imagen oscura, polvo.**
- **Tramos sueltos de menos de 3 s.**

## Cortes

- Empezá un segundo después de que arranca el movimiento y terminá antes de que el dron frene,
  gire o baje.
- Para vertical: mirá dónde queda lo importante (personas, el punto de interés del paisaje) y
  ponelo en `encuadre.x`. En las cenitales suele ser 0.5.
- Una toma puede salir de un tramo de un video largo; un video puede dar dos tomas.
