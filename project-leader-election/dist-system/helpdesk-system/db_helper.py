import psycopg2
import psycopg2.extras
import os


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "postgres"),
        database=os.getenv("DB_NAME", "helpdesk"),
        user=os.getenv("DB_USER", "admin"),
        password=os.getenv("DB_PASSWORD", "admin123"),
        # ← biar hasil query jadi dict, kayak sqlite3.Row
        cursor_factory=psycopg2.extras.RealDictCursor
    )


def init_db():
    """Initialize database with tickets table"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                issue_title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL,
                resolution TEXT
            )
        ''')
        conn.commit()
        conn.close()
        print("[DB] Database initialized successfully", flush=True)
    except Exception as e:
        print(f"[DB ERROR] Failed to initialize database: {e}", flush=True)
        raise


def insert_ticket(ticket_id: str, customer_name: str, issue_title: str, description: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tickets (ticket_id, customer_name, issue_title, description, status) VALUES (%s, %s, %s, %s, %s)",
            (ticket_id, customer_name, issue_title,
             description, "OPEN")  # ← ? diganti %s
        )
        conn.commit()
    finally:
        conn.close()


def get_ticket_by_id(ticket_id: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM tickets WHERE ticket_id = %s", (ticket_id,))  # ← %s
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_tickets():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tickets ORDER BY status DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def update_ticket_status(ticket_id: str, status: str, resolution: str = None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tickets SET status = %s, resolution = %s WHERE ticket_id = %s",  # ← %s
            (status, resolution, ticket_id)
        )
        conn.commit()
    finally:
        conn.close()


def update_ticket(ticket_id: str, customer_name: str = None, issue_title: str = None, description: str = None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        updates = []
        params = []

        if customer_name is not None:
            updates.append("customer_name = %s")  # ← %s
            params.append(customer_name)
        if issue_title is not None:
            updates.append("issue_title = %s")
            params.append(issue_title)
        if description is not None:
            updates.append("description = %s")
            params.append(description)

        if not updates:
            return

        params.append(ticket_id)
        query = f"UPDATE tickets SET {', '.join(updates)} WHERE ticket_id = %s"
        cursor.execute(query, params)
        conn.commit()
    finally:
        conn.close()


def delete_ticket(ticket_id: str):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tickets WHERE ticket_id = %s",
                       (ticket_id,))  # ← %s
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
