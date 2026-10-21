# Fotbolls-AI · Version 1.0

En personlig webbapp för fotbollsanalys. Du får modellernas sannolikheter, motiveringar, avstå-markeringar, oddsjämförelser och en prognoslogg. **Inga betaluppgifter, riktiga insatser, betalknappar eller automatiska spel ingår.**

Ingen match är stensäker och hög träffsäkerhet bevisar inte lönsamhet. Ett utfall med 80 % sannolikhet har negativt beräknat värde vid odds 1,10: för att gå jämnt upp krävs över 90,9 %. V1 visar beräkningen men lovar inte att modellens sannolikheter är korrekta.

## Omfattning för V1

Anslutna tävlingar: Premier League, La Liga, Bundesliga, Serie A och Ligue 1. Champions League/Europa League finns som utbyggnadspunkter och visas som **saknad källa**, aldrig som fungerande analys. Aktuellt spelschema/resultat hämtas från OpenFootball (CC0); officiella CSV-filer från football-data.co.uk kompletterar resultat, skott/hörnor och publicerade odds när de finns. Källorna är inte realtidsflöden. Exakta historiska publiceringstider, xG, frånvaro och startelvor saknas.

Modeller: Poisson-basmodell, Elo, gradient boosting och ensemblekandidat. Ensemble är inte automatiskt vald. Nya prognoser använder Poisson som dokumenterad basmodell och visar de andra separat. Confidence är LOW tills oberoende kalibrering är validerad. Temperaturkalibrering finns som historisk jämförelsekandidat.

## Använd som webbplats

Förberedda Render-inställningar finns i [publiceringsguiden](docs/PUBLICERING.md). De ger inloggning, beständig databas och automatisk källsynk varje timme när ett hostingkonto aktiverat tjänsten. En publik webbadress finns först efter faktisk publicering. Kontot och eventuell driftkostnad måste godkännas av dig.

## Snabbstart på macOS

### 1. Installera program

- **Homebrew**: följ installationsinstruktionen på https://brew.sh om det saknas.
- **Docker Desktop**: hämta från https://www.docker.com/products/docker-desktop/ och öppna programmet.
- Öppna **Terminal** och kör:

```bash
brew install uv node@22
export PATH="$(brew --prefix node@22)/bin:$PATH"
```

`uv` hanterar Python 3.12. Node 22 eller senare behövs. Git installeras vid behov med `xcode-select --install`.

### 2. Öppna projektmappen

Koden finns i Codex-arbetsytan `/workspace/test`. Hämta projektfilerna till din Mac och öppna mappen i Terminal. Koden har inte pushats till GitHub automatiskt, så ett tomt GitHub-repo innehåller inte denna leverans ännu.

Exempel om mappen finns i Hämtade filer:

```bash
cd ~/Downloads/Fotbolls-AI-v1
bash scripts/start.sh
```

**Detta är startkommandot för V1.** Det installerar låsta beroenden, skapar ett eget lokalt databaslösenord om `.env` saknas, startar PostgreSQL, migrerar tabellerna, synkar data, beräknar prognoser, bygger frontend och startar backend/frontend/uppdateringsarbetaren. Befintlig `.env` skrivs inte över. Det behövs inget dataleverantörskonto eller någon API-nyckel för dessa källor.

När Terminal säger att V1 körs: öppna `http://localhost:3000` i webbläsaren **på din Mac**. Stoppa appens processer med Ctrl+C i samma Terminal. Databasen ligger kvar. Kör aldrig `docker compose down -v` om du vill behålla data.

Om appen redan körs startar skriptet inte dubbla webbservrar. Arbetaren ska köras en gång per databas. Starta hela appen med skriptet från början för automatisk synk; en manuellt startad webbserver innebär inte att arbetaren också körs.

### 3. Använd appen

- **Dagens tips**: visar nästa 24 timmar, tre eller sju dygn. Välj liga, kandidater, alla matcher eller din bevakning.
- **Kandidat** betyder ett statistiskt förstaval att granska. Det är inte ett säkert spel eller belägg för att du går plus.
- **Avstå** visar varför underlaget inte räcker. Svaga matcher döljs inte. Det kan vara korrekt att inte ha någon kandidat alls.
- Bokmärket sparar en bevakning i din egen webbläsare. Det är inte en insats och synkas inte till andra enheter.
- **Visa analys & oddsjämförelse** visar modellerna, form, Elo, data som saknas och versionslogg. Finns en aktuell CSV-oddsobservation fylls den i; annars kan du ange tre decimalodds själv. Ursprunglig publiceringstid kan vara okänd. Manuellt jämförda odds loggas uttryckligen som manuella och ej leverantörsverifierade.
- **Prognoslogg** bevarar gamla versioner. JSON-export hämtar högst 500 senaste poster i valt real-/demoläge; hela loggen finns i databasen.
- **Modellprestanda** skiljer verkliga förhandsloggar från retrospektiv historisk forskning. Väntande matcher räknas inte som vinster.
- **Data & metodik** visar källstatus. **Synka källor nu** gör en bakgrundssynk och omberäkning. Begränsat till en manuell begäran per fem minuter. Automatisk synk körs varje timme; nätverksfel bevarar tidigare data.
- **Demodata** är ett separat syntetiskt labb med fiktiva lag. Det blandas inte med verkliga tips eller deras utvärdering.

## När V1 avstår

Den versionsbundna kandidatpolicyn kräver minst åtta resultat per lag, senaste lagresultat högst 35 dagar gamla, minst 52 % basmodellsannolikhet, minst 12 procentenheters avstånd till näst troligaste utfall, minst två samstämmiga förstaval och högst 25 procentenheters skillnad mellan modellernas sannolikheter för förstavalet. Dessutom avstår systemet vid saknade nyligen schemalagda resultat, okänd avsparkstid, ändrat/återtaget schema, inaktuell prognos eller för gammal källsynk.

**Trösklarna är försiktiga heuristiker, inte en historiskt bevisad lönsam strategi.** De gör inte LOW confidence till HIGH. Avsaknad av odds, skador och startelvor visas tydligt. De verkliga förhandsprognoserna måste utvärderas över tid innan påståenden om kvalitet eller lönsamhet kan göras.

## Databas och miljövariabler

PostgreSQL 16 används som standard via `compose.yaml`. `.env` skapas lokalt med slumpmässigt databaslösenord; inga betaluppgifter ingår. Exempel finns i `.env.example` om du vill konfigurera anslutningen själv.

| Variabel | Betydelse |
|---|---|
| `DATABASE_URL` | PostgreSQL-anslutning. Utan variabel används SQLite `backend/football.db` för lokala tester. |
| `POSTGRES_PASSWORD` | Lösenord för den lokala Docker-databasen. |
| `API_URL` | Frontendens serveradress till backend. Standard `http://127.0.0.1:8000`. Aldrig en publik API-nyckel. |
| `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS` | Standard 2 i startsystemet för måttlig CPU-användning. |

`.env`, `.venv`, databaser, Node-beroenden och `artifacts/` ignoreras av Git. Skriv aldrig hemligheter i kod, chatten eller `NEXT_PUBLIC_*`.

## Starta delarna separat

Från projektets rot, efter att Docker är öppet:

```bash
docker compose up -d --wait db
bash scripts/setup.sh
```

Backend, ett Terminal-fönster:

```bash
bash scripts/backend.sh
```

Frontend, ett andra fönster:

```bash
cd frontend
npm run dev
```

Arbetare, ett tredje fönster från projektets rot:

```bash
set -a
source .env
set +a
cd backend
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../.venv/bin/python -m app.worker --sync --interval 3600
```

Utan `--sync` omberäknar arbetaren bara från redan importerade data. Använd inte det som en påstådd live-feed. Inställningar som laddas i en Terminal överförs inte automatiskt till en annan.

## Tester och kontroller

Backend, från projektets rot:

```bash
set -a
source .env
set +a
cd backend
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../.venv/bin/python -m pytest -q
```

API-integrationstesterna förutsätter migrerad databas och demo från startsystemet. De rena modell-/sync-/policytesterna använder isolerade testdata. Tester täcker bl.a. dataläckage, sannolikheter, overround, virtuella förluster, schemarevisioner, återtagna matcher, strikt klubbidentifiering, API-validering och synkjobb.

Frontend, med appen igång:

```bash
cd frontend
npm run build
npx playwright install chromium
npx playwright test
```

På molnmaskinen används redan installerad `/usr/bin/chromium`; då behövs ingen ny Chrome-nedladdning. Webbläsartesterna kontrollerar desktop/mobil, verkliga matcher, separat demo, sparad bevakning, oddsjämförelse, logg, utvärdering och källstatus. Syntetisk utvärdering behöver finnas. Öppna en ny Terminal i projektets rot och kör:

```bash
set -a
source .env
set +a
cd backend
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../.venv/bin/python -m app.pipeline backtest --synthetic
```

Produktionsbygget kör TypeScript-kontrollen. En beroendevarning från Starlettes testklient kan förekomma; ingen kontroll är avstängd för att få godkänt resultat.

## Spårbarhet och reproduktion

Varje prognos bevarar `model_version`, `generated_at`, `data_cutoff_time`, `features_version`, schemarevision, exakta inputresultat och features. Modellkod och beroendelås arkiveras. Matchtidens användning som feature-referens skiljs från den faktiska informations-cutoffen: bara resultat som var kända före cutoffen får ingå.

Från `backend`, välj ett prognos-ID ur loggen:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../.venv/bin/python -m app.audit --prediction-id 1
```

Nya prognoser använder nya poster; gamla skrivs inte över. Databastriggers skyddar forskningsposter mot vanliga UPDATE/DELETE även via direkt SQL. En databasadministratör kan fortfarande ändra skydden; detta ersätter inte oberoende backup. Startsystemet och synkjobben sparar även en kontrollsummerad PostgreSQL-dump under `backend/artifacts/backups/`. Vid start återställs senaste dumpen endast om den lokalt hanterade databasen är tom; befintliga appdata och okända tabeller bevaras. Kopiorna är tidsstämplade och behöver en lagrings-/arkiveringsplan vid längre drift. Säkerhetskopiera **både PostgreSQL och `backend/artifacts/`** till en oberoende plats för långsiktigt skydd.

Boosting tränas på resultat som faktiskt är kända vid träningstillfället. För historiska träningsfeatures antas publicering efter matchdatum + 48 timmar eftersom källornas gamla publiceringstider saknas. Detta anges i prognossnapshoten. Antagandet används inte för att göra ännu okända resultat tillgängliga. Syntetisk träning använder sina registrerade tider. Modellernas råa sannolikheter är inte oberoende validerat kalibrerade för framtida matcher.

## Historisk forskning

OpenFootball-arkivet från 2023/24 bevaras separat. Aktuell synk tar även föregående säsong och aktuell säsong. Råfiler har källa, Git-revision eller URL, hämtningstid och SHA-256. Senare korrigeringar och återtagna matcher får nya observationer. En motsägande slutresultatrad avvisas för separat granskning; den skriver inte tyst över ett tidigare resultat.

Ett retrospektivt backtest, från `backend`:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 ../.venv/bin/python -m app.pipeline backtest --reconstructed --competition PL
```

`--reconstructed` antar resultattillgänglighet vid matchdatum + 48h. Det är en uttrycklig efterhandsanalys, **inte en verifierad historisk förhandslogg**. Utan flaggan används registrerade tillgänglighetstider; nyhämtad historik kan då ge n=0 för gamla matcher. Ett nollresultat validerar inte modellen.

Mått: multiclass Brier score (summa över tre klasser, 0–2), log loss, träffsäkerhet, reliability-kurvor och sample size. Råa och temperaturkalibrerade kandidater jämförs separat. Olika sample size måste matchas innan rättvis modellrangordning. Modellval och kandidatgränser är inte godkända för lönsamhetsanspråk.

Förhandsuppföljningen väljer enligt en fast regel senaste loggade prognos strikt före avspark, en per match. Även felaktiga prognoser räknas. Tidigare versioner går att granska i loggen. ROI visas endast för registrerade virtuella observationer med odds, inte genom att förvandla korrekta förstaval till påstådd vinst.

## Egna verifierade CSV-filer

Från `backend` med rätt `.env` laddad. Alla tider ska ha tidszon, t.ex. `2026-11-01T15:00:00Z`. Källnamn får inte innehålla hemligheter. Ligakoder: PL, LL, BL, SA, L1, CL, EL. Lag-ID och match-ID måste vara stabila.

Historik:

```csv
id,competition_id,season,home_id,away_id,kickoff,available_at,result_available_at,home_goals,away_goals
```

```bash
../.venv/bin/python -m app.pipeline import --csv /sökväg/historik.csv --source min-källa
```

Spelschema:

```csv
id,competition_id,season,home_id,away_id,kickoff,available_at
```

```bash
../.venv/bin/python -m app.fixtures --csv /sökväg/spelschema.csv --source min-källa
../.venv/bin/python -m app.pipeline predict
```

Odds:

```csv
match_id,available_at,home,draw,away
```

```bash
../.venv/bin/python -m app.odds_import --csv /sökväg/odds.csv --source min-oddskälla
```

Decimalodds normaliseras proportionellt: `(1/odds) / sum(1/odds)`. Det tar bort överrundningen under ett uttryckligt antagande; det avslöjar inte sanna sannolikheter. En virtuell observation kan registreras via `app.paper.record(prediction_id, odds_snapshot_id, outcome)` med fast 1 unit; den kräver förhandsprognos och tidigare observerade odds och avvisas efter avspark. Inga riktiga spel genomförs.

## Felsökning

- **Docker nås inte:** öppna Docker Desktop och vänta tills det är igång.
- **Port 3000/8000 upptagen:** stoppa tidigare egna app-processer. Startsidan i en annan app är inte bevis att rätt backend körs. `curl http://localhost:8000/api/status` ska ange version 1.0.0.
- **Alla matcher har Avstå:** läs skälen. Källan kan vara ofullständig, modellen kan sakna historik eller modellerna kan skilja sig. Trösklarna ska inte sänkas för att producera fler tips.
- **Molnmaskinen nekar datakälla:** nätinställningarna behöver tillåta `github.com`, `raw.githubusercontent.com`, `www.football-data.co.uk` och redirectvärden `football-data.co.uk`. Sparad konfiguration och aktiv nätpolicy är olika saker; testa operationen igen efter ändring.
- **Odds saknas:** kommande priser finns inte alltid i det officiella CSV-schemat. Skriv inga påhittade värden. Manuell jämförelse är tydligt märkt och saknar leverantörsverifiering.
- **Saknade lagidentiteter:** importen använder explicita alias och entydig normalisering, inte ungefärlig stavningsmatchning. Oklara rader redovisas som omatchade.

Appen är avsedd för privat personligt bruk. Offentlig fleranvändardrift, autentisering och externt förvaltad produktionsdatabas ingår inte i denna leverans. Ingen publicering, GitHub-push eller aktivering av en ny miljösnapshot görs automatiskt.
