import json
import logging
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from rapidfuzz import fuzz

import ytmusicapi
from app.config import YTMUSIC_SESSION_FILE
from app.tidal_client import clean_song_title

logger = logging.getLogger("uvicorn")

class YTMusicClient:
    def __init__(self):
        self.yt: Optional[ytmusicapi.YTMusic] = None
        self._user_info: Optional[Dict[str, Any]] = None
        self._user_info_time: float = 0.0
        self._try_load_saved_session()

    def _is_session_logged_in(self) -> bool:
        """Verifies with YouTube's backend whether the session cookies are genuinely active."""
        if not self.yt:
            return False
        try:
            res = self.yt._send_request("account/account_menu", {})
            tracking = res.get("responseContext", {}).get("serviceTrackingParams", [])
            for svc in tracking:
                for param in svc.get("params", []):
                    if param.get("key") in ("yt_li", "logged_in") and str(param.get("value")) == "1":
                        return True
            return False
        except Exception as e:
            logger.debug(f"Error comprobando sesión de YouTube Music: {e}")
            return False

    def _try_load_saved_session(self) -> bool:
        if YTMUSIC_SESSION_FILE.exists():
            try:
                self.yt = ytmusicapi.YTMusic(str(YTMUSIC_SESSION_FILE))
                self._user_info = None
                self._user_info_time = 0.0
                if self._is_session_logged_in():
                    logger.info("Sesión de YouTube Music restaurada y verificada exitosamente.")
                    return True
                else:
                    logger.warning("La sesión guardada de YouTube Music no está activa o ha expirado.")
                    self.yt = None
            except Exception as e:
                logger.warning(f"No se pudo cargar la sesión de YouTube Music: {e}")
                self.yt = None
        return False

    def is_authenticated(self) -> bool:
        if not self.yt:
            if not self._try_load_saved_session():
                return False
        info = self.get_user_info()
        return bool(info.get("authenticated"))

    def get_user_info(self, force_refresh: bool = False) -> Dict[str, Any]:
        if not self.yt:
            return {"authenticated": False, "name": "", "handle": "", "photo": None}
        
        now = time.time()
        if not force_refresh and self._user_info and (now - self._user_info_time < 90):
            return self._user_info

        is_logged = self._is_session_logged_in()
        if not is_logged:
            self._user_info = {"authenticated": False, "name": "", "handle": "", "photo": None}
            self._user_info_time = now
            return self._user_info

        user_name = "Usuario de YouTube"
        handle = ""
        photo = None
        try:
            acc = self.yt.get_account_info()
            if isinstance(acc, dict):
                user_name = acc.get("accountName") or user_name
                handle = acc.get("channelHandle") or ""
                photo = acc.get("accountPhotoUrl") or None
        except Exception as e:
            logger.debug(f"Detalle de perfil no extraíble pero sesión activa: {e}")

        self._user_info = {
            "authenticated": True,
            "name": user_name,
            "handle": handle,
            "photo": photo
        }
        self._user_info_time = now
        return self._user_info

    def setup_from_headers(self, raw_input: str) -> bool:
        """
        Parses raw browser request headers, JSON, or cookie strings,
        validates the session, and saves it to YTMUSIC_SESSION_FILE.
        """
        raw_text = raw_input.strip()
        if not raw_text:
            raise ValueError("Las cabeceras no pueden estar vacías.")

        cookie_val = ""
        user_headers = {}

        # If user pasted a JSON string directly
        if raw_text.startswith("{") and raw_text.endswith("}"):
            try:
                parsed_json = json.loads(raw_text)
                if isinstance(parsed_json, dict):
                    user_headers = {k.lower(): str(v) for k, v in parsed_json.items()}
                    cookie_val = user_headers.get("cookie", "")
            except Exception as e:
                logger.debug(f"Fallo al parsear JSON directo: {e}")

        # If user pasted a cURL command (Copy as cURL bash/cmd)
        if "curl" in raw_text.lower() or "-H " in raw_text or "--header " in raw_text:
            curl_matches = re.findall(r'(?:-H|--header)\s+[\'"]?([a-zA-Z0-9\-_]+):\s*([^\r\n\'"]+)[\'"]?', raw_text, re.IGNORECASE)
            for k, v in curl_matches:
                user_headers[k.lower()] = v.strip()
                if k.lower() == "cookie":
                    cookie_val = v.strip()

        # Parse headers: support cURL, Key: Value, and alternating Key \n Value (DevTools table)
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        idx = 0
        while idx < len(lines):
            line_str = lines[idx]
            if ": " in line_str:
                parts = line_str.split(": ", 1)
                k = parts[0].strip().lstrip(":").lower()
                v = parts[1].strip()
                user_headers[k] = v
                if k == "cookie":
                    cookie_val = v
                idx += 1
            elif (line_str.startswith(":") or (line_str.replace("-", "").isalnum() and len(line_str) < 40)) and (idx + 1 < len(lines)):
                next_val = lines[idx + 1]
                k = line_str.lstrip(":").lower()
                if not next_val.startswith(":") and next_val.lower() not in ["accept", "cookie", "authorization", "content-type", "x-goog-authuser"]:
                    user_headers[k] = next_val
                    if k == "cookie":
                        cookie_val = next_val
                    idx += 2
                else:
                    idx += 1
            else:
                idx += 1

        # Direct JSON synthesis for maximum reliability
        if cookie_val or "cookie" in user_headers:
            cookie_str = cookie_val or user_headers.get("cookie", "")
            authuser = user_headers.get("x-goog-authuser", "0")
            auth_data = {
                "user-agent": user_headers.get("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
                "accept": "*/*",
                "accept-encoding": "gzip, deflate",
                "accept-language": user_headers.get("accept-language", "es,en-US;q=0.9,en;q=0.8"),
                "content-type": "application/json",
                "x-goog-authuser": str(authuser),
                "origin": "https://music.youtube.com",
                "x-origin": "https://music.youtube.com",
                "cookie": cookie_str
            }
            if "authorization" in user_headers:
                auth_data["authorization"] = user_headers["authorization"]
            else:
                auth_data["authorization"] = "SAPISIDHASH dummy"

            try:
                with open(YTMUSIC_SESSION_FILE, "w", encoding="utf-8") as f:
                    json.dump(auth_data, f, indent=2, ensure_ascii=False)
                self.yt = ytmusicapi.YTMusic(str(YTMUSIC_SESSION_FILE))
                self._user_info = None
                self._user_info_time = 0.0
                if self._is_session_logged_in():
                    return True
                else:
                    logger.warning("Cabeceras guardadas pero la sesión no figura logueada en YouTube Music.")
            except Exception as direct_err:
                logger.debug(f"Direct JSON auth attempt: {direct_err}")

        # Fallback to ytmusicapi.setup parser
        try:
            ytmusicapi.setup(filepath=str(YTMUSIC_SESSION_FILE), headers_raw=raw_text)
            self.yt = ytmusicapi.YTMusic(str(YTMUSIC_SESSION_FILE))
            self._user_info = None
            self._user_info_time = 0.0
            if self._is_session_logged_in():
                return True
        except Exception as e:
            logger.debug(f"Fallo parser de ytmusicapi.setup: {e}")

        # If it failed verification, clean up
        self.logout()
        raise ValueError("Las cabeceras no corresponden a una sesión activa de YouTube Music. Por favor copia las cabeceras de una petición reciente (como /browse) desde music.youtube.com mientras tu cuenta esté iniciada.")

    def logout(self):
        if YTMUSIC_SESSION_FILE.exists():
            try:
                YTMUSIC_SESSION_FILE.unlink()
            except Exception:
                pass
        self.yt = None
        self._user_info = None
        self._user_info_time = 0.0

    def search_track(self, name: str, artists: List[str] = None, duration_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
        client = self.yt if self.yt else ytmusicapi.YTMusic()
        primary_artist = artists[0] if artists else ""
        query = f"{name} {primary_artist}".strip()
        cleaned_title = clean_song_title(name)

        candidates = []
        try:
            song_results = client.search(query, filter="songs")
            if song_results:
                candidates.extend(song_results[:8])
        except Exception as e:
            logger.debug(f"Error en búsqueda de canciones en YTMusic: {e}")

        if len(candidates) < 3:
            try:
                video_results = client.search(query, filter="videos")
                if video_results:
                    candidates.extend(video_results[:5])
            except Exception as e:
                logger.debug(f"Error en búsqueda de videos en YTMusic: {e}")

        # Throttle slightly to protect sockets
        time.sleep(0.02)

        if not candidates:
            return None

        best_match = None
        best_score = -1.0
        target_sec = (duration_ms / 1000.0) if duration_ms else None

        for item in candidates:
            item_title = item.get("title", "")
            item_clean_title = clean_song_title(item_title)
            
            title_score = max(
                fuzz.token_set_ratio(item_title.lower(), name.lower()),
                fuzz.token_set_ratio(item_clean_title.lower(), cleaned_title.lower())
            )

            item_artists = [a.get("name", "") for a in item.get("artists", []) if isinstance(a, dict)]
            item_artist_str = " ".join(item_artists).lower()
            
            artist_score = 0.0
            if primary_artist:
                artist_score = fuzz.token_set_ratio(item_artist_str, primary_artist.lower())
            else:
                artist_score = 70.0

            total_score = (title_score * 0.65) + (artist_score * 0.35)

            item_sec = item.get("duration_seconds")
            if target_sec and item_sec:
                diff = abs(target_sec - item_sec)
                if diff <= 6:
                    total_score += 10.0
                elif diff <= 15:
                    total_score += 5.0
                elif diff > 60:
                    total_score -= 15.0

            if item.get("resultType") == "song":
                total_score += 5.0

            if total_score > best_score:
                best_score = total_score
                thumb = None
                thumbs = item.get("thumbnails", [])
                if thumbs:
                    thumb = thumbs[-1].get("url")

                best_match = {
                    "videoId": item.get("videoId"),
                    "title": item_title,
                    "artist": ", ".join(item_artists) if item_artists else primary_artist,
                    "album": item.get("album", {}).get("name", "") if isinstance(item.get("album"), dict) else "",
                    "duration": item.get("duration", ""),
                    "thumbnail": thumb,
                    "score": total_score
                }

        if best_match and best_score >= 60.0:
            return best_match
            
        return None

    def get_or_create_playlist(self, title: str, description: str = "") -> str:
        """Finds an existing empty playlist with the same title or creates a new one."""
        if not self.yt:
            raise PermissionError("YouTube Music no está conectado.")
        try:
            lib_playlists = self.yt.get_library_playlists(limit=50)
            for pl in lib_playlists:
                pl_title = pl.get("title")
                pl_count = pl.get("count")
                if pl_title == title and (pl_count in (None, 0, "0")):
                    pl_id = pl.get("playlistId")
                    if pl_id:
                        logger.info(f"Reutilizando playlist vacía existente en YouTube Music: {title} ({pl_id})")
                        return pl_id
        except Exception as e:
            logger.debug(f"No se pudo consultar playlists existentes: {e}")

        return self.create_playlist(title=title, description=description)

    def create_playlist(self, title: str, description: str = "") -> str:
        if not self.yt:
            raise PermissionError("YouTube Music no está conectado.")
        desc = description or "Importada automáticamente desde Spotify"
        try:
            playlist_id = self.yt.create_playlist(title=title, description=desc, privacy_status="PRIVATE")
            if not playlist_id or not isinstance(playlist_id, str):
                raise RuntimeError(f"Respuesta inesperada al crear playlist: {playlist_id}")
            return playlist_id
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "signed in" in err_str.lower() or "unauthorized" in err_str.lower():
                self._user_info = None
                raise PermissionError("Tu sesión de YouTube Music expiró. Por favor vuelve a conectar tu cuenta.")
            logger.error(f"Error creando playlist '{title}' en YouTube Music: {e}")
            raise

    def add_tracks(
        self, 
        playlist_id: str, 
        video_ids: List[str], 
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        if not self.yt:
            raise PermissionError("YouTube Music no está conectado.")
        if not video_ids:
            return {"success": True, "added_count": 0, "failed_count": 0, "total": 0, "errors": []}

        # Deduplicate while preserving order
        seen = set()
        unique_video_ids = []
        for vid in video_ids:
            if vid and vid not in seen:
                seen.add(vid)
                unique_video_ids.append(vid)

        total_tracks = len(unique_video_ids)
        added_total = 0
        failed_ids = []
        errors = []
        chunk_size = 50

        for i in range(0, total_tracks, chunk_size):
            chunk = unique_video_ids[i:i + chunk_size]
            chunk_success = False

            # Retry loop for batch insertion (up to 3 retries for transient DNS/connection issues)
            for attempt in range(1, 4):
                try:
                    res = self.yt.add_playlist_items(playlist_id, chunk, duplicates=True)
                    if isinstance(res, dict) and "status" in res and "SUCCEEDED" not in str(res.get("status", "")):
                        logger.warning(f"Lote de YouTube devolvió status no exitoso: {res}")
                        break
                    added_total += len(chunk)
                    chunk_success = True
                    break
                except Exception as e:
                    err_msg = str(e)
                    if "401" in err_msg or "Unauthorized" in err_msg or "signed in" in err_msg.lower():
                        self._user_info = None
                        logger.error(f"Sesión no autorizada en YouTube Music: {e}")
                        raise PermissionError("Sesión de YouTube Music expirada o no autorizada. Por favor vuelve a conectar tu cuenta de YouTube Music.")
                    
                    logger.warning(f"Intento {attempt}/3 falló agregando lote ({len(chunk)} temas) a playlist {playlist_id}: {e}")
                    if attempt < 3:
                        time.sleep(1.2 * attempt)

            # If the batch failed after 3 retries, fall back to adding one-by-one so good songs don't get lost
            if not chunk_success:
                logger.info(f"Lote de {len(chunk)} canciones falló en bloque. Intentando añadir individualmente...")
                for single_vid in chunk:
                    single_added = False
                    for s_attempt in range(1, 3):
                        try:
                            s_res = self.yt.add_playlist_items(playlist_id, [single_vid], duplicates=True)
                            if isinstance(s_res, dict) and "status" in s_res and "SUCCEEDED" not in str(s_res.get("status", "")):
                                continue
                            added_total += 1
                            single_added = True
                            time.sleep(0.05)
                            break
                        except Exception as se:
                            if "401" in str(se) or "Unauthorized" in str(se):
                                self._user_info = None
                                raise PermissionError("Sesión de YouTube Music expirada. Por favor vuelve a conectar tu cuenta de YouTube Music.")
                            if s_attempt < 2:
                                time.sleep(0.4)
                    if not single_added:
                        failed_ids.append(single_vid)
                        errors.append(f"No se pudo añadir el track {single_vid}")

            # Notify live progress after each batch
            if on_progress:
                try:
                    on_progress(added_total, total_tracks)
                except Exception as cb_err:
                    logger.debug(f"Error en callback de progreso: {cb_err}")

            # Safe throttle between chunks to avoid socket and rate-limit exhaustion
            time.sleep(0.3)

        return {
            "success": added_total > 0,
            "added_count": added_total,
            "failed_count": len(failed_ids),
            "total": total_tracks,
            "errors": errors
        }

    def rate_track_like(self, video_id: str) -> bool:
        if not self.yt or not video_id:
            return False
        try:
            self.yt.rate_song(video_id, rating="LIKE")
            return True
        except Exception as e:
            logger.debug(f"Error dando like a {video_id} en YouTube Music: {e}")
            return False

# Global singleton
ytmusic_manager = YTMusicClient()
