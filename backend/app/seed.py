"""Seed a default set of stakeholders so the dashboard is populated on first run."""

from __future__ import annotations

from . import db

DEFAULT_STAKEHOLDERS = [
    ("Ava Lin", "architect", "consulting"),
    ("Compliance Office", "compliance", "client"),
    ("Security Team", "security", "client"),
    ("FinOps Team", "finops", "client"),
    ("Legal", "legal", "client"),
    ("Diane Cho (CTO)", "cto", "client"),
    ("Project Sponsor", "client_sponsor", "client"),
    ("Consulting Lead", "consultant", "consulting"),
]


def seed_if_empty() -> None:
    with db.connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM stakeholders").fetchone()[0]
        if count:
            return
        for name, role, org in DEFAULT_STAKEHOLDERS:
            conn.execute(
                "INSERT INTO stakeholders (id, name, role, org, email, created_at) VALUES (?,?,?,?,?,?)",
                (db.new_id("sh_"), name, role, org, f"{role}@example.com", db.now()),
            )
