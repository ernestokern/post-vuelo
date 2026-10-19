# Post-vuelo

Una skill de [Claude Code](https://claude.com/claude-code) para lo que pasa después de volar un
dron DJI: bajar la tarjeta, revisar horas de video, quedarse con las tomas que valen y tenerlas
listas para Instagram.

*A Claude Code skill for DJI drone footage: offload the card, analyze every clip, let anyone pick
the best shots on a shareable page, and export sharp 9:16, 4:5 and 16:9 cuts for Instagram.
Spanish-first; Claude answers in your language.*

## Qué hace

1. **Bajar**: copia la tarjeta a la carpeta que elijas (por ejemplo Google Drive), separada por
   salida y con nombre de lugar, verificando cada archivo. Nunca borra la tarjeta.
2. **Analizar**: mide cada segundo de cada video (movimiento, nitidez, brillo), detecta los
   tramos con el dron en el piso y arma hojas de contacto. Claude las mira y elige las tomas:
   revelaciones, cenitales, paisajes, con puntaje y para qué formato sirve cada una.
3. **Elegir**: genera una página con una vista previa de cada toma. Quien la abre marca "La quiero"
   o "Descartar". Publicada como artifact de Claude, las marcas se guardan solas; en cualquier
   otro hosting, cada uno toca "Copiar mi elección" y la manda por WhatsApp.
4. **Recortar**: hace 9:16 (1080×1920), 4:5 (1080×1350) y 16:9 a la resolución original, con
   color corregido para D-Cinelike, encuadre o paneo por toma, y sin metadatos.
5. **Entregar**: los cortes quedan en la carpeta de la salida y la página muestra cuáles están
   nítidos y cuáles son borrador porque el original no tenía resolución.

Con `--sin-ubicacion`, la página sale sin mapa, sin coordenadas y sin el nombre del lugar,
para compartirla con gente de afuera.

## Requisitos

- Claude Code
- Python 3.10 o más nuevo, con `pip install pillow numpy`
- [ffmpeg](https://ffmpeg.org/download.html) (`ffmpeg` y `ffprobe` en el PATH)

## Instalación

Como plugin:

```
/plugin marketplace add ernestokern/post-vuelo
/plugin install post-vuelo@post-vuelo
```

O copiando la carpeta `skills/post-vuelo` a `~/.claude/skills/post-vuelo`.

## Uso

Conectá la tarjeta y decile a Claude **"volví de volar"**. La primera vez te pregunta dónde
guardar las salidas y crea `~/.post-vuelo.json` (ver `skills/post-vuelo/config.ejemplo.json`).
También sirve entrar por la mitad: "analizá los videos de la salida del sábado", "armá la página
para elegir", "leé lo que eligieron", "recortá las que elegí".

Para cortes verticales nítidos hay que grabar en 4K. `skills/post-vuelo/referencia/ajustes.md`
explica cómo configurar el dron y por qué.

## Licencia

MIT
