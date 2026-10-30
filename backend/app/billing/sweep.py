"""Run the billing sweep (reminders + pausing). Schedule daily, e.g. Canner cron:
    .venv/bin/python -m app.billing.sweep
Does nothing while JDS_BILLING_ENABLED is off.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.billing.service import run_billing_sweep


def main() -> None:
    import os

    from app.db.engine import create_database_engine

    engine = create_database_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        print(run_billing_sweep(session))


if __name__ == "__main__":
    main()
