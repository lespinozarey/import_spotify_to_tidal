import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
from rapidfuzz import fuzz

import ytmusicapi
from app.config import YTMUSIC_SESSION_FILE
from app.tidal_client import clean_song_title

logger = logging.getLogger("uvicorn")

class YTMusicClient:
    def __init__(self):
        self.yt: Optional[ytmusicapi.YTMusic] = None
        self._user_info: Optional[Dict[str, Any]] = None
        self._try_load_saved_session()

    def _try_load_saved_session(self) -> bool:
        if YTMUSIC_SESSION_FILE.exists():
            try:
                self.yt = ytmusicapi.YTMusic(str(YTMUSIC_SESSION_FILE))
                if self.is_authenticated():
                    logger.info("Sesión de YouTube Music restaurada exitosamente.")
                    return True
            except Exception as e:
                logger.warning(f"No se pudo cargar la sesión de YouTube Music: {e}")
                self.yt = None
        return False

    def is_authenticated(self) -> bool:
        if not self.yt:
            return False
        try:
            # Check auth status using get_account_info or get_library_playlists
            info = self.get_user_info()
            return bool(info.get("name"))
        except Exception:
            return False

    def get_user_info(self) -> Dict[str, Any]:
        if not self.yt:
            return {"authenticated": False, "name": "", "handle": "", "photo": None}
        
        if self._user_info:
            return self._user_info
            
        try:
            acc = self.yt.get_account_info()
            self._user_info = {
                "authenticated": True,
                "name": acc.get("accountName") or "Usuario de YouTube",
                "handle": acc.get("channelHandle") or "",
                "photo": acc.get("accountPhotoUrl") or None
            }
            return self._user_info
        except Exception as e:
            logger.debug(f"Error obteniendo info de cuenta de YTMusic: {e}")
            # Fallback: check if we can query library playlists
            try:
                self.yt.get_library_playlists(limit=1)
                self._user_info = {
                    "authenticated": True,
                    "name": "Cuenta Conectada",
                    "handle": "",
                    "photo": None
                }
                return self._user_info
            except Exception:
                return {"authenticated": False, "name": "", "handle": "", "photo": None}

    def setup_from_headers(self, raw_input: str) -> bool:
        """
        Parses raw browser request headers, JSON, or cookie strings,
        validates the session, and saves it to YTMUSIC_SESSION_FILE.
        """
        raw_text = raw_input.strip()
        if not raw_text:
            raise ValueError("Las cabeceras no pueden estar vacías.")

        # If user pasted a JSON string directly
        if raw_text.startswith("{") and raw_text.endswith("}"):
            try:
                parsed_json = json.loads(raw_text)
                with open(YTMUSIC_SESSION_FILE, "w", encoding="utf-8") as f:
                    json.dump(parsed_json, f, indent=2, ensure_ascii=False)
                self.yt = ytmusicapi.YTMusic(str(YTMUSIC_SESSION_FILE))
                self._user_info = None
                if self.is_authenticated():
                    return True
            except Exception as e:
                logger.debug(f"Fallo al parsear JSON directo: {e}")

        # If user pasted "cookie: ..." line only or full headers
        lines = raw_text.splitlines()
        cookie_val = ""
        user_headers = {}

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.lower().startswith("cookie:"):
                cookie_val = line_str[7:].strip()
            elif ": " in line_str:
                parts = line_str.split(": ", 1)
                user_headers[parts[0].lower()] = parts[1]

        # Use ytmusicapi.setup parser
        try:
            setup_res = ytmusicapi.setup(filepath=str(YTMUSIC_SESSION_FILE), headers_raw=raw_text)
            self.yt = ytmusicapi.YTMusic(str(YTMUSIC_SESSION_FILE))
            self._user_info = None
            if self.is_authenticated():
                return True
        except Exception as e:
            logger.debug(f"Fallo parser de ytmusicapi.setup: {e}")

        # If standard setup failed because of missing x-goog-authuser, try to synthesize valid headers
        if cookie_val or "cookie" in user_headers:
            cookie_str = cookie_val or user_headers.get("cookie", "")
            authuser = user_headers.get("x-goog-authuser", "0")
            synthesized = (
                f"accept: */*\n"
                f"accept-encoding: gzip, deflate, br\n"
                f"accept-language: es,en-US;q=0.9,en;q=0.8\n"
                f"content-type: application/json\n"
                f"cookie: {cookie_str}\n"
                f"origin: https://music.youtube.com\n"
                f"referer: https://music.youtube.com/\n"
                f"user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36\n"
                f"x-goog-authuser: {authuser}\n"
                f"x-origin: https://music.youtube.com\n"
            )
            try:
                ytmusicapi.setup(filepath=str(YTMUSIC_SESSION_FILE), headers_raw=synthesized)
                self.yt = ytmusicapi.YTMusic(str(YTMUSIC_SESSION_FILE))
                self._user_info = None
                if self.is_authenticated():
                    return True
            except Exception as synth_err:
                raise ValueError(f"No se pudo autenticar con las cabeceras proporcionadas: {synth_err}")

        raise ValueError("No se encontraron las cookies de sesión requeridas. Asegúrate de copiar las cabeceras de una petición desde music.youtube.com")

    def logout(self):
        if YTMUSIC_SESSION_FILE.exists():
            try:
                YTMUSIC_SESSION_FILE.unlink()
            except Exception:
                pass
        self.yt = None
        self._user_info = None

    def search_track(self, name: str, artists: List[str], duration_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Searches for the official song or video in YouTube Music.
        Prioritizes official songs (AUDIO) over music videos.
        Uses RapidFuzz for high accuracy title and artist matching.
        """
        client = self.yt if self.yt else ytmusicapi.YTMusic()
        primary_artist = artists[0] if artists else ""
        query = f"{name} {primary_artist}".strip()
        cleaned_title = clean_song_title(name)

        # 1. Search in "songs" (Official studio audio)
        candidates = []
        try:
            song_results = client.search(query, filter="songs")
            if song_results:
                candidates.extend(song_results[:8])
        except Exception as e:
            logger.debug(f"Error en búsqueda de canciones en YTMusic: {e}")

        # 2. If candidates are sparse, search in "videos"
        if len(candidates) < 3:
            try:
                video_results = client.search(query, filter="videos")
                if video_results:
                    candidates.extend(video_results[:5])
            except Exception as e:
                logger.debug(f"Error en búsqueda de videos en YTMusic: {e}")

        if not candidates:
            return None

        best_match = None
        best_score = -1.0
        target_sec = (duration_ms / 1000.0) if duration_ms else None

        for item in candidates:
            item_title = item.get("title", "")
            item_clean_title = clean_song_title(item_title)
            
            # Title similarity
            title_score = max(
                fuzz.token_set_ratio(item_title.lower(), name.lower()),
                fuzz.token_set_ratio(item_clean_title.lower(), cleaned_title.lower())
            )

            # Artist similarity
            item_artists = [a.get("name", "") for a in item.get("artists", []) if isinstance(a, dict)]
            item_artist_str = " ".join(item_artists).lower()
            
            artist_score = 0.0
            if primary_artist:
                artist_score = fuzz.token_set_ratio(item_artist_str, primary_artist.lower())
            else:
                artist_score = 70.0

            # Composite match score
            total_score = (title_score * 0.65) + (artist_score * 0.35)

            # Duration bonus / penalty
            item_sec = item.get("duration_seconds")
            if target_sec and item_sec:
                diff = abs(target_sec - item_sec)
                if diff <= 6:
                    total_score += 10.0
                elif diff <= 15:
                    total_score += 5.0
                elif diff > 60:
                    total_score -= 15.0

            # Bonus for official song audio
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

        # Threshold of 60 ensures we don't pick a wildly incorrect song
        if best_match and best_score >= 60.0:
            return best_match
            
        return None

    def create_playlist(self, title: str, description: str = "") -> str:
        if not self.yt:
            raise PermissionError("YouTube Music no está conectado.")
        desc = description or "Importada automáticamente desde Spotify"
        playlist_id = self.yt.create_playlist(title=title, description=desc, privacy_status="PRIVATE")
        return playlist_id

    def add_tracks(self, playlist_id: str, video_ids: List[str]) -> bool:
        if not self.yt:
            raise PermissionError("YouTube Music no está conectado.")
        if not video_ids:
            return True
            
        # Add in chunks of 50
        chunk_size = 50
        for i in range(0, len(video_ids), chunk_size):
            chunk = video_ids[i:i + chunk_size]
            try:
                self.yt.add_playlist_items(playlist_id, chunk)
            except Exception as e:
                logger.error(f"Error añadiendo canciones a playlist {playlist_id} en YouTube Music: {e}")
                return False
        return True

    def rate_track_like(self, video_id: str) -> bool:
        """
        Likes a song/video in YouTube Music.
        This provides the strongest algorithmic signal to YouTube's recommendation engine!
        """
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
