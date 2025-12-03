import logging
import os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from database import SantaDatabase

# Токен
TOKEN = os.environ.get('BOT_TOKEN') or '7910806794:AAEJUGA9xhGuWnFUnGukfHSLP71JNSFfqX8'

db = SantaDatabase()

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
                    f"Добро пожаловать, {full_name}!\n\n"
                    "Теперь ты можешь узнать, кому дарить подарок.\n"
                    "⚠️ **Внимание:**\n"
                    "• Получатель назначается ОДИН раз\n"
                    "• Изменить нельзя\n"
                    "• Каждый получит уникального человека"
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
    
    elif text == '🎁 Узнать кому дарить':
        if not db.is_registered(user.id):
            await update.message.reply_text("❌ Сначала зарегистрируйтесь через /start")
            return
        
        # Проверяем, не назначен ли уже получатель
        existing_receiver = db.get_assigned_receiver(user.id)
        
        if existing_receiver:
            # Уже есть получатель
            full_name, wish, not_wish = existing_receiver
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
        
        # Формируем сообщение
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
        participants = db.get_all_participants()
        
        if not participants:
            await update.message.reply_text("📊 Пока нет участников")
            return
        
        total = len(participants)
        with_receiver = sum(1 for p in participants if p[7])  # has_receiver поле
        
        response = f"📊 **Статистика:**\n\n"
        response += f"👥 Всего участников: {total}\n"
        response += f"🎁 Распределено подарков: {with_receiver}\n"
        response += f"⏳ Ожидают распределения: {total - with_receiver}\n\n"
        
        response += "**Участники:**\n"
        for participant in participants:
            status = "✅" if participant[7] else "⏳"  # has_receiver
            name = participant[3]  # full_name
            response += f"{status} {name}\n"
        
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
        "/admin_reset - сбросить всё (админ)"
    )

async def admin_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить все назначения (только для админа)"""
    # Можно добавить проверку на админа по user.id
    success = db.reset_all_assignments()
    if success:
        await update.message.reply_text("✅ Все назначения сброшены! Можно начинать заново.")
    else:
        await update.message.reply_text("❌ Ошибка при сбросе")

# ========== ЗАПУСК БОТА ==========

def main():
    """Главная функция запуска"""
    print("🤖 Запускаю бота...")
    
    # Проверяем токен
    if not TOKEN:
        print("❌ Токен не найден!")
        return
    
    # Создаём приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin_reset", admin_reset_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Бот запущен и готов к работе!")
    print("🔗 Бот будет работать 24/7 на Railway")
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
