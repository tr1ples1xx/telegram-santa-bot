import logging
import os
import sys
import random
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

# Токен
TOKEN = os.environ.get('BOT_TOKEN') or '7910806794:AAEJUGA9xhGuWnFUnGukfHSLP71JNSFfqX8'

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class SantaDatabase:
    def __init__(self):
        self.participants = {}  # user_id -> данные
        self.pairs = {}  # giver_id -> receiver_id
        self.all_assigned = False  # Флаг полного распределения
    
    def register(self, user_id, username, full_name, wish=None, not_wish=None):
        self.participants[user_id] = {
            'name': full_name,
            'wish': wish,
            'not_wish': not_wish,
            'has_receiver': False,  # Есть ли у этого человека даритель
            'is_giver': False       # Является ли дарителем кому-то
        }
        logger.info(f"Registered: {full_name}")
        self.all_assigned = False  # Сброс распределения при новом участнике
        return True
    
    def is_registered(self, user_id):
        return user_id in self.participants
    
    def get_info(self, user_id):
        if user_id in self.participants:
            p = self.participants[user_id]
            return (p['name'], p['wish'], p['not_wish'])
        return None
    
    def ensure_all_assigned(self):
        """Гарантирует полное распределение всех участников"""
        if self.all_assigned:
            return True
        
        participants_list = list(self.participants.keys())
        
        if len(participants_list) < 2:
            return False
        
        # Создаём случайную циклическую цепочку
        shuffled = participants_list.copy()
        random.shuffle(shuffled)
        
        # Создаём цикл: каждый дарит следующему
        self.pairs.clear()
        for i in range(len(shuffled)):
            giver = shuffled[i]
            receiver = shuffled[(i + 1) % len(shuffled)]  # Замыкаем в цикл
            self.pairs[giver] = receiver
        
        # Обновляем статусы
        for user_id in self.participants:
            self.participants[user_id]['has_receiver'] = user_id in self.pairs.values()
            self.participants[user_id]['is_giver'] = user_id in self.pairs
        
        self.all_assigned = True
        logger.info(f"Created distribution chain for {len(participants_list)} participants")
        return True
    
    def assign_receiver(self, giver_id):
        """Получить назначенного получателя"""
        # Гарантируем полное распределение
        if not self.ensure_all_assigned():
            return None
        
        if giver_id not in self.pairs:
            return None
        
        receiver_id = self.pairs[giver_id]
        receiver = self.participants.get(receiver_id)
        
        if not receiver:
            return None
        
        return (receiver_id, receiver['name'], receiver['wish'], receiver['not_wish'])
    
    def get_assigned_receiver(self, giver_id):
        """Получить уже назначенного получателя (для отображения)"""
        if giver_id not in self.pairs:
            return None
        
        receiver_id = self.pairs[giver_id]
        receiver = self.participants.get(receiver_id)
        
        if not receiver:
            return None
        
        return (receiver['name'], receiver['wish'], receiver['not_wish'])
    
    def reset_all(self):
        self.pairs.clear()
        self.all_assigned = False
        for uid in self.participants:
            self.participants[uid]['has_receiver'] = False
            self.participants[uid]['is_giver'] = False
        return True
    
    def get_all(self):
        return self.participants
    
    def get_stats(self):
        """Статистика распределения"""
        total = len(self.participants)
        with_receiver = sum(1 for p in self.participants.values() if p['has_receiver'])
        is_giver = sum(1 for p in self.participants.values() if p['is_giver'])
        
        return {
            'total': total,
            'with_receiver': with_receiver,
            'is_giver': is_giver,
            'all_assigned': self.all_assigned
        }

# Создаём базу данных
db = SantaDatabase()

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
                    "• Каждый получит уникального человека\n"
                    "• Распределение происходит когда все зарегистрируются"
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
        
        # Проверяем общее количество участников
        stats = db.get_stats()
        
        if stats['total'] < 2:
            await update.message.reply_text(
                "🎄 **Нужно больше участников!**\n\n"
                f"Сейчас зарегистрировано: {stats['total']} человек\n"
                "Минимум нужно: 2 человека\n\n"
                "Пригласите друзей!"
            )
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
        
        # Проверяем, все ли зарегистрировались
        # Можно добавить логику, что распределение происходит когда все зарегистрировались
        # Или распределять сразу
        
        # Назначаем получателя
        receiver_info = db.assign_receiver(user.id)
        
        if not receiver_info:
            await update.message.reply_text(
                "🎄 **Распределение ещё не завершено.**\n\n"
                "Возможно:\n"
                "• Ещё не все зарегистрировались\n"
                "• Идёт процесс распределения\n\n"
                "Попробуйте через минуту!"
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
        stats = db.get_stats()
        participants = db.get_all()
        
        if not participants:
            await update.message.reply_text("📊 Пока нет участников")
            return
        
        response = f"📊 **Статистика:**\n\n"
        response += f"👥 Всего участников: {stats['total']}\n"
        response += f"🎁 Имеют дарителя: {stats['with_receiver']}\n"
        response += f"🎅 Являются дарителями: {stats['is_giver']}\n"
        response += f"📋 Распределение: {'✅ Завершено' if stats['all_assigned'] else '⏳ В процессе'}\n\n"
        
        response += "**Участники:**\n"
        for pid, data in participants.items():
            status = "🎁" if data['has_receiver'] else "⏳"
            status += "🎅" if data['is_giver'] else "⏳"
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
        "• Все участники распределяются в ЦЕПОЧКУ\n"
        "• Никто не останется без пары!\n\n"
        "**Команды:**\n"
        "/start - регистрация\n"
        "/help - эта справка\n"
        "/reset - сбросить всё (админ)\n"
        "/distribute - распределить всех (админ)"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить все назначения"""
    success = db.reset_all()
    if success:
        await update.message.reply_text("✅ Все назначения сброшены! Можно начинать заново.")
    else:
        await update.message.reply_text("❌ Ошибка при сбросе")

async def distribute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительно распределить всех"""
    stats = db.get_stats()
    
    if stats['total'] < 2:
        await update.message.reply_text("❌ Нужно минимум 2 участника для распределения")
        return
    
    success = db.ensure_all_assigned()
    
    if success:
        await update.message.reply_text(
            f"✅ Все {stats['total']} участников распределены!\n\n"
            "Теперь каждый может узнать, кому дарить подарок."
        )
    else:
        await update.message.reply_text("❌ Ошибка при распределении")

# ========== ЗАПУСК БОТА ==========

async def main():
    """Асинхронная главная функция"""
    print("🤖 Запускаю бота...")
    
    # Проверяем токен
    if not TOKEN:
        print("❌ Токен не найден!")
        return
    
    # Создаём приложение
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
    application.add_handler(CommandHandler("distribute", distribute_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен и готов к работе!")
    print("🔗 Бот будет работать 24/7 на Railway")
    
    try:
        # Запускаем бота
        await application.initialize()
        await application.start()
        await application.updater.start_polling(
            drop_pending_updates=True,
            timeout=30,
            poll_interval=1.0
        )
        
        # Бесконечный цикл
        await asyncio.Event().wait()
        
    except Conflict as e:
        print(f"⚠️ Бот уже запущен: {e}")
        
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        
    finally:
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
