from flask import Flask, jsonify, request, render_template_string
import requests
from datetime import datetime

app = Flask(__name__)

API_KEY = "2aed42d74d5e1d7cc83751e05757d2a6"
API_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}


def api_get(endpoint, params):
    try:
        r = requests.get(
            API_URL + "/" + endpoint,
            headers=HEADERS,
            params=params,
            timeout=20
        )

        data = r.json()

        if r.status_code != 200:
            return None, "Erreur API : " + str(r.status_code)

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

.match-teams {
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

        const status = fixture.fixture.status;

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

                    <div class="match-teams">

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
                                ${status.long || ""}
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
                                📅 ${fixture.league.round}
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

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
)
