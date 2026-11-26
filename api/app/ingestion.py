"""Lire un fichier CSV et contrôler chaque ligne. Aucun accès à la base ni à HTTP."""
import csv
import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

EXPECTED_HEADER = ["room", "measured_at", "co2_ppm", "temperature_c", "humidity_pct"]
MAX_ROWS = 10_000
MAX_DETAILED_ERRORS = 20


class FileRejected(Exception):
    """Le fichier entier est refusé : le dépôt passera à failed, sans aucune mesure."""


@dataclass
class ParseResult:
    rows: list[dict] = field(default_factory=list)  # lignes valides, prêtes à insérer
    rows_total: int = 0  # lignes de données lues (en-tête et lignes vides exclus)
    rows_rejected: int = 0
    errors: list[dict] = field(default_factory=list)  # 20 premières erreurs seulement


def check_line(values: list[str], now: datetime) -> dict:
    """Contrôler une ligne. Renvoie la mesure, ou lève ValueError avec la raison."""
    # Règle 1 : exactement 5 colonnes.
    if len(values) != 5:
        raise ValueError("Expected 5 columns")
    room, measured_at, co2, temperature, humidity = values

    # Règle 2 : salle de 1 à 30 caractères, après retrait des espaces.
    room = room.strip()
    if not 1 <= len(room) <= 30:
        raise ValueError("Invalid room")

    # Règle 3 : date ISO 8601 avec fuseau horaire.
    try:
        when = datetime.fromisoformat(measured_at.strip())
    except ValueError:
        raise ValueError("Invalid measured_at") from None
    if when.tzinfo is None:
        raise ValueError("Invalid measured_at")

        # Règle 4 : pas plus de 5 minutes dans le futur (l'heure de référence `now` est passée en
    # paramètre pour que les tests ne dépendent pas de l'horloge).
    if when > now + timedelta(minutes=5):
        raise ValueError("measured_at in the future")

    # Règle 5 : CO2 entier entre 250 et 10 000 (int refuse "612.5" et "abc").
    try:
        co2_ppm = int(co2.strip())
    except ValueError:
        raise ValueError("Invalid co2_ppm") from None
    if not 250 <= co2_ppm <= 10_000:
        raise ValueError("Invalid co2_ppm")

    # Règle 6 : température entre -30 et 60.
    try:
        temperature_c = float(temperature.strip())
    except ValueError:
        raise ValueError("Invalid temperature_c") from None
    if not -30 <= temperature_c <= 60:
        raise ValueError("Invalid temperature_c")

    # Règle 7 : humidité entre 0 et 100.
    try:
        humidity_pct = float(humidity.strip())
    except ValueError:
        raise ValueError("Invalid humidity_pct") from None
    if not 0 <= humidity_pct <= 100:
        raise ValueError("Invalid humidity_pct")

    return {
        "room": room,
        "measured_at": when.astimezone(timezone.utc),
        "co2_ppm": co2_ppm,
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
    }


def parse_csv(content: bytes, now: datetime) -> ParseResult:
    """Transformer le contenu brut en lignes valides et en rapport d'erreurs."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise FileRejected("File is not valid UTF-8") from None

    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header != EXPECTED_HEADER:
        raise FileRejected("Invalid header")

    result = ParseResult()
    # start=2 : l'en-tête est la ligne 1, la première ligne de données est la ligne 2.
    for line_number, values in enumerate(reader, start=2):
        if not values or all(not v.strip() for v in values):
            continue  # ligne vide : ignorée, non comptée
        result.rows_total += 1
        try:
            result.rows.append(check_line(values, now))
        except ValueError as error:
            result.rows_rejected += 1
            if len(result.errors) < MAX_DETAILED_ERRORS:
                result.errors.append({"line": line_number, "reason": str(error)})

    if result.rows_total == 0:
        raise FileRejected("No data rows")
    if result.rows_total > MAX_ROWS:
        raise FileRejected("Too many rows")
    return result