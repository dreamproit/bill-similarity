"""
ORM model for bill stored in DB
"""
from sqlalchemy import Column, Integer, String, Text, BLOB, BIGINT
from sqlalchemy.ext.declarative import declarative_base
from config import CONFIG


Base = declarative_base()


class Bill(Base):
    __tablename__ = CONFIG['DB_connection']['bills_table_name']
    id = Column(Integer, primary_key=True)
    title = Column(String(255))
    bill_text = Column(Text, name='text')
    sim_hash = Column(BLOB, name='simhash')
    simhash_value = Column(BIGINT())
    origin = Column(String(255))
    pagenum = Column(Integer)
    paragraph = Column(String(100))
    xml_id = Column(String(50))
    # created_at = Column(DateTime)
    # updated_at = Column(DateTime)

    def __repr__(self):
        return self.title

    # @property
    # def origin_filename(self):
    #     return os.path.split(self.origin)[1]
