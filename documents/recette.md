# Rapport de recette

**Équipe :** karelle-koulibaly (projet solo). **Date :** 26/11/2026. **Exécutant/relecteur :** karelle-koulibaly / relecteur à renseigner (revue croisée).
**Commit applicatif :** 306aaaa. **Digests API/web :** non applicable (aucune image construite en S2).
**Contexte de déploiement et commit de configuration :** poste Windows, API Uvicorn sur le poste, PostgreSQL 17 dans Docker (`compose.dev.yaml`).

## 1. Conditions d'exécution

- Poste Windows (Git Bash), Python 3.14.3, Docker Desktop 29.0.1, PostgreSQL 17-alpine.
- Base d'essais `campus` (port publié 5433) ; base de tests `campus_test`, vidée avant chaque test (`TRUNCATE datasets CASCADE`). `conftest.py` refuse de tourner si `DATABASE_URL` ne se termine pas par `_test`.
- Données de départ : trois fichiers de `data/`. Heure de référence fixe `NOW = 2026-11-16` dans les tests.
- Écarts de configuration : port DB publié **5433** (5432 déjà occupé par un PostgreSQL local), port web publié **8090** (8080 occupé par un autre conteneur).
- Aucun mot de passe ni DSN complet dans ce document.

## 2. Résultats par exigence

| ID | Préconditions | Action / commande | Attendu | Observé | Preuve | Résultat |
|---|---|---|---|---|---|---|
| R1 Tables | DB `campus` vide | `python -m app.init_db` deux fois, puis `\d measurements` | 3 tables ; UNIQUE, 3 CHECK, 2 FK CASCADE ; 2e exécution sans erreur | « Tables prêtes : datasets, ingestions, measurements » deux fois ; `uq_measurement`, `ck_co2`, `ck_temperature`, `ck_humidity` et 2 FK `ON DELETE CASCADE` présents | `proofs/s2-tables.txt` (si créé) | validé |
| R2 Création et erreurs de dépôt | API lancée, jeu « Batiment A » | `curl` : création, dépôt, relecture ; nom en double ; type JSON ; corps vide | 201, 202 `pending` ; 409 ; 415 ; 422 | dépôt `pending` ; 409, 415, 422 | sorties du terminal | validé |
| R3 Fichier de référence | jeu vide | dépôt de `mesures-salles-2026-10-05.csv`, `worker --once` | succeeded, 63 / 0 / 0 ; 63 mesures | succeeded, 63 / 0 / 0 ; `measurement_count` = 63 ; code de sortie 0 | `proofs/s2-tests.txt` | validé |
| R4 Fichier d'erreurs | jeu vide | dépôt de `mesures-avec-erreurs.csv`, worker | succeeded, 4 acceptées, 7 rejetées, 1 doublon | worker : « succeeded (4 acceptées) » ; jeu à 4 mesures ; erreurs lignes 5, 6, 7, 8, 9, 10, 12 avec les raisons du contrat (`parse_csv`) ; test automatique vert | `proofs/s2-tests.txt` | validé |
| R5 En-tête invalide | jeu vide | dépôt de `en-tete-invalide.csv`, worker | failed, `Invalid header`, 0 mesure | worker : « failed (Invalid header) » ; jeu à 0 mesure | `proofs/s2-tests.txt` | validé |
| R6 Idempotence | jeu de 63 mesures | 2e dépôt du fichier de référence, worker | 0 acceptée, 63 doublons, toujours 63 mesures | worker : « succeeded (0 acceptées) » ; jeu toujours à 63 mesures ; test automatique vert | `proofs/s2-tests.txt` | validé |
| R7 Indicateurs | jeu de 63 mesures | `GET /stats?room=A101` | 21 mesures, CO₂ moyen 636.1, min 430, max 1092 | `{"measurements":21,"co2_avg":636.1,"co2_min":430,"co2_max":1092}` | sortie du terminal | validé |
| R8 Relance refusée | dépôt `succeeded` | `POST /retry` | 409 | 409 | log API | validé |
| R9 Période inversée | jeu de 63 mesures | `GET /stats?from=…06&to=…05` | 422 | 422 | log API | validé |
| R10 Relance d'un dépôt failed | dépôt `failed` | clic sur « Relancer » dans l'interface, puis worker | repasse à `pending`, puis de nouveau `failed` | worker : « failed (Invalid header) » après la relance | sortie du terminal | validé |
| R11 Flux Kafka | Kafka démarré, consommateur lancé, jeu du flux neuf | `python -m app.simulator --count 30 --interval 1` | 30 messages : 24 acceptées, 3 rejetées, 3 doublons | `{"rows_total":30,"rows_accepted":24,"rows_rejected":3,"rows_duplicate":3}` ; raisons : Invalid humidity_pct, Invalid co2_ppm, Invalid message | `proofs/s2-kafka.txt` | validé |
| R12 Tests automatiques | `campus_test` initialisée | `python -m pytest -q` | tous verts | 21 passed, 1 avertissement (httpx, sans conséquence) | `proofs/s2-tests.txt` | validé |
| R13 Qualité du code | venv actif | `python -m ruff check api` | « All checks passed! » | 3 erreurs au premier passage (import `datetime` en double dans `ingestion.py`) ; relance après correction : **à compléter** | `proofs/s2-ruff.txt` | à compléter |
| R14 Interface | API et proxy lancés | page ouverte sur http://127.0.0.1:8090 | liste des jeux, version affichée | page chargée, 5 jeux affichés avec leur nombre de mesures, « Version : dev » | capture d'écran | validé (partiel) |
| R15 Parcours complet de l'interface | idem | dépôt, rapport, filtres, suppression avec annulation et confirmation | voir la page de la séance 2 | **non exécuté** (à compléter après le parcours) | - | non exécuté |
| R16 Readiness | tables absentes puis présentes | `/health/ready` avec DB arrêtée, puis avec tables absentes | 503 puis 200 | 200 `{"status":"ready"}` observé avec les tables présentes ; cas d'erreur **non exécuté** | log API | validé (partiel) |

## 3. Cas méthodologique : second dépôt

- **Précondition :** jeu « Batiment A » avec 63 mesures.
- **Action :** 2e dépôt du même fichier, puis `python -m app.worker --once`.
- **Attendu :** `succeeded`, 0 acceptée, 63 doublons, `measurement_count` toujours à 63.
- **Observé :** worker « succeeded (0 acceptées) » ; `measurement_count` = 63 à la relecture ; le test `test_second_upload_adds_nothing` vérifie aussi les 63 doublons.
- **Conclusion :** l'idempotence est assurée par `UNIQUE (dataset_id, room, measured_at)` et `ON CONFLICT DO NOTHING`.

## 4. Expériences de déploiement et de reprise

Non exécutées en séance 2 : persistance Compose, réconciliation API, panne DB, cloud, rollback et restauration relèvent des séances 3 à 6.

## 5. Anomalies connues

| ID | Reproduction minimale | Attendu/observé | Impact | Priorité | Correction ou contournement | État |
|---|---|---|---|---|---|---|
| A1 | `ruff check api` après ajout de la règle 4 | Attendu : aucune erreur ; observé : import `datetime` en double | Technique (qualité) | Basse | Une seule ligne `from datetime import datetime, timedelta, timezone` | Corrigé, à re-contrôler (R13) |
| A2 | Flux Kafka : lire le rapport | Attendu (page) : raisons dans l'ordre 5, 15, 25 ; observé : ordre différent | Aucun : les trois raisons sont présentes | Basse | Comportement normal : 3 partitions lues en parallèle, l'ordre n'est garanti qu'au sein d'une partition | Clos (expliqué) |
| A3 | `docker compose up` avec les ports du kit | Ports 5432 et 8080 déjà utilisés sur le poste | Démarrage impossible | Moyenne | Ports publiés changés : 5433 (DB) et 8090 (web) | Clos |

## 6. Synthèse de remise

- **Validés :** tables et contraintes, API (création, dépôt, relance, indicateurs), worker (4 résultats attendus), flux Kafka (24 / 3 / 3), 21 tests verts.
- **Restant à vérifier :** Ruff après correction (R13), parcours complet de l'interface (R15), cas d'erreur de la readiness (R16).
- **Non exécuté :** persistance, Kubernetes, cloud, rollback, restauration (séances 3 à 6).
- **Limites :** pas de reprise automatique d'un dépôt resté `running` après un arrêt brutal du worker ; schéma gelé (`create_all`).
- **Preuves :** dossier `proofs/` (`s1-socle.txt`, `s2-tests.txt`, `s2-kafka.txt`, `s2-ruff.txt`). **Version à évaluer :** le commit S2.