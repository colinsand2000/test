# Fotbolls-AI 1.0

Personlig analys för fem nationella ligor med källsynk, modellbaserade kandidater/avstå, oddsjämförelse, bevakning och reproducerbar prognoslogg. Inga betalningar eller automatiska spel.

Start: `bash scripts/start.sh` från projektets rot. Se README för macOS-förberedelser.

Källkodspaketet innehåller inga hemligheter, databasfiler, beroendekataloger eller privata körningsartefakter. En ny installation hämtar aktuella data och skapar egna prognoser. Exakta gamla prognoser kräver den ursprungliga databasbackupen och dess kod-/inputarkiv, som bevaras separat i arbetsytan.

42 backendtester, två webbläsartester, faktisk källhämtning, prognosreproduktion och databasåterställning verifierades i Linux-molnmiljön. macOS-instruktionerna är skrivna för Mac; ingen fysisk Mac-körning har verifierats.

CL/EL, xG och spelarfrånvaro har ingen ansluten aktuell källa. Ingen lönsamhet eller stensäkerhet har verifierats.
