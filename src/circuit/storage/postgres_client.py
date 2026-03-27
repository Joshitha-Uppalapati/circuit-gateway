import psycopg2


def get_postgres_conn():
    try:
        conn = psycopg2.connect(
            dbname="circuit",
            user="postgres",
            host="localhost",
            port=5432,
        )
        return conn
    except Exception as e:
        print("postgres not available:", e)
        return None