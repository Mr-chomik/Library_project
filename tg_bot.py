from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from data.books import Book
from data.borrowed_book import BorrowedBook
from data.db_session import create_session, global_init
from aiogram.utils.executor import start_polling
from data.users import User
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

storage = MemoryStorage()

bot = Bot(token=TG_TOKEN)
dp = Dispatcher(bot, storage=storage)


class RegistrationState(StatesGroup):
    waiting_for_name = State()
    waiting_for_username = State()
    waiting_for_password = State()
    confirm_registration = State()


class LoginState(StatesGroup):
    waiting_for_username = State()
    waiting_for_password = State()


@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    user_id = message.from_user.id
    db_sess = create_session()
    user = db_sess.query(User).filter_by(telegram_id=user_id).first()
    logging.info('user start chatting')

    if not user:
        await message.answer(
            "Вы не зарегистрированы в системе.\nИспользуйте /register для регистрации или /login для входа.\n"
            "Используйте /help для полного списка команд.")
    else:
        await message.answer("Добро пожаловать! Используйте /help для списка команд.")


@dp.message_handler(commands=["register"], state="*")
async def register(message: types.Message, state: FSMContext):
    await message.answer("Напишите свое имя.")
    await RegistrationState.waiting_for_name.set()


@dp.message_handler(state=RegistrationState.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Попробуйте снова.")
        return

    await state.update_data(name=name)
    await message.answer("Напишите свой логин.")
    await RegistrationState.waiting_for_username.set()


@dp.message_handler(state=RegistrationState.waiting_for_username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not username:
        await message.answer("Логин не может быть пустым. Попробуйте снова.")
        return

    db_sess = create_session()
    if db_sess.query(User).filter_by(username=username).first():
        await message.answer("Этот логин уже занят. Попробуйте другой.")
        return

    await state.update_data(username=username)
    await message.answer("Напишите свой пароль.")
    await RegistrationState.waiting_for_password.set()


@dp.message_handler(state=RegistrationState.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if not password:
        await message.answer("Пароль не может быть пустым. Попробуйте снова.")
        return

    await state.update_data(password=password)
    data = await state.get_data()

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Подтвердить"), KeyboardButton(text="Отменить")]],
        resize_keyboard=True,
        one_time_keyboard=True)

    await message.answer(
        f"Пожалуйста, подтвердите ваши данные:\n"
        f"Имя: {data['name']}\n"
        f"Логин: {data['username']}\n"
        f"Пароль: {password}",
        reply_markup=keyboard)
    await RegistrationState.confirm_registration.set()


@dp.message_handler(state=RegistrationState.confirm_registration)
async def confirm_registration(message: types.Message, state: FSMContext):
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

        await message.answer(
            "Вы успешно зарегистрировались и вошли в систему!",
            reply_markup=ReplyKeyboardRemove())
        logging.info('successful registration and login')
    else:
        await message.answer(
            "Регистрация отменена. Вы можете попробовать снова (/register) или узнать больше информации (/help).",
            reply_markup=ReplyKeyboardRemove())
        logging.warning('undo registration')

    await state.finish()


@dp.message_handler(commands=["login"], state="*")
async def login(message: types.Message, state: FSMContext):
    await message.answer("Введите ваш логин.")
    await LoginState.waiting_for_username.set()


@dp.message_handler(state=LoginState.waiting_for_username)
async def process_username(message: types.Message, state: FSMContext):
    username = message.text.strip()
    if not username:
        await message.answer("Логин не может быть пустым. Попробуйте снова.")
        return

    await state.update_data(username=username)
    await message.answer("Введите ваш пароль.")
    await LoginState.waiting_for_password.set()


@dp.message_handler(state=LoginState.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    if not password:
        await message.answer("Пароль не может быть пустым. Попробуйте снова.")
        return

    data = await state.get_data()
    username = data.get("username")

    db_sess = create_session()
    user = db_sess.query(User).filter_by(username=username, password=password).first()

    if not user:
        await message.answer("Неверный логин или пароль!")
        logging.info('wrong login or password')
        await state.finish()
        return

    user.telegram_id = message.from_user.id
    db_sess.merge(user)
    db_sess.commit()

    await message.answer("Вы успешно вошли в систему!")
    logging.info('successful login')

    await state.finish()


@dp.message_handler(commands=["logout"])
async def logout(message: types.Message):
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


@dp.message_handler(commands=["help"])
async def help_command(message: types.Message):
    await message.answer(
        "Доступные команды:\n"
        "/my_books — список взятых книг\n"
        "/search [запрос] — поиск книг\n"
        "/register — регистрация\n"
        "/login — вход\n"
        "/logout — выход из аккаунта")


@dp.message_handler(commands=["my_books"])
async def my_books(message: types.Message):
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


@dp.message_handler(commands=["search"])
async def search(message: types.Message):
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


async def start_bot():
    setup_scheduler()
    logging.info('starting bot')
    start_polling(dp, skip_updates=True)