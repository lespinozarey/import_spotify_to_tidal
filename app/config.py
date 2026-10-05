import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables if .env exists
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

TIDAL_SESSION_FILE = BASE_DIR / "tidal_session.json"
YTMUSIC_SESSION_FILE = BASE_DIR / "ytmusic_session.json"
SPOTIFY_CACHE_FILE = BASE_DIR / ".spotify_cache"

def get_env_var(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

def save_spotify_credentials(client_id: str, client_secret: str, redirect_uri: str = "http://127.0.0.1:8000/api/spotify/callback"):
    os.environ["SPOTIFY_CLIENT_ID"] = client_id.strip()
    os.environ["SPOTIFY_CLIENT_SECRET"] = client_secret.strip()
    os.environ["SPOTIFY_REDIRECT_URI"] = redirect_uri.strip()
    
    # Write or update .env file locally
    content = (
        f"SPOTIFY_CLIENT_ID={client_id.strip()}\n"
        f"SPOTIFY_CLIENT_SECRET={client_secret.strip()}\n"
        f"SPOTIFY_REDIRECT_URI={redirect_uri.strip()}\n"
        f"HOST=127.0.0.1\n"
        f"PORT=8000\n"
    )
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(content)
