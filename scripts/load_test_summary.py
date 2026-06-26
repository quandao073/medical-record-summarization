"""Baseline load test: measure latency for /summarize endpoint."""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from pathlib import Path


BASE_URL = "http://localhost"


def request_summary(patient_id: str, force_refresh: bool = False) -> dict:
    url = f"{BASE_URL}/api/v1/summarize/{patient_id}"
    if force_refresh:
        url += "?force_refresh=true"
    req = urllib.request.Request(url, method="POST")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            latency = time.perf_counter() - start
            return {
                "latency_ms": round(latency * 1000, 1),
                "from_cache": data.get("_from_cache", False),
                "cache_source": data.get("_cache_source", "unknown"),
                "error": None,
            }
    except Exception as e:
        latency = time.perf_counter() - start
        return {
            "latency_ms": round(latency * 1000, 1),
            "from_cache": False,
            "cache_source": "none",
            "error": str(e),
        }


def run_load_test(
    patient_id: str, n: int, force_refresh: bool
) -> dict | None:
    print(f"\n{'=' * 50}")
    print(f"Patient: {patient_id} | Requests: {n} | Force refresh: {force_refresh}")
    print(f"{'=' * 50}")

    results = []
    for i in range(n):
        r = request_summary(patient_id, force_refresh)
        results.append(r)
        status = "CACHE" if r["from_cache"] else "FRESH"
        src = f" ({r['cache_source']})" if r["from_cache"] else ""
        error = f" ERROR: {r['error']}" if r["error"] else ""
        print(f"  [{i + 1}/{n}] {r['latency_ms']:>8.1f}ms  {status}{src}{error}")

    latencies = [r["latency_ms"] for r in results if not r["error"]]
    if not latencies:
        print("  All requests failed!")
        return None

    cache_hits = sum(1 for r in results if r["from_cache"])
    sorted_lat = sorted(latencies)
    p50 = sorted_lat[len(sorted_lat) // 2]
    p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)

    print(f"\n  Summary:")
    print(f"    Min:        {min(latencies):>8.1f}ms")
    print(f"    Max:        {max(latencies):>8.1f}ms")
    print(f"    Avg:        {statistics.mean(latencies):>8.1f}ms")
    print(f"    P50:        {p50:>8.1f}ms")
    print(f"    P95:        {sorted_lat[p95_idx]:>8.1f}ms")
    print(f"    Cache hits: {cache_hits}/{len(results)}")

    return {
        "latencies_ms": latencies,
        "cache_hits": cache_hits,
        "total": len(results),
        "min_ms": min(latencies),
        "max_ms": max(latencies),
        "avg_ms": round(statistics.mean(latencies), 1),
        "p50_ms": p50,
        "p95_ms": sorted_lat[p95_idx],
    }


def main():
    parser = argparse.ArgumentParser(description="Load test /summarize endpoint")
    parser.add_argument("--patient", default="P001")
    parser.add_argument("-n", type=int, default=10, help="Number of requests")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--output", help="Save results to JSON file")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.base_url

    # Clear cache first
    print(f"Clearing cache for {args.patient}...")
    try:
        req = urllib.request.Request(
            f"{BASE_URL}/api/v1/cache/{args.patient}", method="DELETE"
        )
        urllib.request.urlopen(req, timeout=10)
        print("  Cache cleared.")
    except Exception as e:
        print(f"  Could not clear cache: {e}")

    # First request: always fresh (cache cleared)
    print("\n--- First request (cold) ---")
    cold = request_summary(args.patient, force_refresh=True)
    print(f"  Cold request: {cold['latency_ms']:.1f}ms")
    if cold["error"]:
        print(f"  ERROR: {cold['error']}")
        return

    # Repeated requests
    print(f"\n--- {args.n} repeated requests ---")
    results = run_load_test(args.patient, args.n, args.force_refresh)

    if args.output and results:
        output = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "patient_id": args.patient,
            "base_url": BASE_URL,
            "cold_latency_ms": cold["latency_ms"],
            "repeated_requests": args.n,
            "force_refresh": args.force_refresh,
            **results,
        }
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"\nResults saved to {args.output}")


if __name__ == "__main__":
    main()
