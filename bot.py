import logging
import os
import sys
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

# Токен
TOKEN = os.environ.get('BOT_TOKEN') or '7910806794:AAEJUGA9xhGuWnFUnGukfHSLP71JNSFfqX8'

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout  # Важно для Railway!
)
logger = logging.getLogger(__name__)

# Простая база данных в памяти (вместо SQLite)
class SimpleDatabase:
    def __init__(self):
        self.participants = {}  # user_id -> {name, wish, not_wish, has_receiver}
        self.pairs = {}  # giver_id -> receiver_id
        self.used_receivers = set()  # Кому уже назначили дарителя
    
    def register(self, user_id, username, full_name, wish=None, not_wish=None):
        self.participants[user_id] = {
            'name': full_name,
            'wish': wish,
            'not_wish': not_wish,
            'has_receiver': False
        }
        logger.info(f"Registered: {full_name}")
        return True
    
    def is_registered(self, user_id):
        return user_id in self.participants
    
    def get_info(self, user_id):
        if user_id in self.participants:
            p = self.participants[user_id]
            return (p['name'], p['wish'], p['not_wish'])
        return None
    
    def assign_receiver(self, giver_id):
        # Проверяем, не назначен ли уже получатель
        if giver_id in self.pairs:
            receiver_id = self.pairs[giver_id]
            p = self.participants.get(receiver_id)
            if p:
                return (receiver_id, p['name'], p['wish'], p['not_wish'])
            return None
        
        # Ищем доступного получателя
        available = []
        for uid, data in self.participants.items():
            if uid != giver_id and not data['has_receiver'] and uid not in self.used_receivers:
                available.append((uid, data))
        
        if not available:
            return None
        
        import random
        receiver_id, receiver_data = random.choice(available)
        
        # Сохраняем пару
        self.pairs[giver_id] = receiver_id
        self.participants[receiver_id]['has_receiver'] = True
        self.used_receivers.add(receiver_id)
        
        logger.info(f"Assigned: {giver_id} -> {receiver_id}")
        return (receiver_id, receiver_data['name'], receiver_data['wish'], receiver_data['not_wish'])
    
    def get_assigned_receiver(self, giver_id):
        if giver_id in self.pairs:
            receiver_id = self.pairs[giver_id]
            p = self.participants.get(receiver_id)
            if p:
                return (p['name'], p['wish'], p['not_wish'])
        return None
    
    def reset_all(self):
        self.pairs.clear()
        self.used_receivers.clear()
        for uid in self.participants:
            self.participants[uid]['has_receiver'] = False
        return True
    
    def get_all(self):
        return self.participants

# Создаём базу данных
db = SimpleDatabase()

# Состояния для регистрации
(WAITING_FOR_NAME, WAITING_FOR_WISH, WAITING_FOR_NOT_WISH) = range(3)

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом"""
    user = update.effective_user
    
    if db.is_registered(user.id):
        await show_main_menu(update)
    else:
        await update.message.reply_text(
            f"Привет, {user.first_name}! 🎅\n\n"
            "Я бот для Новогоднего Тайного Санты.\n\n"
            "📝 **Для регистрации напиши свое ФИО:**\n"
            "Пример: Иванов Иван Иванович"
        )
        context.user_data['reg_step'] = WAITING_FOR_NAME

async def show_main_menu(update: Update):
    """Показать главное меню с кнопками"""
    keyboard = [
        ['📝 Моя анкета'],
        ['🎁 Узнать кому дарить'],
        ['📊 Статистика']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🎄 **Главное меню** 🎄\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех сообщений"""
    user = update.effective_user
    text = update.message.text
    
    # Если пользователь в процессе регистрации
    if 'reg_step' in context.user_data:
        step = context.user_data['reg_step']
        
        if step == WAITING_FOR_NAME:
            if len(text) < 5:
                await update.message.reply_text("❌ Слишком короткое ФИО. Напишите полностью.")
                return
            
            context.user_data['full_name'] = text
            await update.message.reply_text(
                "✨ Отлично! Теперь напиши, что бы ты хотел(а) получить в подарок:\n\n"
                "(Можно написать 'нет' если не хочешь указывать)"
            )
            context.user_data['reg_step'] = WAITING_FOR_WISH
            
        elif step == WAITING_FOR_WISH:
            wish = None if text.lower() == 'нет' else text
            context.user_data['wish'] = wish
            
            await update.message.reply_text(
                "📝 Теперь напиши, что точно НЕ хочешь получать:\n\n"
                "(Можно написать 'нет' если не хочешь указывать)"
            )
            context.user_data['reg_step'] = WAITING_FOR_NOT_WISH
            
        elif step == WAITING_FOR_NOT_WISH:
            not_wish = None if text.lower() == 'нет' else text
            full_name = context.user_data['full_name']
            wish = context.user_data.get('wish')
            
            # Сохраняем в базу
            success = db.register(
                user_id=user.id,
                username=user.username,
                full_name=full_name,
                wish=wish,
                not_wish=not_wish
            )
            
            if success:
                await update.message.reply_text(
                    f"✅ **Регистрация завершена!** 🎉\n\n"
                    f"Добро пожаловать, {full_name}!\n\n"
                    "Теперь ты можешь узнать, кому дарить подарок.\n"
                    "⚠️ **Внимание:**\n"
                    "• Получатель назначается ОДИН раз\n"
                    "• Изменить нельзя\n"
                    "• Каждый получит уникального человека"
                )
                await show_main_menu(update)
                context.user_data.clear()
            else:
                await update.message.reply_text("❌ Ошибка при регистрации")
        return
    
    # Обработка кнопок меню
    if text == '📝 Моя анкета':
        info = db.get_info(user.id)
        if info:
            full_name, wish, not_wish = info
            response = f"👤 **Ваша анкета:**\n\n📝 ФИО: {full_name}\n"
            if wish:
                response += f"✅ Хочет: {wish}\n"
            if not_wish:
                response += f"❌ Не хочет: {not_wish}"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("❌ Вы не зарегистрированы. Напишите /start")
    
    elif text == '🎁 Узнать кому дарить':
        if not db.is_registered(user.id):
            await update.message.reply_text("❌ Сначала зарегистрируйтесь через /start")
            return
        
        # Проверяем, не назначен ли уже получатель
        existing = db.get_assigned_receiver(user.id)
        
        if existing:
            full_name, wish, not_wish = existing
            response = f"🎅 **Ваш Тайный Санта уже назначен!**\n\n"
            response += f"👤 **Вы дарите подарок:** {full_name}\n"
            
            if wish:
                response += f"\n✅ **Что хочет получить:**\n{wish}\n"
            
            if not_wish:
                response += f"\n❌ **Что НЕ хочет получать:**\n{not_wish}\n"
            
            response += "\n🎄 **Счастливого Нового года!** 🎄"
            
            await update.message.reply_text(response)
            return
        
        # Назначаем нового получателя
        receiver_info = db.assign_receiver(user.id)
        
        if not receiver_info:
            await update.message.reply_text(
                "🎄 **Пока нет доступных получателей.**\n\n"
                "Возможно:\n"
                "• Все участники уже распределены\n"
                "• Недостаточно участников (нужно минимум 2)\n"
                "• Подождите пока другие зарегистрируются\n\n"
                "Проверьте позже!"
            )
            return
        
        receiver_id, full_name, wish, not_wish = receiver_info
        
        response = f"🎅 **Ваш Тайный Санта назначен!** 🎅\n\n"
        response += f"👤 **Вы дарите подарок:** {full_name}\n"
        
        if wish:
            response += f"\n✅ **Что хочет получить:**\n{wish}\n"
        
        if not_wish:
            response += f"\n❌ **Что НЕ хочет получать:**\n{not_wish}\n"
        
        response += "\n⚠️ **Важно:**\n"
        response += "• Этот выбор окончательный\n"
        response += "• Изменить получателя нельзя\n"
        response += "• Сохраните это сообщение\n\n"
        response += "🎄 **Счастливого Нового года!** 🎄"
        
        await update.message.reply_text(response)
    
    elif text == '📊 Статистика':
        participants = db.get_all()
        
        if not participants:
            await update.message.reply_text("📊 Пока нет участников")
            return
        
        total = len(participants)
        with_receiver = sum(1 for p in participants.values() if p['has_receiver'])
        
        response = f"📊 **Статистика:**\n\n"
        response += f"👥 Всего участников: {total}\n"
        response += f"🎁 Распределено подарков: {with_receiver}\n"
        response += f"⏳ Ожидают распределения: {total - with_receiver}\n\n"
        
        response += "**Участники:**\n"
        for pid, data in participants.items():
            status = "✅" if data['has_receiver'] else "⏳"
            response += f"{status} {data['name']}\n"
        
        await update.message.reply_text(response)
    
    else:
        await update.message.reply_text(
            "🤔 Используйте кнопки меню или напишите /start"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    await update.message.reply_text(
        "🎅 **Помощь по боту:**\n\n"
        "**Как это работает:**\n"
        "1. Регистрируетесь с ФИО через /start\n"
        "2. Указываете что хотите/не хотите получать\n"
        "3. Нажимаете 'Узнать кому дарить'\n"
        "4. Получаете ОДНОГО уникального человека\n"
        "5. Дарите ему подарок!\n\n"
        "**Важные правила:**\n"
        "• Каждому назначается ОДИН получатель\n"
        "• Каждый получает ОДНОГО дарителя\n"
        "• Изменить получателя НЕЛЬЗЯ\n"
        "• Никто не получит два подарка\n\n"
        "**Команды:**\n"
        "/start - регистрация\n"
        "/help - эта справка\n"
        "/reset - сбросить всё (админ)"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить все назначения"""
    success = db.reset_all()
    if success:
        await update.message.reply_text("✅ Все назначения сброшены! Можно начинать заново.")
    else:
        await update.message.reply_text("❌ Ошибка при сбросе")

# ========== ЗАПУСК БОТА С ЗАЩИТОЙ ОТ КОНФЛИКТОВ ==========

async def main():
    """Асинхронная главная функция"""
    print("🤖 Запускаю бота...")
    
    # Проверяем токен
    if not TOKEN:
        print("❌ Токен не найден!")
        return
    
    # Создаём приложение с таймаутами
    application = Application.builder() \
        .token(TOKEN) \
        .read_timeout(30) \
        .write_timeout(30) \
        .connect_timeout(30) \
        .build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен и готов к работе!")
    print("🔗 Бот будет работать 24/7 на Railway")
    
    try:
        # Запускаем бота с обработкой конфликтов
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            drop_pending_updates=True,  # Важно! Игнорировать старые сообщения
            timeout=30,
            poll_interval=1.0
        )
        
        # Бесконечный цикл с обработкой остановки
        await asyncio.Event().wait()
        
    except Conflict as e:
        print(f"⚠️ ОШИБКА: Бот уже запущен в другом месте!")
        print(f"Сообщение: {e}")
        print("Решение: Подождите 2 минуты или перезапустите проект на Railway")
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {type(e).__name__}: {e}")
        
    finally:
        # Корректная остановка
        if application.updater:
            await application.updater.stop()
        if application.running:
            await application.stop()
        if application.initialized:
            await application.shutdown()
        print("🛑 Бот остановлен")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
