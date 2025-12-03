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
            
            # Таблица участников
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    wish_text TEXT,
                    not_wish_text TEXT,
                    is_available BOOLEAN DEFAULT TRUE,  # Можно ли выбирать этого человека
                    has_receiver BOOLEAN DEFAULT FALSE, # Есть ли у этого человека получатель
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица пар (кто кому дарит)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS santa_pairs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    giver_id INTEGER UNIQUE NOT NULL,   # Кто дарит (уникальный!)
                    receiver_id INTEGER UNIQUE NOT NULL, # Кому дарит (уникальный!)
                    paired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
        """Регистрация участника"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                '''INSERT OR REPLACE INTO participants 
                   (user_id, username, full_name, wish_text, not_wish_text, is_available, has_receiver) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (user_id, username, full_name, wish_text, not_wish_text, True, False)
            )
            
            conn.commit()
            conn.close()
            logger.info(f"Registered: {full_name}")
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return False
    
    def is_registered(self, user_id):
        """Проверка регистрации"""
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
        """Информация об участнике"""
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
    
    def assign_receiver(self, giver_id):
        """
        Назначить уникального получателя для дарителя
        Возвращает (receiver_id, full_name, wish_text, not_wish_text) или None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Проверяем, не назначен ли уже получатель
            cursor.execute(
                "SELECT receiver_id FROM santa_pairs WHERE giver_id = ?",
                (giver_id,)
            )
            existing = cursor.fetchone()
            if existing:
                conn.close()
                return None  # Уже есть получатель
            
            # Ищем доступного получателя, у которого ЕЩЁ НЕТ дарителя
            cursor.execute('''
                SELECT p.user_id, p.full_name, p.wish_text, p.not_wish_text 
                FROM participants p
                LEFT JOIN santa_pairs sp ON sp.receiver_id = p.user_id
                WHERE p.user_id != ? 
                AND p.is_available = TRUE
                AND sp.receiver_id IS NULL  # У этого человека ещё нет дарителя
                AND p.has_receiver = FALSE  # Ещё не назначен как получатель
            ''', (giver_id,))
            
            available_receivers = cursor.fetchall()
            
            if not available_receivers:
                conn.close()
                return None
            
            # Выбираем случайного получателя
            receiver = random.choice(available_receivers)
            receiver_id, full_name, wish_text, not_wish_text = receiver
            
            # Создаём пару
            cursor.execute(
                "INSERT INTO santa_pairs (giver_id, receiver_id) VALUES (?, ?)",
                (giver_id, receiver_id)
            )
            
            # Помечаем получателя как "имеющего дарителя"
            cursor.execute(
                "UPDATE participants SET has_receiver = TRUE WHERE user_id = ?",
                (receiver_id,)
            )
            
            conn.commit()
            conn.close()
            logger.info(f"Assigned receiver {receiver_id} to giver {giver_id}")
            
            return (receiver_id, full_name, wish_text, not_wish_text)
            
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return None
    
    def get_assigned_receiver(self, giver_id):
        """Получить назначенного получателя"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT p.full_name, p.wish_text, p.not_wish_text
                FROM santa_pairs sp
                JOIN participants p ON p.user_id = sp.receiver_id
                WHERE sp.giver_id = ?
            ''', (giver_id,))
            result = cursor.fetchone()
            conn.close()
            return result  # (full_name, wish_text, not_wish_text)
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return None
    
    def reset_all_assignments(self):
        """Сбросить все назначения"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM santa_pairs")
            cursor.execute("UPDATE participants SET has_receiver = FALSE")
            conn.commit()
            conn.close()
            logger.info("All assignments reset")
            return True
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return False
    
    def get_all_participants(self):
        """Все участники для статистики"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM participants ORDER BY full_name")
            participants = cursor.fetchall()
            conn.close()
            return participants
        except sqlite3.Error as e:
            logger.error(f"Error: {e}")
            return []

if __name__ == "__main__":
    print("Testing database...")
    db = SantaDatabase()
    print("Database ready")
