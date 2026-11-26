"""Worker d'ingestion : prend les dépôts pending et les traite, hors du processus API.

    python -m app.worker          tourne en boucle (Compose)
    python -m app.worker --once   traite tout ce qui attend, puis s'arrête (S2, CronJob)
"""
import argparse
import logging
import os
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.database import SessionLocal
from app.ingestion import FileRejected, parse_csv
from app.models import Ingestion, Measurement

log = logging.getLogger("worker")


def claim_next() -> Ingestion | None:
    """Transaction 1 : réserver le plus ancien dépôt pending et le passer à running."""
    with SessionLocal() as session:
        ingestion = session.scalars(
            select(Ingestion)
            .where(Ingestion.status == "pending")
            .order_by(Ingestion.created_at, Ingestion.id)
            .limit(1)
            # SKIP LOCKED : si un autre worker a déjà verrouillé ce dépôt, on passe au suivant.
            .with_for_update(skip_locked=True)
        ).first()
        if ingestion is None:
            return None
        ingestion.status = "running"
        ingestion.started_at = datetime.now(timezone.utc)
        session.commit()  # running est visible tout de suite par l'API
        return ingestion


def process(ingestion: Ingestion, now: datetime | None = None) -> None:
    """Transaction 2 : contrôler les lignes, insérer les mesures et conclure le dépôt."""
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as session:
        current = session.get(Ingestion, ingestion.id)
        try:
            result = parse_csv(current.content, now)
            accepted = 0
            if result.rows:
                rows = [
                    {**row, "dataset_id": current.dataset_id, "ingestion_id": current.id}
                    for row in result.rows
                ]
                # ON CONFLICT DO NOTHING : une mesure déjà présente est ignorée, pas dupliquée.
                statement = (
                    insert(Measurement)
                    .values(rows)
                    .on_conflict_do_nothing(index_elements=["dataset_id", "room", "measured_at"])
                    .returning(Measurement.id)  # une ligne renvoyée par mesure vraiment insérée
                )
                accepted = len(session.execute(statement).all())
            current.rows_total = result.rows_total
            current.rows_accepted = accepted
            current.rows_rejected = result.rows_rejected
            current.rows_duplicate = len(result.rows) - accepted
            current.errors = result.errors
            current.status = "succeeded"
            current.finished_at = datetime.now(timezone.utc)
            session.commit()  # mesures et statut validés ensemble, ou pas du tout
            log.info("dépôt %s : succeeded (%s acceptées)", current.id, accepted)
        except Exception as error:
            # Rien n'est inséré : on annule tout, puis on note l'échec dans une autre transaction.
            session.rollback()
            message = str(error) if isinstance(error, FileRejected) else "Processing error"
            failed = session.get(Ingestion, ingestion.id)
            failed.status = "failed"
            failed.error_message = message
            failed.finished_at = datetime.now(timezone.utc)
            session.commit()
            log.warning("dépôt %s : failed (%s)", ingestion.id, message)


def run_once(now: datetime | None = None) -> int:
    """Traiter tous les dépôts en attente. Renvoie le nombre de dépôts traités."""
    count = 0
    while (ingestion := claim_next()) is not None:
        process(ingestion, now)
        count += 1
    return count


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Worker d'ingestion CampusData")
    parser.add_argument("--once", action="store_true", help="traiter puis s'arrêter")
    args = parser.parse_args()
    interval = float(os.environ.get("WORKER_INTERVAL_SECONDS", "5"))

    if args.once:
        # Base injoignable : on quitte avec une erreur, Kubernetes relancera le Job.
        log.info("%s dépôt(s) traité(s)", run_once())
        return 0
    while True:
        try:
            run_once()
        except OperationalError:
            log.error("base indisponible, nouvel essai dans %s s", interval)
        except ProgrammingError:
            # Tables absentes : init_db n'a pas encore été lancé. On attend au lieu de planter.
            log.error("tables absentes (lancer python -m app.init_db), nouvel essai dans %s s", interval)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())