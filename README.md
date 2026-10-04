# 🎵 Spotify to TIDAL Pro

Una aplicación web moderna, rápida y de código abierto para transferir todas tus listas de reproducción desde **Spotify** hacia **TIDAL**, conservando la máxima fidelidad de audio, metadatos y **sin límite en la cantidad de canciones**.

Diseñada para ser amigable y directa: **no requiere cuenta de desarrollador** para su uso diario y todo se ejecuta de forma **100% local en tu propia computadora**.

---

## ✨ Características Principales

- 🚀 **Sin Límites de Canciones**:
  - Transfiere listas con más de 600, 1.000 o 5.000 canciones sin bloqueos de API.
  - Soporte directo para archivos exportados de **Exportify**, **TuneMyMusic** o **Soundiiz** (formato CSV/TXT), preservando códigos ISRC y metadatos completos.
- 🔑 **Conexión en 1 Clic a TIDAL**:
  - Inicio de sesión oficial mediante el flujo seguro de dispositivos de TIDAL (`link.tidal.com`).
  - No necesitas crear aplicaciones ni lidiar con tokens manuales.
  - Tu sesión se guarda localmente cifrada/protegida en tu equipo.
- 🌐 **Múltiples Formas de Cargar tus Playlists**:
  - **Vía Archivo (CSV / TXT)**: Ideal para listas privadas o gigantescas como *"Mis pistas de Shazam"*.
  - **Vía Enlace / Perfil**: Pega URLs de perfiles o playlists públicas directamente.
  - **Vía Spotify OAuth (Opcional)**: Sincronización automática de toda tu biblioteca para usuarios avanzados.
- 🎯 **Emparejamiento de Canciones de Alta Precisión**:
  - **Código ISRC Universal**: Busca la versión idéntica de la grabación original para evitar versiones en vivo o covers no deseados.
  - **Fuzzy Matching Inteligente (RapidFuzz)**: Limpieza automática de sufijos molestos como `(Remastered 2021)`, `[Deluxe Edition]`, `(Radio Edit)`, etc.
  - **Preferencia de Calidad HiFi / MAX**: Selecciona automáticamente la versión con mejor bitrate disponible en TIDAL.
- 🎨 **Interfaz Moderna & Monitoreo en Tiempo Real**:
  - Estética *Glassmorphism Dark Mode* inspirada en las interfaces oficiales de Spotify y TIDAL.
  - Barra de progreso interactiva y streaming de eventos en vivo (**Server-Sent Events**).
  - Reporte de canciones faltantes para revisar qué temas no están disponibles en el catálogo de TIDAL.
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
git clone https://github.com/TU_USUARIO/import_spotify_to_tidal.git
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

### Paso 1: Conectar tu cuenta de TIDAL
1. En la tarjeta de **TIDAL**, haz clic en el botón **"Conectar TIDAL"**.
2. La app generará un enlace y código de verificación. Presiona **"Abrir TIDAL y Autorizar"**.
3. Se abrirá la página oficial de TIDAL en tu navegador; inicia sesión y presiona **Continuar / Confirmar**.
4. La aplicación detectará el inicio de sesión exitoso y quedará conectada de forma permanente.

### Paso 2: Importar tus Playlists de Spotify

Tienes 3 alternativas según tus necesidades:

#### 📁 Método A: Subir Archivo CSV (Recomendado para listas de 600+ canciones o privadas como Shazam)
1. Abre [Exportify](https://exportify.net) en tu navegador e inicia sesión con tu cuenta de Spotify.
2. Busca la lista que deseas transferir (por ejemplo, *Mis pistas de Shazam*) y presiona **Export**. Se descargará un archivo `.csv`.
3. En la aplicación, haz clic en el botón **"📁 Subir archivo (CSV)"** y selecciona el archivo descargado.
4. ¡La lista con todas sus cientos o miles de canciones e ISRC se cargará al instante sin ningún límite!

#### 🔗 Método B: Enlace Público de Spotify
1. En Spotify, haz clic derecho en tu playlist o perfil público > **Compartir** > **Copiar enlace**.
2. En la aplicación, pega el enlace en el campo de texto y haz clic en **"Cargar"**.
3. Si es tu perfil, cargará todas tus listas públicas automáticamente.

#### ⚙️ Método C: Spotify Developer (Opcional - Sincronización total)
1. Si prefieres sincronizar automáticamente toda tu biblioteca privada directamente desde la API:
2. Ve a [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) y crea una aplicación gratuita.
3. Agrega como Redirect URI: `http://127.0.0.1:8000/api/spotify/callback`.
4. En la app, haz clic en **⚙ Modo Desarrollador (Opcional)**, ingresa tu Client ID y Client Secret, y presiona **Conectar**.

### Paso 3: Iniciar la Transferencia
1. Selecciona las listas que deseas migrar marcando sus casillas de verificación.
2. Haz clic en el botón **"Iniciar Transferencia a TIDAL"**.
3. Observa en tiempo real cómo se empareja y transfiere cada canción.
4. Al finalizar, podrás ver un resumen completo con las canciones añadidas y un reporte de temas faltantes si alguna pista no se encuentra en el catálogo de TIDAL.

---

## 🛠️ Tecnologías Utilizadas

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/), Python 3.10+
- **Integraciones de Audio**: [tidalapi](https://github.com/tamland/python-tidal), [spotipy](https://spotipy.readthedocs.io/)
- **Emparejamiento Inteligente**: [RapidFuzz](https://github.com/maxbachmann/RapidFuzz)
- **Frontend**: HTML5 Semántico, CSS3 Moderno (Glassmorphism, Dark Theme), Vanilla JavaScript (Reactivo con SSE)

---

## 🔒 Privacidad y Seguridad

- **Cero telemetría**: No recopilamos ninguna estadística, correo ni dato de uso.
- **Archivos locales ignorados**: Los archivos que contienen tokens de sesión (`tidal_session.json`, `.spotify_cache`, `.env` y archivos `.csv` subidos) se encuentran estrictamente registrados en `.gitignore` para evitar que se suban a repositorios públicos por error.
- **Sin intermediarios**: La comunicación se realiza de forma directa y exclusiva entre tu ordenador y las APIs oficiales de Spotify y TIDAL.

---

## 📄 Licencia

Este proyecto está bajo la Licencia **MIT**. Consulta el archivo `LICENSE` para más detalles.
