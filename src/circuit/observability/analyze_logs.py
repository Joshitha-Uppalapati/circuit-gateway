import json

LOG_FILE = "src/circuit/logs/requests.jsonl"

total = 0
fallback = 0
latencies = []

with open(LOG_FILE, "r") as f:
    for line in f:
        data = json.loads(line)

        total += 1

        if data["provider"] == "fallback":
            fallback += 1

        latencies.append(data["latency_ms"])

if total == 0:
    print("No data")
    exit()

avg_latency = sum(latencies) / len(latencies)
max_latency = max(latencies)

print(f"Total requests: {total}")
print(f"Fallback count: {fallback}")
print(f"Fallback rate: {fallback/total:.2f}")
print(f"Avg latency: {avg_latency:.2f} ms")
print(f"Max latency: {max_latency:.2f} ms")