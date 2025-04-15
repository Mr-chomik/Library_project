from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

SqlAlchemyBase = declarative_base()


def global_init(db_file):
    engine = create_engine(f'sqlite:///{db_file}?check_same_thread=False')
    SqlAlchemyBase.metadata.create_all(engine)
    global Session
    Session = sessionmaker(bind=engine)


def create_session():
    return Session()