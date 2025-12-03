import logging
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Импортируем нашу базу данных
try:
    from database import SantaDatabase

    db = SantaDatabase()
except:
    # Если база не работает, используем простую версию
    class SimpleDB:
        def __init__(self):
            self.users = {}
            self.gifts = []

        def register_participant(self, user_id, username, full_name, wish_text=None, not_wish_text=None):
            self.users[user_id] = {
                'name': full_name,
                'wish': wish_text,
                'not_wish': not_wish_text
            }
            return True

        def is_registered(self, user_id):
            return user_id in self.users

        def get_participant_info(self, user_id):
            if user_id in self.users:
                user = self.users[user_id]
                return (user['name'], user['wish'], user['not_wish'])
            return None

        def get_random_receiver(self, giver_id, exclude_previous=True):
            import random
            available = [uid for uid in self.users if uid != giver_id]
            if available:
                uid = random.choice(available)
                user = self.users[uid]
                return (uid, user['name'], user['wish'], user['not_wish'])
            return None

        def record_gift(self, giver_id, receiver_id):
            self.gifts.append((giver_id, receiver_id))
            return True

        def get_gifting_history(self, user_id):
            history = []
            for giver, receiver in self.gifts:
                if giver == user_id and receiver in self.users:
                    history.append((self.users[receiver]['name'], "сегодня"))
            return history

        def reset_all(self):
            self.gifts = []
            return True


    db = SimpleDB()

# Токен бота (Railway добавит его сам)
TOKEN = '7910806794:AAEJUGA9xhGuWnFUnGukfHSLP71JNSFfqX8'

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

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
        ['🎁 Выбрать кому дарить'],
        ['📋 История подарков']
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
            # Получили ФИО
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
            # Получили пожелание
            wish = None if text.lower() == 'нет' else text
            context.user_data['wish'] = wish

            await update.message.reply_text(
                "📝 Теперь напиши, что точно НЕ хочешь получать:\n\n"
                "(Можно написать 'нет' если не хочешь указывать)"
            )
            context.user_data['reg_step'] = WAITING_FOR_NOT_WISH

        elif step == WAITING_FOR_NOT_WISH:
            # Получили "не хочу"
            not_wish = None if text.lower() == 'нет' else text
            full_name = context.user_data['full_name']
            wish = context.user_data.get('wish')

            # Сохраняем в базу
            success = db.register_participant(
                user_id=user.id,
                username=user.username,
                full_name=full_name,
                wish_text=wish,
                not_wish_text=not_wish
            )

            if success:
                await update.message.reply_text(
                    f"✅ **Регистрация завершена!** 🎉\n\n"
                    f"Добро пожаловать, {full_name}!"
                )
                await show_main_menu(update)
                # Очищаем временные данные
                context.user_data.clear()
            else:
                await update.message.reply_text("❌ Ошибка при регистрации")
        return

    # Обработка кнопок меню
    if text == '📝 Моя анкета':
        info = db.get_participant_info(user.id)
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

    elif text == '🎁 Выбрать кому дарить':
        if not db.is_registered(user.id):
            await update.message.reply_text("❌ Сначала зарегистрируйтесь через /start")
            return

        # Ищем случайного получателя
        receiver = db.get_random_receiver(user.id, exclude_previous=True)

        if not receiver:
            await update.message.reply_text(
                "🎄 Пока нет доступных получателей.\n\n"
                "Возможно:\n"
                "• Все участники уже получили от вас подарки\n"
                "• Мало участников в базе"
            )
            return

        receiver_id, full_name, wish, not_wish = receiver

        # Формируем сообщение
        response = f"🎁 **Вам выпало дарить подарок:**\n\n👤 **Получатель:** {full_name}\n"

        if wish:
            response += f"\n✅ **Что хочет получить:**\n{wish}\n"

        if not_wish:
            response += f"\n❌ **Что НЕ хочет получать:**\n{not_wish}\n"

        response += "\n---\nПосле вручения нажмите '✅ Подтвердить'"

        # Сохраняем для подтверждения
        context.user_data['receiver_id'] = receiver_id
        context.user_data['receiver_name'] = full_name

        # Кнопки для подтверждения
        keyboard = [['✅ Подтвердить', '🔄 Другой получатель']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        await update.message.reply_text(response, reply_markup=reply_markup)

    elif text == '✅ Подтвердить':
        if 'receiver_id' not in context.user_data:
            await update.message.reply_text("❌ Сначала выберите получателя")
            return

        # Записываем в историю
        success = db.record_gift(user.id, context.user_data['receiver_id'])

        if success:
            name = context.user_data['receiver_name']
            await update.message.reply_text(
                f"✅ **Отлично!** Подарок для {name} запланирован.\n\n"
                f"🎄 Счастливого Нового года! 🎄"
            )
            # Очищаем и возвращаем в меню
            context.user_data.pop('receiver_id', None)
            context.user_data.pop('receiver_name', None)
            await show_main_menu(update)
        else:
            await update.message.reply_text("❌ Ошибка при сохранении")

    elif text == '🔄 Другой получатель':
        # Ищем другого получателя
        receiver = db.get_random_receiver(user.id, exclude_previous=True)

        if not receiver:
            await update.message.reply_text("❌ Больше нет доступных получателей")
            return

        receiver_id, full_name, wish, not_wish = receiver

        response = f"🎁 **Новый получатель:**\n\n👤 {full_name}\n"
        if wish:
            response += f"\n✅ Хочет: {wish}\n"
        if not_wish:
            response += f"\n❌ Не хочет: {not_wish}"

        # Обновляем данные
        context.user_data['receiver_id'] = receiver_id
        context.user_data['receiver_name'] = full_name

        keyboard = [['✅ Подтвердить', '🔄 Другой получатель']]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

        await update.message.reply_text(response, reply_markup=reply_markup)

    elif text == '📋 История подарков':
        history = db.get_gifting_history(user.id)

        if not history:
            await update.message.reply_text(
                "📭 Вы еще никому не дарили подарки.\n\n"
                "Нажмите '🎁 Выбрать кому дарить' чтобы начать!"
            )
            return

        response = "📋 **История ваших подарков:**\n\n"
        for i, (name, date) in enumerate(history, 1):
            response += f"{i}. {name} ({date})\n"

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
        "3. Нажимаете 'Выбрать кому дарить'\n"
        "4. Получаете случайного участника и его пожелания\n"
        "5. Дарите подарок и подтверждаете\n\n"
        "**Команды:**\n"
        "/start - регистрация\n"
        "/help - эта справка\n"
        "/reset - сбросить всё (только для теста)"
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить всё (для теста)"""
    success = db.reset_all()
    if success:
        await update.message.reply_text("✅ Все данные сброшены!")
    else:
        await update.message.reply_text("❌ Ошибка при сбросе")


# ========== ЗАПУСК БОТА ==========

def main():
    """Главная функция запуска"""
    print("🤖 Запускаю бота...")

    # Проверяем токен
    if not TOKEN:
        print("❌ Токен не найден!")
        print("Добавьте переменную окружения BOT_TOKEN в Railway")
        return

    # Создаём приложение
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Бот запущен и готов к работе!")
    print("🔗 Бот будет работать 24/7 на Railway")

    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':

    main()
