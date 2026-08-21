"""
One-time seed script — creates demo accounts and sample data.
Called automatically on startup if the database is empty,
or manually via: python -m app.seed_admin
"""

import os
import sys
import logging

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import SessionLocal, engine, Base
from app.models import User, Report
from app.auth import hash_password

logger = logging.getLogger("seed")


DEMO_USERS = [
    {"username": "admin",  "email": "admin@sef.local",  "password": "AdminPass123!",  "role": "admin"},
    {"username": "editor", "email": "editor@sef.local", "password": "EditorPass123!", "role": "editor"},
    {"username": "viewer", "email": "viewer@sef.local", "password": "ViewerPass123!", "role": "viewer"},
]

DEMO_REPORTS = [
    {"title": "Q3 Revenue Analysis", "body": "Revenue increased 14% QoQ driven by enterprise segment growth in EMEA and APAC regions. SaaS ARR crossed the $50M milestone.", "created_by": "admin"},
    {"title": "Infrastructure Cost Audit", "body": "Cloud compute costs reduced by 22% after migrating batch workloads to spot instances and implementing auto-scaling policies.", "created_by": "editor"},
    {"title": "Security Incident Summary", "body": "No critical incidents in the past 90 days. Two medium-severity findings patched within SLA. Penetration test scheduled for next quarter.", "created_by": "admin"},
    {"title": "API Performance Benchmarks", "body": "P95 latency across all endpoints under 120ms. Database query optimization reduced average response time by 35%.", "created_by": "editor"},
    {"title": "User Onboarding Metrics", "body": "New user activation rate improved from 62% to 78% after UI redesign. Average time-to-first-action dropped to 2.3 minutes.", "created_by": "admin"},
]


def seed_database():
    """Insert demo users and reports if they don't already exist."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = 0

        # Seed users
        for u in DEMO_USERS:
            existing = db.query(User).filter(User.username == u["username"]).first()
            if not existing:
                user = User(
                    username=u["username"],
                    email=u["email"],
                    hashed_password=hash_password(u["password"]),
                    role=u["role"],
                )
                db.add(user)
                created += 1
                logger.info("Seeded user: %s (%s)", u["username"], u["role"])

        # Seed reports
        report_count = db.query(Report).count()
        if report_count == 0:
            for r in DEMO_REPORTS:
                report = Report(
                    title=r["title"],
                    body=r["body"],
                    created_by=r["created_by"],
                )
                db.add(report)
                created += 1
                logger.info("Seeded report: %s", r["title"])

        if created > 0:
            db.commit()
            logger.info("Database seeded with %d records.", created)
        else:
            logger.info("Database already seeded — skipping.")

    finally:
        db.close()


def main():
    """CLI entry point."""
    logging.basicConfig(level=logging.INFO)
    seed_database()


if __name__ == "__main__":
    main()
