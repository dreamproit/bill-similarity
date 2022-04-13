import os
import re
import pickle
from lxml import etree
from bill import Bill
from sqlalchemy import text as text_to_query
from config import CONFIG

# import required utils
from utils import text_cleaning, create_title
from utils import create_session
from utils import build_sim_hash
from utils import get_all_file_paths
from utils import chunk


NAMESPACES = {'uslm': 'http://xml.house.gov/schemas/uslm/1.0'}


def create_bill_from_dict(element):
    """
    Create ORM model of the Bill from xml_element
    :param element: dict with info to create model
    :return: Bill as orm model
    """
    paragraph_text = element.get('text')
    cleaned = text_cleaning(paragraph_text)
    sim_hash = build_sim_hash(cleaned)
    simhash_value = sim_hash.value
    title = create_title(element.get('header', ''))
    origin = element.get('origin')
    paragraph = element.get('num')
    pagenum = int(element.get('pagenum', 0))
    xml_id = element.get('id')
    bill = Bill(bill_text=paragraph_text,
                sim_hash=sim_hash.value.to_bytes(64, byteorder='big'),
                simhash_value=simhash_value,
                origin=origin,
                xml_id=xml_id,
                pagenum=pagenum,
                paragraph=paragraph)
    if title:
        bill.title = title
    return bill


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
    _, filename = os.path.split(section.base)
    if filename:
        parsed['origin'] = filename
    _text = etree.tostring(section, method="text", encoding="unicode")
    parsed['text'] = _text
    nested = list()
    for ch_num, child in enumerate(section.getchildren()):
        if not isinstance(child.tag, str):
            continue
        tag = re.sub('{http://xml.house.gov/schemas/uslm/1.0}', '', child.tag)
        if tag in ('heading', 'header'):
            parsed['header'] = child.text.strip()
        if tag in ('num', 'number'):
            parsed['num'] = child.text
        if 'subsection' in child.tag:
            nested.append(parse_xml_section(child))
    if nested:
        parsed['nested'] = nested
    return parsed


def parse_and_load():
    """
    !WARNING there is no protection of uniqueness texts/hashes or any other check
    if the text/paragraph was already loaded to DB table or not.
    So run this only once, or truncate table, otherwise you create a lot of duplicates,
     and further search of similar will produce a bunch of noise results.

    :return:
    """
    # specify your folder here:
    samples_folder = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples'
    scan_folder = os.path.join(samples_folder, 'congress/116')

    files = get_all_file_paths(scan_folder, ext='xml')
    print('Processing {} files...'.format(len(files)) if files else
          'No files found')
    for filename in files:
        if not os.path.isfile(filename):
            print('file not found')
            continue
        parse_xml_and_load_to_db(filename)


def parse_xml_and_load_to_db(xml_path):
    """
    Parse single xml file and load to DB
    ( exactly as it specified in function name )
    Splits the bill to sections and store them separately.
    If section contain subsections (paragraphs) store each of them as well.

    :param xml_path: path to bill in xml format
    :return: None
    """
    bill_tree = etree.parse(xml_path)
    sections = bill_tree.xpath('//uslm:section', namespaces=NAMESPACES)
    parsed = [parse_xml_section(sec) for sec in sections]
    print('-- Successfully parsed {} xml sections.'. format(len(parsed)))
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    counter = 0
    nested_bills_counter = 0
    for num, element in enumerate(parsed):
        bill = create_bill_from_dict(element)
        session.add(bill)
        counter += 1
        for nested in element.get('nested', []):
            nested_bill = create_bill_from_dict(nested)
            nested_bill.paragraph = '{} | {}'.format(bill.paragraph, nested_bill.paragraph)
            session.add(nested_bill)
            nested_bills_counter += 1
    session.commit()
    print('Added {} texts to db, including {} nested'.format(counter+nested_bills_counter, nested_bills_counter))


def search_similar(session, text=None, hsh=None, n=4):
    """
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
    sql_template = """SELECT * from {} WHERE BIT_COUNT({} ^ simhash_value) < {}"""
    query = text_to_query(sql_template.format(db_table_name, hash_to_find, n))
    return session.query(Bill).from_statement(query).all()


def test_search():
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
                print('FROM: {}\t\t '.format(sim.origin, sim.paragraph))


def parse_xml_bill(element):
    info = dict()
    for k, v in element.items():
        info[k] = v
    info['tag'] = element.tag
    text = etree.tostring(element, method='text', encoding='unicode').strip()
    if text:
        info['text'] = text
    nested = list()
    for ch_num, child in enumerate(element.getchildren()):
        nested.append(parse_xml_bill(child))
    if nested:
        info['nested'] = nested
    return info


def test_parse_and_dump():
    """
    Function to parse congress bills and dump them with pickle as dictionaries.
    Each bill is represented as a dictionary with xml data such as text, tag, attributes
    and nested xml if present.
    :return:
    """
    # specify your folder name here:
    root_folder = '/Users/dmytroustynov/programm/congress/data/117'
    xml_files = get_all_file_paths(root_folder, ext='xml')
    print('Found {} xml-files in {}.'.format(len(xml_files), root_folder))
    for chunk_number, file_chunk in enumerate(chunk(xml_files, chunk_size=5000)):
        counter = 0
        parsed = dict()
        for xml_path in file_chunk:
            if not os.path.isfile(xml_path):
                continue
            bill_tree = etree.parse(xml_path)
            xml_bills = bill_tree.xpath('//bill')
            if not xml_bills:
                continue
            for num, xml_bill in enumerate(xml_bills):
                info = parse_xml_bill(xml_bill)
                info['origin'] = xml_path
                parsed[counter] = info
                counter += 1
        print('parsed {} files with bills'.format(counter))
        pkl_file_name = 'bills_{}.pkl'.format(chunk_number + 7)
        with open(pkl_file_name, 'wb') as pkl:
            pickle.dump(parsed, pkl)
        print('successfully serialized {} xml bills to {}.'.format(len(parsed), pkl_file_name))


if __name__ == '__main__':
    print(' ==== START ==== ')
    # `parse_and_load` performs loading entities to DB:
    # - read and parse xml files from `samples/congress` folder
    # - split them to sections and count simhash for each section
    # - load to MySQL DB
    # uncomment it once the DB and table was created and connection to it could be established
    # Don`t forget to install mysql-connector-python, if you haven't run `pip install -r requirements.txt` yet
    # parse_and_load()

    # `test_search` used to search similar paragraphs among stored in DB
    # you can change the file name and try to use another xml
    # test_search()

    # `test_parse` is a test function that trying to get sections from another set of bills
    test_parse_and_dump()
    print(' ==== END ==== ')
