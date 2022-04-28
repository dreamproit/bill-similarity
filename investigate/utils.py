"""
All required util functions are here just to keep them in one place.
When going to production probably we will refactor utils to several modules according to their purposes.
"""

# LARGE prime numbers for better performing fnv-1a hash function in 128bit
# see: https://en.wikipedia.org/wiki/Fowler%E2%80%93Noll%E2%80%93Vo_hash_function#FNV_hash_parameters
FNV_128_PRIME = 0x1000000000000000000013b
FNV1_128A_INIT = 0x6c62272e07bb014262b821756295c58d


import os
import re
import string
from time import time
from bs4.element import Tag
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fnvhash import fnv1a_64, fnva
from simhash import Simhash
from lxml import etree


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
    text = re.sub(' +', ' ', text)
    return text


def create_title(text, max_len=250, ending='...'):
    """
        Cleaning text in title
        :param text: inpt text
        :param max_len: maximum allowable length of title
        :return:
        """
    text = re.sub('\n|\r|\t', ' ', text.strip())
    text = re.sub(' +', ' ', text)
    return '{}{}'.format(text[:max_len], ending if len(text) > max_len else '')


def _get_text(element, sep='\n'):
    """
    recursive parsing and cleaning of text from beatiful soup elements
    :param element: bs4.element.Tag
    :param sep: separotor between elements
    :return:
    """
    children = []
    if isinstance(element, Tag):
        children = list(element.children)
    if not children:
        txt = element.getText().strip()
        txt = re.sub(' +', ' ', txt)
        return re.sub('\n', '', txt)
    text = ''
    for child in children:
        text += _get_text(child, sep) + ' '
    if element.name == 'header':
        # better to separate text if it's a header
        sep = '\n'
    return text + sep if text else ''


def clean_bill_text(soup):
    """
    Create clean text from beautifulsoup element.
    :param soup:
    :return:
    """
    sections = soup.findAll('section')
    raw_text = '\n'.join([_get_text(section, sep=' ') for section in sections])
    if not re.sub('\n+', '', raw_text):
        raw_text = soup.text
    raw_text = re.sub(' +', ' ', raw_text)
    raw_text = re.sub(' \.', '.', raw_text)
    raw_text = re.sub('\n ?', '\n', raw_text)
    raw_text = re.sub('\n+', '\n', raw_text).strip()
    return raw_text


def parse_xml_section(section):
    """
    Convert xml section to dict with keys or further processing
    :param section: section as xml element
    :return: dictionary with meta_info
    """
    keys = ('id', 'identifier', 'pagenum')
    parsed = dict()
    parsed['element'] = section
    for k, v in section.items():
        if k in keys:
            parsed[k] = v
    filename = create_bill_name(section.base)
    parsed['origin'] = filename
    _text = etree.tostring(section, method="text", encoding="unicode")
    parsed['text'] = _text
    nested = list()
    for ch_num, child in enumerate(section.getchildren()):
        if not isinstance(child.tag, str):
            continue
        tag = re.sub('{http://xml.house.gov/schemas/uslm/1.0}', '', child.tag)
        if tag in ('heading', 'header'):
            header = child.text or etree.tostring(child, method="text", encoding="unicode")
            parsed['header'] = header.strip()
        if tag in ('num', 'number'):
            parsed['num'] = child.text
        if 'subsection' in child.tag:
            nested.append(parse_xml_section(child))
    if nested:
        parsed['nested'] = nested
    return parsed


# ==================== DB UTILS ====================\
def _create_db_connection_uri(user, pwd, db_name, host, connector):
    db_uri_template = '{connector}://{user}:{pwd}@{host}/{db_name}'
    db_uri = db_uri_template.format(connector=connector,    # 'mysql+mysqlconnector'
                                    user=user,
                                    pwd=pwd,
                                    host=host,              # '127.0.0.1:3306'
                                    db_name=db_name         # 'billtext'
    )
    if 'mysql' in connector:
        db_uri += '?charset=utf8mb4&auth_plugin=mysql_native_password'
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
        connector = config['connector']
    except Exception:
        print('Can`t read configuration from file')
        return None
    db_uri = _create_db_connection_uri(user=user, pwd=passw, db_name=db_name,
                                       host=host, connector=connector)
    engine = create_engine(db_uri)
    session = sessionmaker(bind=engine, autoflush=False)()
    return session


# ==================== SIM HASH UTILS ====================
def _get_ngrams(text, width=3):
    """
    Creates ngrams from text with `width`:
    _get_features('some text', 3)
    >>> ['som', 'ome', 'met', 'ete', 'tex', 'ext']
    :param text:
    :param width:
    :return:
    """
    text = str(text or '').strip().lower()
    if not text:
        return list()
    text = re.sub(r'[^\w]+', '', text)
    if not text:
        return list()
    return [text[i:i + width] for i in range(max(len(text) - width + 1, 1))]


def _get_features(text, width=4):
    """
    Create shingles of `width` words from text:
    _get_features('Lorem ipsum dolor sit amet, consectetur adipiscing elit.', 3)
    >>> ['lorem ipsum dolor', 'ipsum dolor sit', 'dolor sit amet',
        'sit amet consectetur', 'amet consectetur adipiscing', 'consectetur adipiscing elit']
    :param text:
    :param n:
    :return:
    """
    if not text:
        return []
    text = text.lower()
    # replace all none alphanumeric characters with spaces
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text)
    # break sentence in the token, remove empty tokens
    tokens = [token for token in text.split(' ') if token != '']
    ngrams = zip(*[tokens[i:] for i in range(width)])
    return [' '.join(ngram) for ngram in ngrams]


def fnv1a_128(data, hval_init=FNV1_128A_INIT):
    """
    Returns the 128 bit FNV-1a hash value for the given data.
    """
    return fnva(data, hval_init, FNV_128_PRIME, 2**128)


def build_sim_hash(data, n=4):
    """
    Builds a hash - a 64 bit string of the input data using SimHash algorithm
    hashfunc - fnv-1a hashing for 64 bit
    :param data: imput data to hash
    :param n: parameter for ngram
    :return: bit string 64 characters long
    """
    features = _get_ngrams(text=data, width=n)
    sim_obj = Simhash(features, hashfunc=fnv1a_64)
    return re.sub(' ', '0', '{0:64b}'.format(sim_obj.value))


def build_128_simhash(data, n=6):
    """
    Builds a hash - a 128 bit string of the input data using SimHash algorithm
    hashfunc - fnv-1a hashing for 128 bit
    :param data: input data to hash
    :param n: parameter for ngram
    :return: bit string 128 characters long
    """
    features = _get_ngrams(data, width=n)
    sim_obj = Simhash(features, f=128, hashfunc=fnv1a_128)
    return re.sub(' ', '0', '{0:128b}'.format(sim_obj.value))


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


def create_bill_name(path):
    path = re.sub(os.environ.get('HOME'), '', path)
    folders = path.split(os.path.sep)
    try:
        congress_number = re.findall(r'\d+', path)[0]
        name = 'BILLS_' + congress_number
        if 'bills' in folders:
            folders.remove('bills')
        if 'text-versions' in folders:
            folders.remove('text-versions')
        name += '_'.join(folders[-4:])
        return name
    except:
        return name + '_'.join(folders)


def get_xml_sections(xml_path):
    namespaces = {'uslm': 'http://xml.house.gov/schemas/uslm/1.0'}
    bill_tree = etree.parse(xml_path)
    try:
        sections = bill_tree.xpath('//uslm:section', namespaces=namespaces) or bill_tree.xpath('//section')
    except Exception as e:
        sections = []
    return sections


def timer_wrapper(func):
    """
    simple decorator to track time of running func
    :param func:
    :return:
    """
    def inner_wrapper(*args, **kwargs):
        t0 = time()
        res = func(*args, **kwargs)
        print('{} TOTAL TIME:\t {} sec\n'.format(func.__name__, round(time() - t0, 3)))
        return res
    return inner_wrapper


def test_utils():
    samples_folder = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples'
    scan_folder = os.path.join(samples_folder, 'congress/116')
    files = get_all_file_paths(scan_folder, ext='xml')
    for filename in files[:20]:
        sections = get_xml_sections(filename)
        print('found {} sections in {}'.format(len(sections), filename))

    samples_folder = '/Users/dmytroustynov/programm/congress.nosync/data'
    scan_folder = os.path.join(samples_folder, '117/bills/hr/hr2471')

    files = get_all_file_paths(scan_folder, ext='xml')
    for filename in files[:20]:
        sections = get_xml_sections(filename)
        print('found {} sections in {}'.format(len(sections), filename))


def test_utils_0():
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
