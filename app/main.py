import os
import asyncio
import json
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel

from fastapi import FastAPI, Request, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


from app.config import (
    BASE_DIR,
    get_env_var,
    save_spotify_credentials,
)
from app.spotify_client import spotify_manager
from app.tidal_client import tidal_manager
from app.ytmusic_client import ytmusic_manager
from app.transfer_engine import transfer_engine

app = FastAPI(title="Spotify to Tidal & YouTube Pro Transfer")

# Static files path
STATIC_DIR = BASE_DIR / "app" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "css").mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "js").mkdir(parents=True, exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Models
class SpotifyConfigRequest(BaseModel):
    client_id: str
    client_secret: str
    redirect_uri: Optional[str] = "http://127.0.0.1:8000/api/spotify/callback"

class TransferStartRequest(BaseModel):
    playlist_ids: List[str]
    destination: Optional[str] = "tidal"  # "tidal", "ytmusic", "both"
    train_algorithm: Optional[bool] = False
    custom_prefix: Optional[str] = ""
    public_on_tidal: Optional[bool] = False

class ImportUrlRequest(BaseModel):
    url: str

class YTMusicConnectRequest(BaseModel):
    headers_raw: str

# Endpoints
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h1>Spotify to Tidal Transfer</h1><p>Cargando interfaz...</p>")

@app.get("/api/status")
async def get_services_status():
    spotify_auth = spotify_manager.is_authenticated()
    tidal_auth = tidal_manager.is_authenticated()
    ytmusic_auth = ytmusic_manager.is_authenticated()

    spotify_profile = None
    tidal_profile = None
    ytmusic_profile = None

    if spotify_auth:
        try:
            spotify_profile = spotify_manager.get_user_profile()
        except Exception:
            spotify_auth = False

    if tidal_auth:
        try:
            tidal_profile = tidal_manager.get_user_profile()
        except Exception:
            tidal_auth = False

    if ytmusic_auth:
        try:
            ytmusic_profile = ytmusic_manager.get_user_info()
        except Exception:
            ytmusic_auth = False

    return {
        "spotify": {
            "configured": spotify_manager.is_configured(),
            "authenticated": spotify_auth,
            "profile": spotify_profile,
        },
        "tidal": {
            "authenticated": tidal_auth,
            "profile": tidal_profile,
        },
        "ytmusic": {
            "authenticated": ytmusic_auth,
            "profile": ytmusic_profile,
        },
        "transfer": {
            "is_running": transfer_engine.is_running,
            "status": transfer_engine.current_state.get("status", "idle")
        }
    }

# Spotify Endpoints
@app.post("/api/spotify/config")
async def set_spotify_config(req: SpotifyConfigRequest):
    if not req.client_id or not req.client_secret:
        raise HTTPException(status_code=400, detail="Client ID y Client Secret son requeridos.")
    save_spotify_credentials(req.client_id, req.client_secret, req.redirect_uri)
    return {"success": True, "message": "Credenciales guardadas correctamente."}

@app.get("/api/spotify/auth-url")
async def get_spotify_auth_url():
    if not spotify_manager.is_configured():
        raise HTTPException(status_code=400, detail="Spotify no está configurado con Client ID y Secret.")
    try:
        url = spotify_manager.get_authorize_url()
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/spotify/callback")
async def spotify_callback(code: Optional[str] = None, error: Optional[str] = None):
    if error:
        return RedirectResponse(url=f"/?spotify_error={error}")
    if not code:
        return RedirectResponse(url="/?spotify_error=no_code_provided")

    try:
        spotify_manager.handle_auth_code(code)
        return RedirectResponse(url="/?spotify_connected=1")
    except Exception as e:
        return RedirectResponse(url=f"/?spotify_error={str(e)}")

@app.post("/api/spotify/logout")
async def spotify_logout():
    spotify_manager.logout()
    return {"success": True}

@app.get("/link.tidal.com/{path:path}")
async def redirect_tidal_link(path: str):
    return RedirectResponse(url=f"https://link.tidal.com/{path}", status_code=302)

@app.get("/api/spotify/playlists")
async def get_spotify_playlists():
    # If authenticated via OAuth, get from account
    if spotify_manager.is_authenticated():
        try:
            playlists = spotify_manager.get_user_playlists()
            # Also combine with any directly loaded playlists
            for pid, pl in spotify_manager.loaded_playlists.items():
                if not any(p["id"] == pid for p in playlists):
                    playlists.insert(0, pl)
            return {"playlists": playlists, "total": len(playlists)}
        except Exception as e:
            pass

    # If not authenticated, return any loaded playlists from memory
    loaded = list(spotify_manager.loaded_playlists.values())
    return {"playlists": loaded, "total": len(loaded)}

class LoadUrlsRequest(BaseModel):
    urls: str

@app.post("/api/spotify/load-urls")
async def load_spotify_urls(req: LoadUrlsRequest):
    raw_urls = req.urls.strip()
    if not raw_urls:
        raise HTTPException(status_code=400, detail="Por favor ingresa al menos un enlace.")

    import re
    # 1. Look for all Spotify URLs inside the input
    found_urls = re.findall(r"https?://open\.spotify\.com/[^\s,]+", raw_urls)
    if not found_urls:
        lines = [line.strip() for line in raw_urls.splitlines() if line.strip()]
        if len(lines) == 1 and "," in lines[0]:
            lines = [u.strip() for u in lines[0].split(",") if u.strip()]
        items_to_process = lines
    else:
        items_to_process = found_urls

    loaded = []
    errors = []

    for item in items_to_process:
        if "user/" in item and "playlist/" not in item:
            try:
                pls = spotify_manager.fetch_user_playlists_without_login(item)
                loaded.extend(pls)
            except Exception as e:
                errors.append(str(e))
        else:
            try:
                pl = spotify_manager.fetch_playlist_without_login(item)
                loaded.append(pl)
            except Exception as e:
                errors.append(str(e))


    return {
        "success": len(loaded) > 0,
        "playlists": loaded,
        "errors": errors,
        "message": f"Se cargaron {len(loaded)} playlist(s) correctamente." if loaded else (errors[0] if errors else "No se pudo cargar.")
    }

@app.post("/api/spotify/upload-file")
async def upload_playlist_file(file: UploadFile = File(...)):
    try:
        content_bytes = await file.read()
        content = content_bytes.decode("utf-8", errors="replace")
        playlist = spotify_manager.parse_playlist_file(file.filename or "playlist.csv", content)
        return {
            "success": True,
            "playlist": playlist,
            "message": f"Playlist '{playlist['name']}' cargada exitosamente con {playlist['tracks_total']} canciones."
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error leyendo archivo de playlist: {str(e)}")

@app.post("/api/spotify/import-url")
async def import_playlist_by_url(req: ImportUrlRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL no proporcionada.")
    try:
        result = spotify_manager.fetch_playlist_without_login(req.url)
        return {"success": True, "playlist": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo cargar la playlist: {str(e)}")



# Tidal Endpoints
@app.get("/api/tidal/login-link")
async def get_tidal_login_link():
    try:
        login_data = tidal_manager.start_oauth_login()
        return {"success": True, **login_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error iniciando conexión con TIDAL: {str(e)}")

@app.get("/api/tidal/check-login")
async def check_tidal_login():
    try:
        res = tidal_manager.check_oauth_status()
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/tidal/logout")
async def tidal_logout():
    tidal_manager.logout()
    return {"success": True}

# YouTube Music Endpoints
@app.get("/api/ytmusic/status")
async def get_ytmusic_status():
    is_auth = ytmusic_manager.is_authenticated()
    user_info = ytmusic_manager.get_user_info() if is_auth else None
    return {
        "authenticated": is_auth,
        "profile": user_info
    }

@app.post("/api/ytmusic/connect")
async def connect_ytmusic(req: YTMusicConnectRequest):
    try:
        success = ytmusic_manager.setup_from_headers(req.headers_raw)
        if success:
            user_info = ytmusic_manager.get_user_info()
            return {"success": True, "profile": user_info, "message": "Conectado a YouTube Music exitosamente."}
        else:
            raise HTTPException(status_code=400, detail="No se pudo verificar la sesión de YouTube Music.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/ytmusic/disconnect")
async def disconnect_ytmusic():
    ytmusic_manager.logout()
    return {"success": True, "message": "Desconectado de YouTube Music."}

# Transfer Endpoints
@app.post("/api/transfer/start")
async def start_transfer(req: TransferStartRequest):
    if not req.playlist_ids:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos una playlist para transferir.")
    try:
        loop = asyncio.get_event_loop()
        transfer_engine.start_transfer_task(
            loop=loop,
            playlist_ids=req.playlist_ids,
            destination=req.destination or "tidal",
            train_algorithm=req.train_algorithm or False,
            custom_prefix=req.custom_prefix or "",
            public_on_tidal=req.public_on_tidal or False,
        )
        return {"success": True, "message": "Transferencia iniciada."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/transfer/stop")
async def stop_transfer():
    transfer_engine.stop_transfer()
    return {"success": True, "message": "Señal de detención enviada."}

@app.get("/api/transfer/state")
async def get_transfer_state():
    return transfer_engine.current_state

@app.get("/api/transfer/events")
async def stream_transfer_events(request: Request):
    """Server-Sent Events stream for live progress updates."""
    queue = transfer_engine.register_subscriber()

    async def event_generator():
        try:
            # First send current snapshot
            init_data = json.dumps({"event": "initial_state", "data": transfer_engine.current_state})
            yield f"data: {init_data}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next event with a periodic heartbeat
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send keep-alive ping
                    yield f": keepalive\n\n"
        finally:
            transfer_engine.remove_subscriber(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/api/transfer/missing-report")
async def get_missing_report():
    return {
        "missing_count": len(transfer_engine.current_state.get("missing_tracks", [])),
        "tracks": transfer_engine.current_state.get("missing_tracks", [])
    }
