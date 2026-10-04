import asyncio
import threading
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.spotify_client import spotify_manager
from app.tidal_client import tidal_manager

logger = logging.getLogger(__name__)

class TransferEngine:
    def __init__(self):
        self.is_running = False
        self.should_cancel = False
        self.subscribers: List[asyncio.Queue] = []
        self.current_state: Dict[str, Any] = {
            "status": "idle",  # idle, running, completed, error, cancelled
            "playlists_total": 0,
            "playlists_completed": 0,
            "current_playlist": None,
            "tracks_total": 0,
            "tracks_processed": 0,
            "tracks_matched": 0,
            "tracks_missed": 0,
            "recent_events": [],
            "missing_tracks": [],
            "error_message": None,
            "started_at": None,
            "finished_at": None,
        }
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def register_subscriber(self) -> asyncio.Queue:
        q = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def remove_subscriber(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)

    def _broadcast(self, event_type: str, data: Dict[str, Any]):
        event = {"event": event_type, "data": data, "timestamp": datetime.now().isoformat()}
        
        # Keep recent event in memory
        recent = self.current_state.get("recent_events", [])
        if event_type in ["track_matched", "track_missed", "playlist_start", "playlist_done", "error"]:
            recent.append(event)
            if len(recent) > 60:
                recent.pop(0)
            self.current_state["recent_events"] = recent

        # Put into queues for all connected SSE clients
        if self._loop and not self._loop.is_closed():
            for q in list(self.subscribers):
                try:
                    self._loop.call_soon_threadsafe(q.put_nowait, event)
                except Exception:
                    pass

    def stop_transfer(self):
        if self.is_running:
            self.should_cancel = True
            self.current_state["status"] = "cancelling"
            self._broadcast("status_update", {"status": "cancelling", "message": "Cancelando transferencia..."})

    def start_transfer_task(
        self,
        loop: asyncio.AbstractEventLoop,
        playlist_ids: List[str],
        custom_prefix: str = "",
        public_on_tidal: bool = False,
    ):
        if self.is_running:
            raise RuntimeError("Ya hay una transferencia en ejecución.")

        if not tidal_manager.is_authenticated():
            raise PermissionError("TIDAL no está conectado. Conéctate primero a TIDAL.")

        self.is_running = True
        self.should_cancel = False
        self._loop = loop
        self.current_state = {
            "status": "running",
            "playlists_total": len(playlist_ids),
            "playlists_completed": 0,
            "current_playlist": None,
            "tracks_total": 0,
            "tracks_processed": 0,
            "tracks_matched": 0,
            "tracks_missed": 0,
            "recent_events": [],
            "missing_tracks": [],
            "error_message": None,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
        }

        self._thread = threading.Thread(
            target=self._run_transfer,
            args=(playlist_ids, custom_prefix, public_on_tidal),
            daemon=True
        )
        self._thread.start()

    def _run_transfer(self, playlist_ids: List[str], custom_prefix: str, public_on_tidal: bool):
        try:
            self._broadcast("status_update", {"status": "running", "message": "Iniciando transferencia..."})

            for p_idx, playlist_id in enumerate(playlist_ids):
                if self.should_cancel:
                    self.current_state["status"] = "cancelled"
                    self._broadcast("status_update", {"status": "cancelled", "message": "Transferencia cancelada por el usuario."})
                    return

                # 1. Fetch Playlist Info & Tracks (From memory, Spotify API or Embed)
                pl_name = f"Playlist {p_idx+1}"
                pl_desc = "Importada desde Spotify"
                tracks = []

                if playlist_id in spotify_manager.loaded_playlists:
                    cached_pl = spotify_manager.loaded_playlists[playlist_id]
                    pl_name = cached_pl.get("name", pl_name)
                    pl_desc = cached_pl.get("description", pl_desc)
                    tracks = cached_pl.get("tracks", [])
                elif spotify_manager.is_authenticated():
                    try:
                        sp = spotify_manager.get_client()
                        spotify_pl = sp.playlist(playlist_id=playlist_id, fields="name,description")
                        pl_name = spotify_pl.get("name", pl_name)
                        pl_desc = spotify_pl.get("description", "") or pl_desc
                        tracks = spotify_manager.get_playlist_tracks(playlist_id)
                    except Exception as e:
                        logger.error(f"Error con Spotify API para playlist {playlist_id}: {e}")
                
                # If still no tracks, try fetching without login
                if not tracks:
                    try:
                        pl_info = spotify_manager.fetch_playlist_without_login(playlist_id)
                        pl_name = pl_info.get("name", pl_name)
                        tracks = pl_info.get("tracks", [])
                    except Exception as e:
                        logger.error(f"Error cargando playlist {playlist_id} sin login: {e}")
                        self._broadcast("error", {"message": f"No se pudo obtener el contenido de la playlist: {e}"})
                        continue

                tidal_title = f"{custom_prefix} {pl_name}".strip() if custom_prefix else pl_name

                self.current_state["current_playlist"] = {
                    "index": p_idx + 1,
                    "total": len(playlist_ids),
                    "name": pl_name,
                    "tidal_title": tidal_title,
                }

                self._broadcast("playlist_start", {
                    "playlist_name": pl_name,
                    "tidal_title": tidal_title,
                    "index": p_idx + 1,
                    "total": len(playlist_ids)
                })

                self.current_state["tracks_total"] += len(tracks)


                # 2. Create Playlist on Tidal
                tidal_pl = None
                try:
                    tidal_pl = tidal_manager.create_playlist(
                        title=tidal_title,
                        description=f"{pl_desc} (Migrada con Spotify to Tidal Pro)"
                    )
                except Exception as e:
                    logger.error(f"Error creando playlist en Tidal '{tidal_title}': {e}")
                    self._broadcast("error", {"message": f"No se pudo crear la playlist '{tidal_title}' en Tidal: {e}"})
                    continue

                # 3. Match and Collect Tidal Track IDs
                matched_track_ids = []
                for t_idx, track in enumerate(tracks):
                    if self.should_cancel:
                        self.current_state["status"] = "cancelled"
                        self._broadcast("status_update", {"status": "cancelled", "message": "Transferencia cancelada por el usuario."})
                        return

                    self.current_state["tracks_processed"] += 1
                    t_name = track.get("name", "Desconocido")
                    t_artists = track.get("artists", [])
                    t_artist_str = track.get("artist_display", "")
                    t_isrc = track.get("isrc")
                    t_dur = track.get("duration_ms")
                    t_album = track.get("album", "")

                    match_result = tidal_manager.match_track(
                        name=t_name,
                        artists=t_artists,
                        isrc=t_isrc,
                        duration_ms=t_dur
                    )

                    if match_result:
                        matched_track_ids.append(match_result["tidal_id"])
                        self.current_state["tracks_matched"] += 1
                        self._broadcast("track_matched", {
                            "spotify_track": t_name,
                            "spotify_artist": t_artist_str,
                            "tidal_track": match_result["name"],
                            "tidal_artist": match_result["artist"],
                            "match_type": match_result["match_type"],
                            "confidence": match_result["confidence"],
                            "audio_quality": match_result["audio_quality"],
                            "progress": {
                                "processed": self.current_state["tracks_processed"],
                                "total": self.current_state["tracks_total"],
                                "matched": self.current_state["tracks_matched"],
                                "missed": self.current_state["tracks_missed"],
                            }
                        })
                    else:
                        self.current_state["tracks_missed"] += 1
                        missing_item = {
                            "playlist": pl_name,
                            "name": t_name,
                            "artist": t_artist_str,
                            "album": t_album,
                        }
                        self.current_state["missing_tracks"].append(missing_item)
                        self._broadcast("track_missed", {
                            "spotify_track": t_name,
                            "spotify_artist": t_artist_str,
                            "progress": {
                                "processed": self.current_state["tracks_processed"],
                                "total": self.current_state["tracks_total"],
                                "matched": self.current_state["tracks_matched"],
                                "missed": self.current_state["tracks_missed"],
                            }
                        })

                # 4. Add matched tracks to Tidal playlist in chunks
                if matched_track_ids and tidal_pl:
                    tidal_manager.add_tracks_to_playlist(tidal_pl, matched_track_ids)

                self.current_state["playlists_completed"] += 1
                self._broadcast("playlist_done", {
                    "playlist_name": pl_name,
                    "tidal_title": tidal_title,
                    "tracks_matched": len(matched_track_ids),
                    "tracks_total": len(tracks)
                })

            self.current_state["status"] = "completed"
            self.current_state["finished_at"] = datetime.now().isoformat()
            self._broadcast("completed", {
                "message": "¡Todas las playlists seleccionadas fueron transferidas exitosamente!",
                "summary": {
                    "playlists_transferred": self.current_state["playlists_completed"],
                    "tracks_matched": self.current_state["tracks_matched"],
                    "tracks_missed": self.current_state["tracks_missed"],
                    "missing_count": len(self.current_state["missing_tracks"]),
                }
            })

        except Exception as e:
            logger.exception("Error durante la transferencia")
            self.current_state["status"] = "error"
            self.current_state["error_message"] = str(e)
            self._broadcast("error", {"message": f"Error fatal durante la transferencia: {str(e)}"})
        finally:
            self.is_running = False

transfer_engine = TransferEngine()
