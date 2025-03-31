from sqlalchemy import Column, Integer, DateTime, ForeignKey
from data.db_session import SqlAlchemyBase
from datetime import datetime


class BorrowedBook(SqlAlchemyBase):
    __tablename__ = 'borrowed_books'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    book_id = Column(Integer, ForeignKey('books.id'), nullable=False)
    borrowed_at = Column(DateTime, default=datetime.utcnow)
    return_by = Column(DateTime, nullable=False)