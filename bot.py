import logging
import os
import sys
import random
import asyncio
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import Conflict

# Токен
TOKEN = os.environ.get('BOT_TOKEN') or '7910806794:AAEJUGA9xhGuWnFUnGukfHSLP71JNSFfqX8'

# ID администратора (ВАШ ID из Telegram)
ADMIN_ID = 5763705344  # Замените на ваш настоящий ID

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
        self.distribution_done = False  # Распределение выполнено?
    
    def register(self, user_id, username, full_name, wish=None, not_wish=None):
        self.participants[user_id] = {
            'name': full_name,
            'wish': wish,
            'not_wish': not_wish,
            'username': username,
            'has_receiver': False,
            'is_giver': False,
            'notified': False  # Получил ли уведомление о получателе
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
    
    def can_distribute(self):
        """Можно ли выполнить распределение?"""
        return len(self.participants) >= 2 and not self.distribution_done
    
    def distribute_gifts(self):
        """Распределить подарки между всеми участниками"""
        if self.distribution_done:
            return False
        
        participants_list = list(self.participants.keys())
        
        if len(participants_list) < 2:
            return False
        
        # Создаём случайную циклическую цепочку
        shuffled = participants_list.copy()
        
        # Пытаемся создать хорошую цепочку (избегаем коротких циклов)
        max_attempts = 10
        for attempt in range(max_attempts):
            random.shuffle(shuffled)
            
            # Проверяем что никто не дарит сам себе
            valid = True
            for i in range(len(shuffled)):
                if shuffled[i] == participants_list[i]:
                    valid = False
                    break
            
            if valid:
                break
        
        # Создаём пары: каждый дарит следующему в списке
        self.pairs.clear()
        for i in range(len(shuffled)):
            giver = shuffled[i]
            receiver = shuffled[(i + 1) % len(shuffled)]  # Замыкаем цикл
            self.pairs[giver] = receiver
        
        # Обновляем статусы
        for user_id in self.participants:
            self.participants[user_id]['has_receiver'] = user_id in self.pairs.values()
            self.participants[user_id]['is_giver'] = user_id in self.pairs
            self.participants[user_id]['notified'] = False
        
        self.distribution_done = True
        logger.info(f"Распределение выполнено для {len(participants_list)} участников")
        return True
    
    def get_receiver_for_giver(self, giver_id):
        """Получить получателя для дарителя"""
        if giver_id not in self.pairs:
            return None
        
        receiver_id = self.pairs[giver_id]
        receiver = self.participants.get(receiver_id)
        
        if not receiver:
            return None
        
        return (receiver_id, receiver['name'], receiver['wish'], receiver['not_wish'])
    
    def mark_as_notified(self, user_id):
        """Пометить что пользователь получил уведомление"""
        if user_id in self.participants:
            self.participants[user_id]['notified'] = True
    
    def is_notified(self, user_id):
        """Проверил ли пользователь своего получателя?"""
        return self.participants.get(user_id, {}).get('notified', False)
    
    def reset_all(self):
        """Полный сброс"""
        self.participants.clear()
        self.pairs.clear()
        self.distribution_done = False
        logger.info("Все данные сброшены")
        return True
    
    def get_all(self):
        return self.participants
    
    def get_stats(self):
        total = len(self.participants)
        notified = sum(1 for p in self.participants.values() if p['notified'])
        
        return {
            'total': total,
            'distributed': self.distribution_done,
            'notified': notified,
            'remaining': total - notified
        }
    
    def get_pair_info(self, giver_id):
        """Полная информация о паре (для администратора)"""
        if giver_id not in self.pairs:
            return None
        
        receiver_id = self.pairs[giver_id]
        giver = self.participants.get(giver_id)
        receiver = self.participants.get(receiver_id)
        
        if not giver or not receiver:
            return None
        
        return {
            'giver_name': giver['name'],
            'giver_username': giver['username'],
            'receiver_name': receiver['name'],
            'receiver_wish': receiver['wish'],
            'receiver_not_wish': receiver['not_wish'],
            'notified': giver['notified']
        }

# Создаём базу данных
db = SantaDatabase()

# Состояния для регистрации
(WAITING_FOR_NAME, WAITING_FOR_WISH, WAITING_FOR_NOT_WISH) = range(3)

# ========== ОСНОВНЫЕ ФУНКЦИИ ==========

def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    return user_id == ADMIN_ID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало работы с ботом"""
    user = update.effective_user
    
    if db.is_registered(user.id):
        await show_user_menu(update, user.id)
    else:
        await update.message.reply_text(
            f"Привет, {user.first_name}! 🎅\n\n"
            "Я бот для Новогоднего Тайного Санты.\n\n"
            "📝 **Для регистрации напиши свое ФИО:**\n"
            "Пример: Иванов Иван Иванович"
        )
        context.user_data['reg_step'] = WAITING_FOR_NAME

async def show_user_menu(update: Update, user_id):
    """Показать меню для обычного пользователя"""
    keyboard = [
        ['📝 Моя анкета'],
        ['🎁 Кому я дарю подарок?']
    ]
    
    # Добавляем админские кнопки если пользователь - админ
    if is_admin(user_id):
        keyboard.append(['👑 Админ панель'])
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "🎄 **Главное меню** 🎄\n\n"
        "Выберите действие:",
        reply_markup=reply_markup
    )

async def show_admin_menu(update: Update):
    """Показать админскую панель"""
    stats = db.get_stats()
    
    keyboard = [
        ['📊 Статистика'],
        ['🎁 Распределить подарки'],
        ['🔔 Отправить уведомления'],
        ['🔄 Сбросить всё'],
        ['👤 Вернуться в меню']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    status_text = "⏳ Ожидание" if not db.distribution_done else "✅ Выполнено"
    
    await update.message.reply_text(
        f"👑 **Админ панель** 👑\n\n"
        f"📈 Статистика:\n"
        f"• Участников: {stats['total']}\n"
        f"• Распределение: {status_text}\n"
        f"• Получили уведомления: {stats['notified']}/{stats['total']}\n\n"
        f"Выберите действие:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка всех сообщений"""
    user = update.effective_user
    text = update.message.text
    user_id = user.id
    
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
                user_id=user_id,
                username=user.username,
                full_name=full_name,
                wish=wish,
                not_wish=not_wish
            )
            
            if success:
                await update.message.reply_text(
                    f"✅ **Регистрация завершена!** 🎉\n\n"
                    f"Добро пожаловать, {full_name}!\n\n"
                    "Теперь жди, когда организатор распределит подарки.\n"
                    "Ты получишь сообщение, кому дарить подарок."
                )
                await show_user_menu(update, user_id)
                context.user_data.clear()
                
                # Уведомляем администратора о новом участнике
                if is_admin(ADMIN_ID):
                    try:
                        await context.bot.send_message(
                            chat_id=ADMIN_ID,
                            text=f"📥 Новый участник: {full_name}\n"
                                 f"Всего участников: {len(db.get_all())}"
                        )
                    except:
                        pass
            else:
                await update.message.reply_text("❌ Ошибка при регистрации")
        return
    
    # Обработка кнопок пользователя
    if text == '📝 Моя анкета':
        info = db.get_info(user_id)
        if info:
            full_name, wish, not_wish = info
            response = f"👤 **Ваша анкета:**\n\n📝 ФИО: {full_name}\n"
            if wish:
                response += f"✅ Хочет: {wish}\n"
            if not_wish:
                response += f"❌ Не хочет: {not_wish}\n"
            
            # Показываем статус распределения
            if db.distribution_done:
                if db.is_notified(user_id):
                    response += "\n📬 Вы уже получили информацию о получателе!"
                else:
                    response += "\n⏳ Распределение выполнено, ждите уведомление!"
            else:
                response += "\n⏳ Распределение ещё не выполнено"
            
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("❌ Вы не зарегистрированы. Напишите /start")
    
    elif text == '🎁 Кому я дарю подарок?':
        if not db.is_registered(user_id):
            await update.message.reply_text("❌ Сначала зарегистрируйтесь через /start")
            return
        
        if not db.distribution_done:
            await update.message.reply_text(
                "🎄 **Распределение ещё не выполнено.**\n\n"
                "Организатор ещё не распределил подарки.\n"
                "Пожалуйста, подождите."
            )
            return
        
        # Проверяем, получал ли уже пользователь уведомление
        if db.is_notified(user_id):
            # Показываем информацию ещё раз
            receiver_info = db.get_receiver_for_giver(user_id)
            if receiver_info:
                receiver_id, full_name, wish, not_wish = receiver_info
                await send_gift_info(update, user_id, full_name, wish, not_wish)
            else:
                await update.message.reply_text("❌ Информация о получателе не найдена")
            return
        
        # Получаем информацию о получателе
        receiver_info = db.get_receiver_for_giver(user_id)
        
        if not receiver_info:
            await update.message.reply_text(
                "❌ Вам ещё не назначен получатель.\n"
                "Обратитесь к организатору."
            )
            return
        
        receiver_id, full_name, wish, not_wish = receiver_info
        
        # Отправляем информацию
        await send_gift_info(update, user_id, full_name, wish, not_wish)
        
        # Помечаем как уведомлённого
        db.mark_as_notified(user_id)
        
        # Уведомляем администратора
        if is_admin(ADMIN_ID):
            try:
                user_data = db.get_all().get(user_id, {})
                user_name = user_data.get('name', 'Неизвестно')
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"✅ {user_name} получил информацию о получателе\n"
                         f"Получатель: {full_name}"
                )
            except:
                pass
    
    # Админские кнопки
    elif text == '👑 Админ панель':
        if not is_admin(user_id):
            await update.message.reply_text("❌ У вас нет доступа к админ панели")
            return
        await show_admin_menu(update)
    
    elif text == '👤 Вернуться в меню':
        await show_user_menu(update, user_id)
    
    # Админские функции
    elif is_admin(user_id):
        if text == '📊 Статистика':
            await show_admin_statistics(update, context)
        
        elif text == '🎁 Распределить подарки':
            await distribute_gifts(update, context)
        
        elif text == '🔔 Отправить уведомления':
            await send_notifications_to_all(update, context)
        
        elif text == '🔄 Сбросить всё':
            await reset_all_data(update, context)
    
    else:
        await update.message.reply_text(
            "🤔 Используйте кнопки меню или напишите /start"
        )

async def send_gift_info(update: Update, user_id: int, receiver_name: str, wish: str, not_wish: str):
    """Отправить информацию о получателе подарка"""
    response = f"🎅 **Твой Тайный Санта назначен!** 🎅\n\n"
    response += f"👤 **Ты даришь подарок:** {receiver_name}\n"
    
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

async def show_admin_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать детальную статистику для админа"""
    stats = db.get_stats()
    participants = db.get_all()
    
    response = f"📊 **Детальная статистика:**\n\n"
    response += f"👥 Всего участников: {stats['total']}\n"
    response += f"🎁 Распределение: {'✅ Выполнено' if db.distribution_done else '❌ Не выполнено'}\n"
    response += f"🔔 Получили уведомления: {stats['notified']}/{stats['total']}\n\n"
    
    if participants:
        response += "**Список участников:**\n"
        for user_id, data in participants.items():
            status = "🔔" if data['notified'] else "⏳"
            status += "🎁" if data['is_giver'] else ""
            username = f"(@{data['username']})" if data['username'] else ""
            response += f"{status} {data['name']} {username}\n"
    
    # Информация о парах если распределение выполнено
    if db.distribution_done:
        response += "\n**Пары (кто → кому):**\n"
        for giver_id, receiver_id in db.pairs.items():
            giver = participants.get(giver_id, {})
            receiver = participants.get(receiver_id, {})
            notified = "✅" if giver.get('notified') else "⏳"
            response += f"{notified} {giver.get('name', '?')} → {receiver.get('name', '?')}\n"
    
    await update.message.reply_text(response)

async def distribute_gifts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Распределить подарки между всеми участниками"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    stats = db.get_stats()
    
    if stats['total'] < 2:
        await update.message.reply_text("❌ Нужно минимум 2 участника для распределения")
        return
    
    if db.distribution_done:
        await update.message.reply_text("⚠️ Распределение уже выполнено!\nИспользуйте 'Сбросить всё' чтобы начать заново.")
        return
    
    # Запрашиваем подтверждение
    keyboard = [['✅ Да, распределить', '❌ Нет, отмена']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        f"⚠️ **Подтверждение распределения** ⚠️\n\n"
        f"Вы собираетесь распределить подарки между {stats['total']} участниками.\n\n"
        f"После этого:\n"
        f"• Каждому будет назначен получатель\n"
        f"• Изменить распределение будет нельзя\n"
        f"• Участники смогут узнать кому дарить\n\n"
        f"Вы уверены?",
        reply_markup=reply_markup
    )
    
    context.user_data['awaiting_distribution_confirmation'] = True

async def send_notifications_to_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить уведомления всем участникам"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    if not db.distribution_done:
        await update.message.reply_text("❌ Сначала выполните распределение подарков!")
        return
    
    participants = db.get_all()
    total = len(participants)
    sent = 0
    failed = 0
    
    await update.message.reply_text(f"⏳ Отправляю уведомления {total} участникам...")
    
    for user_id, data in participants.items():
        if not data['notified']:
            receiver_info = db.get_receiver_for_giver(user_id)
            if receiver_info:
                receiver_id, full_name, wish, not_wish = receiver_info
                
                try:
                    # Отправляем сообщение участнику
                    message = f"🎅 **Твой Тайный Санта назначен!** 🎅\n\n"
                    message += f"👤 **Ты даришь подарок:** {full_name}\n"
                    
                    if wish:
                        message += f"\n✅ **Что хочет получить:**\n{wish}\n"
                    
                    if not_wish:
                        message += f"\n❌ **Что НЕ хочет получать:**\n{not_wish}\n"
                    
                    message += "\n🎄 **Счастливого Нового года!** 🎄"
                    
                    await context.bot.send_message(chat_id=user_id, text=message)
                    
                    # Помечаем как уведомлённого
                    db.mark_as_notified(user_id)
                    sent += 1
                    
                    # Небольшая задержка чтобы не спамить
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки {user_id}: {e}")
                    failed += 1
    
    await update.message.reply_text(
        f"✅ Уведомления отправлены!\n\n"
        f"• Успешно: {sent}\n"
        f"• Ошибок: {failed}\n"
        f"• Всего участников: {total}"
    )

async def reset_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить все данные"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    # Запрашиваем подтверждение
    keyboard = [['✅ Да, сбросить всё', '❌ Нет, отмена']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "⚠️ **ВНИМАНИЕ!** ⚠️\n\n"
        "Вы собираетесь сбросить ВСЕ данные:\n"
        "• Всех участников\n"
        "• Все назначения\n"
        "• Всю историю\n\n"
        "Это действие НЕЛЬЗЯ отменить!\n"
        "Вы уверены?",
        reply_markup=reply_markup
    )
    
    context.user_data['awaiting_reset_confirmation'] = True

# ========== КОМАНДЫ ==========

async def handle_admin_confirmations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка подтверждений для администратора"""
    user = update.effective_user
    text = update.message.text
    
    if not is_admin(user.id):
        return
    
    # Подтверждение распределения
    if context.user_data.get('awaiting_distribution_confirmation'):
        if text == '✅ Да, распределить':
            success = db.distribute_gifts()
            
            if success:
                stats = db.get_stats()
                await update.message.reply_text(
                    f"✅ **Распределение выполнено успешно!**\n\n"
                    f"🎁 Распределено между {stats['total']} участниками\n\n"
                    f"Теперь участники могут:\n"
                    f"1. Нажать 'Кому я дарю подарок?' чтобы узнать\n"
                    f"2. Или вы можете отправить уведомления всем"
                )
                await show_admin_menu(update)
            else:
                await update.message.reply_text("❌ Ошибка при распределении")
        
        elif text == '❌ Нет, отмена':
            await update.message.reply_text("❌ Распределение отменено")
            await show_admin_menu(update)
        
        context.user_data.pop('awaiting_distribution_confirmation', None)
    
    # Подтверждение сброса
    elif context.user_data.get('awaiting_reset_confirmation'):
        if text == '✅ Да, сбросить всё':
            db.reset_all()
            await update.message.reply_text(
                "✅ **Все данные успешно сброшены!**\n\n"
                "База данных очищена.\n"
                "Теперь можно начинать новый розыгрыш с чистого листа."
            )
            await show_admin_menu(update)
        
        elif text == '❌ Нет, отмена':
            await update.message.reply_text("❌ Сброс отменён")
            await show_admin_menu(update)
        
        context.user_data.pop('awaiting_reset_confirmation', None)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    user = update.effective_user
    
    if is_admin(user.id):
        help_text = (
            "👑 **Админ команды:**\n\n"
            "/start - регистрация/меню\n"
            "/stats - статистика\n"
            "/distribute - распределить подарки\n"
            "/notify_all - уведомить всех\n"
            "/reset - сбросить всё\n"
            "/help - эта справка"
        )
    else:
        help_text = (
            "🎅 **Помощь по боту:**\n\n"
            "**Как это работает:**\n"
            "1. Регистрируетесь с ФИО через /start\n"
            "2. Указываете что хотите/не хотите получать\n"
            "3. Ждёте когда организатор распределит подарки\n"
            "4. Получаете уведомление кому дарить\n"
            "5. Дарите подарок!\n\n"
            "**Команды:**\n"
            "/start - регистрация\n"
            "/help - эта справка"
        )
    
    await update.message.reply_text(help_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда статистики"""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Только для администратора!")
        return
    
    await show_admin_statistics(update, context)

# ========== ЗАПУСК БОТА ==========

async def main():
    """Асинхронная главная функция"""
    print("🤖 Запускаю бота...")
    print(f"👑 Администратор: {ADMIN_ID}")
    
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
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Обработчик для админских подтверждений
    application.add_handler(MessageHandler(
        filters.Regex(r'^(✅ Да, распределить|❌ Нет, отмена|✅ Да, сбросить всё)$'),
        handle_admin_confirmations
    ))
    
    # Главный обработчик сообщений
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
    # Добавляем обработку асинхронных ошибок
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
