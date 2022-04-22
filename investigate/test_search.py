import os
import re

from config import CONFIG
from bs4 import BeautifulSoup
from lxml import etree

from bill import Bill
from sqlalchemy import text as text_to_query

# import required utils
from utils import create_session
from utils import build_sim_hash
from utils import build_128_simhash
from utils import text_cleaning
from utils import timer_wrapper
from utils import parse_xml_section
from utils import clean_bill_text

NAMESPACES = {'uslm': 'http://xml.house.gov/schemas/uslm/1.0'}


def find_similar_sections(section, session, n=3, ):
    section_text = etree.tostring(section, method="text", encoding="unicode")
    cleaned = text_cleaning(section_text)
    found_similar = []
    simhash_value = None
    if cleaned and len(cleaned) > 55:
        sim_hash = build_sim_hash(cleaned)
        simhash_value = sim_hash.value
        found_similar = search_similar(hsh=simhash_value, session=session, n=n)
    result = {num: {'origin': found.origin,
                    'text': found.bill_text,
                    'hash': found.simhash_text} for num, found in enumerate(found_similar)} if found_similar else None
    if result:
        result['origin_text'] = section_text
        result['origin_hash'] = simhash_value
    return result


@timer_wrapper
def search_similar_by_text(session, text=None, text_hash=None, n=6, verbose=False):
    """
    Search similar entities in db by text.
    PostgreSQL syntax used here.
    Entities supposed to be similar if they have Hamming distance lower than n (by default 4).
    Hamming distance counted between `simhash_value` - integers stored in every row,
    it counted by MYSQL internal function BIT_COUNT of the XOR operation between values stored in db
    and the hash provided (`text_hash` argument).
    If hsh not provided, we try to count it from `text` provided.
    At least `hsh` or `text` should be specified
    :param session: db_session
    :param text: (optional) text to search
    :param text_hash: (optional) bit string to count Hamming distance
    :param n: distance between similar entities
    :return: list of all entities found
    """
    db_table_name = CONFIG['DB_connection']['bills_table_name']
    if not text_hash:
        if not text:
            if verbose:
                print('ERROR, neither hsh, nor text specified')
            return []
        cleaned = text_cleaning(text)
        hash_to_find = build_128_simhash(cleaned)
    else:
        hash_to_find = text_hash
    if verbose:
        print('hash to find: ', hash_to_find)
    sql_template = """
    SELECT * FROM {db_table} 
    WHERE bit_count(simhash_text # b'{hash_to_find}') < {n}"""
    query = text_to_query(sql_template.format(db_table=db_table_name,
                                              hash_to_find=hash_to_find,
                                              n=n))
    return session.query(Bill).from_statement(query).all()


@timer_wrapper
def search_similar_by_title(session, title=None, title_hash=None, n=4, verbose=False):
    """
    Search similar entities in db by title.
    PostgreSQL syntax used here.
    Entities supposed to be similar if they have Hamming distance lower than n (by default 4).
    Hamming distance counted between `simhash_value` - integers stored in every row,
    it counted by MYSQL internal function BIT_COUNT of the XOR operation between values stored in db
    and the hash provided (`hsh` argument).
    If hsh not provided, we try to count it from `text` provided.
    At least `title_hash` or `title` should be specified
    :param session: db_session
    :param title: (optional) text to search
    :param title_hash: (optional) bit string to count Hamming distance
    :param n: distance between similar entities
    :return: list of all entities found
    """
    db_table_name = CONFIG['DB_connection']['bills_table_name']
    if not title_hash:
        if not title:
            if verbose:
                print('ERROR, neither hash, nor title specified')
            return []
        # cleaned = text_cleaning(title)
        hash_to_find = re.sub(' ', '0', '{0:64b}'.format(build_sim_hash(title).value))
    else:
        hash_to_find = title_hash
    if verbose:
        print('hash to find: ', hash_to_find)
    sql_template = """
    SELECT * FROM {db_table} 
    WHERE bit_count(simhash_title # b'{hash_to_find}') < {n}"""
    query = text_to_query(sql_template.format(db_table=db_table_name,
                                              hash_to_find=hash_to_find,
                                              n=n))
    return session.query(Bill).from_statement(query).all()


@timer_wrapper
def search_similar(session, text=None, hsh=None, n=4):
    """
    ! this is a test function to search within Mysql database
    @TODO deprecate and delete
    Search similar entities in db.
    Entities supposed to be similar if they have Hamming distance lower than n (by default 4).
    Hamming distance counted between `simhash_value` - integers stored in every row,
    it counted by MYSQL internal function BIT_COUNT of the XOR operation between values stored in db
    and the hash provided (`hsh` argument).
    If hsh not provided, we try to count it from `text` provided.
    At least `hsh` or `text` should be specified
    :param session: db_session
    :param text: (optional) text to search
    :param hsh: (optional) hash value to count Hamming distance
    :param n: distance between similar entities
    :return: list of all entities found
    """
    db_table_name = CONFIG['DB_connection']['bills_table_name']
    if not hsh:
        if not text:
            print('ERROR, neither hsh, nor text specified')
            return []
        cleaned = text_cleaning(text)
        hash_to_find = build_sim_hash(cleaned).value
    else:
        hash_to_find = hsh
    print('hash to find: ', hsh)
    sql_template = """SELECT * from {} WHERE BIT_COUNT({} ^ simhash_text) < {}"""
    query = text_to_query(sql_template.format(db_table_name, hash_to_find, n))
    return session.query(Bill).from_statement(query).all()


def test_search_old():
    # ! specify your folder name here:
    samples_folder = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/'
    #  looks like this file has a lot of similar paragraphs with other bills
    #  to prove similar search works fine:
    file_path = 'samples/congress/116/train/BILLS-116hr724enr.xml'
    bill_path = os.path.join(samples_folder, file_path)
    bill_tree = etree.parse(bill_path)
    sections = bill_tree.xpath('//uslm:section', namespaces=NAMESPACES)
    paragraphs = [parse_xml_section(sec) for sec in sections]
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    for element in paragraphs:
        paragraph_text = element.get('text')
        cleaned = text_cleaning(paragraph_text)
        sim_hash = build_sim_hash(cleaned)
        simhash_value = sim_hash.value
        found_similar_paragraphs = search_similar(hsh=simhash_value, session=session, n=3)
        if found_similar_paragraphs:
            print('\n--- found similar paragraphs: ----')
            print('ORIGIN: ', paragraph_text)
            for e, sim in enumerate(found_similar_paragraphs):
                print('SIM {}:\t {}'.format(e, sim.bill_text))
                print('FROM: {}\t\t {}'.format(sim.origin, sim.label))


def test_search():
    root_folder = '../../../congress.nosync/data/117/'
    files = [
        'bills/hr/hr1500/text-versions/ih/document.xml',
        'bills/sres/sres323/text-versions/ats/document.xml',
        'bills/sres/sres323/text-versions/ats/document.xml',
        'bills/sconres/sconres34/text-versions/is/document.xml',
        'bills/hr/hr1030/text-versions/ih/document.xml'
        ]
    print('=' * 55 + '\nSEARCH BY SIMILAR TEXTS\n' + '=' * 55)
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    for filename in files:
        xml_file = os.path.join(root_folder, filename)
        with open(xml_file) as xml:
            soup = BeautifulSoup(xml, features="xml")
        # sections = list(soup.findAll('section'))
        raw_text = clean_bill_text(soup)
        found = search_similar_by_text(session, text=raw_text, verbose=True)
        if found:
            print(f'For xml {xml_file} "{raw_text[:55]}..."')
            print(f'found {len(found)} similar entities')
            for bill in found:
                print(f'ID: {bill.id}  origin: {bill.origin}\n "{bill.title}" \n "{bill.bill_text[:155]}..."\n')
    print('='*55 + '\nSEARCH BY SIMILAR TITLES\n' + '='*55)
    titles = [
        'To extend the authorization of the Maurice D. Hinchey Hudson River Valley National Heritage Area.',
        'To amend title 38, United States Code, to establish in the Department of Veterans Affairs an '
        'Advisory Committee Freely Associated States, and for other purposes.',
        'Providing for congressional disapproval of the proposed foreign military sale to the '
        'Kingdom of Saudi Arabia of certain defense articles.',

    ]
    for title in titles:
        # cleaned = text_cleaning(title)
        found_titles = search_similar_by_title(session, title=title, verbose=True)
        if not found_titles:
            print(f'NOT FOUND similar for {title}')
            continue
        print(f'For title "{title}"')
        print(f'found {len(found_titles)} similar entities')
        for bill in found_titles:
            print(f'ID: {bill.id}  origin: {bill.origin}\n "{bill.title}" \n')
        print('-'*50)


if __name__ == '__main__':
    test_search()
