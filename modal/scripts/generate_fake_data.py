#!/usr/bin/env python3
"""
Generate fake observation data for the RAG database.

Usage:
    python generate_fake_data.py --count 100 --start-date 2026-02-01 --end-date 2026-02-14
"""

import argparse
import random
from datetime import datetime, timedelta
from pathlib import Path
import requests
import json

# API endpoint (update if different)
BACKEND_URL = "https://alemanb--treehacks-vector-search-web.modal.run"

# Data directory for JSON files
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Data pools for generating realistic observations
OBJECTS = [
    "backpack", "laptop", "phone", "wallet", "keys", "watch", "glasses",
    "book", "notebook", "pen", "water bottle", "umbrella", "jacket",
    "headphones", "charger", "mouse", "keyboard", "tablet", "camera",
    "bag", "briefcase", "purse", "hat", "scarf", "gloves", "shoes",
    "mug", "thermos", "lunch box", "badge", "ID card", "credit card"
]

COLORS = [
    "red", "blue", "green", "black", "white", "gray", "silver",
    "brown", "tan", "beige", "navy", "maroon", "purple", "pink",
    "orange", "yellow", "gold", "bronze", "teal", "cyan"
]

LOCATIONS = [
    "desk", "shelf", "table", "chair", "floor", "counter", "bench",
    "windowsill", "cabinet", "drawer", "couch", "bed", "nightstand",
    "bookshelf", "door", "entrance", "hallway", "corner", "wall",
    "kitchen counter", "bathroom sink", "conference room", "lobby",
    "reception desk", "storage room", "locker", "coat rack"
]

ACTIONS = [
    "placed on", "left on", "moved to", "found on", "spotted on",
    "detected on", "observed on", "seen near", "located at",
    "positioned on", "set down on", "dropped on", "resting on"
]

PREPOSITIONS = [
    "near the", "by the", "next to the", "beside the", "in front of",
    "behind the", "under the", "on top of", "inside the", "outside the"
]

DEVICE_IDS = [
    "jetson_01", "jetson_02", "jetson_03", "jetson_super_01",
    "camera_lobby", "camera_hallway_a", "camera_office_1",
    "security_cam_1", "security_cam_2", "entrance_cam"
]


def generate_observation() -> dict:
    """Generate a single realistic observation."""
    obj = random.choice(OBJECTS)
    color = random.choice(COLORS)
    location = random.choice(LOCATIONS)
    action = random.choice(ACTIONS)

    # Sometimes add a preposition for variety
    if random.random() > 0.5:
        prep = random.choice(PREPOSITIONS)
        extra_location = random.choice(LOCATIONS)
        location_phrase = f"{location} {prep} {extra_location}"
    else:
        location_phrase = location

    # Generate content description
    content = f"{color.capitalize()} {obj} {action} {location_phrase}."

    return {
        "object": obj,
        "color": color,
        "content": content
    }


def generate_motion_vector() -> list[float] | None:
    """Generate a random motion vector or None (stationary)."""
    # 30% chance of no motion
    if random.random() < 0.3:
        return None

    # Generate motion vector with reasonable ranges
    # x: -1.0 to 1.0 (left/right)
    # y: -1.0 to 1.0 (up/down)
    x = round(random.uniform(-1.0, 1.0), 2)
    y = round(random.uniform(-1.0, 1.0), 2)

    return [x, y]


def generate_timestamp(start_date: datetime, end_date: datetime) -> str:
    """Generate a random timestamp between start and end dates."""
    time_delta = end_date - start_date
    random_seconds = random.randint(0, int(time_delta.total_seconds()))
    random_date = start_date + timedelta(seconds=random_seconds)

    # Format as ISO 8601
    return random_date.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_observations(count: int, start_date: datetime, end_date: datetime) -> list[dict]:
    """Generate multiple observations with metadata."""
    observations = []

    for i in range(count):
        obs = generate_observation()

        observation = {
            "content": obs["content"],
            "metadata": {
                "object": obs["object"],
                "color": obs["color"],
                "timestamp": generate_timestamp(start_date, end_date),
                "motion_vector": generate_motion_vector(),
                "device_id": random.choice(DEVICE_IDS)
            }
        }

        observations.append(observation)

        # Print progress
        if (i + 1) % 10 == 0:
            print(f"Generated {i + 1}/{count} observations...")

    return observations


def batch_ingest(observations: list[dict], batch_size: int = 10) -> None:
    """Send observations to the backend in batches."""
    total = len(observations)
    successful = 0
    failed = 0

    for i in range(0, total, batch_size):
        batch = observations[i:i + batch_size]

        # Prepare request
        payload = {
            "documents": batch
        }

        try:
            response = requests.post(
                f"{BACKEND_URL}/ingest/batch",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                successful += result.get("indexed", 0)
                failed += result.get("errors", 0)
                print(f"✓ Batch {i//batch_size + 1}: Indexed {result.get('indexed', 0)} documents")
            else:
                print(f"✗ Batch {i//batch_size + 1} failed: {response.status_code} - {response.text}")
                failed += len(batch)

        except requests.exceptions.RequestException as e:
            print(f"✗ Batch {i//batch_size + 1} error: {str(e)}")
            failed += len(batch)

    print(f"\n{'='*60}")
    print(f"Ingestion complete!")
    print(f"  ✓ Successfully indexed: {successful}")
    print(f"  ✗ Failed: {failed}")
    print(f"  Total: {total}")
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="Generate fake observation data for RAG database")
    parser.add_argument("--count", type=int, default=100, help="Number of observations to generate (default: 100)")
    parser.add_argument("--start-date", type=str, default="2026-02-01", help="Start date (YYYY-MM-DD, default: 2026-02-01)")
    parser.add_argument("--end-date", type=str, default="2026-02-14", help="End date (YYYY-MM-DD, default: 2026-02-14)")
    parser.add_argument("--batch-size", type=int, default=10, help="Batch size for ingestion (default: 10)")
    parser.add_argument("--save-json", type=str, help="Save generated data to JSON file in data/ directory (default: data/observations_{timestamp}.json)")
    parser.add_argument("--load-json", type=str, help="Load data from JSON file instead of generating")

    args = parser.parse_args()

    # Parse dates
    try:
        start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_date = datetime.strptime(args.end_date, "%Y-%m-%d")

        # Add time to end date to include the full day
        end_date = end_date.replace(hour=23, minute=59, second=59)

        if start_date >= end_date:
            print("Error: Start date must be before end date")
            return
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        print("Use format: YYYY-MM-DD (e.g., 2026-02-01)")
        return

    print(f"\n{'='*60}")
    print(f"Fake Data Generation for RAG Database")
    print(f"{'='*60}")
    print(f"Count: {args.count} observations")
    print(f"Date range: {args.start_date} to {args.end_date}")
    print(f"Batch size: {args.batch_size}")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"{'='*60}\n")

    # Load or generate observations
    if args.load_json:
        load_path = Path(args.load_json)
        print(f"Loading observations from {load_path}...")
        try:
            with open(load_path, 'r') as f:
                observations = json.load(f)
            print(f"Loaded {len(observations)} observations from file.")
        except Exception as e:
            print(f"Error loading file: {e}")
            return
    else:
        print(f"Generating {args.count} observations...\n")
        observations = generate_observations(args.count, start_date, end_date)
        print(f"\n✓ Generated {len(observations)} observations")

        # Save to JSON (default location or specified path)
        if args.save_json:
            save_path = DATA_DIR / args.save_json
        else:
            # Default: save to data directory with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = DATA_DIR / f"observations_{timestamp}.json"

        print(f"Saving observations to {save_path}...")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump(observations, f, indent=2)
        print(f"✓ Saved to {save_path}")

    # Show sample
    print(f"\nSample observation:")
    print(json.dumps(observations[0], indent=2))

    # Confirm ingestion
    print(f"\n{'='*60}")
    response = input(f"Proceed with ingesting {len(observations)} observations? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Ingestion cancelled.")
        return

    print(f"\nIngesting observations in batches of {args.batch_size}...\n")
    batch_ingest(observations, args.batch_size)


if __name__ == "__main__":
    main()
