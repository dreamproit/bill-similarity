import os
import re
import pickle
from time import time
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
from utils import get_xml_sections
from utils import create_bill_name
from utils import timer_wrapper


NAMESPACES = {'uslm': 'http://xml.house.gov/schemas/uslm/1.0'}


def create_bill_from_dict(element):
    """
    Create ORM model of the Bill from xml_element
    :param element: dict with info to create model
    :return: Bill as orm model
    """
    paragraph_text = element.get('text')
    if not paragraph_text:
        return None
    cleaned = text_cleaning(paragraph_text)
    simhash_text = build_sim_hash(cleaned)
    title = create_title(element.get('header', ''))
    origin = element.get('origin')
    label = element.get('num')
    pagenum = int(element.get('pagenum', 0))
    xml_id = element.get('id')
    bill = Bill(bill_text=paragraph_text,
                simhash_text=simhash_text.value,
                simhash_title=simhash_text.value,
                origin=origin,
                xml_id=xml_id,
                pagenum=pagenum)
    if label:
        bill.label = label
    if title:
        bill.title = title
        bill.simhash_title = build_sim_hash(title).value
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


@timer_wrapper
def parse_and_load():
    """
    !WARNING there is no protection of uniqueness texts/hashes or any other check
    if the text/paragraph was already loaded to DB table or not.
    So run this only once, or truncate table, otherwise you create a lot of duplicates,
     and further search of similar will produce a bunch of noise results.

    :return:
    """
    # specify your folder here:
    # samples_folder = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples'
    samples_folder = '/Users/dmytroustynov/programm/congress.nosync/data'
    scan_folder = os.path.join(samples_folder, '117')

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
    sections = get_xml_sections(xml_path)
    if not sections:
        print('!NO SECTIONS in {}'.format(xml_path))
        return
    parsed = [parse_xml_section(sec) for sec in sections]
    print('-- Successfully parsed {} xml sections.'. format(len(parsed)))
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    counter = 0
    nested_bills_counter = 0
    for num, element in enumerate(parsed):
        bill = create_bill_from_dict(element)
        if not bill:
            continue
        session.add(bill)
        session.commit()
        counter += 1
        for nested in element.get('nested', []):
            nested_bill = create_bill_from_dict(nested)
            if not nested_bill:
                continue
            if bill.label and nested_bill.label:
                nested_bill.label = '{} | {}'.format(bill.label, nested_bill.label)
            nested_bill.parent_bill_id = bill.id
            session.add(nested_bill)
            nested_bills_counter += 1
    session.commit()
    print('Added {} texts to db, including {} nested'.format(counter+nested_bills_counter, nested_bills_counter))


@timer_wrapper
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
    print('hash to find: ', hsh)
    sql_template = """SELECT * from {} WHERE BIT_COUNT({} ^ simhash_text) < {}"""
    query = text_to_query(sql_template.format(db_table_name, hash_to_find, n))
    return session.query(Bill).from_statement(query).all()\


@timer_wrapper
def search_similar_agg(session, text=None, hsh=None, n=4):
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
    print('hash to find: ', hsh)
    sql_template = """
    SELECT origin, avg(bit_count({hsh} ^ simhash_text)) as avg 
    from {db_table} WHERE parent_bill_id is NULL and BIT_COUNT({hsh} ^ simhash_text) < {offset} 
    group by origin
    """
    query = text_to_query(sql_template.format(db_table=db_table_name, hsh=hash_to_find, offset=n))
    return [r.origin for r in session.execute(query)]


def find_similar_sections(section, session, n=3, agg=False):
    info = parse_xml_section(section)
    paragraph_text = info.get('text')
    cleaned = text_cleaning(paragraph_text)
    found_similar = []
    simhash_value = None
    search_func = search_similar if not agg else search_similar_agg
    if cleaned and len(cleaned) > 55:
        sim_hash = build_sim_hash(cleaned)
        simhash_value = sim_hash.value
        found_similar = search_func(hsh=simhash_value, session=session, n=n)
    # nested = []
    # for child in section.getchildren():
    #     nested.append(find_similar_sections(child, session, n))
    if agg:
        result = {num: found for num, found in enumerate(found_similar)} if found_similar else None
    else:
        result = {num: {'origin': found.origin,
                        'text': found.bill_text,
                        'hash': found.simhash_text} for num, found in enumerate(found_similar)} if found_similar else None
    # if nested:
    #     result['nested'] = nested
    if result:
        result['origin_text'] = paragraph_text
        result['origin_hash'] = simhash_value
    return result


@timer_wrapper
def test_search():
    fn = '../../../congress.nosync/data/117/bills/hr/hr1500/text-versions/eh/document.xml'
    sections = get_xml_sections(fn)
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    found, counter = {}, 0
    related_bills = dict()
    related_bills2 = dict()
    for section in sections:
        found_similar_sections = find_similar_sections(section, session, n=3)
        if found_similar_sections:
            found[counter] = found_similar_sections
            related_bills[counter] = {s.get('origin') for s in found_similar_sections.values() if isinstance(s, dict)}
        # nested_found = dict()
        # for nested_section in section.getchildren():
        #     nested_found += find_similar_section(nested_section, session, n=3)
        # if nested_found:
        #     found['nested_{}'.format(counter)] = nested_found
        agg_found = find_similar_sections(section, session, n=3, agg=True)
        if agg_found:
            related_bills2[counter] = agg_found
        counter += 1
    print('recursive search done:')

    _ = [print(r, len(v), v) for r, v in related_bills.items()]

    print('aggregated search: ')
    _ = [print(r, len(v), v) for r, v in related_bills2.items()]


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


def test_parse():
    root_folder = '/Users/dmytroustynov/programm/congress.nosync'
    zip_files = get_all_file_paths(root_folder, ext='zip')
    print('Found {} zip'.format(len(zip_files)))


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
    test_search()

    # `test_parse` is a test function that trying to get sections from another set of bills
    # test_parse()
    print(' ==== END ==== ')
