# Fotbolls-AI V1 · leveransens omfattning

V1 är en personlig analysapp utan betalningar, insatsråd eller automatisk spelplacering. Modellkandidater är förstaval att granska, inte säkra spel eller bevis på lönsamhet.

## Implementerat

1. PostgreSQL/SQLite, Alembic 001–003, separata källor och hämtning-/tillgänglighetstider.
2. Automatisk OpenFootball-synk av aktuell och föregående säsong för PL/LL/BL/SA/L1. CC0, låsta Git-revisioner per hämtning, rådatacache och checksummor.
3. Officiell football-data.co.uk-CSV som kompletterande källa för resultat, skott/hörnor och observerade kommande odds när de publiceras. Entydig klubbidentifiering med explicita alias. Oklara matchningar redovisas och gissas inte.
4. Versionslogg för schemauppdateringar, återtagna och återinförda matcher. Motsägande slutresultat avvisas för granskning.
5. Tidsstyrda features, Poisson/Elo/boosting, ensemblekandidat, walk-forward och temperaturkalibreringskandidater. Boosting använder en dokumenterad +48h-antagandemodell för historiska träningsfeatures men endast faktiskt kända labels vid träningstillfället.
6. Versionsbunden kandidatpolicy med avstå vid tunn/gammal/ofullständig data, modellskillnader, gamla prognoser och ändrat schema. Ingen HIGH/MEDIUM confidence utan oberoende kalibrering.
7. Tipsöversikt, ligor/tidsperiod, lokal bevakning, matchanalys, CSV-odds där tillgängliga, manuell oddsjämförelse, marginalnormalisering och nollresultatströskel.
8. Append-only-prognoslogg, exakt inputsnapshot, kod-/beroendearkiv, reproduktion, JSON-export och separat uppföljning av förhandsprognoser. Väntande matcher räknas inte som vinster.
9. Bakgrundssynk via UI, jobbstatus, femminutersbegränsning, databasbundet processlås och timvis arbetare.
10. Kontrollsummerade PostgreSQL-backuper under arbetsytan och automatisk återställning enbart till tom lokalt hanterad databas.
11. Start med ett kommando (`bash scripts/start.sh`), migrations-/setupskript, macOS-guide, automatiska backend-/webbläsartester och CI.

## Medvetna gränser

- CL/EL saknar en verifierad aktuell källa. Den granskade öppna UEFA-källan saknar säsong 2026/27 och ger därför inte tillförlitliga aktuella scheman för denna leverans.
- xG, skador, avstängningar och startelvor saknar ansluten källa. Tabellen/schema är förberett, men UI visar Saknas.
- Offentliga scheman är inte realtidsverifierade; väggklocketider tolkas i ligans dokumenterade tidszon. Okända tider ger ingen prognos.
- CSV-odds är indirekta källobservationer med okänd ursprunglig publiceringstid; de är inte garanterat aktuella bookmakerpriser. Manuella odds märks som manuella.
- Historiska efterhandsanalyser är inte certifierade förhandsloggar. Separat framåtriktad utvärdering börjar med de prognoser V1 faktiskt registrerar före avspark.
- Ingen lönsamhet är verifierad. Kandidatgränser är heuristiker. Kalibrering/ensemble har inte godkänts via en oberoende framtida holdout.
- Privat bruk, ingen offentlig fleranvändardrift eller automatisk GitHub-publicering.
