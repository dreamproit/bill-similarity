
create table xml_bills
(
    id                  serial
        primary key,
    title               text,
    text                text not null,
    simhash_text        bit(128),
    simhash_title       bit(128),
    origin              text,
    pagenum             integer,
    label               text,
    xml_id              text,
    parent_bill_id      integer,
    meta_info           json,
    title_ngrams_length integer,
    title_word_ngrams   text[]
);

CREATE EXTENSION pg_prewarm;
CREATE EXTENSION pg_trgm;
CREATE EXTENSION btree_gin;
CREATE EXTENSION btree_gist;

create index trgm_gin_idx
    on xml_bills using gin (title gin_trgm_ops);

create index xml_bills_title_ngrams_length_idx
    on xml_bills (title_ngrams_length);

create index word_ngrams_gin_idx
    on xml_bills using gin (title_word_ngrams);

create index id_title_gist_trgm_idx
    on xml_bills using gist (id, title gist_trgm_ops);