from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from datetime import datetime, timedelta
from flask_restful import Api
from sqlalchemy import or_
import base64

import book_resources
from data import db_session
from data.users import User
from data.books import Book
from data.borrowed_book import BorrowedBook
from helping_functions import optimize_image, load_admin_ids, calculate_max_borrow_days

app = Flask(__name__)
api = Api(app)

api.add_resource(book_resources.BooksListResource, '/api/v1/books')
api.add_resource(book_resources.BookResource, '/api/v1/book/<int:book_id>')

app.config['SECRET_KEY'] = 'real_secret_key'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

db_session.global_init("db/library.db")

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

GENRES = ['Все', 'Антиутопия', 'Апокалиптика', 'Басня', 'Военная проза', 'Детектив', 'Детская литература', 'Драма',
          'Историческая проза', 'Исторический жанр', 'Комедия', 'Криминальный жанр', 'Научная фантастика', 'Повесть',
          'Политическая фантастика', 'Постапокалиптика', 'Психологический реализм', 'Роман', 'Роман в стихах', 'Сатира',
          'Фантастика', 'Фикшн', 'Философия']


def update_rating(user, borrowed_book):
    if borrowed_book.borrowed_at.date() == datetime.utcnow().date():
        flash("Вы не можете повысить свой рейтинг при сдаче книги в день ее получения!", "info")
        return

    is_late = datetime.utcnow() > borrowed_book.return_by

    if is_late:
        user.rating -= 30
    else:
        user.rating += 20

    user.max_borrow_days = calculate_max_borrow_days(user.rating)

    db_sess = db_session.create_session()
    db_sess.merge(user)
    db_sess.commit()


@login_manager.user_loader
def load_user(user_id):
    db_sess = db_session.create_session()
    return db_sess.query(User).get(int(user_id))


@app.route('/')
@app.route('/home')
@login_required
def home():
    db_sess = db_session.create_session()
    borrowed_books = (db_sess.query(BorrowedBook).filter_by(user_id=current_user.id).all())

    tomorrow = datetime.utcnow() + timedelta(days=1)
    for borrowed_book in borrowed_books:
        if borrowed_book.return_by.date() == tomorrow.date():
            if not request.cookies.get(f"reminder_{borrowed_book.id}"):
                book = db_sess.query(Book).get(borrowed_book.book_id)
                if book:
                    flash(f"Напоминание: верните книгу '{book.title}' до {borrowed_book.return_by.strftime('%d.%m.%Y')}","info")

    books_ = (db_sess.query(Book).order_by(Book.id.desc()).limit(3).all())
    books_params = []
    for book in books_:
        if book.image_data:
            image_base64 = base64.b64encode(book.image_data).decode('utf-8')
            mimetype = "image/jpeg" if book.image_data.startswith(b'\xff\xd8\xff') else "image/png"
            image_url = f"data:{mimetype};base64,{image_base64}"
        else:
            image_url = url_for('static', filename='images/default-book.png')

        books_params.append({
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'genre': book.genre,
            'quantity': book.quantity,
            'image_url': image_url})

    response = make_response(render_template('home.html', books=books_params))

    db_sess = db_session.create_session()
    borrowed_books = (
        db_sess.query(BorrowedBook).filter_by(user_id=current_user.id).all())

    for borrowed_book in borrowed_books:
        if borrowed_book.return_by.date() == tomorrow.date():
            response.set_cookie(f"reminder_{borrowed_book.id}", "true", max_age=86400)

    return response


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

        new_user = User(name=name, username=username, password=password, role="reader", rating=100, max_borrow_days=56)
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

        new_admin = User(name=name, username=username, password=password, role="admin", rating=100, max_borrow_days=56)
        db_sess.add(new_admin)
        db_sess.commit()

        flash("Администратор успешно зарегистрирован!", "success")
        return redirect(url_for('login'))

    return render_template('register_admin.html')


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

    borrowed_book = (db_sess.query(BorrowedBook).filter_by(user_id=current_user.id, book_id=book_id).first())

    if borrowed_book:
        flash("У вас уже есть эта книга!", "error")
        return redirect(url_for('home'))

    book.quantity -= 1

    return_by = datetime.utcnow() + timedelta(days=current_user.max_borrow_days)

    new_borrowed_book = BorrowedBook(
        user_id=current_user.id,
        book_id=book_id,
        return_by=return_by)
    db_sess.add(new_borrowed_book)
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

    # Возвращаем книгу в библиотеку
    book.quantity += 1  # Увеличиваем количество доступных экземпляров

    # Обновляем рейтинг пользователя
    update_rating(current_user, borrowed_book)  # Передаем объект borrowed_book

    # Удаляем запись о взятой книге
    db_sess.delete(borrowed_book)
    db_sess.commit()

    flash("Вы успешно вернули книгу!", "success")
    return redirect(url_for('home'))


@app.route('/my_books')
@login_required
def my_books():
    db_sess = db_session.create_session()

    borrowed_books = (db_sess.query(BorrowedBook).filter_by(user_id=current_user.id).all())

    tomorrow = datetime.utcnow() + timedelta(days=1)
    books_info = []
    for borrowed_book in borrowed_books:
        book = db_sess.query(Book).get(borrowed_book.book_id)
        if book:
            if borrowed_book.return_by.date() == tomorrow.date():
                if not request.cookies.get(f"reminder_{borrowed_book.id}"):
                    flash(f"Напоминание: верните книгу '{book.title}' до"
                          f" {borrowed_book.return_by.strftime('%d.%m.%Y')}","info")

            books_info.append({
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "genre": book.genre,
                "return_by": borrowed_book.return_by.strftime('%d.%m.%Y'),
                "is_late": datetime.utcnow() > borrowed_book.return_by})

    response = make_response(render_template('my_books.html', books=books_info))

    for borrowed_book in borrowed_books:
        if borrowed_book.return_by.date() == tomorrow.date():
            response.set_cookie(f"reminder_{borrowed_book.id}", "true", max_age=86400)

    return response


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

        file = request.files.get('image')
        if file and file.filename:
            try:
                image_data = optimize_image(file)
            except Exception as e:
                flash(f"Ошибка чтения изображения: {e}", "error")
                image_data = None
        else:
            image_data = None

        db_sess = db_session.create_session()
        new_book = Book(
            title=title,
            author=author,
            genre=genre,
            quantity=quantity,
            image_data=image_data
        )
        db_sess.add(new_book)
        db_sess.commit()

        flash("Книга успешно добавлена!", "success")
        return redirect(url_for('books'))

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


@app.route('/books', methods=['GET'])
@login_required
def books():
    db_sess = db_session.create_session()

    search_query = request.args.get('search', '').strip()
    selected_genres = request.args.getlist('genre')

    query = db_sess.query(Book)

    if search_query:
        query = query.filter(
            (Book.title.ilike(f"%{search_query}%")) |
            (Book.author.ilike(f"%{search_query}%"))
        )

    if selected_genres and "all" not in selected_genres:
        conditions = [Book.genre.like(f"%{genre}%") for genre in selected_genres]
        query = query.filter(or_(*conditions))

    books_ = query.all()

    books_params = []
    for book in books_:
        already_borrowed = (db_sess.query(BorrowedBook).filter_by(user_id=current_user.id, book_id=book.id).first() is not None)

        if book.image_data:
            image_base64 = base64.b64encode(book.image_data).decode('utf-8')
            mimetype = "image/jpeg" if book.image_data.startswith(b'\xff\xd8\xff') else "image/png"
            image_url = f"data:{mimetype};base64,{image_base64}"
        else:
            image_url = url_for('static', filename='images/no_photo.png')

        books_params.append({
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'genre': book.genre,
            'quantity': book.quantity,
            'image_url': image_url,
            'already_borrowed': already_borrowed})

    return render_template('books.html', books=books_params, search_query=search_query, genres=GENRES,
                           selected_genres=selected_genres)


@app.route('/author/<string:author_name>')
@login_required
def books_by_author(author_name):
    db_sess = db_session.create_session()

    books_ = (db_sess.query(Book).filter(Book.author.ilike(f"%{author_name}%")).all())

    if not books_:
        flash("Книги данного автора не найдены!", "info")

    books_params = []
    for book in books_:
        if book.image_data:
            image_base64 = base64.b64encode(book.image_data).decode('utf-8')
            mimetype = "image/jpeg" if book.image_data.startswith(b'\xff\xd8\xff') else "image/png"
            image_url = f"data:{mimetype};base64,{image_base64}"
        else:
            image_url = url_for('static', filename='images/default-book.png')

        books_params.append({
            'id': book.id,
            'title': book.title,
            'author': book.author,
            'genre': book.genre,
            'quantity': book.quantity,
            'image_url': image_url
        })

    return render_template('books_by_author.html', books=books_params, author_name=author_name)


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