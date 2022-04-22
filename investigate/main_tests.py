import os
import re
import pickle
from lxml import etree
from bill import Bill
from sqlalchemy import text as text_to_query
from config import CONFIG
from bs4 import BeautifulSoup

# import required utils
from utils import text_cleaning, create_title
from utils import create_session
from utils import build_sim_hash
from utils import build_128_simhash
from utils import get_all_file_paths
from utils import chunk
from utils import get_xml_sections
from utils import create_bill_name
from utils import timer_wrapper
from utils import clean_bill_text
from utils import parse_xml_section


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
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    for filename in files:
        if not os.path.isfile(filename):
            print('file not found')
            continue
        # parse_xml_and_load_to_db(filename)
        parse_bill_and_load(filename, session)


def parse_bill_and_load(xml_path, session):
    """
    Tool for saving whole bills with their hashes to db
    :param xml_path:
    :param session:
    :return:
    """
    with open(xml_path) as xml:
        soup = BeautifulSoup(xml, features="xml")
    sections = list(soup.findAll('section'))
    if not sections:
        print('!NO SECTIONS in {}'.format(xml_path))
        return
    raw_text = clean_bill_text(soup)
    cleaned = text_cleaning(raw_text)
    bit_simhash_text = build_128_simhash(cleaned)
    origin = create_bill_name(xml_path)
    titles = soup.find('dc:title') or soup.find('title')
    title = titles.text if titles else ''
    if not raw_text:
        print('-- !! NO text in bill ', xml_path)
        return
    res = soup.find('resolution')
    meta_info = res.attrs if res else dict()
    xml_id = meta_info.get('dms-id')
    bill_date = soup.find('dc:date')
    if bill_date:
        meta_info['xml_date'] = bill_date.text
    bill = Bill(bill_text=raw_text,
                simhash_text=bit_simhash_text,
                origin=origin)
    if xml_id:
        bill.xml_id = xml_id
    if meta_info:
        bill.meta_info = meta_info
    if title:
        bill.title = title
        bill.simhash_title = re.sub(' ', '0', '{0:64b}'.format(build_sim_hash(title).value))
    session.add(bill)
    session.commit()
    print('created bill, ', bill.id)


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
def search_grouped_origins(session, text=None, hsh=None, n=4):
    """
    Search not repeated origins (filenames) in which most related sections are present.
    Most related - those which has closer Hamming distance
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
        SELECT origin, sum(bit_count({hsh} ^ simhash_text)) as sum 
        from {db_table} WHERE BIT_COUNT({hsh} ^ simhash_text) < {offset} 
        group by origin 
        order by sum
    """
    query = text_to_query(sql_template.format(db_table=db_table_name, hsh=hash_to_find, offset=n))
    return {r.origin for r in session.execute(query)}


def find_related_origins(section, session, n=3):
    section_text = etree.tostring(section, method="text", encoding="unicode")
    cleaned = text_cleaning(section_text)
    if cleaned and len(cleaned) > 55:
        sim_hash = build_sim_hash(cleaned)
        simhash_value = sim_hash.value
        return search_grouped_origins(hsh=simhash_value, session=session, n=n)


@timer_wrapper
def test_search():
    fn = '../../../congress.nosync/data/117/bills/hr/hr1500/text-versions/ih/document.xml'
    # fn = '../../../congress.nosync/data/117/bills/sres/sres323/text-versions/ats/document.xml'
    # fn = '../../../congress.nosync/data/117/bills/sconres/sconres34/text-versions/is/document.xml'
    # fn = '../../../congress.nosync/data/117/bills/hr/hr1030/text-versions/ih/document.xml'

    fn = '../../../congress.nosync/data/117/bills/s/s2569/text-versions/is/document.xml'
    # fn = '../../../congress.nosync/data/117/bills/hr/hr4521/text-versions/eas/document.xml'
    sections = get_xml_sections(fn)
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    for section in sections:
        headers = section.xpath('header')
        title = etree.tostring(headers[0], method='text', encoding='unicode') if headers else 'No title found'
        origins = set(find_related_origins(section, session, n=3))
        if origins:
            print(' section  "{}".'.format(title.strip()))
            print('Found {} related bills:'.format(len(origins)))
            print(origins)
        print('-'*55)


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
    # - load to PostgreSQL DB
    # uncomment it once the DB and table was created and connection to it could be established
    parse_and_load()

    # `test_search` used to search similar paragraphs among stored in DB
    # you can change the file name and try to use another xml
    # test_search()

    # `test_parse` is a test function that trying to get sections from another set of bills
    # test_parse()
    print(' ==== END ==== ')
