"""
ORM model for bill stored in DB
"""
from sqlalchemy import Column, Integer, String, Text, BIGINT
from sqlalchemy.ext.declarative import declarative_base
from config import CONFIG


Base = declarative_base()


class Bill(Base):
    __tablename__ = CONFIG['DB_connection']['bills_table_name']
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    bill_text = Column(Text, name='text')
    simhash_text = Column(BIGINT())
    simhash_title = Column(BIGINT())
    origin = Column(String(255))
    pagenum = Column(Integer)
    label = Column(String(100))
    xml_id = Column(String(50))
    parent_bill_id = Column(Integer, nullable=True)

    def __repr__(self):
        return self.title
