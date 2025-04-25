from aiogram import Bot, Dispatcher
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from data.db_session import create_session, global_init
from data.users import User
from data.books import Book
from data.borrowed_book import BorrowedBook
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logging
import os

logging.basicConfig(
    filename='tg_bot.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s')

load_dotenv()

TG_TOKEN = os.getenv("TG_TOKEN")
global_init("db/library.db")

bot = Bot(token=TG_TOKEN)
dp = Dispatcher()


class RegistrationState(StatesGroup):
    confirm_registration = State()


@dp.message(Command("start"))
async def start(message):
    user_id = message.from_user.id
    db_sess = create_session()
    user = db_sess.query(User).filter_by(telegram_id=user_id).first()
    logging.info('user start chatting')

    if not user:
        await message.answer(
            "Вы не зарегистрированы в системе. Используйте /register для регистрации или /login для входа.\n"
            "Используйте /help для полного списка команд.")
    else:
        await message.answer("Добро пожаловать! Используйте /help для списка команд.")


@dp.message(Command("register"))
async def register(message, state: FSMContext):
    user_id = message.from_user.id
    db_sess = create_session()
    logging.info('user do registration')

    existing_user = db_sess.query(User).filter_by(telegram_id=user_id).first()
    if existing_user:
        await message.answer("Вы уже зарегистрированы в системе. Используйте /login для входа.")
        return

    args = message.text.split()[1:]
    if len(args) != 3:
        await message.answer(
            "Неверный формат данных. Отправьте ваше имя, логин и пароль в формате:\n"
            "`/register 'Имя' 'Логин' 'Пароль'`",
            parse_mode="Markdown")
        logging.warning('wrong format')
        return

    name, username, password = args

    if db_sess.query(User).filter_by(username=username).first():
        await message.answer("Этот логин уже занят. Попробуйте другой.")
        return

    await state.update_data(name=name, username=username, password=password)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Подтвердить"), KeyboardButton(text="Отменить")]],
        resize_keyboard=True,
        one_time_keyboard=True)

    await message.answer(
        f"Пожалуйста, подтвердите ваши данные:\n"
        f"Имя: {name}\n"
        f"Логин: {username}\n"
        f"Пароль: {password}",
        reply_markup=keyboard)

    await state.set_state(RegistrationState.confirm_registration)


@dp.message(StateFilter(RegistrationState.confirm_registration))
async def confirm_registration(message, state: FSMContext):
    if message.text == "Подтвердить":
        data = await state.get_data()
        if not data:
            await message.answer("Произошла ошибка. Попробуйте снова.", reply_markup=ReplyKeyboardRemove())
            logging.error('problem in confirming data')
            return

        db_sess = create_session()
        new_user = User(
            name=data["name"],
            username=data["username"],
            password=data["password"],
            role="reader",
            rating=100,
            max_borrow_days=56,
            telegram_id=message.from_user.id)

        db_sess.add(new_user)
        db_sess.commit()

        await message.answer("Вы успешно зарегистрировались!", reply_markup=ReplyKeyboardRemove())
        logging.info('successful registration')
    else:
        await message.answer("Регистрация отменена.", reply_markup=ReplyKeyboardRemove())
        logging.warning('undo registration')

    await state.clear()


@dp.message(Command("login"))
async def login(message):
    args = message.text.split()[1:]
    logging.info('user logining')
    if len(args) != 2:
        await message.answer(
            "Неверный формат данных. Отправьте ваш логин и пароль в формате:\n"
            "`/login 'Логин' 'Пароль'`",
            parse_mode="Markdown")
        logging.warning('wrong format')
        return

    username, password = args
    db_sess = create_session()
    user = db_sess.query(User).filter_by(username=username, password=password).first()

    if not user:
        await message.answer("Неверный логин или пароль!")
        logging.info('wrong login or password')
        return

    user.telegram_id = message.from_user.id
    db_sess.merge(user)
    db_sess.commit()

    await message.answer("Вы успешно вошли в систему!")
    logging.info('successful login')


@dp.message(Command("logout"))
async def logout(message):
    user_id = message.from_user.id
    db_sess = create_session()
    user = db_sess.query(User).filter_by(telegram_id=user_id).first()
    logging.info('user logging out')

    if not user:
        await message.answer("Вы не вошли в систему.")
        return

    user.telegram_id = None
    db_sess.merge(user)
    db_sess.commit()

    await message.answer("Вы успешно вышли из аккаунта!")
    logging.info('successful log out')


@dp.message(Command("help"))
async def help_command(message):
    await message.answer(
        "Доступные команды:\n"
        "/my_books — список взятых книг\n"
        "/search [запрос] — поиск книг\n"
        "/register [Имя] [Логин] [Пароль] — регистрация\n"
        "/login [Логин] [Пароль] — вход\n"
        "/logout - выход из аккаунта")


@dp.message(Command("my_books"))
async def my_books(message):
    user_id = message.from_user.id
    db_sess = create_session()
    user = db_sess.query(User).filter_by(telegram_id=user_id).first()

    if not user:
        await message.answer("Вы не зарегистрированы в системе.")
        return

    borrowed_books = db_sess.query(BorrowedBook).filter_by(user_id=user.id).all()

    if not borrowed_books:
        await message.answer("Вы не взяли ни одной книги.")
        logging.info('no books')
        return

    message_text = "Список ваших книг:\n"
    for book in borrowed_books:
        book_info = db_sess.query(Book).get(book.book_id)
        message_text += f"- {book_info.title} (до {book.return_by.strftime('%d.%m.%Y')})\n"

    await message.answer(message_text)


@dp.message(Command("search"))
async def search(message):
    db_sess = create_session()
    search_query = " ".join(message.text.split()[1:])
    logging.info('user searching')

    if not search_query:
        await message.answer("Неверный формат. Отправьте сообщение вида:\n"
                             "/search [запрос]")
        logging.warning('wrong format')
        return

    query = db_sess.query(Book).filter(
        (Book.title.ilike(f"%{search_query.capitalize()}%")) |
        (Book.author.ilike(f"%{search_query.capitalize()}%")))

    books = query.limit(5).all()

    if not books:
        await message.answer("Книги не найдены.")
        logging.info('no such books')
        return

    message_text = "Результаты поиска:\n"
    for book in books:
        message_text += f"- Название: {book.title}\n"
        message_text += f"  Автор: {book.author}\n"
        message_text += f"  Жанр: {book.genre}\n\n"

    max_message_length = 4096
    for i in range(0, len(message_text), max_message_length):
        await message.answer(message_text[i:i + max_message_length])


async def send_reminders(bot: Bot):
    db_sess = create_session()
    today = datetime.utcnow().date()
    _3_days = today + timedelta(days=3)
    _1_day = today + timedelta(days=1)

    borrowed_books = (
        db_sess.query(BorrowedBook)
        .filter((BorrowedBook.return_by == _3_days) | (BorrowedBook.return_by == _1_day))
        .all())

    for borrowed_book in borrowed_books:
        user = db_sess.query(User).get(borrowed_book.user_id)
        book = db_sess.query(Book).get(borrowed_book.book_id)

        if user and book and user.telegram_id:
            days_left = (borrowed_book.return_by - today).days
            message = f"Напоминание: вам нужно вернуть книгу '{book.title}' через {days_left} дней."
            await bot.send_message(chat_id=user.telegram_id, text=message)


async def setup_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, 'cron', hour=9, minute=0, args=[bot])
    scheduler.start()


async def main():
    dp.startup.register(setup_scheduler)
    logging.info('starting bot')
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())