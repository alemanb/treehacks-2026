# Fake Data Generation Script

This script generates realistic fake observation data for the RAG database to test pagination and search functionality.

## Quick Start

```bash
# Generate 100 observations (Feb 1-14, 2026)
python generate_fake_data.py

# Generate custom number of observations
python generate_fake_data.py --count 200

# Custom date range
python generate_fake_data.py --start-date 2026-01-01 --end-date 2026-01-31

# Save to JSON first (for review before ingesting)
python generate_fake_data.py --save-json observations.json

# Load from JSON and ingest
python generate_fake_data.py --load-json observations.json
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--count` | 100 | Number of observations to generate |
| `--start-date` | 2026-02-01 | Start date (YYYY-MM-DD) |
| `--end-date` | 2026-02-14 | End date (YYYY-MM-DD) |
| `--batch-size` | 10 | Batch size for API ingestion |
| `--save-json` | None | Save generated data to JSON file |
| `--load-json` | None | Load data from JSON file |

## Generated Data

### Objects
Backpacks, laptops, phones, wallets, keys, watches, glasses, books, notebooks, headphones, chargers, tablets, cameras, bags, briefcases, jackets, and more.

### Colors
Red, blue, green, black, white, gray, silver, brown, navy, maroon, purple, pink, orange, yellow, gold, bronze, teal, cyan.

### Locations
Desk, shelf, table, chair, floor, counter, bench, windowsill, cabinet, drawer, couch, bookshelf, door, hallway, kitchen counter, lobby, conference room, and more.

### Sample Observation
```json
{
  "content": "Blue backpack placed on desk near the window.",
  "metadata": {
    "object": "backpack",
    "color": "blue",
    "timestamp": "2026-02-07T14:23:45Z",
    "motion_vector": [0.3, -0.1],
    "device_id": "jetson_01"
  }
}
```

## Features

- **Realistic Descriptions**: Combines objects, colors, locations, and actions naturally
- **Random Timestamps**: Evenly distributed across specified date range
- **Motion Vectors**: 70% have motion, 30% stationary
- **Device IDs**: Simulates multiple cameras/sensors
- **Batch Ingestion**: Efficient API usage with configurable batch sizes
- **Progress Tracking**: Shows real-time progress and success/failure counts
- **JSON Export**: Save generated data for review or reuse

## Examples

### Basic Usage
```bash
cd modal
python generate_fake_data.py
```

Output:
```
============================================================
Fake Data Generation for RAG Database
============================================================
Count: 100 observations
Date range: 2026-02-01 to 2026-02-14
Batch size: 10
Backend URL: https://alemanb--treehacks-vector-search-web.modal.run
============================================================

Generating 100 observations...

Generated 10/100 observations...
Generated 20/100 observations...
...
Generated 100/100 observations...

✓ Generated 100 observations

Sample observation:
{
  "content": "Black laptop placed on desk near the window.",
  "metadata": {
    "object": "laptop",
    "color": "black",
    "timestamp": "2026-02-05T09:15:30Z",
    "motion_vector": [0.0, 0.0],
    "device_id": "jetson_super_01"
  }
}

============================================================
Proceed with ingesting 100 observations? (yes/no): yes

Ingesting observations in batches of 10...

✓ Batch 1: Indexed 10 documents
✓ Batch 2: Indexed 10 documents
...
✓ Batch 10: Indexed 10 documents

============================================================
Ingestion complete!
  ✓ Successfully indexed: 100
  ✗ Failed: 0
  Total: 100
============================================================
```

### Save and Review Before Ingesting
```bash
# Generate and save to JSON
python generate_fake_data.py --count 50 --save-json data.json

# Review the file
cat data.json | jq '.[0:3]'

# Load and ingest
python generate_fake_data.py --load-json data.json
```

### Generate Data for Entire Month
```bash
python generate_fake_data.py \
  --count 500 \
  --start-date 2026-02-01 \
  --end-date 2026-02-28
```

## Testing Pagination

After generating data, test pagination with:

```bash
# Search for common objects
curl -X POST 'https://alemanb--treehacks-vector-search-web.modal.run/search' \
  -H 'Content-Type: application/json' \
  -d '{"query": "laptop", "page": 1, "page_size": 10}'

# Test different page sizes
curl -X POST 'https://alemanb--treehacks-vector-search-web.modal.run/search' \
  -H 'Content-Type: application/json' \
  -d '{"query": "blue backpack", "page": 1, "page_size": 25}'

# Test navigation
curl -X POST 'https://alemanb--treehacks-vector-search-web.modal.run/search' \
  -H 'Content-Type: application/json' \
  -d '{"query": "phone", "page": 2, "page_size": 10}'
```

## Troubleshooting

### Backend Connection Error
```
Error: Connection refused
```
**Solution**: Ensure the backend URL is correct and the Modal app is deployed.

### Timeout Error
```
Error: Request timeout
```
**Solution**: Reduce batch size with `--batch-size 5` or check backend status.

### All Observations Failed
```
✗ Failed: 100
```
**Solution**: Check backend logs with `modal app logs treehacks-vector-search` and verify Elasticsearch connection.

## Clean Up

To remove all generated data from Elasticsearch:

```python
from vectordb import get_client
from config import ES_INDEX

client = get_client()
client.delete_by_query(
    index=ES_INDEX,
    body={"query": {"match_all": {}}}
)
```

Or via API (create a cleanup endpoint in main.py if needed).
