# 🎵 Spotify to TIDAL & YouTube Pro

Una aplicación web moderna, rápida y de código abierto para transferir todas tus listas de reproducción desde **Spotify** hacia **TIDAL** y **YouTube Music / YouTube**, conservando la máxima fidelidad de audio, metadatos, **sin límite en la cantidad de canciones** y con un **Entrenador del Algoritmo Musical de YouTube**.

Diseñada para ser amigable y directa: **no requiere cuenta de desarrollador** para su uso diario y todo se ejecuta de forma **100% local en tu propia computadora**.

---

## ✨ Características Principales

- 🚀 **Sin Límites de Canciones**:
  - Transfiere listas con más de 600, 1.000 o 5.000 canciones sin bloqueos de API.
  - Soporte directo para archivos exportados de **Exportify**, **TuneMyMusic** o **Soundiiz** (formato CSV/TXT), preservando códigos ISRC y metadatos completos.
- 🔥 **Entrenador del Algoritmo de YouTube (Algorithmic Booster)**:
  - Al transferir a YouTube Music, puedes activar el interruptor de entrenamiento algorítmico.
  - La aplicación otorga automáticamente **"Me Gusta" (Like)** a cada canción en YouTube Music.
  - **Efecto Inmediato**: Las redes neuronales de recomendación de YouTube (*Candidate Generation* y *Ranking*) absorben tus verdaderos gustos musicales, recalibrando tu **"Supermix"**, el **Mix de Descubrimiento**, la radio de canciones y el feed principal de videos musicales en YouTube.
- 🔑 **Conexión en 1 Clic a TIDAL y Conexión Segura a YouTube Music**:
  - **TIDAL**: Inicio de sesión oficial mediante el flujo seguro de dispositivos de TIDAL (`link.tidal.com`).
  - **YouTube Music**: Conexión directa mediante cabeceras de sesión de tu navegador, sin límites de cuotas de desarrollador de Google Cloud.
  - Tus sesiones se guardan localmente protegidas en tu equipo.
- 🌐 **Múltiples Formas de Cargar tus Playlists**:
  - **Vía Archivo (CSV / TXT)**: Ideal para listas privadas o gigantescas como *"Mis pistas de Shazam"*.
  - **Vía Enlace / Perfil**: Pega URLs de perfiles o playlists públicas directamente.
  - **Vía Spotify OAuth (Opcional)**: Sincronización automática de toda tu biblioteca para usuarios avanzados.
- 🎯 **Emparejamiento de Canciones de Alta Precisión**:
  - **Código ISRC Universal**: En TIDAL busca la versión idéntica de la grabación original para evitar covers no deseados.
  - **Fuzzy Matching Inteligente (RapidFuzz)**: Limpieza automática de sufijos molestos como `(Remastered 2021)`, `[Deluxe Edition]`, `(Radio Edit)`, etc.
  - **Preferencia de Calidad HiFi / MAX**: Selecciona automáticamente la versión con mejor bitrate disponible en TIDAL y audio oficial de estudio en YouTube Music.
- 🎨 **Interfaz Moderna & Monitoreo en Tiempo Real**:
  - Estética *Glassmorphism Dark Mode* inspirada en las interfaces oficiales de Spotify, TIDAL y YouTube Music.
  - Barra de progreso interactiva y streaming de eventos en vivo (**Server-Sent Events**).
  - Reporte de canciones faltantes para revisar qué temas no están disponibles en el catálogo de destino.
- 🔒 **Privacidad Total & Seguridad Local**:
  - No hay servidores externos intermedios.
  - Todas las operaciones y tokens se ejecutan en tu `localhost:8000` y están excluidas de control de versiones mediante `.gitignore`.

---

## 📋 Requisitos Previos

- **Python 3.10** o superior instalado en tu sistema ([Descargar Python](https://www.python.org/downloads/)).
- *(Opcional)* Git instalado si vas a clonar el repositorio.

---

## 🚀 Instalación y Puesta en Marcha

### 1. Clonar o Descargar el Repositorio
```bash
git clone https://github.com/lespinozarey/import_spotify_to_tidal.git
cd import_spotify_to_tidal
```

### 2. Iniciar la Aplicación

#### En Windows (Automático en 1 Clic):
Simplemente haz doble clic en el archivo:
```
iniciar.bat
```
*Este archivo creará automáticamente el entorno virtual `.venv`, instalará las dependencias necesarias, iniciará el servidor y abrirá tu navegador predeterminado en `http://127.0.0.1:8000`.*

#### En Linux / macOS / Terminal:
```bash
# 1. Crear entorno virtual
python3 -m venv .venv

# 2. Activar entorno virtual
# En Windows (PowerShell): .\.venv\Scripts\Activate.ps1
# En Linux/macOS: source .venv/bin/activate

# 3. Instalar librerías
pip install -r requirements.txt

# 4. Iniciar servidor
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Luego abre tu navegador en: [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 📖 Guía de Uso Paso a Paso

### Paso 1: Conectar tus cuentas de Destino

#### A. Conectar TIDAL
1. En la tarjeta de **TIDAL**, haz clic en el botón **"Conectar TIDAL en 1 Clic"**.
2. Presiona **"Abrir TIDAL y Autorizar"** y confirma en la web oficial de TIDAL.

#### B. Conectar YouTube Music
1. En la tarjeta de **YouTube Music**, haz clic en **"Conectar YouTube Music"**.
2. Abre [music.youtube.com](https://music.youtube.com) en tu navegador e inicia sesión con tu cuenta de Google.
3. Presiona `F12` (Herramientas de Desarrollador), ve a la pestaña **Network (Red)** y filtra por `browse`.
4. Haz clic derecho sobre la petición `browse` > **Copiar > Copiar cabeceras de solicitud (Copy request headers)**.
5. Pégalas en la ventana de la aplicación y haz clic en **Conectar YouTube Music**.

### Paso 2: Importar tus Playlists de Spotify

Tienes 3 alternativas:

#### 📁 Método A: Subir Archivo CSV (Recomendado para listas de 600+ canciones o privadas como Shazam)
1. Abre [Exportify](https://exportify.net) en tu navegador e inicia sesión con tu cuenta de Spotify.
2. Busca la lista que deseas transferir (por ejemplo, *Mis pistas de Shazam*) y presiona **Export**. Se descargará un archivo `.csv`.
3. En la aplicación, haz clic en el botón **"📁 Subir archivo (CSV)"** y selecciona el archivo descargado.
4. ¡La lista con todas sus cientos de canciones se cargará al instante sin ningún límite!

#### 🔗 Método B: Enlace Público de Spotify
1. En Spotify, haz clic derecho en tu playlist o perfil público > **Compartir** > **Copiar enlace**.
2. En la aplicación, pega el enlace en el campo de texto y haz clic en **"Cargar"**.

#### ⚙️ Método C: Spotify Developer (Opcional - Sincronización total)
1. Ve a [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) y crea una aplicación gratuita.
2. Agrega como Redirect URI: `http://127.0.0.1:8000/api/spotify/callback`.
3. En la app, haz clic en **⚙ Modo Desarrollador (Opcional)** e ingresa tus credenciales.

### Paso 3: Iniciar la Transferencia y Entrenar el Algoritmo
1. Selecciona las listas que deseas migrar marcando sus casillas de verificación.
2. En la barra inferior, elige tu destino: **TIDAL**, **YouTube Music** o **Ambos**.
3. Si seleccionas YouTube, puedes activar el interruptor: **"🔥 Entrenar Algoritmo de YouTube (Dar 'Me Gusta' automático)"**.
4. Haz clic en **"Iniciar Transferencia"**.
5. Observa en tiempo real cómo se empareja cada canción y cómo se inyectan los "Likes" en YouTube para calibrar tus recomendaciones.

---

## 🛠️ Tecnologías Utilizadas

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), Python 3.10+
- **Integraciones de Audio**: [tidalapi](https://github.com/tamland/python-tidal), [ytmusicapi](https://github.com/sigma67/ytmusicapi), [spotipy](https://spotipy.readthedocs.io/)
- **Emparejamiento Inteligente**: [RapidFuzz](https://github.com/maxbachmann/RapidFuzz)
- **Frontend**: HTML5 Semántico, CSS3 Moderno (Glassmorphism, Dark Theme), Vanilla JavaScript (Reactivo con SSE)

---

## 🔒 Privacidad y Seguridad

- **Cero telemetría**: No recopilamos ninguna estadística, correo ni dato de uso.
- **Archivos locales ignorados**: Los archivos que contienen tokens de sesión (`tidal_session.json`, `ytmusic_session.json`, `browser_auth.json`, `.spotify_cache`, `.env` y archivos `.csv` subidos) se encuentran estrictamente registrados en `.gitignore` para evitar que se suban a repositorios públicos por error.
- **Sin intermediarios**: La comunicación se realiza de forma directa y exclusiva entre tu ordenador y las plataformas oficiales.

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT**. Consulta el archivo `LICENSE` para más detalles.
