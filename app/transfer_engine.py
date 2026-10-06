import asyncio
import threading
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.spotify_client import spotify_manager
from app.tidal_client import tidal_manager
from app.ytmusic_client import ytmusic_manager

logger = logging.getLogger(__name__)

class TransferEngine:
    def __init__(self):
        self.is_running = False
        self.should_cancel = False
        self.subscribers: List[asyncio.Queue] = []
        self.current_state: Dict[str, Any] = {
            "status": "idle",  # idle, running, completed, error, cancelled
            "destination": "tidal",
            "train_algorithm": False,
            "playlists_total": 0,
            "playlists_completed": 0,
            "current_playlist": None,
            "tracks_total": 0,
            "tracks_processed": 0,
            "tracks_matched": 0,
            "tracks_missed": 0,
            "tidal_added_count": 0,
            "yt_added_count": 0,
            "yt_liked_count": 0,
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
        
        recent = self.current_state.get("recent_events", [])
        if event_type in ["track_matched", "track_missed", "yt_matched", "yt_missed", "yt_liked", "playlist_start", "playlist_done", "error"]:
            recent.append(event)
            if len(recent) > 60:
                recent.pop(0)
            self.current_state["recent_events"] = recent

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
        destination: str = "tidal",
        train_algorithm: bool = False,
        custom_prefix: str = "",
        public_on_tidal: bool = False,
    ):
        if self.is_running:
            raise RuntimeError("Ya hay una transferencia en ejecución.")

        dest = destination.lower()
        if dest in ["tidal", "both"] and not tidal_manager.is_authenticated():
            raise PermissionError("TIDAL no está conectado. Conéctate primero a TIDAL.")

        if dest in ["ytmusic", "both"] and not ytmusic_manager.is_authenticated():
            raise PermissionError("YouTube Music no está conectado. Conéctate primero a YouTube Music.")

        self.is_running = True
        self.should_cancel = False
        self._loop = loop
        self.current_state = {
            "status": "running",
            "destination": dest,
            "train_algorithm": bool(train_algorithm),
            "playlists_total": len(playlist_ids),
            "playlists_completed": 0,
            "current_playlist": None,
            "tracks_total": 0,
            "tracks_processed": 0,
            "tracks_matched": 0,
            "tracks_missed": 0,
            "tidal_added_count": 0,
            "yt_added_count": 0,
            "yt_liked_count": 0,
            "recent_events": [],
            "missing_tracks": [],
            "error_message": None,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
        }

        self._thread = threading.Thread(
            target=self._run_transfer,
            args=(playlist_ids, dest, train_algorithm, custom_prefix, public_on_tidal),
            daemon=True
        )
        self._thread.start()

    def _run_transfer(self, playlist_ids: List[str], destination: str, train_algorithm: bool, custom_prefix: str, public_on_tidal: bool):
        try:
            dest_label = "TIDAL y YouTube Music" if destination == "both" else ("YouTube Music" if destination == "ytmusic" else "TIDAL")
            self._broadcast("status_update", {"status": "running", "message": f"Iniciando transferencia hacia {dest_label}..."})

            for p_idx, playlist_id in enumerate(playlist_ids):
                if self.should_cancel:
                    self.current_state["status"] = "cancelled"
                    self._broadcast("status_update", {"status": "cancelled", "message": "Transferencia cancelada por el usuario."})
                    return

                # 1. Fetch Playlist Info & Tracks
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
                
                if not tracks:
                    try:
                        pl_info = spotify_manager.fetch_playlist_without_login(playlist_id)
                        pl_name = pl_info.get("name", pl_name)
                        tracks = pl_info.get("tracks", [])
                    except Exception as e:
                        logger.error(f"Error cargando playlist {playlist_id} sin login: {e}")
                        self._broadcast("error", {"message": f"No se pudo obtener el contenido de la playlist: {e}"})
                        continue

                target_title = f"{custom_prefix} {pl_name}".strip() if custom_prefix else pl_name

                self.current_state["current_playlist"] = {
                    "index": p_idx + 1,
                    "total": len(playlist_ids),
                    "name": pl_name,
                    "target_title": target_title,
                }

                self._broadcast("playlist_start", {
                    "playlist_name": pl_name,
                    "target_title": target_title,
                    "index": p_idx + 1,
                    "total": len(playlist_ids),
                    "tracks_count": len(tracks)
                })

                self.current_state["tracks_total"] += len(tracks)

                # 2. Transfer to TIDAL if selected
                if destination in ["tidal", "both"]:
                    tidal_pl = None
                    try:
                        tidal_pl = tidal_manager.create_playlist(
                            title=target_title,
                            description=f"{pl_desc} (Migrada con Spotify to TIDAL Pro)"
                        )
                    except Exception as e:
                        logger.error(f"Error creando playlist en Tidal '{target_title}': {e}")
                        self._broadcast("error", {"message": f"No se pudo crear la playlist '{target_title}' en Tidal: {e}"})

                    matched_tidal_ids = []
                    for t_idx, track in enumerate(tracks):
                        if self.should_cancel:
                            self.current_state["status"] = "cancelled"
                            self._broadcast("status_update", {"status": "cancelled", "message": "Transferencia cancelada."})
                            return

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
                            matched_tidal_ids.append(match_result["tidal_id"])
                            if destination == "tidal":
                                self.current_state["tracks_processed"] += 1
                                self.current_state["tracks_matched"] += 1
                                self._broadcast("track_matched", {
                                    "platform": "TIDAL",
                                    "spotify_track": t_name,
                                    "spotify_artist": t_artist_str,
                                    "matched_track": match_result["name"],
                                    "matched_artist": match_result["artist"],
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
                            if destination == "tidal":
                                self.current_state["tracks_processed"] += 1
                                self.current_state["tracks_missed"] += 1
                                self.current_state["missing_tracks"].append({
                                    "playlist": pl_name,
                                    "name": t_name,
                                    "artist": t_artist_str,
                                    "album": t_album,
                                    "platform": "TIDAL"
                                })
                                self._broadcast("track_missed", {
                                    "platform": "TIDAL",
                                    "spotify_track": t_name,
                                    "spotify_artist": t_artist_str,
                                    "progress": {
                                        "processed": self.current_state["tracks_processed"],
                                        "total": self.current_state["tracks_total"],
                                        "matched": self.current_state["tracks_matched"],
                                        "missed": self.current_state["tracks_missed"],
                                    }
                                })

                    if matched_tidal_ids and tidal_pl:
                        self._broadcast("status_update", {
                            "status": "running",
                            "message": f"Añadiendo {len(matched_tidal_ids)} temas a TIDAL en '{target_title}'..."
                        })
                        try:
                            added_td = tidal_manager.add_tracks_to_playlist(tidal_pl, matched_tidal_ids)
                            self.current_state["tidal_added_count"] = self.current_state.get("tidal_added_count", 0) + added_td
                            self._broadcast("status_update", {
                                "status": "running",
                                "message": f"¡{added_td} temas añadidos a TIDAL en '{target_title}'!"
                            })
                        except Exception as td_err:
                            logger.error(f"Error agregando pistas a TIDAL: {td_err}")
                            self._broadcast("error", {"message": f"Error agregando pistas a TIDAL: {td_err}"})

                # 3. Transfer to YouTube Music if selected
                if destination in ["ytmusic", "both"]:
                    yt_pl_id = None
                    try:
                        yt_pl_id = ytmusic_manager.get_or_create_playlist(
                            title=target_title,
                            description=f"{pl_desc} (Migrada con Spotify to TIDAL & YouTube Pro)"
                        )
                    except Exception as e:
                        logger.error(f"Error creando o accediendo a playlist en YouTube Music '{target_title}': {e}")
                        self._broadcast("error", {"message": f"No se pudo crear o acceder a la playlist '{target_title}' en YouTube Music: {e}. Verifica que tu sesión esté activa."})

                    if not yt_pl_id:
                        self._broadcast("error", {
                            "message": f"Transferencia a YouTube Music omitida para '{pl_name}': No se pudo acceder a la playlist en YouTube Music. Reconecta tu sesión de YouTube Music."
                        })
                    else:
                        matched_yt_video_ids = []
                        for t_idx, track in enumerate(tracks):
                            if self.should_cancel:
                                self.current_state["status"] = "cancelled"
                                self._broadcast("status_update", {"status": "cancelled", "message": "Transferencia cancelada."})
                                return

                            t_name = track.get("name", "Desconocido")
                            t_artists = track.get("artists", [])
                            t_artist_str = track.get("artist_display", "")
                            t_dur = track.get("duration_ms")
                            t_album = track.get("album", "")

                            yt_match = ytmusic_manager.search_track(
                                name=t_name,
                                artists=t_artists,
                                duration_ms=t_dur
                            )

                            if yt_match:
                                matched_yt_video_ids.append(yt_match["videoId"])
                                
                                # Algorithmic Booster: Rate song as LIKE
                                did_like = False
                                if train_algorithm:
                                    did_like = ytmusic_manager.rate_track_like(yt_match["videoId"])
                                    if did_like:
                                        self.current_state["yt_liked_count"] += 1

                                if destination == "ytmusic":
                                    self.current_state["tracks_processed"] += 1
                                    self.current_state["tracks_matched"] += 1

                                self._broadcast("yt_matched", {
                                    "platform": "YouTube Music",
                                    "spotify_track": t_name,
                                    "spotify_artist": t_artist_str,
                                    "matched_track": yt_match["title"],
                                    "matched_artist": yt_match["artist"],
                                    "video_id": yt_match["videoId"],
                                    "thumbnail": yt_match["thumbnail"],
                                    "duration": yt_match["duration"],
                                    "confidence": round(yt_match["score"]),
                                    "liked_for_algorithm": did_like,
                                    "progress": {
                                        "processed": self.current_state["tracks_processed"],
                                        "total": self.current_state["tracks_total"],
                                        "matched": self.current_state["tracks_matched"],
                                        "missed": self.current_state["tracks_missed"],
                                        "yt_liked_count": self.current_state["yt_liked_count"]
                                    }
                                })
                            else:
                                if destination == "ytmusic":
                                    self.current_state["tracks_processed"] += 1
                                    self.current_state["tracks_missed"] += 1

                                self.current_state["missing_tracks"].append({
                                    "playlist": pl_name,
                                    "name": t_name,
                                    "artist": t_artist_str,
                                    "album": t_album,
                                    "platform": "YouTube Music"
                                })
                                self._broadcast("yt_missed", {
                                    "platform": "YouTube Music",
                                    "spotify_track": t_name,
                                    "spotify_artist": t_artist_str,
                                    "progress": {
                                        "processed": self.current_state["tracks_processed"],
                                        "total": self.current_state["tracks_total"],
                                        "matched": self.current_state["tracks_matched"],
                                        "missed": self.current_state["tracks_missed"],
                                    }
                                })

                        if matched_yt_video_ids and yt_pl_id:
                            self._broadcast("status_update", {
                                "status": "running",
                                "message": f"Añadiendo {len(matched_yt_video_ids)} temas a YouTube Music en '{target_title}'..."
                            })
                            try:
                                def on_yt_progress(added, total):
                                    self._broadcast("status_update", {
                                        "status": "running",
                                        "message": f"Añadiendo a YouTube Music: {added}/{total} temas..."
                                    })

                                add_res = ytmusic_manager.add_tracks(
                                    yt_pl_id,
                                    matched_yt_video_ids,
                                    on_progress=on_yt_progress
                                )
                                added_cnt = add_res.get("added_count", 0)
                                self.current_state["yt_added_count"] = self.current_state.get("yt_added_count", 0) + added_cnt
                                if added_cnt == 0:
                                    self._broadcast("error", {
                                        "message": f"No se pudieron añadir temas a YouTube Music en '{target_title}'. Tu sesión expiró o fue rechazada. Reconecta tu cuenta."
                                    })
                                else:
                                    self._broadcast("status_update", {
                                        "status": "running",
                                        "message": f"¡{added_cnt} temas añadidos exitosamente a YouTube Music en '{target_title}'!"
                                    })
                            except Exception as yt_add_err:
                                logger.error(f"Error añadiendo canciones a YouTube Music: {yt_add_err}")
                                self._broadcast("error", {
                                    "message": f"Fallo al agregar canciones a YouTube Music: {yt_add_err}. La playlist quedó creada pero sin temas. Por favor reconecta YouTube Music."
                                })

                self.current_state["playlists_completed"] += 1
                self._broadcast("playlist_done", {
                    "playlist_name": pl_name,
                    "target_title": target_title,
                    "tracks_total": len(tracks)
                })

            self.current_state["status"] = "completed"
            self.current_state["finished_at"] = datetime.now().isoformat()
            self._broadcast("completed", {
                "message": f"¡Todas las playlists fueron procesadas para {dest_label}!",
                "summary": {
                    "playlists_transferred": self.current_state["playlists_completed"],
                    "tracks_matched": self.current_state["tracks_matched"],
                    "tracks_missed": self.current_state["tracks_missed"],
                    "tidal_added_count": self.current_state.get("tidal_added_count", 0),
                    "yt_added_count": self.current_state.get("yt_added_count", 0),
                    "missing_count": len(self.current_state["missing_tracks"]),
                    "yt_liked_count": self.current_state["yt_liked_count"],
                    "algorithm_trained": train_algorithm
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
