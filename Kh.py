from flask import Flask, jsonify, request, render_template_string
import requests
import os
import sys
import sqlite3
import hashlib
from datetime import datetime

app = Flask(__name__)

API_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}

# Sportmonks (source complémentaire)
SPORTMONKS_TOKEN = os.getenv("SPORTMONKS_TOKEN", "").strip()
SPORTMONKS_URL = "https://api.sportmonks.com/v3/football"
SPORTMONKS_HEADERS = {"Authorization": SPORTMONKS_TOKEN} if SPORTMONKS_TOKEN else {}

# Facebook Page publishing
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
FB_GRAPH_VERSION = os.getenv("FB_GRAPH_VERSION", "v26.0")
FB_GRAPH_URL = "https://graph.facebook.com/" + FB_GRAPH_VERSION


def _safe_api_message(response, secret=""):
    """Return provider error details without ever echoing configured secrets."""
    try:
        payload = response.json()
        error_obj = payload.get("error") or {}
        error_message = error_obj.get("message") if isinstance(error_obj, dict) else str(error_obj)
        message = payload.get("message") or error_message or str(payload)
    except Exception:
        message = (response.text or "Réponse vide")[:500]
    if secret:
        message = str(message).replace(secret, "[masqué]")
    return str(message)[:700]


def sportmonks_get(endpoint, params=None):
    if not SPORTMONKS_TOKEN:
        return None, "SPORTMONKS_TOKEN non configuré"
    try:
        r = requests.get(
            SPORTMONKS_URL + "/" + endpoint,
            headers={"Authorization": SPORTMONKS_TOKEN},
            params=params or {},
            timeout=20
        )
        try:
            data = r.json()
        except Exception:
            data = {}
        if r.status_code != 200:
            detail = _safe_api_message(r, SPORTMONKS_TOKEN)
            if r.status_code == 403:
                return None, ("Sportmonks 403 : accès refusé par les droits du forfait ou du flux. "
                              "Détail fournisseur : " + detail)
            if r.status_code == 401:
                return None, "Sportmonks 401 : token invalide ou non reconnu. " + detail
            return None, "Sportmonks HTTP " + str(r.status_code) + " : " + detail
        return data, None
    except Exception as e:
        return None, "Erreur de connexion Sportmonks : " + str(e)[:300]


def sportmonks_live_or_fixtures():
    """Try the live feed first; fall back to today's fixtures if that feed is not enabled."""
    live_data, live_error = sportmonks_get(
        "livescores/inplay",
        {"include": "scores;events.player;participants;state;league;venue"}
    )
    if not live_error:
        return live_data.get("data", []), None, "livescores/inplay"

    # A 403 can mean that the live feed is not included in the current plan.
    # The date endpoint may still be available for leagues included in the plan.
    today = datetime.now().strftime("%Y-%m-%d")
    fixture_data, fixture_error = sportmonks_get(
        "fixtures/date/" + today,
        {"include": "scores;events.player;participants;state;league;venue", "per_page": 50}
    )
    if not fixture_error:
        return fixture_data.get("data", []), None, "fixtures/date"
    return [], (live_error + " | Essai du calendrier du jour : " + fixture_error), None


def facebook_request(method, path, params=None):
    if not FB_PAGE_ACCESS_TOKEN:
        return None, "FB_PAGE_ACCESS_TOKEN non configuré"
    url = FB_GRAPH_URL + "/" + path.lstrip("/")
    headers = {"Authorization": "Bearer " + FB_PAGE_ACCESS_TOKEN}
    try:
        if method.upper() == "POST":
            response = requests.post(url, data=params or {}, headers=headers, timeout=20)
        else:
            response = requests.get(url, params=params or {}, headers=headers, timeout=20)
        try:
            payload = response.json()
        except Exception:
            payload = {}
        if response.status_code >= 400 or payload.get("error"):
            detail = _safe_api_message(response, FB_PAGE_ACCESS_TOKEN)
            return None, "Facebook HTTP " + str(response.status_code) + " : " + detail
        return payload, None
    except Exception as e:
        return None, "Erreur de connexion Facebook : " + str(e)[:300]


def facebook_page_info():
    payload, error = facebook_request("GET", "me", {"fields": "id,name"})
    if error:
        return None, error
    page_id = str(payload.get("id", ""))
    if not page_id:
        return None, "Facebook n'a pas retourné l'identifiant de la Page."
    return {"id": page_id, "name": payload.get("name", "Page Facebook")}, None


def facebook_publish(message):
    """Publish a text-only post to the configured Facebook Page."""
    if not FB_PAGE_ACCESS_TOKEN:
        return None, "FB_PAGE_ACCESS_TOKEN non configuré"
    # The Page ID returned by this Page token is authoritative. An old
    # FB_PAGE_ID environment value must not redirect posts to another Page.
    page, error = facebook_page_info()
    if error:
        return None, error
    page_id = page["id"]
    payload, error = facebook_request("POST", page_id + "/feed", {"message": message})
    if error:
        return None, error
    return payload.get("id"), None


def facebook_publish_photo(message, image_bytes, filename="kfscore-match.png"):
    """Publish a generated match visual and caption to the Page."""
    if not FB_PAGE_ACCESS_TOKEN:
        return None, "FB_PAGE_ACCESS_TOKEN non configuré"
    # Use the Page actually associated with the current token, not a stale
    # FB_PAGE_ID left in Render from a previous token/Page selection.
    page, error = facebook_page_info()
    if error:
        return None, error
    page_id = page["id"]
    url = FB_GRAPH_URL + "/" + page_id + "/photos"
    try:
        response = requests.post(
            url,
            headers={"Authorization": "Bearer " + FB_PAGE_ACCESS_TOKEN},
            data={"caption": message},
            files={"source": (filename, image_bytes, "image/jpeg" if filename.lower().endswith((".jpg", ".jpeg")) else "image/png")},
            timeout=45
        )
        try:
            payload = response.json()
        except Exception:
            payload = {}
        if response.status_code >= 400 or payload.get("error"):
            return None, "Facebook photo HTTP " + str(response.status_code) + " : " + _safe_api_message(response, FB_PAGE_ACCESS_TOKEN)
        return payload.get("post_id") or payload.get("id"), None
    except Exception as e:
        return None, "Erreur publication image Facebook : " + str(e)[:300]

def automation_db_path():
    configured = os.getenv("KF_SCORE_DB_PATH", "").strip()
    if configured:
        return configured
    if os.path.isdir("/var/data"):
        return "/var/data/kfscore_automation.sqlite3"
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "kfscore_automation.sqlite3")


def init_automation_db():
    path = automation_db_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with sqlite3.connect(path, timeout=20) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS published_events (event_key TEXT PRIMARY KEY, post_id TEXT, created_at TEXT NOT NULL)")
        conn.commit()


def publish_once(event_key, message):
    """Publish an event once; a unique SQLite key prevents duplicate posts."""
    init_automation_db()
    path = automation_db_path()
    with sqlite3.connect(path, timeout=20) as conn:
        row = conn.execute("SELECT post_id FROM published_events WHERE event_key = ?", (event_key,)).fetchone()
        if row:
            return {"published": False, "reason": "already_published", "post_id": row[0]}
        try:
            conn.execute("INSERT INTO published_events(event_key, post_id, created_at) VALUES (?, ?, ?)",
                         (event_key, "PENDING", datetime.utcnow().isoformat()))
            conn.commit()
        except sqlite3.IntegrityError:
            return {"published": False, "reason": "already_claimed"}

    post_id, error = facebook_publish(message)
    with sqlite3.connect(path, timeout=20) as conn:
        if error:
            conn.execute("DELETE FROM published_events WHERE event_key = ? AND post_id = 'PENDING'", (event_key,))
            conn.commit()
            return {"published": False, "error": error}
        conn.execute("UPDATE published_events SET post_id = ? WHERE event_key = ?", (post_id or "OK", event_key))
        conn.commit()
    return {"published": True, "post_id": post_id}


def _nested_name(value, fallback=""):
    if isinstance(value, dict):
        return str(value.get("name") or value.get("common_name") or value.get("short_code") or fallback)
    if isinstance(value, str):
        return value
    return fallback


# Emojis de clubs : liste extensible, sans modifier les noms officiels.
CLUB_EMOJI = {
    "manchester united": "👹", "chelsea": "🧿", "real madrid": "⚪",
    "tottenham": "🐔", "tottenham hotspur": "🐔", "liverpool": "🔴",
    "arsenal": "🔴", "barcelona": "🔵🔴", "manchester city": "🔵",
    "bayern munich": "🔴", "borussia dortmund": "🟡⚫", "dortmund": "🟡⚫",
    "juventus": "⚫⚪", "inter": "🔵⚫", "ac milan": "🔴⚫",
    "paris saint-germain": "🔵🔴", "psg": "🔵🔴", "atletico madrid": "🔴⚪"
}

COUNTRY_FLAGS = {
    "guinea": "🇬🇳", "argentina": "🇦🇷", "hungary": "🇭🇺", "spain": "🇪🇸",
    "france": "🇫🇷", "england": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "germany": "🇩🇪", "brazil": "🇧🇷",
    "portugal": "🇵🇹", "senegal": "🇸🇳", "cameroon": "🇨🇲", "nigeria": "🇳🇬",
    "ivory coast": "🇨🇮", "côte d'ivoire": "🇨🇮", "morocco": "🇲🇦", "netherlands": "🇳🇱",
    "italy": "🇮🇹", "uruguay": "🇺🇾", "belgium": "🇧🇪", "norway": "🇳🇴"
}


# Noms français normalisés pour les publications Facebook.
TEAM_NAMES_FR = {
    "fc barcelona": "FC BARCELONE", "barcelona": "FC BARCELONE",
    "atletico madrid": "ATLÉTICO DE MADRID", "atlético madrid": "ATLÉTICO DE MADRID",
    "real madrid": "REAL MADRID", "bayern munich": "BAYERN MUNICH",
    "borussia dortmund": "BORUSSIA DORTMUND", "manchester united": "MANCHESTER UNITED",
    "manchester city": "MANCHESTER CITY", "tottenham hotspur": "TOTTENHAM",
    "paris saint-germain": "PARIS SAINT-GERMAIN", "psg": "PARIS SAINT-GERMAIN",
    "inter milan": "INTER MILAN", "internazionale": "INTER MILAN", "inter": "INTER MILAN",
    "ac milan": "AC MILAN", "juventus": "JUVENTUS", "liverpool": "LIVERPOOL",
    "chelsea": "CHELSEA", "arsenal": "ARSENAL", "newcastle united": "NEWCASTLE UNITED",
    "aston villa": "ASTON VILLA", "west ham united": "WEST HAM", "nottingham forest": "NOTTINGHAM FOREST",
    "eintracht frankfurt": "EINTRACHT FRANCFORT", "bayer 04 leverkusen": "BAYER LEVERKUSEN",
    "paris fc": "PARIS FC", "olympique de marseille": "OLYMPIQUE DE MARSEILLE",
    "olympique lyonnais": "OLYMPIQUE LYONNAIS", "as monaco": "AS MONACO",
    "lille osc": "LOSC LILLE", "rc lens": "RC LENS", "ajax amsterdam": "AJAX AMSTERDAM",
    "sporting clube de portugal": "SPORTING CP", "al hilal": "AL-HILAL",
    "al nassr": "AL-NASSR", "inter miami": "INTER MIAMI"
}

# Drapeaux des clubs utilisés notamment en Ligue des champions.
CLUB_COUNTRY_FLAGS = {
    "fc barcelona": "🇪🇸", "barcelona": "🇪🇸", "real madrid": "🇪🇸",
    "atletico madrid": "🇪🇸", "atlético madrid": "🇪🇸", "sevilla": "🇪🇸",
    "bayern munich": "🇩🇪", "borussia dortmund": "🇩🇪", "bayer leverkusen": "🇩🇪",
    "rb leipzig": "🇩🇪", "liverpool": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "manchester united": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "manchester city": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "arsenal": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "chelsea": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "tottenham": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "tottenham hotspur": "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f",
    "paris saint-germain": "🇫🇷", "psg": "🇫🇷", "marseille": "🇫🇷",
    "inter": "🇮🇹", "inter milan": "🇮🇹", "internazionale": "🇮🇹",
    "ac milan": "🇮🇹", "juventus": "🇮🇹", "napoli": "🇮🇹", "roma": "🇮🇹",
    "ajax": "🇳🇱", "psv": "🇳🇱", "feyenoord": "🇳🇱",
    "benfica": "🇵🇹", "porto": "🇵🇹", "sporting cp": "🇵🇹",
    "galatasaray": "🇹🇷", "fenerbahce": "🇹🇷", "celtic": "🏴\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
}

COMPETITION_NAMES_FR = {
    "uefa champions league": "Ligue des champions",
    "champions league": "Ligue des champions",
    "uefa europa league": "Ligue Europa",
    "europa league": "Ligue Europa",
    "uefa conference league": "Ligue Conférence",
    "conference league": "Ligue Conférence",
    "premier league": "Premier League", "bundesliga": "Bundesliga",
    "serie a": "Serie A", "la liga": "Liga", "laliga": "Liga",
    "ligue 1": "Ligue 1", "eredivisie": "Eredivisie",
    "saudi pro league": "Championnat d'Arabie saoudite",
    "major league soccer": "Championnat des États-Unis", "mls": "Championnat des États-Unis"
}


def _french_team_name(name):
    raw = str(name or "Équipe").strip()
    return TEAM_NAMES_FR.get(raw.lower(), raw.upper())


def _is_champions_league(competition):
    name = str(competition or "").lower()
    return "champions league" in name or "uefa champions" in name or "ligue des champions" in name


def _club_label(name, competition=None, side="home"):
    raw = str(name or "Équipe").strip()
    team_name = _french_team_name(raw)
    if _is_champions_league(competition):
        # Respect strict KF SCORE placement: home flag before the club,
        # away flag after the club name.
        flag = CLUB_COUNTRY_FLAGS.get(raw.lower(), "⚽")
        return (flag + " " + team_name) if side == "home" else (team_name + " " + flag)
    emoji = CLUB_EMOJI.get(raw.lower(), "⚽")
    return emoji + " " + team_name


def _fixture_teams(fixture):
    participants = fixture.get("participants") or []
    home = away = ""
    for item in participants:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("short_code") or "Équipe")
        meta = item.get("meta") or {}
        location = str(meta.get("location") or item.get("location") or "").lower()
        if location == "home":
            home = name
        elif location == "away":
            away = name
    if home and away:
        return home, away
    names = [str(x.get("name") or x.get("short_code") or "Équipe") for x in participants if isinstance(x, dict)]
    if len(names) >= 2:
        return names[0], names[1]
    name = str(fixture.get("name") or "Match")
    if " vs " in name:
        return tuple(name.split(" vs ", 1))
    return name, ""


def _fixture_scores(fixture):
    """Return current home/away score, preferring Sportmonks CURRENT score rows."""
    participants = fixture.get("participants") or []
    home_id = away_id = None
    for team in participants:
        if not isinstance(team, dict):
            continue
        loc = str((team.get("meta") or {}).get("location") or team.get("location") or "").lower()
        if loc == "home": home_id = team.get("id")
        if loc == "away": away_id = team.get("id")
    scores = fixture.get("scores") or []
    chosen = {}
    for row in scores:
        if not isinstance(row, dict):
            continue
        desc = str(row.get("description") or "").upper()
        if desc and desc not in ("CURRENT", "2ND_HALF", "1ST_HALF", "FT", "FULLTIME"):
            continue
        participant_id = row.get("participant_id")
        value = row.get("score")
        if isinstance(value, dict): value = value.get("goals")
        if value is None: continue
        if participant_id == home_id: chosen["home"] = value
        elif participant_id == away_id: chosen["away"] = value
    if "home" in chosen and "away" in chosen:
        return str(chosen["home"]), str(chosen["away"])
    vals = []
    for row in scores:
        if isinstance(row, dict):
            value = row.get("score")
            if isinstance(value, dict): value = value.get("goals")
            if value is not None: vals.append(str(value))
    return (vals[0], vals[1]) if len(vals) >= 2 else ("0", "0")


def _minute(event):
    value = event.get("minute") or event.get("time") or event.get("fixture_period") or ""
    if isinstance(value, dict):
        value = value.get("minute") or value.get("elapsed") or ""
    extra = event.get("extra_minute") or event.get("added_time")
    return str(value) + ("+" + str(extra) if extra else "")


def _event_kind(event):
    kind = _nested_name(event.get("type") or event.get("type_name") or event.get("type_id") or event.get("event_type"), "")
    detail = " ".join(str(event.get(k) or "") for k in ("name", "addition", "info", "description", "result"))
    text = (kind + " " + detail).lower()
    if any(x in text for x in ("red card", "redcard", "carton rouge", "second yellow", "2nd yellow")):
        return "red"
    if any(x in text for x in ("goal", "own goal", "penalty scored", "but")):
        return "goal"
    if any(x in text for x in ("yellow card", "yellowcard", "carton jaune")):
        return "yellow"
    return None


def _player_name(event):
    player = event.get("player") or event.get("player_name") or event.get("player_name_en") or ""
    return _nested_name(player, str(player))


def _player_flag(event):
    player = event.get("player") if isinstance(event.get("player"), dict) else {}
    nationality = str(player.get("nationality") or event.get("nationality") or "").lower()
    return COUNTRY_FLAGS.get(nationality, "")


def _competition_name(fixture):
    league = fixture.get("league") or fixture.get("competition") or {}
    return _nested_name(league, str(fixture.get("league_name") or "Football"))


def _competition_name_fr(fixture):
    raw = _competition_name(fixture)
    return COMPETITION_NAMES_FR.get(raw.lower(), raw)


def _competition_hashtag(competition):
    name = str(competition or "").lower()
    mapping = (
        (("champions league", "uefa champions"), "#UCL"),
        (("europa league",), "#UEL"),
        (("conference league",), "#UECL"),
        (("premier league",), "#PremierLeague"),
        (("bundesliga",), "#Bundesliga"),
        (("serie a",), "#SerieA"),
        (("la liga", "laliga"), "#LaLiga"),
        (("ligue 1", "ligue1"), "#Ligue1"),
        (("eredivisie",), "#Eredivisie"),
        (("saudi pro",), "#SaudiProLeague"),
        (("mls", "major league soccer"), "#MLS"),
    )
    for needles, tag in mapping:
        if any(item in name for item in needles):
            return tag
    return "#Football"


def _format_scorers(events):
    lines = []
    for event in sorted(events, key=lambda e: (int(_minute(e).split("+")[0]) if _minute(e).split("+")[0].isdigit() else 999, str(e.get("id") or ""))):
        if _event_kind(event) != "goal":
            continue
        player = _player_name(event)
        if not player:
            continue
        minute = _minute(event)
        flag = _player_flag(event)
        lines.append((flag + " " if flag else "") + player + (" " + minute + "'" if minute else ""))
    return lines


def _image_url_from(value):
    """Find an image URL only in explicitly supplied media/image fields."""
    if isinstance(value, dict):
        for key in ("match_action_image", "action_image", "match_image", "image_path", "photo_url", "image_url", "image", "photo", "picture"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.startswith(("https://", "http://")):
                return candidate
            if isinstance(candidate, dict):
                found = _image_url_from(candidate)
                if found:
                    return found
        # Search nested media containers, but never player/profile objects.
        for key in ("media", "images", "gallery", "venue", "stadium"):
            if key in value:
                found = _image_url_from(value[key])
                if found:
                    return found
    elif isinstance(value, list):
        for child in value:
            found = _image_url_from(child)
            if found:
                return found
    return None


def _download_photo(url):
    """Download a real provider-supplied photograph; reject non-image responses."""
    if not url:
        return None
    try:
        from io import BytesIO
        from PIL import Image
        response = requests.get(url, timeout=12, headers={"User-Agent": "KFScore/1.0"})
        response.raise_for_status()
        if len(response.content) > 8 * 1024 * 1024:
            return None
        photo = Image.open(BytesIO(response.content)).convert("RGB")
        photo.thumbnail((1800, 2200))
        return photo
    except Exception:
        return None


def _match_action_photo_url(fixture, events):
    """Only accept explicit match/media images, never a player's portrait."""
    for event in events or []:
        # Event objects may expose editorial/action media. Do not inspect event['player'].
        for key in ("media", "images", "match_action_image", "action_image", "match_image"):
            url = _image_url_from(event.get(key)) if isinstance(event, dict) else None
            if url:
                return url
    return None


def _stadium_photo_url(fixture):
    """Use a real venue/stadium image as the fallback when the provider supplies one."""
    venue = fixture.get("venue") or fixture.get("stadium") or {}
    return _image_url_from(venue)


def _make_match_image(home, away, score_home, score_away, competition, phase, fixture, events=None):
    """Create the fixed KF SCORE match card. No player/stadium photographs are used."""
    from io import BytesIO
    from PIL import Image, ImageDraw, ImageFont

    width, height = 1080, 1350
    img = Image.new("RGB", (width, height), (8, 11, 18))
    draw = ImageDraw.Draw(img, "RGBA")

    # Fixed background: deliberately identical for every KF SCORE publication.
    draw.rectangle((0, 0, width, height), fill=(8, 11, 18, 255))
    draw.ellipse((-260, 300, 1340, 1900), fill=(18, 24, 38, 180))
    draw.ellipse((180, 470, 900, 1190), outline=(255, 255, 255, 20), width=3)
    draw.line((0, 830, width, 830), fill=(255, 255, 255, 16), width=2)
    draw.line((width // 2, 470, width // 2, 1190), fill=(255, 255, 255, 12), width=2)

    # Fixed top branding and status.
    try:
        font_brand = ImageFont.truetype("DejaVuSans-Bold.ttf", 58)
        font_status = ImageFont.truetype("DejaVuSans-Bold.ttf", 42)
        font_comp = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
        font_team = ImageFont.truetype("DejaVuSans-Bold.ttf", 34)
        font_score = ImageFont.truetype("DejaVuSans-Bold.ttf", 122)
        font_scorer = ImageFont.truetype("DejaVuSans-Bold.ttf", 25)
        font_tag = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
    except Exception:
        font_brand = font_status = font_comp = font_team = font_score = font_scorer = font_tag = ImageFont.load_default()

    draw.rounded_rectangle((38, 30, 365, 108), radius=18, fill=(20, 25, 36, 245), outline=(255, 255, 255, 35), width=2)
    draw.text((62, 43), "KF SCORE", font=font_brand, fill=(255, 255, 255, 255))

    phase_label = "MI-TEMPS" if str(phase).lower() in ("mi-temps", "halftime", "half time") else "TERMINÉ"
    b = draw.textbbox((0, 0), phase_label, font=font_status)
    draw.text(((width - (b[2] - b[0])) / 2, 150), phase_label, font=font_status, fill=(255, 255, 255, 255))

    comp = COMPETITION_NAMES_FR.get(str(competition or "").lower(), str(competition or "Football"))
    b = draw.textbbox((0, 0), comp, font=font_comp)
    draw.text(((width - (b[2] - b[0])) / 2, 220), comp, font=font_comp, fill=(190, 198, 210, 255))

    # Fixed score panel with one horizontal team/score line.
    panel = (35, 340, width - 35, 900)
    draw.rounded_rectangle(panel, radius=30, fill=(13, 17, 27, 245), outline=(255, 255, 255, 35), width=2)

    def centered(text, cx, y, font, fill):
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((cx - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)

    # Exact requested order: home flag/symbol before its name, then score,
    # then away name followed by its flag/symbol.
    home_label = _club_label(home, competition)
    away_label = _club_label(away, competition, "away")
    font_team_line = ImageFont.truetype("DejaVuSans-Bold.ttf", 27)
    centered(home_label[:30], 255, 520, font_team_line, (255, 255, 255, 255))
    centered(str(score_home) + " - " + str(score_away), width // 2, 455, font_score, (255, 255, 255, 255))
    centered(away_label[:30], 825, 520, font_team_line, (255, 255, 255, 255))

    # Scorers are fixed in the same area; only their data changes.
    scorer_lines = _format_scorers(events or [])
    if scorer_lines:
        draw.line((130, 735, width - 130, 735), fill=(255, 255, 255, 18), width=2)
        max_lines = 5 if phase_label == "TERMINÉ" else 4
        shown = scorer_lines[:max_lines]
        for i, line in enumerate(shown):
            center_text(line[:70], width // 2, 755 + i * 35, font_scorer, (225, 230, 238, 255))

    # Fixed footer.
    draw.rounded_rectangle((55, 1010, width - 55, 1235), radius=24, fill=(12, 16, 25, 245), outline=(255, 255, 255, 28), width=2)
    center_text("KF SCORE", width // 2, 1050, font_brand, (255, 255, 255, 255))
    center_text(comp, width // 2, 1125, font_comp, (190, 198, 210, 255))
    center_text("#KFScore", width // 2, 1180, font_tag, (225, 230, 238, 255))

    out = BytesIO()
    img.save(out, format="JPEG", quality=92, optimize=True)
    out.seek(0)
    return out.getvalue()


def _publish_match_post(key, message, fixture, home, away, score_home, score_away, phase, with_image=False):
    """Claim dedupe key, then publish either a card or a text-only post."""
    init_automation_db()
    path = automation_db_path()
    with sqlite3.connect(path, timeout=20) as conn:
        if conn.execute("SELECT 1 FROM published_events WHERE event_key = ?", (key,)).fetchone():
            return {"published": False, "reason": "already_published"}
        try:
            conn.execute("INSERT INTO published_events(event_key, post_id, created_at) VALUES (?, 'PENDING', ?)", (key, datetime.utcnow().isoformat()))
            conn.commit()
        except sqlite3.IntegrityError:
            return {"published": False, "reason": "already_claimed"}
    if with_image:
        image_bytes = _make_match_image(home, away, score_home, score_away, _competition_name(fixture), phase, fixture, fixture.get("events") or [])
        if not image_bytes:
            with sqlite3.connect(path, timeout=20) as conn:
                conn.execute("DELETE FROM published_events WHERE event_key = ? AND post_id = 'PENDING'", (key,))
                conn.commit()
            return {"published": False, "reason": "impossible de créer le visuel fixe KF SCORE"}
        post_id, error = facebook_publish_photo(message, image_bytes, "kfscore-" + str(fixture.get("id")) + "-" + phase.lower().replace(" ", "-") + ".jpg")
    else:
        post_id, error = facebook_publish(message)
    with sqlite3.connect(path, timeout=20) as conn:
        if error:
            conn.execute("DELETE FROM published_events WHERE event_key = ? AND post_id = 'PENDING'", (key,))
            conn.commit()
            return {"published": False, "error": error}
        conn.execute("UPDATE published_events SET post_id = ? WHERE event_key = ?", (post_id or "OK", key))
        conn.commit()
    return {"published": True, "post_id": post_id}


def _fixture_state(fixture):
    status = fixture.get("status") or {}
    if isinstance(status, dict):
        status = status.get("long") or status.get("short") or ""
    return _nested_name(fixture.get("state"), str(fixture.get("state_name") or status or "")).lower().replace("_", " ").strip()


def _api_football_to_internal(item, events=None):
    """Convert API-Football v3 data to the internal match format used by KF SCORE."""
    teams = item.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    league = item.get("league") or {}
    fixture_info = item.get("fixture") or {}
    home_id, away_id = home.get("id"), away.get("id")
    raw_events = []
    for ev in events or []:
        tm = ev.get("time") or {}
        player = ev.get("player") or {}
        raw_events.append({
            "id": ev.get("id") or "",
            "type": ev.get("type") or "",
            "name": ev.get("detail") or "",
            "minute": tm.get("elapsed") or "",
            "extra_minute": tm.get("extra"),
            "player": {"name": player.get("name") or ""},
            "team": ev.get("team") or {},
        })
    status = fixture_info.get("status") or {}
    return {
        "id": fixture_info.get("id"),
        "name": (home.get("name") or "Équipe") + " vs " + (away.get("name") or "Équipe"),
        "participants": [
            {"id": home_id, "name": home.get("name") or "Équipe", "meta": {"location": "home"}},
            {"id": away_id, "name": away.get("name") or "Équipe", "meta": {"location": "away"}},
        ],
        "scores": [
            {"participant_id": home_id, "description": "CURRENT", "score": {"goals": (item.get("goals") or {}).get("home") if (item.get("goals") or {}).get("home") is not None else 0}},
            {"participant_id": away_id, "description": "CURRENT", "score": {"goals": (item.get("goals") or {}).get("away") if (item.get("goals") or {}).get("away") is not None else 0}},
        ],
        "state": {"name": status.get("long") or status.get("short") or ""},
        "status": status,
        "league": {"name": league.get("name") or "Football", "country": league.get("country") or ""},
        "events": raw_events,
        "_provider": "api-football",
    }


def api_football_live_or_today():
    """Fetch today's full fixture list, merge live fixtures, then load events for started matches."""
    if not API_KEY:
        return [], "API_FOOTBALL_KEY non configuré", None

    # Use the competition-local date rather than the server's UTC date.
    try:
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo("Africa/Douala")).strftime("%Y-%m-%d")
    except Exception:
        today = datetime.utcnow().strftime("%Y-%m-%d")

    day_data, day_error = api_get("fixtures", {"date": today, "timezone": "Africa/Douala"})
    if day_error:
        return [], day_error, None
    by_id = {}
    for item in (day_data.get("response") or []):
        fixture_id = (item.get("fixture") or {}).get("id")
        if fixture_id:
            by_id[str(fixture_id)] = item

    # Merge the live feed so matches crossing the local date boundary are not lost.
    live_data, live_error = api_get("fixtures", {"live": "all", "timezone": "Africa/Douala"})
    if not live_error:
        for item in (live_data.get("response") or []):
            fixture_id = (item.get("fixture") or {}).get("id")
            if fixture_id:
                by_id[str(fixture_id)] = item

    items = list(by_id.values())
    source = "fixtures?date=" + today + "+live=all"
    normalized = []
    # Keep the number of event requests bounded; provider quotas depend on the API plan.
    for item in items[:50]:
        status = ((item.get("fixture") or {}).get("status") or {}).get("short", "")
        events = []
        if status not in ("NS", "TBD", "PST", "CANC", "ABD", "AWD", "WO"):
            fixture_id = (item.get("fixture") or {}).get("id")
            if fixture_id:
                event_data, event_error = api_get("fixtures/events", {"fixture": fixture_id})
                if event_data:
                    events = event_data.get("response") or []
        normalized.append(_api_football_to_internal(item, events))
    return normalized, None, source


def _match_has_started(fixture):
    """Recognize API-Football live states; used to publish one kickoff notice per match."""
    status = fixture.get("status") or {}
    short = str(status.get("short") or "").upper() if isinstance(status, dict) else ""
    state = _fixture_state(fixture)
    active_codes = {"1H", "2H", "HT", "ET", "BT", "P", "LIVE"}
    active_names = ("first half", "second half", "half time", "halftime", "extra time",
                    "break time", "penalty", "in play", "live")
    return short in active_codes or any(name in state for name in active_names)


def run_automation_once():
    """One polling cycle. Configure as a Render Cron Job for scheduled polling."""
    if not FB_PAGE_ACCESS_TOKEN:
        return {"ok": False, "error": "FB_PAGE_ACCESS_TOKEN non configuré"}
    page, fb_error = facebook_page_info()
    if fb_error:
        return {"ok": False, "error": "Vérification Facebook impossible : " + fb_error}
    # API-Football is the primary feed. Sportmonks is retained as a fallback;
    # a Sportmonks 403 is a subscription restriction, not something code can bypass.
    fixtures, api_error, source = api_football_live_or_today()
    provider_errors = []
    if api_error:
        provider_errors.append("API-Football : " + api_error)
    if api_error or not fixtures:
        sm_fixtures, sm_error, sm_source = sportmonks_live_or_fixtures()
        if sm_error:
            provider_errors.append("Sportmonks : " + sm_error)
        elif sm_fixtures:
            fixtures, source = sm_fixtures, sm_source
        elif not fixtures:
            fixtures = []
    if not fixtures and provider_errors:
        return {"ok": False, "facebook_page": page.get("name"), "provider_errors": provider_errors}
    if not fixtures:
        return {"ok": True, "facebook_page": page.get("name"), "source": source,
                "fixtures_checked": 0, "published_count": 0, "skipped_or_duplicate_count": 0,
                "provider_errors": provider_errors, "message": "Aucun match à traiter pour le moment."}

    published, skipped, errors = [], 0, []
    for fixture in fixtures:
        if not isinstance(fixture, dict):
            continue
        fixture_id = str(fixture.get("id") or "")
        if not fixture_id:
            continue
        home, away = _fixture_teams(fixture)
        score_home, score_away = _fixture_scores(fixture)
        events = fixture.get("events") or []
        competition = _competition_name(fixture)
        state = _fixture_state(fixture)

        # Kickoff notice: one text-only post when the provider first reports the match as started.
        if _match_has_started(fixture):
            kickoff_key = fixture.get("_provider", "sportmonks") + ":kickoff:" + fixture_id
            kickoff_message = ("🚨 𝗖’𝗘𝗦𝗧 𝗣𝗔𝗥𝗧𝗜 ! ⚽\n\n" +
                               _club_label(home, competition) + " - " +
                               _club_label(away, competition, "away") + "\n\n" +
                               "🏆 " + _competition_name_fr(fixture) + "\n\n" +
                               _competition_hashtag(competition) + " #KFScore")
            kickoff_result = _publish_match_post(kickoff_key, kickoff_message, fixture,
                                                   home, away, score_home, score_away,
                                                   "Coup d’envoi", with_image=False)
            if kickoff_result.get("published"):
                published.append(kickoff_result)
            elif kickoff_result.get("error"):
                errors.append(kickoff_result["error"])
            else:
                skipped += 1

        # Only goals and red cards are published live. Yellow cards are intentionally ignored.
        for event in events:
            if not isinstance(event, dict):
                continue
            kind = _event_kind(event)
            if kind not in ("goal", "red"):
                continue
            player = _player_name(event) or "Joueur"
            flag = _player_flag(event)
            teams_line = _club_label(home, competition) + " " + score_home + "-" + score_away + " " + _club_label(away, competition, "away")
            if kind == "goal":
                headline = "🚨 BUUUUT DE " + player.upper() + ((" " + flag) if flag else "")
                key_type = "goal"
            else:
                headline = "🟥 CARTON ROUGE DE " + player.upper() + ((" " + flag) if flag else "")
                key_type = "red"
            message = headline + "\n\n" + teams_line + "\n\n" + _competition_hashtag(competition) + " #KFScore"
            event_id = str(event.get("id") or hashlib.sha256((key_type + "|" + _minute(event) + "|" + player).encode("utf-8")).hexdigest()[:24])
            provider = fixture.get("_provider", "sportmonks")
            result = _publish_match_post(provider + ":" + key_type + ":" + fixture_id + ":" + event_id,
                                         message, fixture, home, away, score_home, score_away,
                                         key_type, with_image=False)
            if result.get("published"): published.append(result)
            elif result.get("error"): errors.append(result["error"])
            else: skipped += 1

        # Halftime post: API-Football supplies both a short code (HT) and
        # a long label (Halftime). Check both because _fixture_state prefers
        # the long label and providers do not use identical wording.
        status_short = str((fixture.get("status") or {}).get("short") or "").upper()
        state_norm = state.replace("-", " ").strip()
        if status_short == "HT" or state_norm in ("half time", "halftime", "ht", "break", "break time"):
            key = fixture.get("_provider", "sportmonks") + ":halftime:" + fixture_id
            scorers = _format_scorers(events)
            message = "🚨 𝗠𝗜-𝗧𝗘𝗠𝗣𝗦 ⏱️\n\n" + _club_label(home, competition) + " " + score_home + "-" + score_away + " " + _club_label(away, competition, "away")
            message += "\n\n🏆 " + _competition_name_fr(fixture)
            if scorers:
                message += "\n\n⚽ 𝗕𝗨𝗧𝗘𝗨𝗥𝗦\n" + "\n".join(scorers)
            message += "\n\n" + _competition_hashtag(competition) + " #KFScore"
            result = _publish_match_post(key, message, fixture, home, away, score_home, score_away, "Mi-temps", with_image=True)
            if result.get("published"): published.append(result)
            elif result.get("error"): errors.append(result["error"])
            else: skipped += 1

        # Full-time post: API-Football's long status is usually "Match Finished"
        # while its short status is "FT". Accept both, plus Sportmonks labels.
        # This was the reason FT posts could be silently skipped.
        if status_short in ("FT", "AET", "PEN") or state_norm in (
            "ft", "aet", "pen", "full time", "fulltime", "finished",
            "match finished", "after extra time", "after penalties"
        ):
            key = fixture.get("_provider", "sportmonks") + ":fulltime:" + fixture_id
            scorers = _format_scorers(events)
            message = "🚨 𝗧𝗘𝗥𝗠𝗜𝗡É ⏱️\n\n" + _club_label(home, competition) + " " + score_home + "-" + score_away + " " + _club_label(away, competition, "away")
            message += "\n\n🏆 " + _competition_name_fr(fixture)
            if scorers:
                message += "\n\n⚽ 𝗕𝗨𝗧𝗘𝗨𝗥𝗦\n" + "\n".join(scorers)
            message += "\n\n" + _competition_hashtag(competition) + " #KFScore"
            result = _publish_match_post(key, message, fixture, home, away, score_home, score_away, "Terminé", with_image=True)
            if result.get("published"): published.append(result)
            elif result.get("error"): errors.append(result["error"])
            else: skipped += 1

    return {"ok": True, "facebook_page": page.get("name"), "source": source,
            "fixtures_checked": len(fixtures), "published_count": len(published),
            "skipped_or_duplicate_count": skipped, "errors": errors[:10],
            "provider_errors": provider_errors}

def api_get(endpoint, params):
    try:
        r = requests.get(
            API_URL + "/" + endpoint,
            headers=HEADERS,
            params=params,
            timeout=20
        )

        try:
            data = r.json()
        except Exception:
            data = {}

        if r.status_code != 200:
            detail = _safe_api_message(r, API_KEY)
            return None, "API-Football HTTP " + str(r.status_code) + " : " + detail
        api_errors = data.get("errors") if isinstance(data, dict) else None
        if api_errors:
            return None, "API-Football : " + str(api_errors)[:500]
        return data, None

    except Exception as e:
        return None, "Erreur : " + str(e)


@app.route("/")
def home():
    return render_template_string(HTML)

@app.route("/api/matches")
def matches():

    date = request.args.get("date")

    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    data, error = api_get(
        "fixtures",
        {
            "date": date,
            "timezone": "Africa/Douala"
        }
    )

    if error:
        return jsonify({
            "error": error
        }), 500

    return jsonify({
        "date_demandee": date,
        "nombre_matchs": len(data.get("response", [])),
        "api_results": data.get("results"),
        "api_errors": data.get("errors"),
        "response": data.get("response", [])
    })
    
@app.route("/api/sportmonks/live")
def sportmonks_live():
    fixtures, error, source = sportmonks_live_or_fixtures()
    if error:
        return jsonify({"provider": "sportmonks", "error": error}), 502
    return jsonify({"provider": "sportmonks", "source": source, "response": fixtures})


@app.route("/api/facebook/status")
def facebook_status():
    page, error = facebook_page_info()
    if error:
        return jsonify({"connected": False, "error": error}), 502
    return jsonify({"connected": True, "page": page, "publishing_permission": "test requis"})


@app.route("/api/automation/run", methods=["POST"])
def automation_run_route():
    expected = os.getenv("KF_AUTOMATION_SECRET", "").strip()
    supplied = request.headers.get("X-Automation-Secret", "").strip()
    if not expected or supplied != expected:
        return jsonify({"ok": False, "error": "Accès non autorisé"}), 403
    try:
        result = run_automation_once()
        if not isinstance(result, dict):
            result = {"ok": False, "error": "Résultat inattendu du traitement automatique."}
        return jsonify(result), (200 if result.get("ok") else 502)
    except Exception as exc:
        # Return a useful diagnostic to the caller; never expose environment secrets.
        app.logger.exception("Échec inattendu de l'automatisation KF SCORE")
        return jsonify({"ok": False, "error": "Erreur interne pendant l'automatisation : " + str(exc)[:300]}), 500


@app.route("/api/sportmonks/fixtures/<date>")
def sportmonks_fixtures(date):

    data, error = sportmonks_get(
        "fixtures/date/" + date,
        {"include": "participants;scores;state;league"}
    )

    if error:
        return jsonify({"error": error}), 500

    return jsonify({
        "provider": "sportmonks",
        "date": date,
        "response": data.get("data", [])
    })


@app.route("/api/sportmonks/fixture/<int:fixture_id>")
def sportmonks_fixture(fixture_id):

    data, error = sportmonks_get(
        "fixtures/" + str(fixture_id),
        {
            "include": "participants;scores;state;league;events.player;lineups;statistics"
        }
    )

    if error:
        return jsonify({"error": error}), 500

    return jsonify({
        "provider": "sportmonks",
        "fixture": data.get("data")
    })


@app.route("/api/live")
def live():

    data, error = api_get(
        "fixtures",
        {"live": "all"}
    )

    if error:
        return jsonify({
            "error": error
        }), 500

    return jsonify({
        "response": data.get("response", [])
    })
@app.route("/api/match/<int:match_id>")
def get_match_detail(match_id):

    data, error = api_get(
        "fixtures",
        {"id": match_id}
    )

    if error:
        return jsonify({
            "error": error
        }), 500

    matches = data.get("response", [])

    if not matches:
        return jsonify({
            "error": "Match introuvable"
        }), 404

    fixture = matches[0]

    events_data, events_error = api_get(
        "fixtures/events",
        {"fixture": match_id}
    )

    events = []

    if events_data:
        events = events_data.get("response", [])

    stats_data, stats_error = api_get(
        "fixtures/statistics",
        {"fixture": match_id}
    )

    statistics = []

    if stats_data:
        statistics = stats_data.get("response", [])

    # COMPOSITIONS
    lineups_data, lineups_error = api_get(
        "fixtures/lineups",
        {"fixture": match_id}
    )

    lineups = []

    if lineups_data:
        lineups = lineups_data.get("response", [])
    
    # CLASSEMENT
    standings = []

    league_id = fixture["league"]["id"]
    season = fixture["league"]["season"]

    standings_data, standings_error = api_get(
        "standings",
        {
            "league": league_id,
            "season": season
        }
    )

    if standings_data:
        standings = standings_data.get("response", [])
        
    return jsonify({
        "fixture": fixture,
        "events": events,
        "events_error": events_error,
        "statistics": statistics,
        "statistics_error": stats_error,
        "lineups": lineups,
        "lineups_error": lineups_error,
        "standings": standings,
        "standings_error": standings_error
    })
    
HTML = r"""
<!doctype html>

<html lang="fr">

<head>

<meta charset="utf-8">

<meta name="viewport"
      content="width=device-width,initial-scale=1">

<style>

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f2f3f5;
    color: #111;
}

header {
    background: #111827;
    color: white;
    text-align: center;
    padding: 16px;
    font-size: 24px;
    font-weight: bold;
}

nav {
    display: flex;
    background: white;
}

nav button {
    flex: 1;
    padding: 14px;
    border: 0;
    background: white;
    font-weight: bold;
}

nav button.active {
    color: #2563eb;
    border-bottom: 3px solid #2563eb;
}

main {
    max-width: 900px;
    margin: auto;
    padding: 12px;
    box-sizing: border-box;
}

@media (max-width: 600px) {
    main:has(.match-detail-page) {
        max-width: none;
        width: 100%;
        padding: 0;
        margin: 0;
    }
}

.tools {
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
}

.date-display {
    flex: 1;
    padding: 10px;
    border: 1px solid #ccc;
    border-radius: 8px;
    background: white;
    font-weight: bold;
    text-align: center;
    font-size: 14px;
}

.tools > * {
    padding: 10px;
    border: 1px solid #ccc;
    border-radius: 8px;
    background: white;
}

.tools input {
    flex: 1;
}

.league {
    background: white;
    margin: 10px 0;
    border-radius: 10px;
    overflow: hidden;
}

.league h3 {
    margin: 0;
    padding: 10px;
    background: #e5e7eb;
    font-size: 15px;
}

.league-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    background: #e5e7eb;
}

.league-logo {
    width: 32px;
    height: 32px;
    object-fit: contain;
}

.league-flag {
    font-size: 22px;
}

.league-info {
    display: flex;
    flex-direction: column;
}

.league-name {
    font-weight: bold;
    font-size: 15px;
}

.league-country {
    font-size: 12px;
    color: #666;
}

.match {
    display: grid;
    grid-template-columns: 55px minmax(0, 1fr) 35px;
    grid-template-rows: 1fr 1fr;
    align-items: center;
    min-height: 64px;
    padding: 8px 10px;
    border-top: 1px solid #eee;
    cursor: pointer;
    background: white;
}

.match-time {
    grid-column: 1;
    grid-row: 1 / 3;
    align-self: stretch;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    font-size: 11px;
    color: #666;
    font-weight: bold;
}

.match-time .second-status {
    margin-top: 8px;
}

.match-teams {
    grid-column: 2;
    grid-row: 1 / 3;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 7px;
}

.team-row {
    display: flex;
    align-items: center;
    min-width: 0;
    gap: 7px;
}

.team-row img {
    width: 24px;
    height: 24px;
    object-fit: contain;
    flex-shrink: 0;
}

.team-name {
    font-size: 13px;
    line-height: 18px;
    white-space: normal;
    overflow: visible;
    text-overflow: clip;
    min-width: 0;
}

.match-scores {
    grid-column: 3;
    grid-row: 1 / 3;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 7px;
    font-size: 14px;
    font-weight: bold;
}

.team-score {
    height: 24px;
    display: flex;
    align-items: center;
}

.match-time-main {
    font-size: 11px;
    font-weight: bold;
    color: #444;
}

.match-status {
    font-size: 11px;
    font-weight: bold;
    color: #666;
}

.match-status.live {
    color: #e11d48;
}

.match-score-live {
    color: #e11d48;
}

.box {
    text-align: center;
    padding: 25px;
}

.error {
    color: #b91c1c;
    text-align: center;
    padding: 20px;
}

.back {
    padding: 10px 14px;
    background: #111827;
    color: white;
    border: 0;
    border-radius: 8px;
    margin-bottom: 10px;
}

.detail {
    background: white;
    border-radius: 12px;
    padding: 18px;
    text-align: center;
}

.teams {
    display: flex;
    justify-content: space-around;
    align-items: center;
}

.teams img {
    width: 65px;
    height: 65px;
    object-fit: contain;
}

.big {
    font-size: 30px;
    font-weight: bold;
}

.event {
    background: white;
    margin-top: 8px;
    padding: 10px;
    border-radius: 8px;
}

.top-header {
    height: 65px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #111;
    border-bottom: 2px solid #222;
}

.brand {
    display: flex;
    align-items: center;
    gap: 8px;
}

.ball {
    font-size: 25px;
}

.brand-name {
    font-size: 24px;
    font-weight: 900;
    letter-spacing: 1px;
}

/* ONGLET DE LA PAGE DÉTAIL DU MATCH */

.match-tabs {
    display: flex;
    gap: 8px;
    width: 100%;
    overflow-x: auto;
    overflow-y: hidden;
    white-space: nowrap;
    padding: 10px 4px;
    margin-top: 18px;
    border-bottom: 1px solid rgba(255,255,255,0.08);

    scroll-behavior: smooth;
    -webkit-overflow-scrolling: touch;

    scrollbar-width: none;
}

.match-tabs::-webkit-scrollbar {
    display: none;
}

.match-tab {
    flex: 0 0 auto;
    border: none;
    background: transparent;
    color: #999;
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 700;
    white-space: nowrap;
    cursor: pointer;
    border-radius: 8px;
    transition: 0.2s;
}

.match-tab.active {
    color: #fff;
    background: rgba(255,255,255,0.08);
}

/* =========================================
   PAGE DÉTAIL DU MATCH
   ========================================= */

.match-detail-page {
    width: 100%;
    max-width: 900px;
    margin: 0 auto;
    padding: 12px;
    box-sizing: border-box;
}


/* BOUTON RETOUR */

.match-back-button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: none;
    background: transparent;
    color: #aaa;
    font-size: 14px;
    font-weight: 700;
    padding: 8px 0;
    margin-bottom: 10px;
    cursor: pointer;
}

.match-back-button:hover {
    color: white;
}


/* CARTE PRINCIPALE */

.match-main-card {
    background: linear-gradient(
        145deg,
        #151515,
        #0d0d0d
    );

    border: 1px solid #242424;
    border-radius: 20px;
    padding: 20px 14px;
    box-sizing: border-box;

    box-shadow:
        0 8px 30px rgba(0,0,0,0.35);
}


/* COMPÉTITION */

.match-competition {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    margin-bottom: 25px;
    text-align: center;
}

.competition-logo {
    width: 36px;
    height: 36px;
    object-fit: contain;
}

.competition-text {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
}

.competition-name {
    color: white;
    font-size: 15px;
    font-weight: 800;
}

.competition-country {
    color: #888;
    font-size: 12px;
    margin-top: 3px;
}


/* ÉQUIPES */

.detail-match-teams {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: 15px;
}


/* ÉQUIPE */

.detail-team {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 0;
    text-align: center;
}

.detail-team-logo {
    width: 68px;
    height: 68px;
    object-fit: contain;
    margin-bottom: 10px;
}

.detail-team-name {
    color: white;
    font-size: 15px;
    font-weight: 800;
    line-height: 1.25;
    overflow-wrap: anywhere;
}


/* SCORE */

.detail-score-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 90px;
}

.detail-score {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;

    color: white;
    font-size: 36px;
    font-weight: 900;
    line-height: 1;
}

.score-separator {
    color: #777;
    font-weight: 500;
}

.detail-status {
    margin-top: 10px;
    padding: 5px 10px;

    border-radius: 20px;

    background: rgba(255,255,255,0.08);
    color: #bbb;

    font-size: 10px;
    font-weight: 800;
    text-transform: uppercase;

    white-space: nowrap;
}


/* INFOS RAPIDES */

.match-quick-info {
    display: flex;
    justify-content: center;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;

    margin-top: 22px;
    padding-top: 15px;

    border-top: 1px solid #222;

    color: #888;
    font-size: 11px;
}

.match-quick-info span {
    background: #171717;
    border: 1px solid #252525;
    border-radius: 20px;
    padding: 6px 10px;
}


/* CONTENU */

.match-content {
    margin-top: 15px;
}


/* CHARGEMENT */

.match-loading {
    min-height: 250px;

    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;

    gap: 12px;

    color: #aaa;
    font-size: 14px;
}

.loading-spinner {
    width: 30px;
    height: 30px;

    border: 3px solid #333;
    border-top-color: white;
    border-radius: 50%;

    animation: matchSpin 0.8s linear infinite;
}

@keyframes matchSpin {
    to {
        transform: rotate(360deg);
    }
}


/* ERREUR */

.match-error-page {
    width: 100%;
    max-width: 900px;
    margin: 0 auto;
    padding: 15px;
    box-sizing: border-box;
}


/* VERSION MOBILE */

@media (max-width: 600px) {

    .match-detail-page {
        padding: 8px;
    }

    .match-main-card {
        border-radius: 16px;
        padding: 18px 10px;
    }

    .match-competition {
        margin-bottom: 20px;
    }

    .competition-logo {
        width: 32px;
        height: 32px;
    }

    .competition-name {
        font-size: 14px;
    }

    .match-teams {
        gap: 7px;
    }

    .detail-team-logo {
        width: 55px;
        height: 55px;
    }

    .detail-team-name {
        font-size: 13px;
    }

    .detail-score-area {
        min-width: 75px;
    }

    .detail-score {
        font-size: 30px;
        gap: 5px;
    }

    .detail-status {
        font-size: 9px;
        padding: 4px 7px;
    }

    .match-quick-info {
        font-size: 10px;
    }

}

/* LARGEUR COMPLÈTE DE LA CARTE DU MATCH */
.match-main-card {
    width: 100%;
    box-sizing: border-box;
}

.detail-match-teams {
    width: 100%;
    box-sizing: border-box;
}

/* ZONE DU SCORE */
.detail-score-area {
    width: 100%;
    box-sizing: border-box;
}

/* BUTEURS */
.detail-scorers {
    width: 100%;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 15px;
    margin-top: 10px;
    box-sizing: border-box;
}

.detail-scorer-home {
    text-align: right;
}

.detail-scorer-away {
    text-align: left;
}

/* ============================= */
/* CORRECTION PAGE MATCH */
/* ============================= */

.match-main-card {
    width: 90%;
    max-width: none;
    box-sizing: border-box;
    margin-left: 0;
    margin-right: 0;
}

.detail-match-teams {
    width: 100%;
    box-sizing: border-box;

    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: start;
    gap: 8px;

    padding: 15px 8px;
}

.detail-team {
    min-width: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
}

.detail-team-logo {
    width: 50px;
    height: 50px;
    object-fit: contain;
}

.detail-team-name {
    margin-top: 6px;
    font-size: 14px;
    line-height: 18px;
    text-align: center;
    overflow-wrap: anywhere;
}

.detail-score-area {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-width: 75px;
}

.detail-score {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 24px;
    font-weight: bold;
    white-space: nowrap;
}

.detail-status {
    margin-top: 5px;

/* ============================= */
/* CORRECTION FINALE PAGE MATCH  */
/* ============================= */

.match-main-card {
    width: 100%;
    box-sizing: border-box;
}

/* ÉQUIPES + SCORE */

.detail-match-teams {
    width: 100%;
    box-sizing: border-box;

    display: grid;
    grid-template-columns: 1fr auto 1fr;

    align-items: center;
    gap: 15px;
}

/* ÉQUIPE */

.detail-team {
    min-width: 0;

    display: flex;
    flex-direction: column;

    align-items: center;
    justify-content: center;

    text-align: center;
}

.detail-team-logo {
    width: 55px;
    height: 55px;

    object-fit: contain;

    margin-bottom: 8px;
}

.detail-team-name {
    color: white;

    font-size: 14px;
    font-weight: 800;

    line-height: 18px;

    text-align: center;

    overflow-wrap: anywhere;
}

/* SCORE */

.detail-score-area {
    display: flex;

    flex-direction: column;

    align-items: center;
    justify-content: center;

    min-width: 75px;
}

.detail-score {
    display: flex;

    align-items: center;
    justify-content: center;

    gap: 8px;

    color: white;

    font-size: 28px;
    font-weight: 900;

    white-space: nowrap;
}

.detail-status {
    margin-top: 7px;

    color: #bbb;

    font-size: 10px;
    font-weight: 800;

    white-space: nowrap;
}

/* BUTEURS */

.detail-scorers {
    grid-column: 1 / 4;

    width: 100%;

    display: grid;

    grid-template-columns: 1fr 1fr;

    gap: 10px;

    margin-top: 8px;

    box-sizing: border-box;

    color: white;
}

.detail-scorer-home {
    text-align: right;
    padding-right: 8px;
}

.detail-scorer-away {
    text-align: left;
    padding-left: 8px;
}

.detail-scorer-home div,
.detail-scorer-away div {
    color: white;

    font-size: 12px;
    line-height: 18px;
}

/* CARTE SUR TOUTE LA LARGEUR DU TÉLÉPHONE */

@media (max-width: 600px) {

    .match-detail-page {
        padding: 0;
    }

    .match-main-card {
        width: 100%;
        border-radius: 0;
    }

    .detail-match-teams {
        padding: 10px 8px;
        gap: 8px;
    }

    .detail-team-logo {
        width: 50px;
        height: 50px;
    }

    .detail-team-name {
        font-size: 13px;
    }

    .detail-score-area {
        min-width: 65px;
    }

    .detail-score {
        font-size: 24px;
    }
}

</style>

</head>


<body>

<header class="top-header">
    <div class="brand">
        <span class="ball">⚽</span>
        <span class="brand-name">KF SCORE</span>
    </div>
</header> 

<nav>

<button id="dateBtn"
        onclick="datePage()">

📅 MATCHS

</button>


<button id="liveBtn"
        onclick="livePage()">

🔴 EN DIRECT

</button>

</nav>


<main id="app"></main>
    

<script>

const app = document.getElementById("app");


const leagueRanking = [
    2,     // UEFA Champions League
    39,    // Premier League
    140,   // La Liga
    135,   // Serie A
    78,    // Bundesliga
    61,    // Ligue 1
    88,    // Eredivisie
    94,    // Primeira Liga
    203,   // Süper Lig
    71,    // Brasileirão Serie A
    128,   // Argentine Primera
    307,   // Saudi Pro League
    253,   // MLS
    200,   // Botola Pro
    197    // Elite One Cameroun
];

function sortLeagues(groups) {

    const ranking = {
        2: 1,      // Champions League
        39: 2,     // Premier League
        140: 3,    // La Liga
        135: 4,    // Serie A
        78: 5,     // Bundesliga
        61: 6,     // Ligue 1
        88: 7,     // Eredivisie
        94: 8,     // Primeira Liga
        203: 9,    // Süper Lig
        71: 10,    // Brasileirão Serie A
        128: 11,   // Argentine
        307: 12,   // Saudi Pro League
        253: 13,   // MLS
        200: 14,   // Botola Pro
        197: 15    // Elite One Cameroun
    };


    return Object.values(groups).sort((a, b) => {

        const idA = Number(a.id);
        const idB = Number(b.id);

        const rankA =
            ranking[idA] !== undefined
            ? ranking[idA]
            : 9999;

        const rankB =
            ranking[idB] !== undefined
            ? ranking[idB]
            : 9999;


        return rankA - rankB;

    });

}

function active(id) {

    document
        .getElementById("dateBtn")
        .classList
        .remove("active");

    document
        .getElementById("liveBtn")
        .classList
        .remove("active");

    document
        .getElementById(id)
        .classList
        .add("active");
}


function status(f) {

    const s = f.status.short;

    if (
        ["1H", "2H", "ET", "P", "LIVE"]
        .includes(s)
    ) {

        return `
        <span class="status live">
        ${f.status.elapsed || 0}' 
        </span>
        `;

    }


    if (s === "HT") {

        return `
        <span class="status live">
        MI-TEMPS
        </span>
        `;

    }


    if (
        ["FT", "AET", "PEN"]
        .includes(s)
    ) {

        return `
        <span class="status">
        TERMINÉ
        </span>
        `;

    }


    if (s === "NS") {

        const d = new Date(f.date);

        return `
        <span class="status">
        ${d.toLocaleTimeString(
            "fr-FR",
            {
                hour: "2-digit",
                minute: "2-digit"
            }
        )}
        </span>
        `;

    }


    return `
    <span class="status">
    ${f.status.long || s}
    </span>
    `;
}

function card(m) {

    const f = m.fixture;
    const t = m.teams;
    const g = m.goals;

    const statusCode = f.status.short;

    const kickoff = new Date(f.date);

    const time = kickoff.toLocaleTimeString(
        "fr-FR",
        {
            hour: "2-digit",
            minute: "2-digit"
        }
    );

    const date = kickoff.toLocaleDateString(
        "fr-FR",
        {
            day: "2-digit",
            month: "2-digit",
            year: "numeric"
        }
    );

    let firstTime = time;
    let secondTime = "-";

    let homeScore = "";
    let awayScore = "";

    // MATCH À VENIR
    if (statusCode === "NS") {

        homeScore = "";
        awayScore = "";

        firstTime = time;
        secondTime = "-";
    }

    // MATCH EN COURS
    else if (
        ["1H", "2H", "ET", "P", "LIVE"].includes(statusCode)
    ) {

        homeScore = g.home ?? 0;
        awayScore = g.away ?? 0;

        firstTime = time;
        secondTime =
            (f.status.elapsed || 0) + "'";
    }

    // MI-TEMPS
    else if (statusCode === "HT") {

        homeScore = g.home ?? 0;
        awayScore = g.away ?? 0;

        firstTime = time;
        secondTime = "MT";
    }

    // MATCH TERMINÉ
    else if (
        ["FT", "AET", "PEN"].includes(statusCode)
    ) {

        homeScore = g.home ?? 0;
        awayScore = g.away ?? 0;

        firstTime = time;
        secondTime = "FT";
    }

    // MATCH ANCIEN / AUTRE STATUT
    else {

        homeScore = g.home ?? 0;
        awayScore = g.away ?? 0;

        firstTime = time;
        secondTime = "FT";
    }

    return `
    <div
        class="match"
        onclick="detailPage(${f.id})"
    >

        <div class="match-time">

            <span class="match-time-main">
                ${firstTime}
            </span>

            <span class="match-status ${
                ["1H", "2H", "ET", "P", "LIVE", "HT"].includes(statusCode)
                ? "live"
                : ""
            } second-status">
                ${secondTime}
            </span>

        </div>


        <div class="match-teams">

            <div class="team-row">

                <img
                    src="${t.home.logo || ""}"
                    alt=""
                >

                <span class="team-name">
                    ${translateTeam(t.home.name)}
                </span>

            </div>


            <div class="team-row">

                <img
                    src="${t.away.logo || ""}"
                    alt=""
                >

                <span class="team-name">
                    ${translateTeam(t.away.name)}
                </span>

            </div>

        </div>


            <div class="match-scores">

        <span class="team-score ${
            ["1H", "2H", "ET", "P", "LIVE", "HT"].includes(statusCode)
            ? "match-score-live"
            : ""
        }">
            ${homeScore}
        </span>

        <span class="team-score ${
            ["1H", "2H", "ET", "P", "LIVE", "HT"].includes(statusCode)
            ? "match-score-live"
            : ""
        }">
            ${awayScore}
        </span>

    </div>

</div>
    `;
}

function dateLabel(dateString) {

    const selected = new Date(dateString + "T12:00:00");

    const today = new Date();
    today.setHours(12, 0, 0, 0);

    const difference = Math.round(
        (selected - today) / (1000 * 60 * 60 * 24)
    );

    if (difference === 0) {
        return "Aujourd'hui";
    }

    if (difference === -1) {
        return "Hier";
    }

    if (difference === 1) {
        return "Demain";
    }

    return selected.toLocaleDateString("fr-FR", {
        day: "numeric",
        month: "long",
        year: "numeric"
    });
}

async function datePage(date) {

    active("dateBtn");


    const d =
        date ||
        new Date()
        .toISOString()
        .slice(0, 10);

    app.innerHTML = `
<div class="tools">
    <button onclick="moveDate(-1)">◀</button>

    <button
        id="dateDisplay"
        class="date-display"
        onclick="document.getElementById('picker').showPicker()"
    >
        ${dateLabel(d)}
    </button>

    <input
        id="picker"
        type="date"
        value="${d}"
        onchange="datePage(this.value)"
        style="display:none;"
    >

    <button onclick="moveDate(1)">▶</button>
</div>

    <div
        id="list"
        class="box"
    >
        Chargement...
    </div>

    `;


    try {

        const r =
            await fetch(
                "/api/matches?date=" + d
            );


        const data =
            await r.json();


        if (!r.ok || data.error) {

            document
                .getElementById("list")
                .innerHTML =
                '<div class="error">' +
                (data.error || "Erreur API") +
                "</div>";

            return;
        }


        const ms =
            data.response || [];


        if (!ms.length) {

            document
                .getElementById("list")
                .innerHTML =
                "Aucun match pour cette date.";

            return;
        }


        const groups = {};


        ms.forEach(m => {

            const id =
                m.league.id;


            if (!groups[id]) {
groups[id] = {
    id: id,
    name: m.league.name,
    country: m.league.country,
    logo: m.league.logo,
    ms: []
};
            }


            groups[id].ms.push(m);

groups[id].ms.sort(
    (a, b) =>
        new Date(a.fixture.date) -
        new Date(b.fixture.date)
);

        });


        document
            .getElementById("list")
            .className = "";


        document
            .getElementById("list")
            .innerHTML =
            
sortLeagues(groups)
    .map(g => `

               <section class="league">

    <div class="league-header">

        ${
            g.logo
            ? `
            <img
                class="league-logo"
                src="${g.logo}"
                alt=""
            >
            `
            : ""
        }

        <span class="league-flag">
            ${countryFlag(g.country)}
        </span>

        <div class="league-info">

        <div class="league-name">
            ${translateLeague(g.name)}
        </div>

        <div class="league-country">
            ${translateCountry(g.country)}
        </div>

        </div>

    </div>

    ${g.ms.map(card).join("")}

</section>

            `)
            .join("");


    } catch (e) {

        document
            .getElementById("list")
            .innerHTML =
            '<div class="error">' +
            "Erreur de connexion." +
            "</div>";

    }

}


function moveDate(n) {

    const p =
        document.getElementById("picker");


    const d =
        new Date(
            p.value + "T12:00:00"
        );


    d.setDate(
        d.getDate() + n
    );


    datePage(
        d.toISOString().slice(0, 10)
    );

}


async function livePage() {

    active("liveBtn");


    app.innerHTML = `
        <div
            id="live"
            class="box"
        >
            Chargement des matchs
            en direct...
        </div>
    `;


    await loadLive();

}

function translateCountry(country) {

    const countries = {
        "England": "Angleterre",
        "France": "France",
        "Spain": "Espagne",
        "Germany": "Allemagne",
        "Italy": "Italie",
        "Portugal": "Portugal",
        "Netherlands": "Pays-Bas",
        "Belgium": "Belgique",
        "Brazil": "Brésil",
        "Argentina": "Argentine",
        "Cameroon": "Cameroun",
        "United States": "États-Unis",
        "Mexico": "Mexique",
        "Saudi-Arabia": "Arabie saoudite",
        "Saudi Arabia": "Arabie saoudite",
        "Turkey": "Turquie",
        "Scotland": "Écosse",
        "Greece": "Grèce",
        "Switzerland": "Suisse",
        "Austria": "Autriche",
        "Japan": "Japon",
        "South Korea": "Corée du Sud",
        "Australia": "Australie",
        "China": "Chine",
        "Morocco": "Maroc",
        "Egypt": "Égypte",
        "South Africa": "Afrique du Sud"
    };

    return countries[country] || country;
}


function translateLeague(league) {

    const leagues = {
        "UEFA Champions League": "Ligue des champions UEFA",
        "UEFA Europa League": "Ligue Europa UEFA",
        "UEFA Europa Conference League": "Ligue Conférence UEFA",
        "Premier League": "Premier League",
        "La Liga": "Liga",
        "Serie A": "Serie A",
        "Bundesliga": "Bundesliga",
        "Ligue 1": "Ligue 1",
        "Eredivisie": "Eredivisie",
        "Primeira Liga": "Liga Portugal",
        "Süper Lig": "Süper Lig",
        "Brasileirão Serie A": "Brasileirão Série A",
        "Saudi Pro League": "Championnat d'Arabie saoudite",
        "Major League Soccer": "Major League Soccer",
        "Botola Pro": "Botola Pro",
        "Elite One": "Elite One Cameroun"
    };

    return leagues[league] || league;
}



function translateTeam(name) {

    if (!name) return "";

    const translations = {

        // AFRIQUE
        "Algeria": "Algérie",
        "Angola": "Angola",
        "Benin": "Bénin",
        "Botswana": "Botswana",
        "Burkina Faso": "Burkina Faso",
        "Burundi": "Burundi",
        "Cameroon": "Cameroun",
        "Cape Verde": "Cap-Vert",
        "Central African Republic": "République centrafricaine",
        "Chad": "Tchad",
        "Comoros": "Comores",
        "Congo": "Congo",
        "Congo DR": "RD Congo",
        "Democratic Republic of the Congo": "RD Congo",
        "Djibouti": "Djibouti",
        "Egypt": "Égypte",
        "Equatorial Guinea": "Guinée équatoriale",
        "Eritrea": "Érythrée",
        "Eswatini": "Eswatini",
        "Ethiopia": "Éthiopie",
        "Gabon": "Gabon",
        "Gambia": "Gambie",
        "Ghana": "Ghana",
        "Guinea": "Guinée",
        "Guinea-Bissau": "Guinée-Bissau",
        "Ivory Coast": "Côte d'Ivoire",
        "Kenya": "Kenya",
        "Lesotho": "Lesotho",
        "Liberia": "Liberia",
        "Libya": "Libye",
        "Madagascar": "Madagascar",
        "Malawi": "Malawi",
        "Mali": "Mali",
        "Mauritania": "Mauritanie",
        "Mauritius": "Maurice",
        "Morocco": "Maroc",
        "Mozambique": "Mozambique",
        "Namibia": "Namibie",
        "Niger": "Niger",
        "Nigeria": "Nigeria",
        "Rwanda": "Rwanda",
        "Sao Tome and Principe": "Sao Tomé-et-Principe",
        "Senegal": "Sénégal",
        "Seychelles": "Seychelles",
        "Sierra Leone": "Sierra Leone",
        "Somalia": "Somalie",
        "South Africa": "Afrique du Sud",
        "South Sudan": "Soudan du Sud",
        "Sudan": "Soudan",
        "Tanzania": "Tanzanie",
        "Togo": "Togo",
        "Tunisia": "Tunisie",
        "Uganda": "Ouganda",
        "Zambia": "Zambie",
        "Zimbabwe": "Zimbabwe",

        // EUROPE
        "Albania": "Albanie",
        "Andorra": "Andorre",
        "Armenia": "Arménie",
        "Austria": "Autriche",
        "Azerbaijan": "Azerbaïdjan",
        "Belarus": "Biélorussie",
        "Belgium": "Belgique",
        "Bosnia and Herzegovina": "Bosnie-Herzégovine",
        "Bosnia": "Bosnie",
        "Bulgaria": "Bulgarie",
        "Croatia": "Croatie",
        "Cyprus": "Chypre",
        "Czech Republic": "République tchèque",
        "Czechia": "Tchéquie",
        "Denmark": "Danemark",
        "England": "Angleterre",
        "Estonia": "Estonie",
        "Faroe Islands": "Îles Féroé",
        "Finland": "Finlande",
        "France": "France",
        "Georgia": "Géorgie",
        "Germany": "Allemagne",
        "Gibraltar": "Gibraltar",
        "Greece": "Grèce",
        "Hungary": "Hongrie",
        "Iceland": "Islande",
        "Ireland": "Irlande",
        "Israel": "Israël",
        "Italy": "Italie",
        "Kazakhstan": "Kazakhstan",
        "Kosovo": "Kosovo",
        "Latvia": "Lettonie",
        "Liechtenstein": "Liechtenstein",
        "Lithuania": "Lituanie",
        "Luxembourg": "Luxembourg",
        "Malta": "Malte",
        "Moldova": "Moldavie",
        "Montenegro": "Monténégro",
        "Netherlands": "Pays-Bas",
        "North Macedonia": "Macédoine du Nord",
        "Northern Ireland": "Irlande du Nord",
        "Norway": "Norvège",
        "Poland": "Pologne",
        "Portugal": "Portugal",
        "Romania": "Roumanie",
        "Russia": "Russie",
        "San Marino": "Saint-Marin",
        "Scotland": "Écosse",
        "Serbia": "Serbie",
        "Slovakia": "Slovaquie",
        "Slovenia": "Slovénie",
        "Spain": "Espagne",
        "Sweden": "Suède",
        "Switzerland": "Suisse",
        "Turkey": "Turquie",
        "Ukraine": "Ukraine",
        "Wales": "Pays de Galles",

        // AMÉRIQUE DU NORD, CENTRALE ET CARAÏBES
        "Anguilla": "Anguilla",
        "Antigua and Barbuda": "Antigua-et-Barbuda",
        "Aruba": "Aruba",
        "Bahamas": "Bahamas",
        "Barbados": "Barbade",
        "Belize": "Belize",
        "Bermuda": "Bermudes",
        "British Virgin Islands": "Îles Vierges britanniques",
        "Canada": "Canada",
        "Cayman Islands": "Îles Caïmans",
        "Costa Rica": "Costa Rica",
        "Cuba": "Cuba",
        "Curacao": "Curaçao",
        "Curaçao": "Curaçao",
        "Dominica": "Dominique",
        "Dominican Republic": "République dominicaine",
        "El Salvador": "Salvador",
        "Grenada": "Grenade",
        "Guadeloupe": "Guadeloupe",
        "Guatemala": "Guatemala",
        "Guyana": "Guyana",
        "Haiti": "Haïti",
        "Honduras": "Honduras",
        "Jamaica": "Jamaïque",
        "Martinique": "Martinique",
        "Mexico": "Mexique",
        "Montserrat": "Montserrat",
        "Nicaragua": "Nicaragua",
        "Panama": "Panama",
        "Puerto Rico": "Porto Rico",
        "Saint Kitts and Nevis": "Saint-Christophe-et-Niévès",
        "Saint Lucia": "Sainte-Lucie",
        "Saint Vincent and the Grenadines": "Saint-Vincent-et-les-Grenadines",
        "Trinidad and Tobago": "Trinité-et-Tobago",
        "Turks and Caicos Islands": "Îles Turques-et-Caïques",
        "United States": "États-Unis",
        "US Virgin Islands": "Îles Vierges américaines",
        "United States Virgin Islands": "Îles Vierges américaines",

        // AMÉRIQUE DU SUD
        "Argentina": "Argentine",
        "Bolivia": "Bolivie",
        "Brazil": "Brésil",
        "Chile": "Chili",
        "Colombia": "Colombie",
        "Ecuador": "Équateur",
        "Paraguay": "Paraguay",
        "Peru": "Pérou",
        "Suriname": "Suriname",
        "Uruguay": "Uruguay",
        "Venezuela": "Venezuela",

        // ASIE
        "Afghanistan": "Afghanistan",
        "Australia": "Australie",
        "Bahrain": "Bahreïn",
        "Bangladesh": "Bangladesh",
        "Bhutan": "Bhoutan",
        "Brunei": "Brunei",
        "Cambodia": "Cambodge",
        "China": "Chine",
        "Chinese Taipei": "Taïwan",
        "Chinese Hong Kong": "Hong Kong",
        "Hong Kong": "Hong Kong",
        "India": "Inde",
        "Indonesia": "Indonésie",
        "Iran": "Iran",
        "Iraq": "Irak",
        "Japan": "Japon",
        "Jordan": "Jordanie",
        "Korea Republic": "Corée du Sud",
        "South Korea": "Corée du Sud",
        "North Korea": "Corée du Nord",
        "Kuwait": "Koweït",
        "Kyrgyzstan": "Kirghizistan",
        "Laos": "Laos",
        "Lebanon": "Liban",
        "Macau": "Macao",
        "Malaysia": "Malaisie",
        "Maldives": "Maldives",
        "Mongolia": "Mongolie",
        "Myanmar": "Myanmar",
        "Nepal": "Népal",
        "Oman": "Oman",
        "Pakistan": "Pakistan",
        "Palestine": "Palestine",
        "Philippines": "Philippines",
        "Qatar": "Qatar",
        "Saudi Arabia": "Arabie saoudite",
        "Singapore": "Singapour",
        "Sri Lanka": "Sri Lanka",
        "Syria": "Syrie",
        "Tajikistan": "Tadjikistan",
        "Thailand": "Thaïlande",
        "Timor-Leste": "Timor oriental",
        "Turkmenistan": "Turkménistan",
        "United Arab Emirates": "Émirats arabes unis",
        "Uzbekistan": "Ouzbékistan",
        "Vietnam": "Vietnam",
        "Yemen": "Yémen",

        // OCÉANIE ET ÎLES
        "American Samoa": "Samoa américaines",
        "Cook Islands": "Îles Cook",
        "Fiji": "Fidji",
        "Guam": "Guam",
        "Kiribati": "Kiribati",
        "New Caledonia": "Nouvelle-Calédonie",
        "New Zealand": "Nouvelle-Zélande",
        "Papua New Guinea": "Papouasie-Nouvelle-Guinée",
        "Samoa": "Samoa",
        "Solomon Islands": "Îles Salomon",
        "Tahiti": "Tahiti",
        "Tonga": "Tonga",
        "Vanuatu": "Vanuatu"
    };

    // Correspondance exacte
if (translations[name]) {
    return translations[name];
}

// Équipes féminines :
// England W → Angleterre F
// France W → France F
// Cameroon W → Cameroun F
if (name.endsWith(" W")) {

    const baseName = name.slice(0, -2);

    return translateTeam(baseName) + " F";
}

// Traduction du pays au début du nom
    

    // Traduction du pays au début du nom
    // en conservant automatiquement le suffixe :
    // U17, U20, U21, U23, Women, etc.
    for (const country in translations) {

        if (name === country) {
            return translations[country];
        }

        if (name.startsWith(country + " ")) {

            const suffix = name.substring(country.length);

            return translations[country] + suffix;
        }
    }

    // Si aucun pays n'est trouvé,
    // conserver le nom original
    return name;
}
    
function countryFlag(country) {

    const flags = {

        "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
        "France": "🇫🇷",
        "Spain": "🇪🇸",
        "Germany": "🇩🇪",
        "Italy": "🇮🇹",
        "Portugal": "🇵🇹",
        "Netherlands": "🇳🇱",
        "Belgium": "🇧🇪",
        "Brazil": "🇧🇷",
        "Argentina": "🇦🇷",
        "Cameroon": "🇨🇲",
        "United States": "🇺🇸",
        "Mexico": "🇲🇽",
        "Saudi-Arabia": "🇸🇦",
        "Saudi Arabia": "🇸🇦",
        "Turkey": "🇹🇷",
        "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
        "Greece": "🇬🇷",
        "Switzerland": "🇨🇭",
        "Austria": "🇦🇹",
        "Japan": "🇯🇵",
        "South Korea": "🇰🇷",
        "Australia": "🇦🇺",
        "China": "🇨🇳",
        "Morocco": "🇲🇦",
        "Egypt": "🇪🇬",
        "South Africa": "🇿🇦"
    };

    return flags[country] || "🌍";
}


async function loadLive() {

    const box =
        document.getElementById("live");

    if (!box) {
        return;
    }

    try {

        const r =
            await fetch("/api/live");

        const data =
            await r.json();

        if (!r.ok || data.error) {

            box.innerHTML =
                '<div class="error">' +
                (data.error || "Erreur API") +
                "</div>";

            return;
        }

        const ms =
            data.response || [];

        if (!ms.length) {

            box.innerHTML =
                "🔴 Aucun match en direct actuellement.";

            return;
        }

        /*
         * Regrouper les matchs par ligue
         */

        const groups = {};

        ms.forEach(m => {

            const league =
                m.league;

            const id =
                league.id;

            if (!groups[id]) {

                groups[id] = {
                    id: id,
                    name: league.name,
                    country: league.country,
                    logo: league.logo,
                    matches: []
                };

            }

            groups[id].matches.push(m);

groups[id].matches.sort(
    (a, b) =>
        new Date(a.fixture.date) -
        new Date(b.fixture.date)
);
        });


        /*
         * Afficher les ligues
         */

        box.className = "";

        box.innerHTML =
            sortLeagues(groups)
    .map(g => `

                <section class="league">

                    <div class="league-header">

                        ${
                            g.logo
                            ? `
                            <img
                                class="league-logo"
                                src="${g.logo}"
                                alt=""
                            >
                            `
                            : ""
                        }

                        <span class="league-flag">
                            ${countryFlag(g.country)}
                        </span>

                        <div class="league-info">

                            <div class="league-name">
                                ${translateLeague(g.name)}
                            </div>

                            <div class="league-country">
                                ${translateCountry(g.country)}
                            </div>

                        </div>

                    </div>


                    ${g.matches
                        .map(card)
                        .join("")
                    }

                </section>

            `)
            .join("");


    } catch (e) {

    document
        .getElementById("list")
        .innerHTML =
        '<div class="error">' +
        "Erreur : " + e.message +
        "</div>";

}

}

function translateRound(round) {

    if (!round) return "";

    const text = String(round).trim();

    // Recherche d'un numéro de journée
    const match = text.match(/(?:-|–|—|\s)(\d+)\s*$/);

    if (match) {
        return "Journée " + match[1];
    }

    // Formats comme "Matchday 5", "Week 5", etc.
    const numberMatch = text.match(
        /(?:matchday|match day|week|jornada|giornata|spieltag|round|journee|journée)\s*(\d+)/i
    );

    if (numberMatch) {
        return "Journée " + numberMatch[1];
    }

    return text;
}

function translateStatus(status) {

    if (!status) return "";

    const code = status.short;

    if (["FT", "AET", "PEN"].includes(code)) {
        return "TERMINÉ";
    }

    if (code === "HT") {
        return "MI-TEMPS";
    }

    if (["1H", "2H", "ET", "P"].includes(code)) {
        return "EN DIRECT";
    }

    if (code === "NS") {
        return "À VENIR";
    }

    if (code === "PST") {
        return "REPORTÉ";
    }

    if (code === "CANC") {
        return "ANNULÉ";
    }

    if (code === "ABD") {
        return "ABANDONNÉ";
    }

    return "";
}

async function detailPage(id) {

    app.innerHTML = `
        <div class="match-loading">
            <div class="loading-spinner"></div>
            <div>Chargement du match...</div>
        </div>
    `;

    try {

        const r = await fetch("/api/match/" + id);
        const data = await r.json();

        console.log("DONNÉES MATCH :", data);

        if (!r.ok || data.error) {
            throw new Error(
                data.error || "Erreur serveur"
            );
        }

        window.matchActuel = data;

        const fixture = data.fixture;

        const home = fixture.teams.home;
        const away = fixture.teams.away;

        const homeScore = fixture.goals.home ?? 0;
        const awayScore = fixture.goals.away ?? 0;

        const status = translateStatus(fixture.fixture.status);
        const homeScorers = (data.events || []).filter(
    e => e.type === "Goal" && e.team.id === home.id
);

const awayScorers = (data.events || []).filter(
    e => e.type === "Goal" && e.team.id === away.id
);

        app.innerHTML = `

            <div class="match-detail-page">

                <!-- RETOUR -->

                <button
                    class="match-back-button"
                    onclick="datePage()"
                >
                    ← <span>Retour</span>
                </button>


                <!-- CARTE PRINCIPALE DU MATCH -->

                <div class="match-main-card">

                    <!-- COMPÉTITION -->

                    <div class="match-competition">

                        ${
                            fixture.league.logo
                            ? `
                            <img
                                src="${fixture.league.logo}"
                                alt=""
                                class="competition-logo"
                            >
                            `
                            : ""
                        }

                        <div class="competition-text">

                            <div class="competition-name">
                                ${translateLeague(
                                    fixture.league.name
                                )}
                            </div>

                            <div class="competition-country">

                                ${countryFlag(
                                    fixture.league.country
                                )}

                                ${fixture.league.country || ""}

                            </div>

                        </div>

                    </div>


                    <!-- ÉQUIPES -->

                    <div class="detail-match-teams">

                        <!-- ÉQUIPE DOMICILE -->

                        <div class="detail-team">

                            <img
                                src="${home.logo || ""}"
                                alt=""
                                class="detail-team-logo"
                            >

                            <div class="detail-team-name">
                                ${translateTeam(home.name)}
                            </div>

                        </div>


                        <!-- SCORE -->

                        <div class="detail-score-area">

                            <div class="detail-score">

                                <span>
                                    ${homeScore}
                                </span>

                                <span class="score-separator">
                                    -
                                </span>

                                <span>
                                    ${awayScore}
                                </span>

                            </div>

                            <div class="detail-status">
                                ${status}
                            </div>

    <div class="detail-scorer-away">
        ${
            awayScorers.length
            ? awayScorers.map(e => `
                <div>${e.time?.elapsed || ""}' ${e.player?.name || ""} ⚽</div>
            `).join("")
            : ""
        }
    </div>

</div>


                        </div>


                        <!-- ÉQUIPE EXTÉRIEURE -->

                        <div class="detail-team">

                            <img
                                src="${away.logo || ""}"
                                alt=""
                                class="detail-team-logo"
                            >

                            <div class="detail-team-name">
                                ${translateTeam(away.name)}
                            </div>

                        </div>


<!-- BUTEURS -->

<div class="detail-scorers">

    <div class="detail-scorer-home">
        ${
            homeScorers.length
            ? homeScorers.map(e => `
                <div>
                    ⚽ ${e.player?.name || ""}
                    ${e.time?.elapsed || ""}'
                </div>
            `).join("")
            : ""
        }
    </div>

    <div class="detail-scorer-away">
        ${
            awayScorers.length
            ? awayScorers.map(e => `
                <div>
                    ${e.time?.elapsed || ""}'
                    ${e.player?.name || ""} ⚽
                </div>
            `).join("")
            : ""
        }
    </div>

</div>


</div>

                    </div>


                    <!-- INFOS RAPIDES -->

                    <div class="match-quick-info">

                        <span>
                            🏆
                            ${translateLeague(
                                fixture.league.name
                            )}
                        </span>
                            ${
    fixture.league.round
    ? `
        <span>
            📅 ${translateRound(fixture.league.round)}
        </span>
    `
    : ""
}

                    </div>

                </div>


                <!-- ONGLES -->

                <div class="match-tabs">

                    <button
                        class="match-tab active"
                        onclick="
                            afficherOngletMatch(
                                'resume',
                                ${id}
                            )
                        "
                    >
                        RÉSUMÉ
                    </button>


                    <button
                        class="match-tab"
                        onclick="
                            afficherOngletMatch(
                                'stats',
                                ${id}
                            )
                        "
                    >
                        STATS
                    </button>


                    <button
                        class="match-tab"
                        onclick="
                            afficherOngletMatch(
                                'compositions',
                                ${id}
                            )
                        "
                    >
                        COMPOSITIONS
                    </button>


                    <button
                        class="match-tab"
                        onclick="
                            afficherOngletMatch(
                                'details',
                                ${id}
                            )
                        "
                    >
                        DÉTAILS
                    </button>


                    <button
                        class="match-tab"
                        onclick="
                            afficherOngletMatch(
                                'classement',
                                ${id}
                            )
                        "
                    >
                        CLASSEMENT
                    </button>

                </div>


                <!-- CONTENU -->

                <div
                    id="contenu-match"
                    class="match-content"
                >

                    ${afficherResumeMatch(
                        data.events || []
                    )}

                </div>

            </div>

        `;

    } catch (e) {

        console.error(
            "ERREUR MATCH :",
            e
        );

        app.innerHTML = `

            <div class="match-error-page">

                <button
                    class="match-back-button"
                    onclick="datePage()"
                >
                    ← <span>Retour</span>
                </button>

                <div class="error">

                    Erreur :
                    ${e.message}

                </div>

            </div>

        `;

    }

}

function eventHtml(e) {

    let icon = "•";


    if (e.type === "Goal") {
        icon = "⚽";
    }


    if (e.type === "Card") {

        icon =
            e.detail &&
            e.detail.includes("Yellow")
            ? "🟨"
            : "🟥";

    }


    if (e.type === "subst") {
        icon = "🔄";
    }


    const p =
        e.player &&
        e.player.name
        ? e.player.name
        : "";


    const a =
        e.assist &&
        e.assist.name
        ? " — Passe : " +
          e.assist.name
        : "";


    const t =
        e.team &&
        e.team.name
        ? e.team.name
        : "";


    return `

    <div class="event">

        ${icon}

        ${(e.time.elapsed || "")}'

        —

        <b>${p}</b>

        ${a}

        <br>

        <small>
            ${t}
            —
            ${e.detail || e.type}
        </small>

    </div>

    `;

}


datePage();


setInterval(
    function() {

        if (
            document
            .getElementById("liveBtn")
            .classList
            .contains("active")
        ) {

            loadLive();

        }

    },
    60000
);

async function afficherCentreMatch(matchId) {

    const zone = document.getElementById("match-detail");

    if (!zone) {
        console.log("Zone match-detail introuvable");
        return;
    }

    zone.innerHTML = `
        <div style="padding:20px;text-align:center;">
            Chargement du match...
        </div>
    `;

    try {

        const response = await fetch(`/api/match/${matchId}`);
        const data = await response.json();

        if (data.error) {
            zone.innerHTML = `
                <div style="padding:20px;text-align:center;">
                    ${data.error}
                </div>
            `;
            return;
        }

        const fixture = data.fixture;
        const events = data.events || [];
        const statistics = data.statistics || [];

        const home = fixture.teams.home;
        const away = fixture.teams.away;

        zone.innerHTML = `

            <div class="match-center">

                <div class="match-center-header">

                    <div class="match-team">
                        <img src="${home.logo || ""}" alt="">
                        <strong>${translateTeam(home.name)}</strong>
                    </div>

                    <div class="match-center-score">
                        <div>
                            ${fixture.goals.home ?? 0}
                            -
                            ${fixture.goals.away ?? 0}
                        </div>
                        <small>${fixture.fixture.status.short}</small>
                    </div>

                    <div class="match-team">
                        <img src="${away.logo || ""}" alt="">
                        <strong>${translateTeam(away.name)}</strong>
                    </div>

                </div>

                <div class="match-tabs">

                    <button onclick="afficherOngletMatch('resume', ${matchId})">
                        RÉSUMÉ
                    </button>

                    <button onclick="afficherOngletMatch('stats', ${matchId})">
                        STATS
                    </button>

                    <button onclick="afficherOngletMatch('compositions', ${matchId})">
                        COMPOSITIONS
                    </button>

                    <button onclick="afficherOngletMatch('classement', ${matchId})">
                        CLASSEMENT
                    </button>

                </div>

                <div id="contenu-match">
                    ${afficherResumeMatch(events)}
                </div>

            </div>
        `;

        window.matchActuel = data;

    } catch (error) {

        zone.innerHTML = `
            <div style="padding:20px;text-align:center;">
                Erreur lors du chargement du match.
            </div>
        `;
    }
}


function afficherOngletMatch(onglet, matchId) {

    const data = window.matchActuel;

    if (!data) return;

    const contenu = document.getElementById("contenu-match");

    if (onglet === "resume") {
        contenu.innerHTML = afficherResumeMatch(data.events || []);
    }

    if (onglet === "stats") {
        contenu.innerHTML = afficherStatsMatch(data.statistics || []);
    }

    if (onglet === "compositions") {
        contenu.innerHTML = afficherCompositionsMatch(data);
    }

    if (onglet === "classement") {
        contenu.innerHTML = `
            <div style="padding:20px;text-align:center;">
                Classement disponible lorsque les données de classement sont récupérées.
            </div>
        `;
    }
}


function afficherResumeMatch(events) {

    if (!events.length) {
        return `
            <div style="padding:20px;text-align:center;">
                Aucun événement.
            </div>
        `;
    }

    return `
        <div class="match-events">

            ${events.map(event => `

                <div style="
                    padding:10px;
                    border-bottom:1px solid #eee;
                ">

                    <strong>${event.time?.elapsed || ""}'</strong>

                    ${event.type === "Goal" ? "⚽" : ""}
                    ${event.type === "Card" ? "🟨" : ""}
                    ${event.type === "subst" ? "🔄" : ""}

                    ${event.player?.name || ""}

                    ${event.assist?.name
                        ? ` — Passe : ${event.assist.name}`
                        : ""
                    }

                </div>

            `).join("")}

        </div>
    `;
}


function afficherStatsMatch(statistics) {

    if (!statistics.length) {
        return `
            <div style="padding:20px;text-align:center;">
                Aucune statistique disponible.
            </div>
        `;
    }

    return `
        <div style="padding:15px;">

            ${statistics.map(team => `

                <div style="
                    display:flex;
                    align-items:center;
                    gap:10px;
                    margin-bottom:15px;
                ">

                    <img
                        src="${team.team?.logo || ""}"
                        width="30"
                    >

                    <strong>
                        ${translateTeam(team.team?.name || "")}
                    </strong>

                </div>

                ${(team.statistics || []).map(stat => `

                    <div style="
                        display:flex;
                        justify-content:space-between;
                        padding:8px 0;
                        border-bottom:1px solid #eee;
                    ">

                        <span>${stat.type}</span>

                        <strong>${stat.value ?? "-"}</strong>

                    </div>

                `).join("")}

            `).join("")}

        </div>
    `;
}


function afficherCompositionsMatch(data) {

    return `
        <div style="padding:15px;">

            <h3>COMPOSITIONS</h3>

            <p>
                Les compositions détaillées seront affichées ici
                à partir des données de l'API.
            </p>

        </div>
    `;
}

</script>

</body>
</html>
"""

# TEST TEMPORAIRE DE L'API
@app.route("/test-api")
def test_api():
    try:
        import requests
        import os

        api_key = os.environ.get("API_KEY")

        if not api_key:
            return {"erreur": "API_KEY non configurée"}, 500

        response = requests.get(
            "https://v3.football.api-sports.io/fixtures",
            headers={"x-apisports-key": api_key},
            params={"date": "2026-09-30"},
            timeout=20
        )

        data = response.json()

        return {
            "http_status": response.status_code,
            "api_errors": data.get("errors"),
            "nombre_de_matchs": len(data.get("response", []))
        }

    except Exception as e:
        return {"erreur": str(e)}, 500

if __name__ == "__main__":
    if "--automation-once" in sys.argv:
        result = run_automation_once()
        print(result)
        sys.exit(0 if result.get("ok") else 1)

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
        use_reloader=False
    )
