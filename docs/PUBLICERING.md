# Publicera din personliga Fotbolls-AI

Vald driftplats: **Render**, så du får en adress på tjänstens domän och inte behöver köpa ett eget domännamn. `render.yaml` och `deploy/render.Dockerfile` beskriver webbapp, PostgreSQL, beständigt modellarkiv och en arbetare som hämtar data varje timme. Webbplatsen skyddas med inloggning. Riktiga spel och betalningar finns inte i appen.

## Steget som kräver dig

En extern tjänst kan inte aktiveras utan ditt hostingkonto och godkännande av dess villkor/pris. Den valda konfigurationen använder betald, kontinuerligt körande drift i stället för en tjänst som somnar. Kontrollera priset i Render innan du bekräftar. Ingen hostingavgift har godkänts automatiskt.

1. Logga in eller skapa konto på https://render.com och anslut ditt GitHub-konto.
2. Välj **New → Blueprint** och repot `colinsand2000/test` på grenen `main`.
3. Render läser `render.yaml`. Granska de två resurserna och priset. Bekräfta först när du vill aktivera driften.
4. När bygg- och hälsokontrollerna är klara visar Render den **faktiska webbadressen**. Den går inte att fastställa innan tjänsten är skapad.
5. Öppna webbservicens Environment-inställningar. Användarnamnet är `owner`; lösenordet finns i den automatiskt genererade `SITE_PASSWORD`. Ange aldrig lösenord eller databasuppgifter i chatten.
6. Öppna adressen och logga in. Kontrollera källstatus och tidpunkten för senaste uppdateringen.

Direkt ingång till Blueprint-publicering:
https://render.com/deploy?repo=https://github.com/colinsand2000/test

**Detta är en publiceringslänk, inte en redan publicerad webbplats.** Privat GitHub-repo kräver att Render får åtkomst genom ditt konto. Plan-/schemaacceptans och faktisk drift måste verifieras i Render; en lokal Dockerbuild bevisar inte att kontot är aktiverat.

## Uppdatering varje dag

Arbetaren kör en källsynk och omberäkning varje timme, vilket ger uppdateringar varje dag så länge tjänsten körs. Vid nätfel bevaras äldre observationer. Inaktuell/ofullständig data ger Avstå; det hävdas inte att en misslyckad synk lyckades. Uppdateringstidpunkterna visas i appen.

Webbserver, API och arbetare övervakas tillsammans. Om en process avslutas avslutas tjänsten, så driftplatsen kan starta om den. PostgreSQL och modellarkivet är separata beständiga resurser. Aktivera och verifiera databasbackup/återställning hos driftplatsen; lokala Docker-backuper är inte en verifiering av Renders backupfunktion.

## Inloggning och hälsokontroll

`REQUIRE_SITE_AUTH=true` måste vara aktivt. `SITE_PASSWORD` genereras av Render och ska inte läggas i Git. Utan konfigurerat lösenord blockeras appen. Endast `/api/health` är öppet för driftplatsens hälsokontroll; det visar inga tips eller privata uppgifter. API-processen lyssnar enbart internt i containern.

## Modellernas gräns

Löpande datainsamling eller publicering gör inte matcher stensäkra. Kandidaterna är statistiska förstaval, inte verifierade vinstlöften. Det finns ingen styrkt framtida lönsamhet. Fem nationella ligor stöds; CL/EL och spelarfrånvaro saknar fortfarande verifierad aktuell källa.
