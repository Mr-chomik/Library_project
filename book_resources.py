from flask import jsonify
from flask_restful import abort, Resource

from data import db_session
from data.books import Book


def abort_if_not_found(book_id):
    session = db_session.create_session()
    book = session.query(Book).get(book_id)
    if not book:
        abort(404, message=f"Book {book_id} not found")


class BookResource(Resource):
    def get(self, book_id):
        abort_if_not_found(book_id)
        session = db_session.create_session()
        book = session.query(Book).get(book_id)
        return jsonify({'book': book.to_dict(only=('title', 'author', 'genre'))})


class BooksListResource(Resource):
    def get(self):
        session = db_session.create_session()
        books = session.query(Book).all()
        return jsonify({'books': [item.to_dict(only=('title', 'author', 'genre')) for item in books]})