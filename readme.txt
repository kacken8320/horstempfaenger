discord rss feed
================

message format
--------------

- tier (T1 (major agency)/T2 (minor agency)/T3/T4/...)
- outlet name
- country of origin
- grobe ausrichtung
- title
- date
- content (summary/body)
- author
- further reading: http://linktofullarticle.com/

tier 1 (agencies)
-----------------

geopolitically the most interesting agencies:

- reuters
- ap
- kyodo
- dpa
- afp

tier 2 (agencies)
-----------------

- jiji
- antara
- pa media
- efe
- sda

geplant: jev als entscheidungs-filter (noch NICHT implementiert)
----------------------------------------------------------------

jev (typesafe, ueber openrouter: POST https://openrouter.ai/api/alpha/decisions,
model typesafe/jev-1.13) ist kein llm, sondern eine "decision engine": man gibt
state + typisierte fragen (noul = ja/nein, choice = eine option, score = skala)
und bekommt antworten mit wahrscheinlichkeiten zurueck. kein text, output
kostet nichts, 32k token kontext, ~70-500 ms pro call.

zwei entscheidungen pro frisch gefetchtem artikel (zentral in main.py, nach
dem 5-min-freshness-check, vor dem tier-cap, gilt fuer ALLE outlets):

1. relevanz: passt der artikel zu dem, was ich sehen will?
   - die beschreibung steht als liste/satz im code (z.B. RELEVANCE_PROFILE in
     einer eigenen datei), leicht aenderbar. beispiele: kategorien-pool
     ("politics", "economy", "war", "finance", "china") ODER freitext
     ("alles zu politik, wirtschaft, technik, regionales aus deutschland, aber
     nichts mit celebrities").
   - state = titel + erste ~256 zeichen summary, frage = noul "gehoert dazu?".
   - nein -> verwerfen (als gesehen markieren, nicht posten).

2. duplikat-check gegen den "pool von heute":
   - pool = titel (+ tier) aller heute schon gepostet/akzeptierten artikel.
   - frage = choice "berichtet einer dieser pool-eintraege ueber dasselbe
     ereignis?" (optionen: "none" + ein eintrag pro pool-titel).
   - nicht im pool -> posten, in den pool aufnehmen.
   - schon im pool, neue tier HOEHER (z.B. T0 vs T2) -> posten (kommt rein).
   - schon im pool, neue tier gleich oder NIEDRIGER -> verwerfen.

entscheidungen / offene punkte:
- fail-open: wenn jev/openrouter nicht antwortet, artikel durchlassen statt
  droppen (sonst schweigt der bot bei einem ausfall).
- unsicherheit: unter einer confidence-schwelle (z.B. 0.6) lieber durchlassen.
- t0/t1 sind vom cycle-cap ausgenommen; ob sie auch den relevanz-filter
  umgehen sollen (z.B. reuters/dpa), ist noch zu entscheiden.
- pool darf nicht ueber 32k token wachsen -> nur letzte ~12-24h und max. ~800
  titel; aeltere raus.

deployment (railway):
- neue env var OPENROUTER_API_KEY (railway variables + lokale .env, steht
  nicht im repo; .env.example ergaenzen).
- modell fest auf typesafe/jev-1.13 pinnen, nicht den ~jev-latest alias (api
  ist "alpha", antwortformat kann sich aendern).
- pool muss einen neustart ueberleben -> in state.db (eigene tabelle oder
  seen_articles mit title/tier der letzten 24h); setzt voraus, dass data/ auf
  railway auf einem persistenten volume liegt.
- ausgehender traffic zu openrouter.ai; titel/summaries gehen an einen dritten
  (typesafe), datenschutz-policy auf der jev-modellseite pruefen.
- rate limits sind in der doku nicht genannt -> bei 429 backoff + fail-open.
- kostenlimit auf dem openrouter-konto setzen.

kosten (grobe schaetzung, $0.042 pro 1m input-token, output gratis):
- annahme: 40 outlets, ~2000-4000 frische artikel/tag, davon ~1000 relevant.
- entscheidung 1: ~250 token/call (titel+summary+profil) x 3000 = 0.75m
  token -> ca. $0.03/tag.
- entscheidung 2: pool schickt jedes mal alle titel mit (~20 token/titel);
  pool waechst von 0 auf ~1000 titel = im schnitt ~10k token x 1000 calls =
  10m token -> ca. $0.42/tag, bei vollem pool (~20k) ca. $0.85/tag.
- gesamt ca. $0.5-1 pro tag, also ~$15-30 pro monat. entscheidung 2 ist der
  kostentreiber; pool-groesse begrenzen haelt es klein.
