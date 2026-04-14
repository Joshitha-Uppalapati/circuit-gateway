from __future__ import annotations

from collections import defaultdict
from typing import Dict, Optional


class Metrics:
    def __init__(self):
        self._counters: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def inc(self, name: str, value: float = 1.0, client: Optional[str] = None):
        key = client or "global"
        self._counters[name][key] += value

    def snapshot(self, client: Optional[str] = None):
        if client:
            return {
                name: values.get(client, 0)
                for name, values in self._counters.items()
            }

        return {
            name: dict(values)
            for name, values in self._counters.items()
        }

    def prometheus(self) -> str:
        lines = []

        for metric_name, values in self._counters.items():
            prom_name = f"circuit_{metric_name}"

            lines.append(f"# TYPE {prom_name} counter")

            for client, value in values.items():
                if client == "global":
                    lines.append(f"{prom_name} {value}")
                else:
                    lines.append(f'{prom_name}{{client="{client}"}} {value}')

        return "\n".join(lines) + "\n"


metrics = Metrics()