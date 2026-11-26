# CONTEXTE ÉTUDIANT : S2-S6 | fourni complet, comme les fichiers de data/ : c'est la source du flux
# À PRÉPARER / ADAPTER : Kafka démarré ; KAFKA_BOOTSTRAP_SERVERS = 127.0.0.1:9092 (poste) ou kafka:9092.
# CONTRÔLE ATTENDU : --count 30 envoie 30 messages ; le flux compte 24 acceptées, 3 rejetées, 3 doublons.
#
"""Simulateur de capteurs : publie des mesures fictives dans le topic Kafka.

    python -m app.simulator                          en continu (Compose, Kubernetes)
    python -m app.simulator --count 30 --interval 1  30 messages, puis arrêt (S2, preuves)

Chaque message est un objet JSON qui contient une mesure d'une salle, avec les
mêmes champs que les colonnes du CSV :

    {"room": "A101", "measured_at": "2026-11-16T10:00:00+00:00",
     "co2_ppm": 712, "temperature_c": 20.8, "humidity_pct": 46.3}

La clé du message est la salle : Kafka range toutes les mesures d'une salle dans
la même partition, elles sont donc lues dans leur ordre d'envoi.

Pour exercer les contrôles qualité, des anomalies sont envoyées volontairement,
toujours aux mêmes positions. Dans chaque bloc de 10 messages, le 5e est invalide
et le 10e est une copie exacte du 9e (un doublon, comme un capteur qui réémet).
30 messages donnent donc 24 mesures valides, 3 messages invalides et 3 doublons.
"""
import argparse
import json
import logging
import os
import random
import signal
import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from confluent_kafka import Producer

ROOMS = ["A101", "A102", "B201"]
log = logging.getLogger("simulator")


def _reading(room: str, measured_at: datetime, rng: random.Random, **changes) -> bytes:
    """Une mesure au format JSON ; changes remplace un champ pour créer une anomalie."""
    values = {
        "room": room,
        "measured_at": measured_at.isoformat(),
        "co2_ppm": rng.randint(420, 1400),
        "temperature_c": round(rng.uniform(19, 24), 1),
        "humidity_pct": round(rng.uniform(35, 55), 1),
    }
    values.update(changes)
    return json.dumps(values).encode("utf-8")


# Les trois anomalies envoyées à tour de rôle (messages 5, 15, 25, puis 35...),
# avec la raison que le consommateur doit enregistrer.
ANOMALIES = [
    ("Invalid co2_ppm", lambda room, at, rng: _reading(room, at, rng, co2_ppm=99999)),
    ("Invalid message", lambda room, at, rng: b"capteur en panne"),
    ("Invalid humidity_pct", lambda room, at, rng: _reading(room, at, rng, humidity_pct=140.0)),
]


def messages(start: datetime, interval: int, seed: int = 42) -> Iterator[tuple[int, str, bytes, str]]:
    """Produire sans fin les messages dans l'ordre d'envoi : (numéro, clé, valeur, nature).

    Fonction pure (aucun accès réseau) : un test peut vérifier les 30 premiers messages.
    Un « tour » envoie une mesure par salle ; measured_at avance de interval secondes par tour.
    """
    rng = random.Random(seed)  # graine fixe : la même suite de valeurs à chaque lancement
    previous: tuple[str, bytes] = ("", b"")
    number = 0
    while True:
        number += 1
        tick, index = divmod(number - 1, len(ROOMS))
        room = ROOMS[index]
        measured_at = start + timedelta(seconds=tick * interval)
        if number % 10 == 0:
            key, value, kind = *previous, "duplicate"  # copie exacte du message précédent
        elif number % 10 == 5:
            reason, build = ANOMALIES[(number // 10) % len(ANOMALIES)]
            key, value, kind = room, build(room, measured_at, rng), f"invalid ({reason})"
        else:
            key, value, kind = room, _reading(room, measured_at, rng), "valid"
        previous = (key, value)
        yield number, key, value, kind


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="CampusData sensor simulator")
    parser.add_argument("--count", type=int, default=0, help="number of messages (0 = endless)")
    parser.add_argument(
        "--interval",
        type=int,
        default=int(os.environ.get("SIMULATOR_INTERVAL_SECONDS", "10")),
        help="seconds between two rounds (one message per room and per round)",
    )
    args = parser.parse_args()
    interval = max(1, args.interval)  # au moins 1 s : deux tours n'ont jamais le même instant
    topic = os.environ.get("KAFKA_TOPIC", "campus.measurements")
    servers = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092")

    # Kubernetes et Docker arrêtent un conteneur avec SIGTERM : on termine proprement.
    stopping: list[bool] = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))

    # Le producteur garde les messages en mémoire et les envoie en arrière-plan ;
    # si Kafka est absent, il réessaie seul pendant message.timeout.ms.
    producer = Producer({"bootstrap.servers": servers, "client.id": "campus-simulator"})
    failures: list[str] = []

    def delivered(error, message) -> None:
        # Appelé par producer.poll() ou flush() : Kafka a confirmé (ou refusé) le message.
        if error is not None:
            failures.append(str(error))
            log.error("message not delivered: %s", error)

    # measured_at part de l'heure courante, à la seconde près, en UTC.
    start = datetime.now(timezone.utc).replace(microsecond=0)
    log.info("sending to %s, topic %s, one round every %s s", servers, topic, interval)
    for number, key, value, kind in messages(start, interval):
        producer.produce(topic, key=key.encode("utf-8"), value=value, on_delivery=delivered)
        producer.poll(0)  # traiter les confirmations déjà reçues, sans attendre
        log.info("message %s -> %s: %s", number, key, kind)
        if number == args.count or stopping:
            break
        if number % len(ROOMS) == 0:
            time.sleep(interval)  # fin d'un tour : attendre le suivant
    # Attendre que tous les messages en mémoire soient confirmés par Kafka.
    remaining = producer.flush(30)
    if remaining or failures:
        log.error("%s message(s) not confirmed, %s failure(s)", remaining, len(failures))
        return 1
    log.info("all messages confirmed by Kafka")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
