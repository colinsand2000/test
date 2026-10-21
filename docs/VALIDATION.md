# V1-verifiering · 2026-10-21

## Funktionell verifiering

- PostgreSQL 16 med Docker Compose, migrationer 001–003. SQLite-migrationer och direkt-SQL-skydd testas separat.
- Pythonberoenden låsta i `backend/requirements.lock`; Nodeberoenden i `frontend/package-lock.json`.
- **42 backendtester godkända.** Backendtester täcker sannolikheter, odds/marginal, P/L inklusive förluster, strikt tidsfilter, okända framtida labels, walk-forward, kalibrering, källformat, schemasynk, återtagna/återinförda matcher, avstå-regler, ofullständiga resultat, oddsvalidering, jobbstatus, importidentifiering, ORM-immutabilitet och SQL-triggers.
- Faktisk ny prognos med Poisson, Elo, gradient boosting och ensemblekandidat återskapad från arkiverad kod och inputhistorik. Sannolikheter matchade inom 1e-10.
- Frontendens produktionsbygge kör även TypeScript-kontroll.
- **2 Playwrighttester godkända.** Playwright kör desktop 1440×1000 och mobil 390×844: verklig tipslista, isolerad demo, bevakning som överlever omladdning, manuell oddsjämförelse, nollresultatströskel, versionslogg, väntande utfall, utvärdering och källstatus.
- Testklienten ger en Starlette/httpx-deprecationsvarning. Inga kontroller har stängts av för att få godkänt resultat.

## Faktisk datainsamling

OpenFootball-revision `e6744429ee395bc86f247348c6184bb08d4eb361` och officiella CSV-hämtningar har använts. Fem ligors nuvarande/föregående säsonger har importerats. Det äldre 2023/24-arkivet med 1 752 resultat bevaras.

football-data.co.uk var först blockerad av molnnätpolicyn. Senare lyckades den verkliga hämtningen. Vid slutkontrollen fanns 3 848 verkliga resultat i PostgreSQL. Den officiella kompletteringen fyllde saknade resultat och matchstatistik. Alla rader som nådde identifieringskontrollen i slutkörningen fick entydig klubbmatchning; ofullständiga tids-/resultatuppgifter är fortfarande synliga som saknade.

V1 visade vid omberäkningen **52 kommande matcher, 18 modellkandidater och 34 avstå-markeringar**. Detta är ett ögonblicksvärde som kan ändras när källor och tid uppdateras. Kandidaterna är inte verifierat lönsamma. En kommande oddsobservation fanns vid den officiella CSV-körningen; övriga saknade priser fabricerades inte.

Systemet gav tidigare korrekt Avstå för samtliga 52 matcher när resultatunderlaget var ofullständigt. Kraven sänktes inte för att skapa tips. Kandidater uppstod först efter datakomplettering och omberäkning.

## Modellkvalitet

Äldre retrospektiv körning för 2023/24 omfattar 1 676 utvärderade matcher efter uppvärmning. Poisson gav 52,57 % träffsäkerhet, Brier 0,5930 och log loss 0,9940. Ensemblekandidatens Brier/log loss var sämre och den uppgraderades inte. Denna rapport avser den då arkiverade modellversionen och är inte bevis för den senaste V1-versionens framtida kvalitet.

Historiska publiceringstider är antagna vid matchdatum +48h i rekonstruerad forskning. Modeller med olika n måste jämföras på gemensamt urval innan rättvis rangordning. Ingen separat framtida holdout har ännu styrkt lönsamhet eller HIGH confidence.

Förhandsloggen hade vid kontrollen **0 avgjorda matcher** och väntande verkliga prognoser. Det redovisas som saknade kvalitetsmått, inte som godkänt resultat. Manuell oddsjämförelse är matematiskt verifierad men är inte en verifiering av modellens sannolikheter eller marknadens pris.

## Driftgränser

Inga betaluppgifter, betalningsintegrationer eller riktiga insatser finns. Startsystemet stöder privat lokal användning och lösenordsskyddad Render-drift. Källkoden har pushats till GitHub. Ingen extern driftsättning har genomförts.

CL/EL, xG, frånvaro och startelvor har ingen ansluten aktuell källa. Källstatus visar detta. Källornas publiceringstid är inte alltid känd och de är inte realtidsfeeds.

Installations- och startkonfiguration sparas separat i miljöutkastet. Sparat utkast, aktuell körning och publicerad återställbar snapshot är olika saker. En rapporterad miljöomstart under arbetet avbröt en startsession; tjänsterna startades därefter om från de bevarade filerna. Ingen fullständig nyuppgiftsåterställning ska anses verifierad enbart av detta.

## Backup och återstart

Hela appen startades via `bash scripts/start.sh`: installation, PostgreSQL, migrationer, två källsynkar, prognoser, frontendbygge, webbservrar och timvis synkarbetare. Faktiska proxyanrop verifierade 52 matcher/18 kandidater/34 avstå, fem anslutna nationella ligor och en aktuell indirekt CSV-oddsobservation. Prognos #310 reproducerades med alla fyra modellutdata.

En kontrollsummerad PostgreSQL-dump på cirka 10,9 MB skapades under arbetsytans artifacts. Den återställdes till en separat tillfällig databas och prognosantalet verifierades mot originalet; testdatabasen togs därefter bort. Återställningsvakten bekräftade att befintliga appdata inte skrivs över. Detta verifierar backupens återställbarhet, inte en publicerad molnsnapshot eller extern katastrofåterställning.

## Hostingkontroller

46 backendtester och frontendens produktionsbygge passerade. Separat inloggningstest verifierade 401 utan inloggning, 200 med korrekt lösenord och 503 när obligatoriskt lösenord saknas. Render-avbildningen byggdes med låsta beroenden. Plattformens plan, fakturering och faktiska externa driftsättning behöver verifieras efter kontoaktivering.

Ett isolerat containertest med tom SQLite-databas verifierade migreringar, paketerad API/frontend, health 200, anonym sida 401 och autentiserad sida 200. Testet körde inte Render-plattformen eller extern källsynk.
