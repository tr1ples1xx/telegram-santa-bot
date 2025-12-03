import sqlite3
import logging
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SantaDatabase:
    def __init__(self, db_name='santa.db'):
        self.db_name = db_name
        self.init_database()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_database(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    wish_text TEXT,
                    not_wish_text TEXT,
                    is_available BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS gifting_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    giver_id INTEGER NOT NULL,
                    receiver_id INTEGER NOT NULL,
                    gift_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (giver_id) REFERENCES participants(user_id),
                    FOREIGN KEY (receiver_id) REFERENCES participants(user_id)
                )
            ''')

            conn.commit()
            conn.close()
            logger.info("Database created")

        except sqlite3.Error as e:
            logger.error(f"Error: {e}")

    def register_participant(self, user_id, username, full_name, wish_text=None, not_wish_text=None):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                '''INSERT OR REPLACE INTO participants 
                   (user_id, username, full_name, wish_text, not_wish_text, is_available) 
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (user_id, username, full_name, wish_text, not_wish_text, True)
            )

            conn.commit()
            conn.close()
            logger.info(f"Registered: {full_name}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return False

    def is_registered(self, user_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM participants WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result is not None
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return False

    def get_participant_info(self, user_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT full_name, wish_text, not_wish_text FROM participants WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            conn.close()
            return result
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return None

    def get_random_receiver(self, giver_id, exclude_previous=True):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if exclude_previous:
                cursor.execute('''
                    SELECT p.user_id, p.full_name, p.wish_text, p.not_wish_text 
                    FROM participants p
                    LEFT JOIN gifting_history gh ON gh.receiver_id = p.user_id AND gh.giver_id = ?
                    WHERE p.user_id != ? 
                    AND p.is_available = TRUE
                    AND gh.id IS NULL
                ''', (giver_id, giver_id))
            else:
                cursor.execute('''
                    SELECT user_id, full_name, wish_text, not_wish_text 
                    FROM participants 
                    WHERE user_id != ? 
                    AND is_available = TRUE
                ''', (giver_id,))

            available = cursor.fetchall()
            conn.close()

            if available:
                return random.choice(available)
            return None

        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return None

    def record_gift(self, giver_id, receiver_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO gifting_history (giver_id, receiver_id) VALUES (?, ?)",
                (giver_id, receiver_id)
            )

            conn.commit()
            conn.close()
            logger.info(f"Gift recorded: {giver_id} -> {receiver_id}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return False

    def get_gifting_history(self, user_id):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.full_name, gh.gift_date 
                FROM gifting_history gh
                JOIN participants p ON p.user_id = gh.receiver_id
                WHERE gh.giver_id = ?
                ORDER BY gh.gift_date DESC
            ''', (user_id,))
            history = cursor.fetchall()
            conn.close()
            return history
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return []

    def reset_all(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM gifting_history")
            cursor.execute("UPDATE participants SET is_available = TRUE")
            conn.commit()
            conn.close()
            logger.info("All data reset")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return False


if __name__ == "__main__":
    print("Testing database...")
    db = SantaDatabase()
    print("Database ready")