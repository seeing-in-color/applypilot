#!/usr/bin/env python3
"""Sync local SQLite jobs to Supabase."""

import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client

# Load environment
load_dotenv(Path.home() / ".applypilot" / ".env")

# Also check for Supabase vars in project root
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
DB_PATH = Path.home() / ".applypilot" / "applypilot.db"


def sync_to_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables")
        print("  export SUPABASE_URL=https://xxx.supabase.co")
        print("  export SUPABASE_ANON_KEY=eyJhbG...")
        return

    print(f"Connecting to local SQLite: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all jobs
    cursor.execute("SELECT * FROM jobs")
    rows = cursor.fetchall()
    print(f"Found {len(rows)} jobs in local database")

    if not rows:
        print("No jobs to sync")
        return

    # Connect to Supabase
    print(f"Connecting to Supabase: {SUPABASE_URL}")
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Get column names
    columns = [description[0] for description in cursor.description]
    
    # Convert to list of dicts, handling None values
    jobs = []
    for row in rows:
        job = {}
        for i, col in enumerate(columns):
            val = row[i]
            # Skip None values and empty strings for required fields
            if val is not None and val != '':
                job[col] = val
        # Ensure url is present (required field)
        if 'url' in job:
            jobs.append(job)

    print(f"Syncing {len(jobs)} jobs to Supabase...")

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i:i + batch_size]
        try:
            # Upsert based on url (unique key)
            result = supabase.table("jobs").upsert(batch, on_conflict="url").execute()
            print(f"  Synced batch {i//batch_size + 1}: {len(batch)} jobs")
        except Exception as e:
            print(f"  Error in batch {i//batch_size + 1}: {e}")
            # Try one by one to identify problematic records
            for job in batch:
                try:
                    supabase.table("jobs").upsert(job, on_conflict="url").execute()
                except Exception as e2:
                    print(f"    Failed job {job.get('url', 'unknown')[:50]}: {e2}")

    print("Sync complete!")
    conn.close()


if __name__ == "__main__":
    sync_to_supabase()
