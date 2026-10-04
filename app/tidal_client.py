import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import concurrent.futures

import time
import tidalapi
from rapidfuzz import fuzz
from app.config import TIDAL_SESSION_FILE

logger = logging.getLogger(__name__)

def clean_song_title(title: str) -> str:
    """Removes noise like (Remastered 2011), [Deluxe Edition], - Live at..., etc."""
    cleaned = title
    # Remove things like - 2011 Remastered Version, - Live, etc.
    cleaned = re.sub(r"\s*-\s*(?:remaster(?:ed)?|live|bonus track|deluxe|radio edit|mono|stereo).*", "", cleaned, flags=re.IGNORECASE)
    # Remove parentheses with remaster or version info
    cleaned = re.sub(r"\s*\((?:remaster(?:ed)?|version|bonus|deluxe|edit|live|mono|stereo)[^)]*\)", "", cleaned, flags=re.IGNORECASE)
    # Remove brackets
    cleaned = re.sub(r"\s*\[(?:remaster(?:ed)?|version|bonus|deluxe|edit|live)[^\]]*\]", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

class TidalManager:
    def __init__(self):
        self.session = tidalapi.Session()
        self._configure_session_headers(self.session)
        self._login_obj: Optional[tidalapi.session.LinkLogin] = None
        self._login_future: Optional[concurrent.futures.Future] = None
        self._last_check_time: float = 0.0
        self._try_load_saved_session()

    def _configure_session_headers(self, session: tidalapi.Session):
        session.request_session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        })

    def _try_load_saved_session(self) -> bool:
        if TIDAL_SESSION_FILE.exists():
            try:
                success = self.session.load_session_from_file(TIDAL_SESSION_FILE)
                if success and self.session.check_login():
                    logger.info("Sesión de TIDAL restaurada exitosamente.")
                    return True
            except Exception as e:
                logger.warning(f"No se pudo cargar la sesión de TIDAL previa: {e}")
        return False

    def is_authenticated(self) -> bool:
        try:
            return bool(self.session and self.session.check_login())
        except Exception:
            return False

    def start_oauth_login(self) -> Dict[str, Any]:
        """Initiates OAuth device code login."""
        self.session = tidalapi.Session()
        self._configure_session_headers(self.session)
        link_login = self.session.get_link_login()
        self._login_obj = link_login
        self._login_future = None
        self._last_check_time = time.time()

        uri = link_login.verification_uri_complete or f"link.tidal.com/{link_login.user_code}"
        if not uri.startswith("http://") and not uri.startswith("https://"):
            uri = f"https://{uri}"

        return {
            "verification_uri": uri,
            "user_code": link_login.user_code,
            "expires_in": link_login.expires_in,
        }

    def check_oauth_status(self) -> Dict[str, Any]:
        if not self._login_obj:
            return {"logged_in": self.is_authenticated(), "status": "no_pending_login"}

        if self.is_authenticated():
            return {"logged_in": True, "status": "completed"}

        now = time.time()
        # Enforce rate limit of at least 4.5 seconds between actual requests to Tidal API
        if now - self._last_check_time < 4.5:
            return {"logged_in": False, "status": "pending"}

        self._last_check_time = now

        try:
            result = self.session.process_link_login(self._login_obj, until_expiry=False)
            if result and self.session.check_login():
                try:
                    self.session.save_session_to_file(TIDAL_SESSION_FILE)
                except Exception as e:
                    logger.error(f"No se pudo guardar la sesión de TIDAL en disco: {e}")
                self._login_obj = None
                return {"logged_in": True, "status": "completed"}
        except TimeoutError:
            return {"logged_in": False, "status": "pending"}
        except Exception as e:
            logger.error(f"Error durante OAuth de TIDAL: {e}")
            return {"logged_in": False, "status": "error", "error": str(e)}

        return {"logged_in": False, "status": "pending"}



    def logout(self):
        if TIDAL_SESSION_FILE.exists():
            try:
                TIDAL_SESSION_FILE.unlink()
            except Exception:
                pass
        self.session = tidalapi.Session()
        self._login_obj = None
        self._login_future = None

    def get_user_profile(self) -> Dict[str, Any]:
        if not self.is_authenticated():
            raise PermissionError("TIDAL no está conectado.")

        user = self.session.user
        name = ""
        if hasattr(user, "first_name") and user.first_name:
            name = f"{user.first_name} {getattr(user, 'last_name', '')}".strip()
        if not name:
            name = getattr(user, "username", "Usuario de Tidal")

        return {
            "id": getattr(user, "id", None),
            "username": getattr(user, "username", ""),
            "name": name,
            "email": getattr(user, "email", ""),
            "picture": getattr(user, "picture_id", None),
        }

    def match_track(
        self,
        name: str,
        artists: List[str],
        isrc: Optional[str] = None,
        duration_ms: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Attempts to match a track on Tidal:
        1. Query exact ISRC.
        2. Fallback to Tidal Search with fuzzy scoring.
        """
        if not self.is_authenticated():
            raise PermissionError("TIDAL no está conectado.")

        # 1. Try ISRC matching
        if isrc:
            try:
                tracks = self.session.get_tracks_by_isrc(isrc)
                if tracks and len(tracks) > 0:
                    best = tracks[0]
                    artist_name = best.artist.name if hasattr(best, "artist") and best.artist else ""
                    return {
                        "tidal_id": str(best.id),
                        "name": best.name,
                        "artist": artist_name,
                        "album": getattr(best.album, "name", "") if hasattr(best, "album") and best.album else "",
                        "match_type": "ISRC_EXACT",
                        "confidence": 100,
                        "audio_quality": getattr(best, "audio_quality", "LOSSLESS"),
                    }
            except Exception:
                pass  # Fallback to search query

        # 2. Search fallback
        primary_artist = artists[0] if artists else ""
        cleaned_title = clean_song_title(name)
        search_queries = [
            f"{cleaned_title} {primary_artist}".strip(),
            f"{name} {primary_artist}".strip(),
            cleaned_title
        ]

        best_candidate = None
        highest_score = 0.0

        for query in search_queries:
            if not query:
                continue
            try:
                search_results = self.session.search(
                    query=query,
                    models=[tidalapi.media.Track],
                    limit=8
                )
                tracks = search_results.get("tracks", [])
                if not tracks:
                    continue

                for t in tracks:
                    if not t or not hasattr(t, "name"):
                        continue
                    t_artist = t.artist.name if hasattr(t, "artist") and t.artist else ""
                    
                    # Calculate similarity scores
                    title_ratio = fuzz.token_set_ratio(t.name.lower(), name.lower())
                    clean_title_ratio = fuzz.token_set_ratio(clean_song_title(t.name).lower(), cleaned_title.lower())
                    max_title_score = max(title_ratio, clean_title_ratio)

                    artist_score = 100
                    if primary_artist:
                        artist_score = fuzz.token_set_ratio(t_artist.lower(), primary_artist.lower())

                    # Combined score
                    combined = (max_title_score * 0.65) + (artist_score * 0.35)

                    # Duration penalty if duration differs significantly (> 12 seconds)
                    if duration_ms and hasattr(t, "duration") and t.duration:
                        tidal_dur_ms = t.duration * 1000
                        diff_sec = abs(tidal_dur_ms - duration_ms) / 1000.0
                        if diff_sec > 15:
                            combined -= min(20, (diff_sec - 15) * 1.5)

                    if combined > highest_score:
                        highest_score = combined
                        best_candidate = t

                if highest_score >= 82:
                    break  # Found good match, no need to try weaker queries

            except Exception as e:
                logger.warning(f"Error buscando en Tidal '{query}': {e}")
                continue

        if best_candidate and highest_score >= 70:
            match_type = "HIGH_CONFIDENCE" if highest_score >= 85 else "FUZZY_MATCH"
            artist_name = best_candidate.artist.name if hasattr(best_candidate, "artist") and best_candidate.artist else ""
            return {
                "tidal_id": str(best_candidate.id),
                "name": best_candidate.name,
                "artist": artist_name,
                "album": getattr(best_candidate.album, "name", "") if hasattr(best_candidate, "album") and best_candidate.album else "",
                "match_type": match_type,
                "confidence": round(highest_score, 1),
                "audio_quality": getattr(best_candidate, "audio_quality", "LOSSLESS"),
            }

        return None

    def create_playlist(self, title: str, description: str = "") -> Any:
        if not self.is_authenticated():
            raise PermissionError("TIDAL no está conectado.")
        return self.session.user.create_playlist(title=title, description=description)

    def add_tracks_to_playlist(self, playlist: Any, track_ids: List[str], chunk_size: int = 50) -> int:
        """Adds tracks in safe chunks to avoid Tidal API request size or timeout issues."""
        if not track_ids:
            return 0

        added_total = 0
        for i in range(0, len(track_ids), chunk_size):
            chunk = track_ids[i:i + chunk_size]
            try:
                res = playlist.add(chunk, allow_duplicates=False)
                added_total += len(res) if res else len(chunk)
            except Exception as e:
                logger.error(f"Error agregando lote de canciones a playlist de Tidal: {e}")
                # Try adding one by one if batch failed
                for tid in chunk:
                    try:
                        res = playlist.add([tid], allow_duplicates=False)
                        if res:
                            added_total += len(res)
                    except Exception:
                        pass
        return added_total

tidal_manager = TidalManager()
