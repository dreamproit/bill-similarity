"""
All required util functions are here just to keep them in one place.
When going to production probably we will refactor utils to several modules according to their purposes.
"""

import os
import re
import string
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fnvhash import fnv1a_64
from simhash import Simhash
from nltk.tokenize import wordpunct_tokenize


# ==================== TEXT UTILS ====================
def clean_text(text):
    """
        Cleaning text for further processing with minhash / simhash
        - remove /r /n , remove stopwords, remove punctuation, remove digitals,
        - remove other patterns like http://
        :param text:
        :return: cleaned text
        """
    text = re.sub('\n|\r', ' ', text.lower())
    # clean links and emails
    text = re.sub(r'((www\.[^\s]+)|(https?://[^\s]+))', '', text)
    text = re.sub(r'[\w\+.-\]+@[A-Za-z-]+\.[\w.]+', '', text)
    # clean punctuation
    text = re.sub(r'[^\w ]', '', text)
    text = re.sub(' +', ' ', text)
    return text.strip()


def text_cleaning(text):
    """
    Clean text method
    """
    text = str(text).lower()
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'https?://\S+|www\.\S+', '', text)
    text = re.sub(r'<.*?>+', '', text)
    text = re.sub(r'[%s]' % re.escape(string.punctuation), '', text)
    text = re.sub(r'\n', '', text)
    text = re.sub(r'\w*\d\w*', '', text)
    return text



def create_title(text, max_len=250):
    """
        Cleaning text in title
        :param text: inpt text
        :param max_len: maximum allowable length of title
        :return:
        """
    text = re.sub('\n|\r|\t', ' ', text.strip())
    text = re.sub(' +', ' ', text)
    return '{}{}'.format(text[:max_len], '...' if len(text) > max_len else '')


# ==================== DB UTILS ====================\
def _create_db_connection_uri(user, pwd, db_name, host):
    db_uri_template = 'mysql+mysqlconnector://{user}:{pwd}@{host}/{db_name}' \
                      '?charset=utf8mb4&auth_plugin=mysql_native_password'
    db_uri = db_uri_template.format(user=user,
                                    pwd=pwd,
                                    host=host,              # '127.0.0.1:3306'
                                    db_name=db_name         # 'billtext'
    )
    return db_uri


def create_session(config):
    """

    :param config: configuration for db, should contain
        'user', 'password', 'host', 'db_name' keys to establish connection
    :type config: dict
    :return: db_session
    """
    try:
        user = config['user']
        passw = config['password']
        db_name = config['db_name']
        host = config['host']
    except Exception:
        print('Can`t read configuration from file')
        return None
    db_uri = _create_db_connection_uri(user=user, pwd=passw, db_name=db_name,
                                      host=host)
    engine = create_engine(db_uri)
    session = sessionmaker(bind=engine, autoflush=False)()
    return session


# ==================== SIM HASH UTILS ====================
def _get_features(text, width=3):
    text = str(text or '').strip().lower()
    if not text:
        return list()
    text = re.sub(r'[^\w]+', '', text)
    if not text:
        return list()
    return [text[i:i + width] for i in range(max(len(text) - width + 1, 1))]


def build_sim_hash(data):
    try:
        s_features = _get_features(text=data)
        sim_obj = Simhash(s_features, hashfunc=fnv1a_64)
        return sim_obj
        # return sim_obj.value
    except Exception as e:
        print('{}: {}'.format(type(e).__name__, e))


# ==================== READING FILES UTILS ====================
def _get_file_ext(filename):
    return filename.split('.')[-1]


def _read_texts(filepath):
    texts = []
    if os.path.isfile(filepath):
        with open(filepath, 'r') as file:
            texts = file.read().split('\n')
    else:
        print('file {} doesn`t exist'.format(filepath))
    return texts


def get_all_file_paths(root_folder, ext):
    """
    Recursive reading folder including all subfolders to find
    all files with required extension

    :param root_folder: folder to scan
    :param ext: file extension to grab
    :return: list of full filenames to read
    """
    filenames = list()
    for root_path, folders, files in os.walk(root_folder):
        filenames += [os.path.join(root_path, f) for f in files if _get_file_ext(f) == ext]
        for folder in folders:
            filenames += get_all_file_paths(folder, ext)
    return filenames


def chunk(iterable, chunk_size=50):
    """
    Split iterable to chunks of chunk size
    [1,2,3,4,5] --> chunk( chunk_size=3) --> [1,2,3], [4,5]
    :param iterable: any iterable to split
    :param chunk_size: chunk size
    :return: generate parts of iterable
    """
    i = 0
    while i <= len(iterable):
        yield iterable[i:i + chunk_size]
        i += chunk_size


def get_asymmetric_diff(s1, s2):
    assert isinstance(s1, set), "s1 must be set"
    assert isinstance(s2, set), "s2 must be set"
    assert len(s1) != 0, "shouldn't be empty set"
    return len(s1.intersection(s2)) / len(s1)


def test_utils():
    import random

    s1 = {random.randint(1, 100) for i in range(15)}
    s2 = {random.randint(1, 20) for i in range(10)}

    diff = get_asymmetric_diff(s1, s2)
    diff2 = get_asymmetric_diff(s2, s1)
    print('s1: ', s1)
    print('s2: ', s2)
    print('diff s1--s2', diff)
    print('diff s2--s1', diff2)
    print('No intersection: ', get_asymmetric_diff({1, 2, 3}, {4, 5, 6}))
    print('Full intersection: ', get_asymmetric_diff({1, 2, 3}, {1, 2, 3}))
    print('Full s1 inside s2: ', get_asymmetric_diff({1, 2, 3}, {1, 2, 3, 4, 5, 6}))
    print('Full s2 inside s1: ', get_asymmetric_diff({1, 2, 3, 4, 5, 6}, {1, 2, 3}))
    print('Partial s1 inside large s2: ', get_asymmetric_diff({1, 2, 3}, {1, 3, 4, 5, 6, 7, 8}))


if __name__ == '__main__':
    test_utils()
