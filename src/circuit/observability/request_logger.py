from circuit.storage.postgres_client import get_postgres_conn


def log_request(data: dict):
    print("LOGGING CALLED:", data)
    conn = get_postgres_conn()

    if not conn:
        print("no postgres, skipping log")
        return

    try:
        cursor = conn.cursor()

        cursor.execute("""
        INSERT INTO request_logs (
            id, client, provider, latency_ms, breaker_state,
            tokens_in, tokens_out, failure_reason,
            input_size, used_fallback
        )
        
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data["request_id"],
            data["client"],
            data["provider"],
            data["latency_ms"],
            data["breaker_state"],
            data["tokens_in"],
            data["tokens_out"],
            data["failure_reason"],
            data.get("input_size"),
            data.get("used_fallback"),
        ))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print("failed to log request:", e)