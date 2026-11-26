# Dossier de conception - CampusData

**Membres :** Karelle-koulibaly (projet solo). **Version du dossier / commit :** S1 `ddb7d47`, S2 `306aaaa`.
**Date de revue :** 26/11/2026. **Relecteur :** à renseigner (revue croisée, tâche 8).

## 1. Besoin et utilisateurs

1. L'équipe data du campus utilise l'application.
2. Aujourd'hui, les CSV des capteurs sont recopiés à la main dans un tableur, ce qui crée des erreurs et des doublons.
3. Elle dépose un fichier CSV et consulte le rapport de traitement et les indicateurs par salle.
4. On conserve les jeux de données, l'historique des dépôts et les mesures (salle, date, CO₂, température, humidité).
5. Sont exclus : connexion utilisateur, IA, temps réel.

**Scénario de démo :** ouvrir l'appli vide → créer un jeu → déposer `mesures-salles-2026-10-05.csv` → attendre `succeeded` (63 acceptées) → lire les indicateurs → redéposer le fichier (0 acceptée, 63 doublons).

**Cas d'erreur :** déposer `en-tete-invalide.csv` → `failed`, « Invalid header », aucune mesure insérée.

- Problème observé : fichiers CSV recopiés à la main dans un tableur, avec doublons et lignes erronées.
- Résultat attendu : déposer un CSV, voir les lignes rejetées avec leur raison, consulter les indicateurs par salle.
- Périmètre retenu : US01 à US10. Le responsable déclaré est un simple texte, pas un compte authentifié.
- Exclusions : connexion utilisateur, IA, temps réel. Toutes les données sont fictives.

## 2. Backlog et critères d'acceptation

| ID | En tant que… je veux… afin de… | Priorité | Étant donné / Quand / Alors | Cas d'erreur | Responsable | Test/preuve |
|---|---|---|---|---|---|---|
| US01 | créer un jeu de données | Haute | Étant donné aucun jeu « salle-A », quand je le crée, alors l'API répond 201 et il apparaît dans la liste | Nom déjà utilisé : 409 | Moi | `test_create_dataset`, `test_name_errors` |
| US02 | lister et ouvrir les jeux | Haute | Étant donné un jeu de 63 mesures, quand j'ouvre la liste, alors je vois « 63 mesures » | Id inconnu : 404 | Moi | `test_unknown_and_malformed_ids`, R2 |
| US03 | supprimer un jeu | Moyenne | Étant donné un jeu avec des mesures, quand je confirme, alors le jeu et ses mesures sont supprimés | Si j'annule, aucune requête n'est envoyée | Moi | `test_delete_dataset` (API) ; confirmation et annulation dans l'interface : non exécuté (R15) |
| US04 | déposer un fichier CSV | Haute | Étant donné un jeu vide, quand je dépose le fichier de référence, alors l'API répond 202 et le dépôt est pending | Fichier vide : 422 Empty file, aucun dépôt créé | Moi | `test_upload_is_pending`, `test_upload_refused` |
| US05 | voir mon dépôt traité | Haute | Étant donné un dépôt pending, quand le worker l'a traité, alors il est succeeded (63 acceptées, 0 rejetée, 0 doublon) | en-tete-invalide.csv : failed, « Invalid header », 0 mesure | Moi | `test_reference_file`, `test_invalid_header_and_retry` |
| US06 | voir les lignes rejetées | Haute | Étant donné mesures-avec-erreurs.csv, alors 4 acceptées, 7 rejetées, 1 doublon, chaque rejet avec sa raison | co2_ppm = abc : ligne rejetée et comptée, le dépôt continue | Moi | `test_error_file` |
| US07 | redéposer sans doublon | Haute | Étant donné un jeu de 63 mesures, quand je redépose le même fichier, alors 0 acceptée, 63 doublons, toujours 63 mesures | Un doublon est ignoré et compté, jamais une erreur | Moi | `test_second_upload_adds_nothing` |
| US08 | consulter les indicateurs | Moyenne | Étant donné plusieurs salles, quand je filtre salle et période, alors je vois moyenne, min, max | Période sans mesure : liste vide ; from ≥ to : 422 | Moi | `test_stats` |
| US09 | relancer un dépôt échoué | Basse | Étant donné un dépôt failed, quand je le relance, alors il repasse à pending | Dépôt non failed (ex. succeeded) : 409 | Moi | `test_invalid_header_and_retry` |
| US10 | compter sur un service fiable | Moyenne | Étant donné un jeu rempli, quand je redémarre les conteneurs, alors les données sont toujours là | Base indisponible : 503 | Moi | gestionnaire 503 dans `main.py`, non testé ; persistance à prouver en S3 |

## 3. Maquettes et interactions

### Écran 1 : jeux de données

```
CampusData                                         Version : abc123

Nouveau jeu de données
Nom*         [____________________]   (3 à 120 caractères)
Description  [____________________]
Responsable  [Équipe______]   [ Créer ]    <message de résultat / erreur>

Jeux de données
Nom                    Responsable   Mesures   Créé le
Qualité air - bât. A   Équipe A          63    2026-11-16   [Ouvrir] [Supprimer]
```

| État | Ce que l'utilisateur voit |
|---|---|
| Chargement | « Chargement des jeux… », bouton Créer actif |
| Liste vide | « Aucun jeu de données. Créez-en un ci-dessus. » |
| Données visibles | Tableau avec nom, responsable, nombre de mesures, date |
| Erreur | « Impossible de charger les jeux (service indisponible). » + bouton Réessayer |

Messages du formulaire : 409 → « Ce nom est déjà utilisé » ; 422 → « Nom trop court (3 caractères minimum) ». Après un échec, les champs saisis restent remplis. Pendant l'envoi, le bouton Créer est désactivé, puis réactivé dans un `finally`.
Suppression : une confirmation affiche le nom du jeu et le nombre de mesures supprimées avec lui. Si j'annule, aucune requête n'est envoyée.

### Écran 2 : un jeu, ses dépôts et ses indicateurs

```
Qualité air - bât. A                                  63 mesures

Déposer un fichier CSV   [ Choisir un fichier ] [ Déposer ]
Dépôts   [ Tous les statuts v ] [ Actualiser ]
Fichier                    Statut      Acceptées Rejetées Doublons  Déposé à
mesures-avec-erreurs.csv   succeeded          4        7        1   10:42  [Rapport]
en-tete-invalide.csv       failed             -        -        -   10:40  [Relancer]

Indicateurs   Salle [toutes v]  Du [____]  Au [____]  [Filtrer]
Salle  Mesures  CO₂ moy.  CO₂ min  CO₂ max  Temp. moy.  Hum. moy.  Dernière mesure
A101       21     636.1      430     1092      20.3        44.2     05/10 18:00
```

| Liste | Chargement | Vide | Données visibles | Erreur |
|---|---|---|---|---|
| Dépôts | « Chargement des dépôts… » | « Aucun dépôt. Déposez un CSV. » | Tableau ci-dessus | « Erreur de chargement » + Réessayer |
| Indicateurs | « Calcul… » | « Aucune mesure pour ce filtre. » | Tableau par salle | « Période invalide (Du doit précéder Au) » ou « Service indisponible » |

Un dépôt accepté affiche d'abord `pending` : 202 signifie « reçu », pas « traité ». L'interface interroge le statut toutes les 2 s, au plus 60 fois, jusqu'à `succeeded` ou `failed`.
Accessibilité : chaque champ a un `<label>`, les boutons sont utilisables au clavier, les tableaux ont un `<caption>` et des `<th scope="col">`. Les valeurs sont affichées avec `textContent`, jamais `innerHTML`.

## 4. Architecture et flux

### Diagramme 1 : composants et ports

```mermaid
flowchart LR
    N[Navigateur] -->|HTTP| W["web (Nginx)<br/>8080 (8090 en dev)"]
    W -->|"/api"| A["api (FastAPI)<br/>port 8000"]
    A -->|SQL| D[("db (PostgreSQL)<br/>port 5432")]
    K["worker (Python)<br/>aucun port"] -->|SQL| D
    S["simulateur"] -->|JSON| Q["kafka<br/>port 9092"]
    Q --> C["stream (consommateur)<br/>aucun port"]
    C -->|SQL| D
```

Seul `web` est accessible depuis le navigateur. `api` et `db` restent internes. Le worker et le consommateur n'écoutent rien : ils interrogent la base (le consommateur lit Kafka).

### Diagramme 2 : séquence d'un dépôt (succès et refus)

```mermaid
sequenceDiagram
    actor U as Équipe data
    participant B as Navigateur
    participant A as API :8000
    participant D as PostgreSQL :5432
    participant W as Worker

    U->>B: Choisir un fichier CSV
    B->>A: POST /api/datasets/{id}/ingestions (text/csv)
    A->>D: INSERT ingestion pending + COMMIT
    A-->>B: 202 + Location
    W->>D: SELECT ... FOR UPDATE SKIP LOCKED
    W->>D: status = running + COMMIT
    W->>W: contrôler chaque ligne
    alt fichier valide
        W->>D: INSERT mesures ON CONFLICT DO NOTHING
        W->>D: compteurs, succeeded + COMMIT
    else en-tête invalide
        W->>D: ROLLBACK (aucune mesure insérée)
        W->>D: status = failed, error_message + COMMIT
    end
    B->>A: GET /api/ingestions/{id}
    A-->>B: 200 succeeded ou failed + rapport
```

Le **rollback** a lieu dans le traitement du worker : il annule toute l'insertion de la transaction 2. Un dépôt `failed` n'a donc jamais de mesures partielles.

### Diagramme 3 : déploiement

```mermaid
flowchart TB
    subgraph Compose["Compose (poste) : http://127.0.0.1:8080"]
        c1[web :8080] --> c2[api :8000] --> c3[(db :5432<br/>volume pgdata)]
        c4[worker] --> c3
    end
    subgraph K3d["k3d (poste) : http://127.0.0.1:8081"]
        k0[Ingress] --> k1[web :8080] --> k2["api :8000<br/>2 Pods"] --> k3[(db :5432<br/>PVC)]
        k4[CronJob ingest<br/>chaque minute] --> k3
    end
    subgraph AWS["AWS : VM EC2 avec K3s"]
        t[Tunnel SSH<br/>127.0.0.1:8082 vers EC2:80] --> a0[Ingress] --> a1[web :8080] --> a2[api :8000] --> a3[(db :5432<br/>disque EC2)]
        a4[CronJob ingest<br/>chaque minute] --> a3
    end
```

### Contextes, ports et stockage

| Contexte | Point d'entrée utilisateur | Accès API | Accès DB depuis API | Lieu du stockage |
|---|---|---|---|---|
| Développement (S1-S2) | http://127.0.0.1:8090 (Nginx de `compose.dev.yaml`, relaie vers l'API du poste) | http://127.0.0.1:8000 (Uvicorn sur le poste) | 127.0.0.1:5433 (port publié ; 5432 déjà occupé) | volume Docker `devpgdata` |
| Compose (S3) | http://127.0.0.1:8080 par défaut, à adapter si le port est pris | via web (`/api` vers api:8000), non publié | db:5432 (réseau interne) | volume `pgdata` |
| k3d (S4) | http://127.0.0.1:8081 via Ingress | Service api:8000 | Service db:5432 | PVC (à confirmer en S4) |
| AWS/K3s (S5) | http://127.0.0.1:8082 via tunnel SSH vers EC2:80 | Service api:8000 | Service db:5432 | disque de la VM (à confirmer en S5) |

*Écarts avec l'énoncé en développement : port DB publié 5433 (5432 occupé par un PostgreSQL local) et port web 8090 (8080 occupé par un autre conteneur). Aucun impact sur l'architecture.*

Frontières : en développement, l'API tourne sur le poste et seuls la base, Nginx et Kafka sont dans des conteneurs. En Compose, tous les services sont des conteneurs du poste et seul `web` est publié. En k3d, tout tourne dans des Pods locaux. Sur AWS, tout tourne sur la VM et n'est joignable que par le tunnel SSH. Le stockage durable est toujours PostgreSQL, jamais l'API ni le worker.

## 5. Données et contrat

### Dictionnaire des tables

**datasets**

| Colonne | Type | Obligatoire | Contrainte / défaut |
|---|---|---|---|
| id | UUID | oui | PK, UUID v4 généré par le serveur |
| name | VARCHAR(120) | oui | UNIQUE, 3 à 120 caractères, espaces externes retirés |
| description | TEXT | non | max 2 000 caractères, défaut null |
| owner | VARCHAR(60) | oui | 2 à 60 caractères, défaut « Équipe » |
| created_at | TIMESTAMPTZ | oui | posé par le serveur, UTC, immuable |

`measurement_count` est calculé, pas stocké.

**ingestions**

| Colonne | Type | Obligatoire | Contrainte / défaut |
|---|---|---|---|
| id | UUID | oui | PK, généré par le serveur |
| dataset_id | UUID | oui | FK → datasets.id, ON DELETE CASCADE |
| filename | VARCHAR(255) | oui | 1 à 255 caractères, sans / ni \ |
| status | VARCHAR(10) | oui | pending, running, succeeded, failed ; défaut pending |
| content | BYTEA | oui | fichier brut ≤ 1 Mio, jamais renvoyé par l'API |
| rows_total, rows_accepted, rows_rejected, rows_duplicate | INTEGER | non | null jusqu'au traitement |
| errors | JSONB | oui | max 20 objets {line, reason}, défaut [] |
| error_message | TEXT | non | cause d'un échec, défaut null |
| created_at | TIMESTAMPTZ | oui | date du dépôt |
| started_at, finished_at | TIMESTAMPTZ | non | posés par le worker, null à la création |

Invariant d'un dépôt réussi : rows_total = rows_accepted + rows_rejected + rows_duplicate.

**measurements**

| Colonne | Type | Obligatoire | Contrainte |
|---|---|---|---|
| id | BIGINT identité | oui | PK technique |
| dataset_id | UUID | oui | FK, ON DELETE CASCADE |
| ingestion_id | UUID | oui | FK, ON DELETE CASCADE |
| room | VARCHAR(30) | oui | 1 à 30 caractères |
| measured_at | TIMESTAMPTZ | oui | instant avec fuseau |
| co2_ppm | INTEGER | oui | CHECK 250 à 10 000 |
| temperature_c | NUMERIC(4,1) | oui | CHECK -30 à 60 |
| humidity_pct | NUMERIC(4,1) | oui | CHECK 0 à 100 |

**Unicité :** `UNIQUE (dataset_id, room, measured_at)` rend l'ingestion idempotente : une même mesure ne peut exister qu'une fois par jeu, même si le fichier est déposé deux fois.
**Index :** `ingestions (status, created_at)` pour que le worker trouve vite les dépôts en attente (coût : écriture un peu plus lente).
**Qui produit quoi :** le serveur génère les UUID et `created_at` ; le worker pose `started_at` et `finished_at`. Les dates sont stockées en TIMESTAMPTZ et renvoyées en UTC.
**Valeurs nulles :** `description`, `error_message`, les quatre compteurs, `started_at` et `finished_at`.

| Champ | Exemple valide | Exemple invalide |
|---|---|---|
| co2_ppm | 712 | abc, ou 100 (< 250) |
| temperature_c | 20.8 | 75 (> 60), ou « chaud » |
| humidity_pct | 46.3 | 120 (> 100), ou -5 |

### Trois cas à ne pas confondre

| Cas | Exemple | Résultat |
|---|---|---|
| Ligne invalide | co2_ppm = abc | ligne rejetée et comptée, le dépôt continue |
| Fichier invalide | en-tête faux | dépôt failed, aucune mesure insérée |
| Doublon | même salle, même heure | ligne ignorée et comptée, pas une erreur |

### Statuts d'un dépôt

| Statut courant | Événement | Nouveau statut | Qui | Réponse |
|---|---|---|---|---|
| - | Dépôt d'un fichier | pending | API | 202 |
| pending | Prise en charge | running | Worker | - |
| running | Traitement terminé | succeeded | Worker | - |
| running | Fichier refusé ou exception | failed | Worker | - |
| failed | Relance | pending | API | 200 |
| pending, running, succeeded | Relance | inchangé | API | 409 |

Le client ne choisit jamais un statut : il n'existe pas de route de modification du statut.

### Contrôles d'une ligne CSV (dans cet ordre)

1. Exactement 5 colonnes → `Expected 5 columns`
2. room de 1 à 30 caractères → `Invalid room`
3. measured_at en ISO 8601 avec fuseau → `Invalid measured_at`
4. measured_at au plus 5 min dans le futur → `measured_at in the future`
5. co2_ppm entier 250 à 10 000 → `Invalid co2_ppm`
6. temperature_c entre -30 et 60 → `Invalid temperature_c`
7. humidity_pct entre 0 et 100 → `Invalid humidity_pct`

Les lignes vides sont ignorées. Seules les 20 premières lignes rejetées sont détaillées dans `errors`, mais toutes sont comptées dans `rows_rejected`.

### Contrôles du fichier entier

| Situation | Où | Résultat |
|---|---|---|
| Corps vide | API | 422 Empty file, aucun dépôt créé |
| Plus de 1 Mio | API | 413 File too large, aucun dépôt créé |
| Content-Type différent de text/csv | API | 415 Expected text/csv, aucun dépôt créé |
| Contenu non UTF-8 | Worker | failed, File is not valid UTF-8 |
| En-tête différent de `room,measured_at,co2_ppm,temperature_c,humidity_pct` | Worker | failed, Invalid header |
| Aucune ligne de données | Worker | failed, No data rows |
| Plus de 10 000 lignes | Worker | failed, Too many rows |

**Flux Kafka :** un message qui n'est pas un objet JSON avec exactement les 5 champs donne `Invalid message` ; sinon il passe par les mêmes 7 règles qu'une ligne de CSV.

### Routes

| Méthode | Route | Entrée | Succès | Erreurs |
|---|---|---|---|---|
| GET | /api/datasets | - | 200, liste | 503 |
| POST | /api/datasets | JSON {name, description?, owner?} | 201 | 422, 409, 503 |
| GET | /api/datasets/{id} | UUID | 200 | 422, 404, 503 |
| DELETE | /api/datasets/{id} | UUID | 204 sans corps | 422, 404, 503 |
| POST | /api/datasets/{id}/ingestions?filename=… | corps text/csv | 202 + en-tête Location | 415, 413, 422, 404, 503 |
| GET | /api/datasets/{id}/ingestions | status? | 200 | 422, 404, 503 |
| GET | /api/ingestions/{id} | UUID | 200 | 422, 404, 503 |
| POST | /api/ingestions/{id}/retry | - | 200, repasse à pending | 422, 404, 409, 503 |
| GET | /api/datasets/{id}/stats | room?, from?, to? | 200 | 422, 404, 503 |
| GET | /api/version | - | 200 | - |
| GET | /health/live | - | 200 | - |
| GET | /health/ready | - | 200 | 503 |

### Codes d'erreur

- **404** : UUID valide mais jeu ou dépôt inconnu (`Dataset not found` / `Ingestion not found`).
- **409** : nom de jeu déjà utilisé, ou relance d'un dépôt qui n'est pas `failed`.
- **413** : fichier de plus de 1 Mio.
- **415** : Content-Type différent de text/csv.
- **422** : entrée non conforme (nom trop court, champ inconnu, UUID mal formé, statut inconnu), corps vide (`Empty file`), période invalide (from ≥ to).
- **503** : PostgreSQL injoignable (`Database unavailable`).
- **500** : erreur inattendue, message générique, trace seulement dans les logs, jamais de DSN ni de mot de passe.

Ordre d'évaluation : validation (422, 415, 413), puis recherche (404), puis règle métier (409), puis enregistrement.

### Exemples HTTP

**1. Créer un jeu → 201**
```
POST /api/datasets
Content-Type: application/json

{"name": "Qualité de l'air - bâtiment A", "owner": "Équipe A"}

→ 201 Created
{"id": "6b1e7c0a-3f4d-4d0e-9a51-2d8f0c7a1b23", "name": "Qualité de l'air - bâtiment A",
 "description": null, "owner": "Équipe A",
 "created_at": "2026-11-16T10:00:00Z", "measurement_count": 0}
```

**2. Déposer un fichier → 202**
```
POST /api/datasets/6b1e7c0a-3f4d-4d0e-9a51-2d8f0c7a1b23/ingestions?filename=mesures-avec-erreurs.csv
Content-Type: text/csv

room,measured_at,co2_ppm,temperature_c,humidity_pct
A101,2026-10-06T08:00:00+02:00,455,19.6,43.0
…

→ 202 Accepted
Location: /api/ingestions/1d9c4f2e-8b7a-4c61-9e0d-5a3b2c1d0e9f
{"id": "1d9c4f2e-…", "status": "pending", "filename": "mesures-avec-erreurs.csv", …}
```

**3. Lire un dépôt traité → 200**
```
GET /api/ingestions/1d9c4f2e-8b7a-4c61-9e0d-5a3b2c1d0e9f

→ 200 OK
{"id": "1d9c4f2e-…", "status": "succeeded", "rows_total": 12, "rows_accepted": 4,
 "rows_rejected": 7, "rows_duplicate": 1,
 "errors": [{"line": 5, "reason": "Invalid co2_ppm"}, …],
 "error_message": null, "finished_at": "2026-11-16T10:42:03Z"}
```

**4. Relancer un dépôt réussi → 409**
```
POST /api/ingestions/1d9c4f2e-8b7a-4c61-9e0d-5a3b2c1d0e9f/retry

→ 409 Conflict
{"detail": "Ingestion cannot be retried"}
```
Aucune mutation : le dépôt reste `succeeded`.

**5. Fichier trop volumineux → 413** : `{"detail": "File too large"}`, aucun dépôt créé.
**6. Suppression → 204** : `DELETE /api/datasets/{id}` renvoie 204 sans corps ; les dépôts et mesures sont supprimés (CASCADE).

Les identifiants et dates sont illustratifs. Les compteurs (12 lignes = 4 + 7 + 1) sont ceux de `mesures-avec-erreurs.csv` déposé dans un jeu vide.

## 6. Découpage du code et transactions

| Module | Responsabilité | Dépendances | Invariant important | Test associé |
|---|---|---|---|---|
| routes.py | HTTP : paramètres, codes, ordre 415, 413, 422, 404 | schemas, services | pas de SQL ni de lecture CSV | `test_upload_refused` |
| schemas.py | valider les entrées, sérialiser les sorties | - | `extra="forbid"`, `content` jamais renvoyé | `test_name_errors`, `test_upload_is_pending` |
| services.py | cas d'utilisation : jeux, dépôts, relance, indicateurs | models | relance seulement si `failed` | `test_invalid_header_and_retry` |
| ingestion.py | lire le CSV, contrôler les lignes | aucune | pur : ni base ni HTTP | `test_error_file` |
| worker.py | prendre un dépôt, traiter, conclure | ingestion, models | un `failed` n'insère aucune mesure | `test_invalid_header_and_retry` |
| stream.py | consommer Kafka, contrôler, enregistrer | ingestion, models | offset validé après le COMMIT SQL | `test_thirty_simulated_messages` |
| database.py | engine, session par requête | - | session fermée même en cas d'erreur | tous les tests API |
| models.py | tables et contraintes | database | UNIQUE (dataset_id, room, measured_at) | `test_second_upload_adds_nothing` |
| init_db.py | création explicite du schéma | models | idempotent | R1 (deux exécutions) |

**Transactions :** le service fait le `commit` en fin de cas d'utilisation et le `rollback` en cas d'exception. La session est fermée dans `get_session`. Le worker ouvre ses propres transactions : prise en charge (`FOR UPDATE SKIP LOCKED`), puis traitement, puis échec éventuel après `rollback`. La relance verrouille la ligne (`with_for_update`).
**Initialisation :** `python -m app.init_db` appelle `create_all`, une fois avant l'ouverture du trafic. `create_all` ne modifie pas une table existante : le schéma est gelé après S2, une évolution demanderait une migration versionnée (Alembic en extension).

## 7. Décisions argumentées

| Décision | Option retenue | Alternative étudiée | Motif concret | Conséquence/limite | Preuve ou référence |
|---|---|---|---|---|---|
| Stockage | PostgreSQL partout, y compris pour les dépôts en attente | Fichier ou file en mémoire | Une seule source durable : les dépôts pending survivent à un redémarrage | La base devient un point unique de panne | Test de persistance en S3 |
| Traitement | Worker séparé | Traiter le CSV dans la requête HTTP | L'API répond 202 tout de suite, même pour un gros fichier | Il faut un statut pending / running / succeeded / failed | Séquence de dépôt (§4) |
| Doublons | Contrainte d'unicité (salle + heure) | Vérifier en code avant d'insérer | La base garantit l'idempotence même en cas de traitement concurrent | Un doublon est compté, pas une erreur | `test_second_upload_adds_nothing` : 0 acceptée, 63 doublons |
| Fichier brut | BYTEA dans `ingestions` | Stockage objet ou disque | Permet la relance et le refus d'un fichier non UTF-8 par le worker | Limité à 1 Mio | contrôle 413 |
| Accès DB | SQLAlchemy synchrone, fonctions `def` | Code asynchrone | Volume faible, code plus simple | Pas adapté à une forte charge | mesure de réactivité (non exécutée) |
| Flux capteurs | Consommateur Kafka qui réutilise `check_line` | Seconde logique de validation | Une règle, un seul endroit | Livraison « au moins une fois » : un message relu devient un doublon | `test_thirty_simulated_messages`, R11 |

## 8. Risques et mesures

| Risque | Effet utilisateur | Détection | Mesure prévue | Limite restante |
|---|---|---|---|---|
| Panne API | interface inutilisable | /health/live | redémarrage automatique, 2 Pods en k3d (S4) | une seule instance en Compose |
| Panne DB | erreurs 503, plus de traitement | /health/ready renvoie 503 | volume durable, le worker réessaie sans perdre de dépôt | point unique de panne |
| Perte du nœud | service coupé | machine injoignable | sauvegarde restaurable, somme de contrôle (S6) | deux Pods sur un nœud ne protègent pas de sa perte |
| Secret exposé | accès non autorisé à la base | `git check-ignore .env`, revue des fichiers | `.env` ignoré, Secret Kubernetes, mot de passe changé avant S3 | un Secret base64 n'est pas chiffré |
| Ressource cloud oubliée | coût inattendu | console AWS | suppression en S6 avec preuve | oubli humain possible |
| Worker arrêté en plein traitement | dépôt bloqué en `running` | statut inchangé | limite documentée | relance manuelle nécessaire |

## 9. Validation croisée

- Relu par : à renseigner (revue croisée).
- Écarts avec l'énoncé : port DB publié 5433 en développement (5432 occupé), port web 8090 en développement (8080 occupé par un autre conteneur). Sans impact sur l'architecture.
- Correction pendant la rédaction : un fichier vide donne 422 `Empty file` et aucun dépôt (et non un dépôt `failed`).
- Différence conception et réalisation : le flux Kafka (S2) n'était pas dans la conception initiale ; il est ajouté aux §4 à §7.
- Questions non résolues : stockage exact en k3d et sur AWS (S4, S5) ; cas 503 non testé.