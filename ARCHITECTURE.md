# 🏗️ Arquitectura y Decisiones Técnicas

Este documento detalla la arquitectura de software, las decisiones de diseño y las soluciones de ingeniería implementadas en **Spotify to TIDAL & YouTube Pro**.

---

## 📐 Diagrama de Arquitectura del Sistema

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      Frontend SPA (Vanilla JS / CSS)                   │
│   • Estado Reactivo en Memoria        • Streaming SSE (EventSource)    │
│   • Diálogos Nativos (<dialog>)       • UI Glassmorphism Dark Mode     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP REST + SSE Stream (/events)
┌───────────────────────────────────▼────────────────────────────────────┐
│                       FastAPI Backend (Python 3.10+)                   │
│   ┌───────────────────────────────┴────────────────────────────────┐   │
│   │  Bucle Asíncrono Principal (asyncio Event Loop / ASGI)         │   │
│   │  • Endpoints REST / Pydantic DTOs                              │   │
│   │  • Broker de Eventos SSE (asyncio.Queue por suscriptor)        │   │
│   └───────────────────────────────┬────────────────────────────────┘   │
│                                   │ loop.call_soon_threadsafe()        │
│   ┌───────────────────────────────▼────────────────────────────────┐   │
│   │  Worker de Transferencia en Hilo Dedicado (threading.Thread)   │   │
│   │  • Ejecución secuencial y aislada de I/O bloqueante            │   │
│   │  • Manejo de cancelaciones y estado de progreso atómico        │   │
│   └───────┬───────────────────────┬────────────────────────┬───────┘   │
└───────────┼───────────────────────┼────────────────────────┼───────────┘
            │                       │                        │
┌───────────▼───────────┐ ┌─────────▼───────────┐ ┌──────────▼───────────┐
│     Spotify Extractor │ │     TIDAL Client    │ │   YT Music Client    │
│ • Embed Scraper JSON  │ │ • OAuth Device Flow │ │ • Browser Headers    │
│ • Spotipy OAuth       │ │ • ISRC Priority     │ │ • Batch / Fallback   │
│ • Parser CSV / TXT    │ │ • RapidFuzz Matcher │ │ • Reutilización Auto │
└───────────────────────┘ └─────────────────────┘ └──────────────────────┘
```

---

## 1. Backend (Python + FastAPI)

### ¿Por qué FastAPI y no Flask o Django?
* **Async nativo & Rendimiento ASGI:** Necesitamos servir endpoints de control al mismo tiempo que mantenemos conexiones de **Server-Sent Events (SSE)** abiertas y fluidas sin bloquear el hilo principal.
* **Tipado estático con Pydantic:** Validación automática y documentación de schemas para todas las solicitudes (`TransferStartRequest`, `SpotifyConfigRequest`, etc.).
* **Cero sobrecarga de ORM / Base de Datos:** La aplicación no requiere base de datos relacional; las sesiones se persisten en JSON locales (`tidal_session.json`, `ytmusic_session.json`) excluidos en `.gitignore`.

### Patrón de Concurrencia Híbrido: `asyncio` + `threading`
Librerías de integración como `tidalapi` y `ytmusicapi` dependen internamente de llamadas síncronas bloqueantes (`requests`). Si se ejecuta una transferencia de 600 canciones en el hilo asíncrono principal de FastAPI, el servidor entero se congela.

**Implementación en `app/transfer_engine.py`:**
1. Al invocar la tarea, capturamos el bucle asíncrono: `loop = asyncio.get_event_loop()`.
2. Lanzamos la tarea pesada en un hilo secundario: `threading.Thread(target=self._run_transfer, daemon=True)`.
3. Para la comunicación en tiempo real con el cliente web, utilizamos colas `asyncio.Queue` suscritas por cada conexión SSE activa.
4. El hilo secundario emite eventos hacia el bucle asíncrono de forma segura usando:
   ```python
   self._loop.call_soon_threadsafe(queue.put_nowait, event)
   ```

---

## 2. Frontend (JavaScript Moderno + CSS)

### ¿Por qué Vanilla JS y no React / Vue / Next.js?
* **Cero Dependencias de Node.js:** El usuario solo necesita Python. No requiere `npm`, `npx`, bundlers (Vite/Webpack) ni carpetas `node_modules` pesadas. La aplicación se distribuye limpia y arranca instantáneamente con `iniciar.bat` o `iniciar.sh`.
* **Estado Reactivo Centralizado:** En `app/static/js/app.js` se implementa un store simple (`state = { ... }`). Cada actualización del estado dispara renders específicos (`renderPlaylists()`, `updateBottomDock()`).
* **HTML5 Moderno:** Uso nativo de `<dialog>` con las APIs `.showModal()` y `.close()`, eliminando librerías externas de modales.

### Streaming en Tiempo Real: Server-Sent Events (SSE) vs WebSockets
* Se utilizó la API estándar de JavaScript `EventSource('/api/transfer/events')`.
* **¿Por qué SSE?** La transferencia es un flujo **unidireccional** (el backend reporta progreso al frontend). SSE funciona sobre HTTP/1.1 estándar, cuenta con reconexión automática nativa en el navegador y es mucho más ligero y robusto que mantener un servidor WebSocket bidireccional.

---

## 3. Estrategia de Extracción de Datos (Spotify)

Implementada en `app/spotify_client.py`:

1. **Modo Zero-Config (Sin API Keys de Spotify):**
   * Exigir que un usuario cree una cuenta en *Spotify Developer Dashboard* es una gran barrera de entrada.
   * **Extracción vía Embed:** Al inspeccionar `https://open.spotify.com/embed/playlist/{id}`, Spotify devuelve la página prerenderizada con Next.js que contiene el tag `<script id="__NEXT_DATA__">`.
   * Parseamos este JSON directamente para obtener nombres de pistas, artistas, duraciones y carátulas en milisegundos.

2. **Parser Polimórfico de Archivos CSV / TXT:**
   * La función `parse_playlist_file` auto-detecta delimitadores (`,` o `;`) para soportar exportaciones de Excel en español o inglés.
   * Normaliza cabeceras ignorando mayúsculas y acentos, mapeando sinónimos comunes de exportadores populares (*Exportify*, *Soundiiz*, *TuneMyMusic*).

---

## 4. Algoritmo de Matching Difuso (Fuzzy Matching)

Emparejar canciones entre plataformas con catálogos dispares requiere tolerancia a fallos:

1. **Normalización Regex (`clean_song_title`):**
   * Se eliminan sufijos ruidosos que arruinan las búsquedas exactas:
     * `(Remastered 2011)`, `[2021 Remaster]`, `- Live at Wembley`, `(Deluxe Edition)`, `[Radio Edit]`.
2. **Prioridad ISRC (TIDAL):**
   * Si la canción tiene código ISRC (*International Standard Recording Code*), se consulta primero ese identificador universal (100% de coincidencia exacta con la grabación de estudio).
3. **Puntuación Ponderada con RapidFuzz:**
   * `combined_score = (title_score * 0.65) + (artist_score * 0.35)`.
   * Se utiliza `token_set_ratio` para tolerar cambios en el orden de las palabras (ej. *"The Beatles"* vs *"Beatles, The"* o feats).
4. **Penalización Temporal por Duración:**
   * Si una canción candidata difiere en más de 15 segundos respecto a la original, se penaliza la puntuación para evitar emparejar versiones extendidas, remixes o canciones en vivo por error.

---

## 5. Resiliencia en Destinos (TIDAL & YouTube Music)

### TIDAL (`app/tidal_client.py`)
* **Flujo OAuth Device Code:** Se conecta mediante `link.tidal.com/{user_code}`. No requiere configurar servidores de redirección con IP pública ni puertos dinámicos.
* **Inserción en Lotes:** Maneja la paginación interna de la API de TIDAL (`chunk_size = 50`) con reintento unitario automático si un track está restringido por territorio.

### YouTube Music (`app/ytmusic_client.py`)
* **Autenticación Basada en Sesión Web (`ytmusicapi`):** Permite conectarse copiando las cabeceras de red desde DevTools (`music.youtube.com`), evitando las estrictas cuotas diarias de Google Cloud YouTube Data API v3.
* **Reutilización Inteligente de Playlists (`get_or_create_playlist`):** Antes de crear una lista, el motor inspecciona la biblioteca del usuario. Si ya existe una lista vacía con ese título (por ejemplo, si una transferencia anterior fue interrumpida), la reutiliza directamente en lugar de duplicarla.
* **Inserción en Bloques (50 items) con Fallback Unitario:** Se envían lotes de hasta 50 canciones por petición (`browse/edit_playlist`). Si un lote es rechazado (por ejemplo, por una pista restringida geográficamente), el sistema hace fallback e inserta las canciones una a una para asegurar que no se pierdan las demás.
* **Entrenador del Algoritmo (Algorithmic Booster):** Si está activo, por cada canción emparejada ejecuta `rate_song(videoId, rating="LIKE")`, forzando al motor de recomendaciones de YouTube Music a aprender los gustos del usuario de inmediato.
