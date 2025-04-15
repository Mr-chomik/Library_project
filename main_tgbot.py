from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from data.db_session import create_session, global_init
from data.users import User
from data.books import Book
from data.borrowed_book import BorrowedBook
from datetime import datetime, timedelta

BOT_TOKEN = "7895623707:AAGr2PuJ4Z5W7IUszqKioiPvDFyyfkfhBt0"

STATE_CONFIRM_REGISTRATION = 1
STATE_LOGIN = 2
global_init("db/library.db")


async def start(update, context):
    user_id = update.message.from_user.id
    db_sess = create_session()
    user = db_sess.query(User).filter_by(telegram_id=user_id).first()

    if not user:
        await update.message.reply_text(
            "Вы не зарегистрированы в системе. Используйте /register для регистрации или /login для входа.\n"
            "Используйте /help для полного списка команд.")
    else:
        await update.message.reply_text("Добро пожаловать! Используйте /help для списка команд.")


async def register(update, context):
    args = context.args
    if len(args) != 3:
        await update.message.reply_text(
            "Неверный формат данных. Отправьте ваше имя, логин и пароль в формате:\n"
            "`/register 'Имя' 'Логин' 'Пароль'`",
            parse_mode="Markdown")
        return

    name, username, password = args
    db_sess = create_session()

    if db_sess.query(User).filter_by(username=username).first():
        await update.message.reply_text("Этот логин уже занят. Попробуйте другой.")
        return

    context.user_data["registration_data"] = {"name": name, "username": username, "password": password}

    keyboard = [["Подтвердить", "Отменить"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)

    await update.message.reply_text(
        f"Пожалуйста, подтвердите ваши данные:\n"
        f"Имя: {name}\n"
        f"Логин: {username}\n"
        f"Пароль: {password}",
        reply_markup=reply_markup)

    return STATE_CONFIRM_REGISTRATION


async def confirm_registration(update, context):
    user_response = update.message.text
    if user_response == "Подтвердить":
        registration_data = context.user_data.get("registration_data")
        if not registration_data:
            await update.message.reply_text("Произошла ошибка. Попробуйте снова.", reply_markup=ReplyKeyboardRemove())
            return

        db_sess = create_session()
        new_user = User(
            name=registration_data["name"],
            username=registration_data["username"],
            password=registration_data["password"],
            role="reader",
            rating=100,
            max_borrow_days=56,
            telegram_id=update.message.from_user.id)

        db_sess.add(new_user)
        db_sess.commit()

        await update.message.reply_text("Вы успешно зарегистрировались!", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Регистрация отменена.", reply_markup=ReplyKeyboardRemove())

    context.user_data.clear()
    return -1


async def login(update, context):
    args = context.args

    if len(args) != 2:
        await update.message.reply_text(
            "Неверный формат данных. Отправьте ваш логин и пароль в формате:\n"
            "`/login 'Логин' 'Пароль'`", parse_mode="Markdown")
        return

    username, password = args
    db_sess = create_session()
    user = db_sess.query(User).filter_by(username=username, password=password).first()

    if not user:
        await update.message.reply_text("Неверный логин или пароль!")
        return

    user.telegram_id = update.message.from_user.id
    db_sess.merge(user)
    db_sess.commit()

    await update.message.reply_text("Вы успешно вошли в систему!")


async def help_command(update, context):
    await update.message.reply_text(
        "Доступные команды:\n"
        "/my_books — список взятых книг\n"
        "/search [запрос] — поиск книг\n"
        "/register [Имя] [Логин] [Пароль] — регистрация\n"
        "/login [Логин] [Пароль] — вход")


async def my_books(update, context):
    user_id = update.message.from_user.id
    db_sess = create_session()
    user = db_sess.query(User).filter_by(telegram_id=user_id).first()

    if not user:
        await update.message.reply_text("Вы не зарегистрированы в системе.")
        return

    borrowed_books = (db_sess.query(BorrowedBook).filter_by(user_id=user.id).all())

    if not borrowed_books:
        await update.message.reply_text("Вы не взяли ни одной книги.")
        return

    message = "Список ваших книг:\n"
    for book in borrowed_books:
        book_info = db_sess.query(Book).get(book.book_id)
        message += f"- {book_info.title} (до {book.return_by.strftime('%d.%m.%Y')})\n"

    await update.message.reply_text(message)


async def search(update, context):
    db_sess = create_session()
    search_query = (" ".join(context.args)).capitalize()
    if not search_query:
        await update.message.reply_text("Неверный формат. Отправьте сообщение вида:\n"
                                        "/search [запрос]")
        return

    query = db_sess.query(Book).filter(
        (Book.title.ilike(f"%{search_query}%")) |
        (Book.author.ilike(f"%{search_query}%")))

    books = query.limit(5).all()

    if not books:
        await update.message.reply_text("Книги не найдены.")
        return

    message = "Результаты поиска:\n"
    for book in books:
        message += f"- Название: {book.title}\n"
        message += f"  Автор: {book.author}\n"
        message += f"  Жанр: {book.genre}\n\n"

    max_message_length = 4096
    for i in range(0, len(message), max_message_length):
        await update.message.reply_text(message[i:i + max_message_length])


async def send_reminders(context):
    db_sess = create_session()
    today = datetime.utcnow().date()
    _3_days = today + timedelta(days=3)
    _1_day = today + timedelta(days=1)

    borrowed_books = (db_sess.query(BorrowedBook)
                      .filter((BorrowedBook.return_by == _3_days) | (BorrowedBook.return_by == _1_day)).all())

    for borrowed_book in borrowed_books:
        user = db_sess.query(User).get(borrowed_book.user_id)
        book = db_sess.query(Book).get(borrowed_book.book_id)

        if user and book and user.telegram_id:
            days_left = (borrowed_book.return_by - today).days
            message = f"Напоминание: вам нужно вернуть книгу '{book.title}' через {days_left} дней."
            await context.bot.send_message(chat_id=user.telegram_id, text=message)


async def setup_scheduler(application):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, 'cron', hour=9, minute=0, args=[application])
    scheduler.start()


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("login", login))
    application.add_handler(CommandHandler("my_books", my_books))
    application.add_handler(CommandHandler("search", search))

    application.job_queue.run_once(setup_scheduler, when=0)

    application.run_polling()


if __name__ == "__main__":
    main()