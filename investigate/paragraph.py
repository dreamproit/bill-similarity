"""
Comparable class for bill paragraphs

"""
import pickle
from itertools import product

from utils import build_sim_hash
from utils import text_cleaning


class Paragraph:
    def __init__(self, text, **kwargs):
        self.text = text
        self.hash_value = None
        self.children = list()
        self.tag = kwargs.get('tag')
        if kwargs.get('nested') is not None:
            for item in kwargs.get('nested'):
                self.add_child(Paragraph.from_dict(item))
        if kwargs.get('hash_value') is not None:
            self.hash_value = kwargs.get('hash_value')
        if not self.hash_value and text is not None:
            cleaned = text_cleaning(self.text)
            self.hash_value = build_sim_hash(cleaned).value

    def get_children(self):
        for ch in self.children:
            yield ch

    @classmethod
    def from_dict(cls, data):
        text = None
        if data.get('text') is not None:
            text = data.pop('text')
        return Paragraph(text, **data)

    def to_dict(self):
        return dict(text=self.text,
                    hash_value=self.hash_value,
                    tag=self.tag,
                    children=[f.to_dict() for f in self.get_children()])

    def add_child(self, child):
        self.children.append(child)

    @property
    def has_children(self):
        return bool(self.children)

    def __len__(self):
        return len(self.text)

    def process(self, func):
        for ch in self.get_children():
            if ch.has_children:
                ch.process(func)
            func(self)

    def hashes(self):
        hashes = list()
        for ch in self.get_children():
            if ch.has_children:
                hashes += [h for h in ch.hashes() if h]
            hashes.append(self.hash_value)
        return hashes

    def compare(self, other):
        similars = []
        if self is other:
            return [('the same bills were compared', True)]
        for p1, p2 in product(self.get_children(), other.get_children()):
            h1 = p1.hash_value
            h2 = p2.hash_value
            if h1 and h2 and bin(h1 ^ h2).count('1') < 5:
                similars.append((p1.text, p2.text))
        return similars

    @classmethod
    def metric(cls, paragraph1, paragraph2):
        return len(paragraph1.text) - len(paragraph2.text)

    def full_text(self, sep='\n'):
        return self.text + \
               sep + \
               sep.join([ch.text for ch in self.get_children()])

    def __repr__(self):
        return '{} - [{}]'.format(self.text, len(self))


def test_parse():

    with open('../investigate/bills_6.pkl', 'rb') as pkl:
        bills = pickle.load(pkl)
    paragraphs = dict()
    print('Load OK: {} bills.'.format(len(bills)))
    for i, (num, b) in enumerate(bills.items()):
        paragraphs[num] = Paragraph.from_dict(b)
        if i % 100 == 0:
            print(f'\r {i}')
    print()
    print('All {} converted.'.format(len(paragraphs)))
    with open('../investigate/paragraphs_6.pkl', 'wb') as file:
        pickle.dump(paragraphs, file)
