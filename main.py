from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from datetime import datetime, timedelta
import os


from data import db_session
from data.users import User
from data.books import Book
from data.borrowed_book import BorrowedBook

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret_key'

db_session.global_init("db/library.db")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(int(user_id))


@app.route('/')
@app.route('/home')
@login_required
def home():
    db_sess = db_session.create_session()
    books = db_sess.query(Book).all()
    return render_template('index.html', books=books)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        db_sess = db_session.create_session()
        user = db_sess.query(User).filter_by(username=username).first()
        if user and user.password == password:
            login_user(user)
            flash("Вы успешно вошли!", "success")
            return redirect(url_for('home'))
        else:
            flash("Неверный логин или пароль!", "error")

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Пароли не совпадают!", "error")
            return redirect(url_for('register'))

        db_sess = db_session.create_session()
        if db_sess.query(User).filter_by(username=username).first():
            flash("Логин уже занят!", "error")
            return redirect(url_for('register'))

        new_user = User(name=name, username=username, password=password, role="reader", rating=100, max_borrow_days=14)
        db_sess.add(new_user)
        db_sess.commit()

        flash("Вы успешно зарегистрировались!", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/register_admin', methods=['GET', 'POST'])
def register_admin():
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        admin_id = request.form.get('admin_id')

        if password != confirm_password:
            flash("Пароли не совпадают!", "error")
            return redirect(url_for('register_admin'))

        db_sess = db_session.create_session()
        if db_sess.query(User).filter_by(username=username).first():
            flash("Логин уже занят!", "error")
            return redirect(url_for('register_admin'))

        admin_ids = load_admin_ids()
        if admin_id not in admin_ids:
            flash("Неверный ID администратора!", "error")
            return redirect(url_for('register_admin'))

        new_admin = User(name=name, username=username, password=password, role="admin", rating=100, max_borrow_days=14)
        db_sess.add(new_admin)
        db_sess.commit()

        flash("Администратор успешно зарегистрирован!", "success")
        return redirect(url_for('login'))

    return render_template('register_admin.html')


def load_admin_ids():
    admin_ids = []
    file_path = os.path.join(os.path.dirname(__file__), 'admin_ids.txt')

    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            admin_ids = [line.strip() for line in f.readlines() if line.strip()]

    return admin_ids


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Вы успешно вышли!", "success")
    return redirect(url_for('login'))


@app.route('/borrow/<int:book_id>')
@login_required
def borrow_book(book_id):
    if current_user.role == "admin":
        flash("Администраторы не могут брать книги!", "error")
        return redirect(url_for('home'))

    db_sess = db_session.create_session()
    book = db_sess.query(Book).get(book_id)

    if not book or book.quantity <= 0:
        flash("Книга недоступна!", "error")
        return redirect(url_for('home'))

    book.quantity -= 1
    return_by = datetime.utcnow() + timedelta(days=current_user.max_borrow_days)

    borrowed_book = BorrowedBook(user_id=current_user.id, book_id=book_id, return_by=return_by)
    db_sess.add(borrowed_book)
    db_sess.commit()

    flash("Вы успешно взяли книгу!", "success")
    return redirect(url_for('home'))


@app.route('/return/<int:book_id>')
@login_required
def return_book(book_id):
    db_sess = db_session.create_session()
    borrowed_book = db_sess.query(BorrowedBook).filter_by(user_id=current_user.id, book_id=book_id).first()

    if not borrowed_book:
        flash("Эта книга не была взята вами!", "error")
        return redirect(url_for('home'))

    book = db_sess.query(Book).get(book_id)
    if not book:
        flash("Книга не найдена!", "error")
        return redirect(url_for('home'))

    is_late = datetime.utcnow() > borrowed_book.return_by
    update_rating(current_user, is_late)

    book.quantity += 1
    db_sess.delete(borrowed_book)
    db_sess.commit()

    flash("Вы успешно вернули книгу!", "success")
    return redirect(url_for('home'))


@app.route('/my_books')
@login_required
def my_books():
    db_sess = db_session.create_session()

    borrowed_books = (
        db_sess.query(BorrowedBook)
        .filter_by(user_id=current_user.id)
        .all()
    )

    books_info = []
    for borrowed_book in borrowed_books:
        book = db_sess.query(Book).get(borrowed_book.book_id)
        if book:
            books_info.append({
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "genre": book.genre,
                "return_by": borrowed_book.return_by,
                "is_late": datetime.utcnow() > borrowed_book.return_by
            })

    return render_template('my_books.html', books=books_info)


def update_rating(user, is_late):
    if is_late:
        user.rating -= 20
    else:
        user.rating += 10

    user.max_borrow_days = calculate_max_borrow_days(user.rating)


def calculate_max_borrow_days(rating):
    if rating < 20:
        return 28
    elif rating < 50:
        return 35
    elif rating < 80:
        return 42
    elif rating < 100:
        return 49
    elif rating < 150:
        return 56
    elif rating < 200:
        return 63
    elif rating < 250:
        return 70
    elif rating < 300:
        return 77
    elif rating < 350:
        return 84
    elif rating < 400:
        return 91
    elif rating < 450:
        return 98
    else:
        return 105


@app.route('/add_book', methods=['GET', 'POST'])
@login_required
def add_book():
    if current_user.role != "admin":
        flash("У вас нет прав для доступа к этой странице!", "error")
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form.get('title')
        author = request.form.get('author')
        genre = request.form.get('genre')
        quantity = int(request.form.get('quantity', 1))

        db_sess = db_session.create_session()
        new_book = Book(title=title, author=author, genre=genre, quantity=quantity)
        db_sess.add(new_book)
        db_sess.commit()

        flash("Книга успешно добавлена!", "success")
        return redirect(url_for('home'))

    return render_template('add_book.html')


@app.route('/edit_book/<int:book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    if current_user.role != "admin":
        flash("У вас нет прав для доступа к этой странице!", "error")
        return redirect(url_for('home'))

    db_sess = db_session.create_session()
    book = db_sess.query(Book).get(book_id)

    if not book:
        flash("Книга не найдена!", "error")
        return redirect(url_for('books'))

    if request.method == 'POST':
        book.title = request.form.get('title', book.title)
        book.author = request.form.get('author', book.author)
        book.genre = request.form.get('genre', book.genre)
        book.quantity = int(request.form.get('quantity', book.quantity))

        db_sess.commit()
        flash("Книга успешно отредактирована!", "success")
        return redirect(url_for('books'))

    return render_template('edit_book.html', book=book)


@app.route('/remove_one_book/<int:book_id>')
@login_required
def remove_one_book(book_id):
    if current_user.role != "admin":
        flash("У вас нет прав для доступа к этой странице!", "error")
        return redirect(url_for('home'))

    db_sess = db_session.create_session()
    book = db_sess.query(Book).get(book_id)

    if not book or book.quantity <= 0:
        flash("Невозможно удалить экземпляр книги — их больше нет!", "error")
        return redirect(url_for('books'))

    book.quantity -= 1
    db_sess.commit()

    flash("Экземпляр книги успешно удален!", "success")
    return redirect(url_for('books'))


@app.route('/delete_all_books/<int:book_id>')
@login_required
def delete_all_books(book_id):
    if current_user.role != "admin":
        flash("У вас нет прав для доступа к этой странице!", "error")
        return redirect(url_for('home'))

    db_sess = db_session.create_session()
    book = db_sess.query(Book).get(book_id)

    if not book:
        flash("Книга не найдена!", "error")
        return redirect(url_for('books'))

    db_sess.delete(book)
    db_sess.commit()

    flash("Книга успешно удалена!", "success")
    return redirect(url_for('books'))


@app.route('/books')
@login_required
def books():
    db_sess = db_session.create_session()
    books_ = db_sess.query(Book).all()

    return render_template('books.html', books=books_)


@app.route('/profile')
@login_required
def profile():
    db_sess = db_session.create_session()
    user = db_sess.query(User).get(current_user.id)

    if not user:
        flash("Пользователь не найден!", "error")
        return redirect(url_for('home'))

    return render_template('profile.html', user=user)


if __name__ == '__main__':
    app.run(port=8080, host='127.0.0.1')