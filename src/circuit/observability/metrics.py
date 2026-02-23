from __future__ import annotations
from collections import defaultdict
from typing import Dict


class Metrics:
    def __init__(self) -> None:
        # Global counters
        self._global: Dict[str, float] = defaultdict(float)

        # Per-client counters
        self._per_client: Dict[str, Dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )

        # Latency histogram buckets (ms)
        self._latency_buckets = {
            5: 0,
            10: 0,
            25: 0,
            50: 0,
            100: 0,
            float("inf"): 0,
        }

    # Counter increment
    def inc(self, key: str, value: float = 1.0, client: str | None = None):
        self._global[key] += value
        if client:
            self._per_client[client][key] += value

    # Latency observation
    def observe_latency(self, latency_ms: float, client: str | None = None):
        for bucket in sorted(self._latency_buckets.keys()):
            if latency_ms <= bucket:
                self._latency_buckets[bucket] += 1
                break
            
        #Track totals for averages
        self._global["total_latency_ms"] += latency_ms
        self._global["max_latency_ms"] = max(
            self._global["max_latency_ms"], latency_ms
        )
        if client:
            self._per_client[client]["total_latency_ms"] += latency_ms
            self._per_client[client]["max_latency_ms"] = max(
                self._per_client[client]["max_latency_ms"], latency_ms
            )
            
    # Snapshot (JSON view)
    def snapshot(self, client: str | None = None):
        if client:
            data = self._per_client.get(client, {})
            total = data.get("total_requests", 0)
            avg_latency = (
                data.get("total_latency_ms", 0) / total if total else 0
            )

            return {
                "client": client,
                "metrics": {
                    **data,
                    "avg_latency_ms": avg_latency,
                },
            }

        total = self._global.get("total_requests", 0)
        avg_latency = (
            self._global.get("total_latency_ms", 0) / total if total else 0
        )

        return {
            "global": {
                **self._global,
                "avg_latency_ms": avg_latency,
            },
            "per_client": self._per_client,
        }

    # Prometheus format
    def prometheus(self) -> str:
        lines = []

        # Global counters
        for key, value in self._global.items():
            lines.append(f"# TYPE circuit_{key} counter")
            lines.append(f"circuit_{key} {value}")

        # Per-client counters
        for client, data in self._per_client.items():
            for key, value in data.items():
                lines.append(
                    f'circuit_{key}{{client="{client}"}} {value}'
                )

        # Latency histogram
        lines.append("# TYPE circuit_request_latency_ms histogram")
        cumulative = 0
        for bucket in sorted(self._latency_buckets.keys()):
            cumulative += self._latency_buckets[bucket]
            label = "+Inf" if bucket == float("inf") else bucket
            lines.append(
                f'circuit_request_latency_ms_bucket{{le="{label}"}} {cumulative}'
            )

        return "\n".join(lines) + "\n"


metrics = Metrics()