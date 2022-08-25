"""
ORM model for bill stored in DB
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import BIT, JSON, TIMESTAMP
from config import CONFIG


Base = declarative_base()


class Bill(Base):
    __tablename__ = CONFIG['DB_connection']['bills_table_name']
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    bill_text = Column(Text, name='text')
    simhash_text = Column(BIT(128))
    simhash_title = Column(BIT(128))
    origin = Column(String(255))
    pagenum = Column(Integer)
    label = Column(String(100))
    xml_id = Column(String(50))
    parent_bill_id = Column(Integer, nullable=True)
    meta_info = Column(JSON)

    created = Column(TIMESTAMP, default=datetime.now())

    def __repr__(self):
        return self.title


class Section(Base):
    __tablename__ = CONFIG['DB_connection']['sections_table_name']
    id = Column(Integer, primary_key=True)
    bill_id = Column(Integer, nullable=True)
    bill_origin = Column(String(255))
    text = Column(Text)
    section_id = Column(String(50))
    parent_id = Column(String(50))
    label = Column(String(200))
    header = Column(String(225))
    simhash_text = Column(BIT(128))
    hash_ngrams = Column(BIT(128))
    hash_words = Column(BIT(128))
    pagenum = Column(Integer)
    length = Column(Integer, nullable=True)

    created = Column(TIMESTAMP, onupdate=datetime.now(), default=datetime.now())


class BillPath(Base):
    __tablename__ = CONFIG['DB_connection']['bill_path_table_name']
    id = Column(Integer, primary_key=True)
    origin = Column(String(255))
    full_path = Column(String(255))
