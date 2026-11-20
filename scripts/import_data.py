"""Import the three Starbucks JSON Lines files in one validated transaction."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

import psycopg
from psycopg.types.json import Jsonb


PROJECT_DIR = Path(__file__).resolve().parents[1]
REQUIRED_KEYS = {
    "profile.json": {"id", "age", "gender", "income", "became_member_on"},
    "portfolio.json": {"id", "offer_type", "difficulty", "reward", "duration", "channels"},
    "transcript.json": {"person", "event", "time", "value"},
}


def connection_settings(env_file):
    """Read Compose-compatible settings without printing the connection secret."""
    settings = {}
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                key, separator, value = line.partition("=")
                if not separator:
                    raise ValueError(f"Invalid setting in {env_file.name}.")
                settings[key.strip()] = value.strip().strip("\"'")
    settings.update(os.environ)
    password = settings.get("POSTGRES_PASSWORD")
    if not password:
        raise ValueError("Set POSTGRES_PASSWORD in .env or the environment.")
    return {
        "host": settings.get("POSTGRES_HOST", "127.0.0.1"),
        "port": settings.get("POSTGRES_PORT", "5432"),
        "dbname": settings.get("POSTGRES_DB", "starbucks"),
        "user": settings.get("POSTGRES_USER", "loyalty"),
        "password": password,
        "connect_timeout": 15,
    }


def read_sources(data_dir):
    # Keep the exact bytes hashed here so concurrent file edits cannot change the import.
    sources = {}
    manifest = {}
    for name in REQUIRED_KEYS:
        content = (data_dir / name).read_bytes()
        lines = content.splitlines()
        record_count = sum(bool(line.strip()) for line in lines)
        if not record_count:
            raise ValueError(f"{name} is empty.")
        sources[name] = lines
        manifest[name] = {"sha256": hashlib.sha256(content).hexdigest(), "rows": record_count}
    return sources, manifest


def validate(connection):
    for filename in ("003_validation.sql", "007_funnel_validation.sql", "010_retention_rfm_validation.sql", "012_campaign_validation.sql"):
        checks = connection.execute(
            (PROJECT_DIR / "sql" / filename).read_text(encoding="utf-8")
        ).fetchall()
        for name, actual, expected, passed in checks:
            print(f"{'PASS' if passed else 'FAIL'} {name}: {actual} (expected {expected})")
        if any(not row[3] for row in checks):
            raise ValueError("Database reconciliation failed. Import rolled back.")


def import_data(data_dir, env_file):
    sources, manifest = read_sources(data_dir)
    with psycopg.connect(**connection_settings(env_file)) as connection:
        # Serialize initial imports and reruns, including schema creation.
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('starbucks_loyalty_import'))")
        connection.execute((PROJECT_DIR / "sql" / "001_schema.sql").read_text(encoding="utf-8"))
        connection.execute((PROJECT_DIR / "sql" / "005_offer_funnel.sql").read_text(encoding="utf-8"))
        connection.execute((PROJECT_DIR / "sql" / "008_retention_rfm.sql").read_text(encoding="utf-8"))
        connection.execute((PROJECT_DIR / "sql" / "011_campaign_inputs.sql").read_text(encoding="utf-8"))
        previous = connection.execute("SELECT manifest FROM loyalty.ingestion_batches").fetchall()
        if previous:
            if len(previous) != 1 or previous[0][0] != manifest:
                raise ValueError("This database already contains a different file set. Use a separate database for another dataset.")
            validate(connection)
            print("Identical files are already imported. Validation passed; row counts are unchanged.")
            return

        batch_id = uuid.uuid4()
        connection.execute(
            "INSERT INTO loyalty.ingestion_batches (batch_id, manifest) VALUES (%s, %s)",
            (batch_id, Jsonb(manifest)),
        )
        with connection.cursor() as cursor:
            with cursor.copy(
                "COPY loyalty.raw_records (batch_id, source_file, source_line, payload) FROM STDIN"
            ) as copy:
                for name, lines in sources.items():
                    for line_number, line in enumerate(lines, start=1):
                        if not line.strip():
                            continue
                        try:
                            payload = json.loads(line)
                            if not isinstance(payload, dict) or not REQUIRED_KEYS[name].issubset(payload):
                                raise ValueError("Missing required fields or record is not an object.")
                            if name == "portfolio.json" and not isinstance(payload["channels"], list):
                                raise ValueError("Offer channels must be a list.")
                            if name == "transcript.json" and not isinstance(payload["value"], dict):
                                raise ValueError("Event value must be an object.")
                            copy.write_row((batch_id, name, line_number, line.decode("utf-8")))
                        except (ValueError, UnicodeError) as error:
                            raise ValueError(f"{name}, line {line_number}: {error}") from error
        connection.execute((PROJECT_DIR / "sql" / "002_transform.sql").read_text(encoding="utf-8"))
        validate(connection)
    print("Import committed successfully.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_DIR)
    parser.add_argument("--env-file", type=Path, default=PROJECT_DIR / ".env")
    args = parser.parse_args()
    try:
        import_data(args.data_dir, args.env_file)
    except psycopg.Error as error:
        # Avoid exposing a password-bearing DSN or connection details in public logs.
        detail = error.diag.message_primary if error.diag else None
        print(f"Database import failed; changes rolled back. {detail or type(error).__name__}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
