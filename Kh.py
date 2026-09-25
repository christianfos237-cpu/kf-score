from flask import Flask, jsonify, request, render_template_string
import requests
from datetime import datetime

app = Flask(__name__)

API_KEY = "00a3ff8fc860a0917461ddd539c9c609"
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
        {"date": date}
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

    return jsonify({
        "fixture": fixture,
        "events": events,
        "events_error": events_error
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
    grid-template-columns: 1fr 70px 1fr;
    align-items: center;
    gap: 10px;
    padding: 12px 10px;
    border-top: 1px solid #eee;
    cursor: pointer;
}

.team {
    display: grid;
    grid-template-columns: 38px 1fr;
    align-items: center;
    gap: 8px;
    min-width: 0;
}

.team span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.team img {
    width: 30px;
    height: 30px;
    object-fit: contain;
}

.away {
    grid-template-columns: 1fr 38px;
    justify-content: initial;
    text-align: right;
}

.away span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.team {
    display: flex;
    align-items: center;
    gap: 7px;
}

.away {
    justify-content: flex-end;
    text-align: right;
}

.team img {
    width: 30px;
    height: 30px;
    object-fit: contain;
}

.score {
    text-align: center;
    font-weight: bold;
}

.status {
    display: block;
    font-size: 11px;
    color: #666;
    margin-top: 4px;
}

.live {
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


    return `
    <div
        class="match"
        onclick="detailPage(${f.id})"
    >

        <div class="team">

            <img src="${t.home.logo || ""}">

            <span>
                ${translateTeam(t.home.name)}
            </span>

        </div>


        <div class="score">

            ${(g.home ?? "-")}
            -
            ${(g.away ?? "-")}

            ${status(f)}

        </div>


        <div class="team away">

            <span>
                ${translateTeam(t.away.name)}
            </span>

            <img src="${t.away.logo || ""}">

        </div>

    </div>
    `;
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

        <button onclick="moveDate(-1)">
        ◀
        </button>


        <input
            id="picker"
            type="date"
            value="${d}"
            onchange="datePage(this.value)"
        >


        <button onclick="moveDate(1)">
        ▶
        </button>

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
                ${g.name}
            </div>

            <div class="league-country">
                ${g.country}
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


function countryFlag(country) {

    const flags = {

        "England": "🇬🇧",
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
        "Scotland": "🏴",
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
                                ${g.name}
                            </div>

                            <div class="league-country">
                                ${g.country}
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

        box.innerHTML =
            '<div class="error">' +
            "Erreur de connexion." +
            "</div>";

    }

}

async function detailPage(id) {

    app.innerHTML = `
        <div class="box">
            Chargement...
        </div>
    `;

    try {

        const r = await fetch("/api/match/" + id);

        const data = await r.json();

        console.log(data);

        if (!r.ok) {
            throw new Error(data.error || "Erreur serveur");
        }

        app.innerHTML = `
            <button class="back" onclick="datePage()">
                ← Retour
            </button>

            <div class="box">
                <h2>Match chargé ✅</h2>

                <p>ID : ${id}</p>

                <p>
                    Ligue :
                    ${data.fixture.league.name}
                </p>

                <p>
                    ${translateTeam(data.fixture.lineups[0].team.name)}
    —
                    ${translateTeam(data.fixture.lineups[1].team.name)}
                </p>

                <p>
                    Score :
                    ${data.fixture.goals.home}
                    -
                    ${data.fixture.goals.away}
                </p>
            </div>
        `;

    } catch (e) {

        console.error("ERREUR :", e);

        app.innerHTML = `
            <div class="error">
                Erreur : ${e.message}
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

</script>

</body>
</html>
"""


if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        use_reloader=False
)
