import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    if not DATABASE_URL:
        return None
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        return conn
    except Exception as e:
        print(f"[Memory] Database connection error: {e}")
        return None

def save_chat(user_id, role, content):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_history (user_id, role, content) VALUES (%s, %s, %s)",
                (user_id, role, content)
            )
        conn.commit()
    except Exception as e:
        print(f"[Memory] save_chat error: {e}")
    finally:
        conn.close()

def get_recent_chat(user_id, limit=8):
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT role, content FROM chat_history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit)
            )
            rows = cur.fetchall()
            return list(reversed(rows))
    except Exception as e:
        print(f"[Memory] get_recent_chat error: {e}")
        return []
    finally:
        conn.close()

def clear_chat(user_id):
    conn = get_connection()
    if not conn:
        return
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_history WHERE user_id = %s", (user_id,))
        conn.commit()
    except Exception as e:
        print(f"[Memory] clear_chat error: {e}")
    finally:
        conn.close()

def save_note(user_id, note_key, note_value):
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            # Check if note exists
            cur.execute("SELECT id FROM user_notes WHERE user_id = %s AND note_key = %s", (user_id, note_key))
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE user_notes SET note_value = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s AND note_key = %s",
                    (note_value, user_id, note_key)
                )
            else:
                cur.execute(
                    "INSERT INTO user_notes (user_id, note_key, note_value) VALUES (%s, %s, %s)",
                    (user_id, note_key, note_value)
                )
        conn.commit()
        return True
    except Exception as e:
        print(f"[Memory] save_note error: {e}")
        return False
    finally:
        conn.close()

def get_notes(user_id):
    conn = get_connection()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT note_key, note_value, updated_at FROM user_notes WHERE user_id = %s ORDER BY updated_at DESC", (user_id,))
            return cur.fetchall()
    except Exception as e:
        print(f"[Memory] get_notes error: {e}")
        return []
    finally:
        conn.close()

def delete_note(user_id, note_key):
    conn = get_connection()
    if not conn:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM user_notes WHERE user_id = %s AND note_key = %s", (user_id, note_key))
        conn.commit()
        return True
    except Exception as e:
        print(f"[Memory] delete_note error: {e}")
        return False
    finally:
        conn.close()
