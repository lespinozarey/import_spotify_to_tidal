import re
from typing import List, Dict, Any, Optional
import spotipy
from spotipy.oauth2 import SpotifyOAuth, SpotifyClientCredentials
from app.config import (
    SPOTIFY_CACHE_FILE,
    get_env_var,
    save_spotify_credentials,
)

SCOPE = "playlist-read-private playlist-read-collaborative user-library-read"

class SpotifyManager:
    def __init__(self):
        self._sp: Optional[spotipy.Spotify] = None
        self._oauth: Optional[SpotifyOAuth] = None
        self.loaded_playlists: Dict[str, Any] = {}

    def get_oauth(self) -> SpotifyOAuth:
        client_id = get_env_var("SPOTIFY_CLIENT_ID")
        client_secret = get_env_var("SPOTIFY_CLIENT_SECRET")
        redirect_uri = get_env_var("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/api/spotify/callback")

        if not client_id or not client_secret:
            raise ValueError("Faltan el Client ID o Client Secret de Spotify.")

        return SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=SCOPE,
            cache_path=str(SPOTIFY_CACHE_FILE),
            show_dialog=True,
        )

    def is_configured(self) -> bool:
        cid = get_env_var("SPOTIFY_CLIENT_ID")
        sec = get_env_var("SPOTIFY_CLIENT_SECRET")
        return bool(cid and sec)

    def is_authenticated(self) -> bool:
        if not self.is_configured():
            return False
        try:
            oauth = self.get_oauth()
            token_info = oauth.get_cached_token()
            return bool(token_info and not oauth.is_token_expired(token_info))
        except Exception:
            return False

    def get_client(self) -> spotipy.Spotify:
        oauth = self.get_oauth()
        token_info = oauth.get_cached_token()
        if not token_info:
            raise PermissionError("Spotify no está conectado. Inicia sesión primero.")

        if oauth.is_token_expired(token_info):
            token_info = oauth.refresh_access_token(token_info["refresh_token"])

        return spotipy.Spotify(auth=token_info["access_token"])

    def get_authorize_url(self) -> str:
        oauth = self.get_oauth()
        return oauth.get_authorize_url()

    def handle_auth_code(self, code: str) -> bool:
        oauth = self.get_oauth()
        token_info = oauth.get_access_token(code, as_dict=True)
        return bool(token_info)

    def logout(self):
        if SPOTIFY_CACHE_FILE.exists():
            try:
                SPOTIFY_CACHE_FILE.unlink()
            except Exception:
                pass

    def get_user_profile(self) -> Dict[str, Any]:
        sp = self.get_client()
        me = sp.current_user()
        avatar = ""
        if me.get("images") and len(me["images"]) > 0:
            avatar = me["images"][0].get("url", "")
        return {
            "id": me.get("id"),
            "display_name": me.get("display_name") or me.get("id"),
            "email": me.get("email"),
            "avatar": avatar,
            "product": me.get("product"),
            "followers": me.get("followers", {}).get("total", 0),
        }

    def get_user_playlists(self) -> List[Dict[str, Any]]:
        sp = self.get_client()
        playlists = []
        limit = 50
        offset = 0

        while True:
            results = sp.current_user_playlists(limit=limit, offset=offset)
            items = results.get("items", [])
            for item in items:
                if not item:
                    continue
                image_url = ""
                if item.get("images") and len(item["images"]) > 0:
                    image_url = item["images"][0].get("url", "")

                playlists.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "description": item.get("description") or "",
                    "tracks_total": item.get("tracks", {}).get("total", 0),
                    "public": item.get("public", False),
                    "owner": item.get("owner", {}).get("display_name", "Desconocido"),
                    "image": image_url,
                    "url": item.get("external_urls", {}).get("spotify", "")
                })

            if len(items) < limit:
                break
            offset += limit

        return playlists

    def get_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        sp = self.get_client()
        tracks = []
        limit = 100
        offset = 0

        while True:
            results = sp.playlist_items(
                playlist_id=playlist_id,
                fields="items(track(id,name,artists(name),album(name,images),duration_ms,external_ids)),total,next",
                additional_types=["track"],
                limit=limit,
                offset=offset,
            )
            items = results.get("items", [])
            for item in items:
                track = item.get("track")
                if not track:
                    continue

                artists = [a.get("name") for a in track.get("artists", []) if a.get("name")]
                artist_str = ", ".join(artists) if artists else "Desconocido"

                album = track.get("album", {})
                album_name = album.get("name", "")
                album_image = ""
                if album.get("images") and len(album["images"]) > 0:
                    album_image = album["images"][0].get("url", "")

                isrc = track.get("external_ids", {}).get("isrc", "")

                tracks.append({
                    "id": track.get("id"),
                    "name": track.get("name"),
                    "artists": artists,
                    "artist_display": artist_str,
                    "album": album_name,
                    "album_image": album_image,
                    "duration_ms": track.get("duration_ms", 0),
                    "isrc": isrc.strip() if isrc else None,
                })

            if len(items) < limit or not results.get("next"):
                break
            offset += limit

        return tracks

    def extract_playlist_id_from_url(self, url: str) -> str:
        # Matches https://open.spotify.com/playlist/{id} or spotify:playlist:{id}
        pattern = r"playlist[/:]([a-zA-Z0-9]+)"
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        return url.strip()

    def fetch_playlist_without_login(self, url_or_id: str) -> Dict[str, Any]:
        """Fetches all playlist tracks directly without requiring any developer account or API keys."""
        import requests
        import json

        playlist_id = self.extract_playlist_id_from_url(url_or_id)
        embed_url = f"https://open.spotify.com/embed/playlist/{playlist_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        res = requests.get(embed_url, headers=headers, timeout=10)
        if res.status_code != 200:
            raise ValueError(f"No se pudo cargar la playlist (código {res.status_code}). Verifica que el enlace sea público.")

        match = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', res.text)
        if not match:
            raise ValueError("No se pudo extraer la información de la playlist. Verifica que el enlace sea correcto.")

        try:
            page_data = json.loads(match.group(1))
            entity = page_data["props"]["pageProps"]["state"]["data"]["entity"]
        except Exception as e:
            raise ValueError(f"Error interpretando los datos de la playlist: {e}")

        title = entity.get("title") or entity.get("name") or "Playlist Importada"
        track_list = entity.get("trackList", [])

        # Extract image
        image_url = ""
        visual = entity.get("visualIdentity", {})
        images = visual.get("image", [])
        if images and len(images) > 0:
            image_url = images[-1].get("url", "")
        elif entity.get("images") and len(entity["images"]) > 0:
            image_url = entity["images"][0].get("url", "")

        tracks = []
        for t in track_list:
            t_title = t.get("title", "")
            if not t_title:
                continue

            subtitle = t.get("subtitle", "")
            artists = [a.strip() for a in subtitle.split(",") if a.strip()]
            if not artists:
                artists = ["Desconocido"]

            duration_ms = t.get("duration", 0)

            tracks.append({
                "id": t.get("uri", "").replace("spotify:track:", ""),
                "name": t_title,
                "artists": artists,
                "artist_display": subtitle or ", ".join(artists),
                "album": "",
                "album_image": image_url,
                "duration_ms": duration_ms,
                "isrc": None,
            })

        result = {
            "id": playlist_id,
            "name": title,
            "description": "Importada desde Spotify",
            "tracks_total": len(tracks),
            "public": True,
            "owner": "Spotify",
            "image": image_url,
            "tracks": tracks,
            "url": f"https://open.spotify.com/playlist/{playlist_id}"
        }

        # Cache in memory
        self.loaded_playlists[playlist_id] = result
        return result

    def fetch_user_playlists_without_login(self, profile_url_or_username: str) -> List[Dict[str, Any]]:
        """Extracts public playlists from a Spotify user profile without API keys."""
        import requests
        clean_input = profile_url_or_username.strip()
        if "?" in clean_input:
            clean_input = clean_input.split("?")[0]
            
        user_match = re.search(r"user[/:]([a-zA-Z0-9_\-\.]+)", clean_input)
        username = user_match.group(1) if user_match else clean_input.replace("https://open.spotify.com/user/", "")

        url = f"https://open.spotify.com/user/{username}"
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            raise ValueError(f"No se pudo acceder al perfil '{username}'. Verifica el usuario o enlace.")

        playlist_ids = list(dict.fromkeys(re.findall(r"playlist/([a-zA-Z0-9]{22})", res.text)))
        if not playlist_ids:
            raise ValueError(f"No se encontraron playlists públicas visibles en el perfil de '{username}'.")

        playlists = []
        for pid in playlist_ids:
            try:
                pl = self.fetch_playlist_without_login(pid)
                playlists.append(pl)
            except Exception:
                continue

        return playlists


    def parse_playlist_file(self, filename: str, content: str) -> Dict[str, Any]:
        """Parses CSV (Exportify, TuneMyMusic, Soundiiz) or TXT playlist files without any track limits."""
        import csv
        import io
        import uuid
        from pathlib import Path

        playlist_name = Path(filename).stem or "Playlist Importada"
        tracks = []

        # Check if CSV
        if filename.lower().endswith(".csv") or ("," in content.splitlines()[0] if content.splitlines() else False):
            sample = content[:2048]
            delimiter = ";" if ";" in sample and "," not in sample else ","
            reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
            
            fieldnames = [f.strip() for f in (reader.fieldnames or [])]
            col_map = {f.lower(): f for f in fieldnames}

            name_col = next((col_map[k] for k in ["track name", "title", "song", "track"] if k in col_map), None)
            artist_col = next((col_map[k] for k in ["artist name(s)", "artist name", "artist", "artists"] if k in col_map), None)
            album_col = next((col_map[k] for k in ["album name", "album"] if k in col_map), None)
            isrc_col = next((col_map[k] for k in ["isrc"] if k in col_map), None)
            dur_col = next((col_map[k] for k in ["track duration (ms)", "duration (ms)", "duration"] if k in col_map), None)

            if name_col and artist_col:
                for row in reader:
                    t_name = row.get(name_col, "").strip()
                    if not t_name:
                        continue
                    t_artist = row.get(artist_col, "").strip()
                    artists = [a.strip() for a in t_artist.split(",") if a.strip()]
                    t_album = row.get(album_col, "").strip() if album_col else ""
                    t_isrc = row.get(isrc_col, "").strip() if isrc_col else None
                    t_dur = 0
                    if dur_col and row.get(dur_col):
                        try:
                            t_dur = int(float(row.get(dur_col)))
                        except Exception:
                            pass

                    tracks.append({
                        "id": str(uuid.uuid4())[:8],
                        "name": t_name,
                        "artists": artists or ["Desconocido"],
                        "artist_display": t_artist or "Desconocido",
                        "album": t_album,
                        "album_image": "",
                        "duration_ms": t_dur,
                        "isrc": t_isrc or None,
                    })

        # Fallback to plain text (line by line: Artist - Song)
        if not tracks:
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            for l in lines:
                if " - " in l:
                    parts = l.split(" - ", 1)
                    artist, name = parts[0].strip(), parts[1].strip()
                else:
                    name, artist = l, "Desconocido"

                tracks.append({
                    "id": str(uuid.uuid4())[:8],
                    "name": name,
                    "artists": [artist],
                    "artist_display": artist,
                    "album": "",
                    "album_image": "",
                    "duration_ms": 0,
                    "isrc": None,
                })

        pid = f"file_{uuid.uuid4().hex[:12]}"
        result = {
            "id": pid,
            "name": playlist_name,
            "description": f"Importada desde archivo {filename} ({len(tracks)} canciones)",
            "tracks_total": len(tracks),
            "public": True,
            "owner": "Archivo",
            "image": "",
            "tracks": tracks,
            "url": ""
        }
        self.loaded_playlists[pid] = result
        return result

    def get_public_playlist_by_url(self, url_or_id: str) -> Dict[str, Any]:
        return self.fetch_playlist_without_login(url_or_id)

spotify_manager = SpotifyManager()


