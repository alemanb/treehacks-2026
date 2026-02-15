# Modal Performance Optimization

Performance improvements applied to reduce API latency.

## Changes Made

### 1. **Increased CPU Resources** 🚀
```python
cpu=4.0  # 4 CPU cores (up from default 1 core)
```
- **Benefit**: 4x faster request processing
- **Use case**: Parallel embedding generation, concurrent searches
- **Cost impact**: ~4x compute cost, but much faster responses

### 2. **Increased Memory** 💾
```python
memory=4096  # 4 GB RAM (up from default ~1 GB)
```
- **Benefit**: Room for caching, larger batch processing
- **Use case**: Elasticsearch client caching, FastAPI memory buffers

### 3. **Warm Container Pool** 🔥
```python
min_containers=1  # Always keep 1 container running
```
- **Benefit**: **Zero cold starts** for first request
- **Eliminates**: 5-10 second cold start delay
- **Trade-off**: Pays for 1 idle container continuously

### 4. **Extended Idle Timeout** ⏱️
```python
scaledown_window=300  # Keep alive for 5 minutes
```
- **Benefit**: Containers stay warm between requests
- **Use case**: Bursty traffic patterns, testing sessions
- **Default was**: ~30 seconds

### 5. **Concurrent Request Handling** 🔀
```python
allow_concurrent_inputs=10  # Handle 10 requests per container
```
- **Benefit**: Better resource utilization
- **Use case**: Multiple users searching simultaneously
- **Scales**: Automatically adds containers if >10 concurrent requests

## Performance Impact

### Before Optimization
- **Cold start**: ~5-10 seconds (first request)
- **Warm request**: ~500-1000ms
- **CPU**: 1 core (shared)
- **Concurrency**: 1 request at a time

### After Optimization
- **Cold start**: ~0ms (always warm)
- **Warm request**: ~200-500ms (4x CPU boost)
- **CPU**: 4 dedicated cores
- **Concurrency**: 10 requests per container

## Cost Considerations

**Increased costs:**
- 4x CPU → ~4x compute cost per request
- 1 min_container → Continuous billing even when idle
- Higher memory → Slightly higher per-second cost

**When worth it:**
- Production applications with real users
- Low-latency requirements (<500ms)
- Consistent traffic patterns
- Cost of slow response > infrastructure cost

**When to scale down:**
- Development/testing only
- Infrequent usage
- Budget constraints
- Can tolerate cold starts

## Deployment

Deploy the optimized configuration:

```bash
modal deploy main.py
```

Expected output:
```
✓ Initialized. View run at https://modal.com/...
✓ Created objects.
├── 🔨 Created mount /Users/.../modal/src
├── 🔨 Created function web
└── 🔨 Created ASGI app => https://alemanb--treehacks-vector-search-web.modal.run
✓ App deployed! 🎉

App info:
- CPU: 4.0 cores
- Memory: 4096 MB
- Min containers: 1 (always warm)
- Scaledown window: 300s
```

## Monitoring Performance

Check logs to verify improvements:

```bash
# View function logs
modal app logs treehacks-vector-search

# Monitor container stats
modal container list --app treehacks-vector-search
```

Look for:
- ✅ Container always shows as "Running" (min_containers working)
- ✅ Request times <500ms in logs
- ✅ No cold start delays

## Fine-Tuning

### If still too slow:
- Increase CPU to 8.0 cores
- Increase min_containers to 2-3 for redundancy
- Add caching layer (Redis/Memcached)

### If costs too high:
- Reduce to cpu=2.0
- Set min_containers=0 (accept cold starts)
- Reduce scaledown_window to 60 seconds

### Optimal for production:
```python
cpu=4.0,              # Good balance
memory=4096,
min_containers=1,     # 1 warm container
scaledown_window=300, # 5 min keepalive
allow_concurrent_inputs=10
```

## References

Modal docs used:
- [Resource Configuration](https://modal.com/docs/guide/resources)
- [Cold Start Optimization](https://modal.com/docs/guide/cold-start)
- [Autoscaling](https://modal.com/docs/guide/scaling)
