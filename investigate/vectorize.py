# python
import json
import os
import pickle
import subprocess
import random
from time import time
from os import path, listdir
from os.path import isfile, join
from lxml import etree
from nltk.tokenize import RegexpTokenizer
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from config import CONFIG
from bill import Bill

from utils import text_cleaning
from utils import get_all_file_paths
from utils import create_session
from utils import timer_wrapper


# Among the larger bills is samples/congress/116/BILLS-116s1790enr.xml (~ 10MB)
PATH_116_USLM = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples/congress/116/uslm'
PATH_117_USLM = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples/congress/116/uslm'
PATH_116_USLM_TRAIN = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples/congress/116/train'
PATH_116_TEXT = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples/congress/116/txt'

BILLS_SAMPLE = [f'BILLS-116hr{number}ih.xml' for number in range(100, 300)]
BIG_BILLS = ['BILLS-116s1790enr.xml', 'BILLS-116hjres31enr.xml']
BIG_BILLS_PATHS = [path.join(PATH_116_USLM, bill) for bill in (BIG_BILLS + BILLS_SAMPLE)]

SAMPLE_BILL_PATHS_TRAIN = [join(PATH_116_USLM_TRAIN, f) for f in listdir(PATH_116_USLM) if
                           isfile(join(PATH_116_USLM_TRAIN, f))]
SAMPLE_BILL_PATHS = [join(PATH_117_USLM, f) for f in listdir(PATH_117_USLM) if isfile(join(PATH_117_USLM, f))]

NAMESPACES = {'uslm': 'http://xml.house.gov/schemas/uslm/1.0'}


def get_enum(section) -> str:
    enum_path = section.xpath('enum')
    if len(enum_path) > 0:
        return enum_path[0].text
    return ''


def get_header(section) -> str:
    header_path = section.xpath('header')
    if len(header_path) > 0:
        return header_path[0].text
    return ''


def sec_to_dict(section):
    data = {'section_text': etree.tostring(section, method="text", encoding="unicode"),
            'section_xml': etree.tostring(section, method="xml", encoding="unicode"),
            'section_number': '',
            'section_header': ''}
    if (section.xpath('header') and len(section.xpath('header')) > 0
            and section.xpath('enum') and len(section.xpath('enum')) > 0):
        data['section_number'] = get_enum(section)
        data['section_header'] = get_header(section)
    return data


def xml_to_sections(xml_path: str):
    """
    Parses the xml file into sections
    """
    bill_tree = etree.parse(xml_path)
    sections = bill_tree.xpath('//uslm:section', namespaces=NAMESPACES)
    if len(sections) == 0:
        print('No sections found in ', xml_path)
        return []
    return [sec_to_dict(section) for section in sections]


def xml_to_text(xml_path: str, level: str = 'section', separator: str = '\n*****\n') -> str:
    """
    Parses the xml file and returns the text of the body element, if any
    """
    bill_tree = etree.parse(xml_path)
    sections = bill_tree.xpath('//uslm:' + level, namespaces=NAMESPACES)
    if not sections:
        print('No sections found')
        return ''
    return separator.join([etree.tostring(section, method="text", encoding="unicode") for section in sections])


# Get document and section text from xml file for testing purpose
def get_document_and_section_from_xml_file(file_path):
    t_secs = xml_to_sections(file_path)
    if not t_secs:
        return '', []
    t_section_data = []
    t_doc_content = ""
    # iterate over all parse sections text of bill doc file
    for section in t_secs:
        # text cleaning applied on each section text
        sec_text = text_cleaning(section['section_text'])
        # concatenate section text to doc content
        t_doc_content = t_doc_content + sec_text + " "
        # for now sentence id is sentence number in document
        t_section_data.append(sec_text)
    return t_doc_content, t_section_data


def vectorized_transformation(section_doc, sec_count_vectorizer):
    section_doc_vectorized = sec_count_vectorizer.transform(section_doc)
    return section_doc_vectorized


def create_json_response(A_doc_name, B_doc_name, doc_sim_score, sec_doc_sim_score, sentences=None):
    # create result list
    res_list = []
    temp = ["ORIGINAL DOCUMENT ID: " + A_doc_name,
            "MATCHED DOCUMENT ID: " + B_doc_name,
            "DOCUMENT SIMILARITY SCORE: " + str(doc_sim_score[0][0])]

    # iterate over sec_doc_sim_score list 
    for i, section_score_list in enumerate(sec_doc_sim_score):
        # add original document sentence id number
        temp.append("ORIGINAL SENTENCE ID: " + str(i + 1))

        # sort similarity score of sections list
        section_score_list = list(enumerate(section_score_list))
        sorted_section_score_list = sorted(section_score_list, key=lambda x: x[1], reverse=True)

        # iterate over section level score only 
        for j, sim_score in sorted_section_score_list:
            if sim_score and sim_score > 10 ** -2:
                temp.append({"MATCHED DOCUMENT ID": B_doc_name,
                             "MATCHED SENTENCE ID": j + 1 if not isinstance(sentences, dict) else sentences[j+1],
                             "SENTENCE SIMILARITY SCORE": sim_score})
    res_list.append(temp)
    r = json.dumps(res_list)
    parsed = json.loads(r)
    return json.dumps(parsed, indent=5)


def main_test():
    BIG_BILLS = ['BILLS-116s1790enr.xml', 'BILLS-116hjres31enr.xml']
    # BIG_BILLS = ['BILLS-116hconres106enr.xml', 'BILLS-116hconres92enr.xml']
    fld = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples/congress/116/uslm'
    path_a = os.path.join(fld, BIG_BILLS[0])
    path_b = os.path.join(fld, BIG_BILLS[1])

    only_doc_data = []
    only_section_data = []
    root_folder = '/Users/dmytroustynov/programm/BillMap/xc-nlp-test/samples/congress'
    xml_files = get_all_file_paths(root_folder, ext='xml')
    print('FOUND {} files'.format(len(xml_files)))
    for path in xml_files:
        sections = xml_to_sections(path)
        doc_content = ""
        for section in sections:
            sec_text = text_cleaning(section['section_text'])
            doc_content = doc_content + sec_text + " "
            only_section_data.append(sec_text)
        only_doc_data.append(doc_content)

    doc_count_vectorizer = CountVectorizer(ngram_range=(4, 4),
                                           tokenizer=RegexpTokenizer(r"\w+").tokenize,
                                           lowercase=True)

    doc_count_vectorizer.fit_transform(only_doc_data)
    print('fit 1 OK')

    sec_count_vectorizer = CountVectorizer(ngram_range=(4, 4),
                                           tokenizer=RegexpTokenizer(r"\w+").tokenize,
                                           lowercase=True)
    sec_count_vectorizer.fit_transform(only_section_data)
    print('fit 2 OK')

    A_doc, A_section_doc = get_document_and_section_from_xml_file(path_a)
    B_doc, B_section_doc = get_document_and_section_from_xml_file(path_b)
    print('LEN sections in A_doc: ', len(A_section_doc))
    print('LEN sections in B_doc: ', len(B_section_doc))

    A_doc_vectorized = vectorized_transformation([A_doc], doc_count_vectorizer)
    B_doc_vectorized = vectorized_transformation([B_doc], doc_count_vectorizer)
    print('Vector A_doc_vectorized: ', A_doc_vectorized.shape)
    print('Vector B_doc_vectorized: ', B_doc_vectorized.shape)
    A_section_doc_vectorized = vectorized_transformation(A_section_doc, sec_count_vectorizer)
    B_section_doc_vectorized = vectorized_transformation(B_section_doc, sec_count_vectorizer)
    print('Vector A_section_doc_vectorized: ', A_section_doc_vectorized.shape)
    print('Vector B_section_doc_vectorized: ', B_section_doc_vectorized.shape)

    doc_sim_score = cosine_similarity(A_doc_vectorized, B_doc_vectorized)
    sec_doc_sim_score = cosine_similarity(A_section_doc_vectorized, B_section_doc_vectorized)
    print('DOC SIM:')
    print(doc_sim_score)
    print('SECTION SIM:', sec_doc_sim_score.shape)
    print(sec_doc_sim_score)

    A_doc_name, B_doc_name = BIG_BILLS
    response = create_json_response(A_doc_name, B_doc_name, doc_sim_score, sec_doc_sim_score, )
    # print(A_doc_name' + " vs. " + 'B_doc_name')
    print(response)


@timer_wrapper
def create_models():
    """
    Create and serialize to .pkl-files count-vectorizer models.

    DOC model - count-vectorizer model with whole bill texts as input text corpus.
    SECTIONS model - count-vectorizer model with sections texts of the bills as input text corpus.

    For both models text corpora are loaded from DB and cleaned prior to fitting.
    Models then serialized to pkl files `model_filename` and `sections_model_filename`
    so you can use them for further processing.

    :return: none
    """
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)

    # ------- BEGIN CREATE DOC MODEL --------
    text_bills = session.query(Bill).filter(Bill.parent_bill_id == None)
    doc_corpus = []
    print('Start loading bills...')
    t0 = time()
    for bill in text_bills.all():
        doc_corpus.append(text_cleaning(bill.bill_text))
    print('- corpus with {} bills from DB created - OK.'.format(len(doc_corpus)))
    print('took {} sec'.format(round(time() - t0, 3)))
    # with open('bill_texts.pkl', 'wb') as pkl:
    #     pickle.dump(text_corpus, pkl)
    count_vectorizer = CountVectorizer(ngram_range=(4, 4),
                                       tokenizer=RegexpTokenizer(r"\w+").tokenize,
                                       lowercase=True)
    print('- start fitting model...')
    t0 = time()
    count_vectorizer.fit_transform(doc_corpus)
    print('- model fit - OK.')
    print('took {} sec'.format(round(time() - t0, 3)))
    model_filename = 'CV_model.pkl'
    with open(model_filename, 'wb') as pkl:
        pickle.dump(count_vectorizer, pkl)
    res = subprocess.check_output(['du', '-h', model_filename])
    print('DOC Model saved! Model size: {}'.format(res.decode().split('\t')[0]))

    # ------- BEGIN CREATE SECTIONS MODEL --------
    text_sections = session.query(Bill).filter(Bill.parent_bill_id!=None)
    sections_corpus = []
    print('\nStart loading section texts ...')
    t0 = time()
    for bill in text_sections.all():
        sections_corpus.append(text_cleaning(bill.bill_text))
    print('- corpus with {} sections from DB created - OK.'.format(len(sections_corpus)))
    print('took {} sec'.format(round(time() - t0, 3)))
    count_vectorizer_sections = CountVectorizer(ngram_range=(4, 4),
                                                tokenizer=RegexpTokenizer(r"\w+").tokenize,
                                                lowercase=True)
    print(' - start fitting model...')
    t0 = time()
    count_vectorizer_sections.fit_transform(sections_corpus)
    print(' - model fit - OK')
    print('took {} sec'.format(round(time() - t0, 3)))
    sections_model_filename = 'CV_sections_model.pkl'
    with open(sections_model_filename, 'wb') as pkl:
        pickle.dump(count_vectorizer_sections, pkl)
    res = subprocess.check_output(['du', '-h', sections_model_filename])
    print('SECTIONS Model saved! Model size: {}'.format(res.decode().split('\t')[0]))
    # example of output:
    """
        ____ START ____
        Start loading bills...
        - corpus with 107538 bills from DB created - OK.
        took 47.901 sec
        - start fitting model...
        - model fit - OK.
        took 77.226 sec
        DOC Model saved! Model size: 254M
        
        Start loading section texts ...
        - corpus with 180837 sections from DB created - OK.
        took 39.119 sec
         - start fitting model...
         - model fit - OK
        took 54.672 sec
        SECTIONS Model saved! Model size: 185M
        
        TOTAL TIME:	 226.908 sec
        ____ END ____
    """


def test_vectorizer():
    #  ------ GET SOME BILLS FROM DB ------
    db_config = CONFIG['DB_connection']
    session = create_session(db_config)
    bills = [b for b in session.query(Bill).limit(100).all()]

    # ----- DESERILALIZE MODELS -----
    model_filename = 'CV_model.pkl'
    with open(model_filename, 'rb') as pkl:
        doc_count_vectorizer = pickle.load(pkl)

    sections_model_filename = 'CV_sections_model.pkl'
    with open(sections_model_filename, 'rb') as pkl:
        sec_count_vectorizer = pickle.load(pkl)

    bill = random.choice(bills)
    text = bill.bill_text
    print('selected bill: ', bill.id)
    print(text)
    bill_simhash = bill.simhash_text
    print('selected bill simhash: ', bill_simhash)
    if bill.parent_bill_id is not None:
        doc_vectorized = vectorized_transformation([text], doc_count_vectorizer)
        trans_vocab = {v: k for k, v in doc_count_vectorizer.vocabulary_.items()}
    else:
        doc_vectorized = vectorized_transformation([text], sec_count_vectorizer)
        trans_vocab = {v: k for k, v in sec_count_vectorizer.vocabulary_.items()}
    print('vectorized - ok')
    print(doc_vectorized.shape)
    for ind in doc_vectorized.indices:
        print('INDEX: ', int(ind))
        ngram = trans_vocab.get(int(ind))
        print(ngram)
        sim_bill = session.query(Bill).filter_by(id=int(ind)).one_or_none()
        if sim_bill:
            print('   Bill ID: ', sim_bill.id)
            print(sim_bill.bill_text)
            # cnt = str(bill_simhash ^ sim_bill.simhash_text).count('1')
            print('bit count: ', str(bill_simhash ^ sim_bill.simhash_text).count('1'))


if __name__ == '__main__':
    print('____ START ____')
    # main_test()
    # create_models()
    test_vectorizer()
    print('____ END ____')
