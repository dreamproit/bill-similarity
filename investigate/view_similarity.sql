WITH left_titles AS (
    SELECT id, origin, title, title_word_ngrams, title_ngrams_length as tnl
    FROM xml_bills
    order by title_ngrams_length desc
    limit 1 offset 0
),
     right_titles AS (
         SELECT id, origin, title, title_word_ngrams, title_ngrams_length as tnl
         FROM xml_bills
         order by title_ngrams_length desc
     ),
     p as (
         select lt.id                                                      as lt_id,
                rt.id                                                      as rt_id,
                lt.origin                                                  as lb_id,
                rt.origin                                                  as rb_id,
                lt.title                                                   as lt,
                lt.title_word_ngrams                                       as lt_n_n,
                rt.title                                                   as rt,
                rt.title_word_ngrams                                       as rt_n_n,
                lt.tnl                                                     as l_len,
                rt.tnl                                                     as r_len,
                concat(GREATEST(lt.id, rt.id), '<->', LEAST(lt.id, rt.id)) as uid
         from left_titles lt,
              right_titles rt
         WHERE lt.id != rt.id
           and lt.title % rt.title
     ),
     x AS (
         SELECT uid,
                lt,
                rt,
                lb_id,
                rb_id,
                lt_id,
                rt_id,
                (
                    SELECT count(*)
                    FROM (
                             SELECT unnest(lt_n_n)
                             INTERSECT
#                              DISTINCT
                             SELECT unnest(rt_n_n)
                         ) AS s0
                )::integer          AS same,
                (
                    SELECT count(*)
                    FROM (
                             SELECT unnest(lt_n_n)
                             UNION
--                              DISTINCT
                             SELECT unnest(rt_n_n)
                         ) AS s0
                )::integer          AS total,
                l_len,
                r_len,
                similarity(lt, rt)  AS similarity_score
         FROM p
     ),
     with_r2l_l2r as (
         SELECT uid,
                lt_id,
                rt_id,
                lb_id,
                rb_id,
--                 lt,
--                 rt,
                same,
                total,
                l_len,
                r_len,
                same::real / l_len::real                                 AS ltr,
                same::real / r_len::real                                 as rtl,
                same::real / total::real                                 AS sim_1,
                ABS(same::real / l_len::real - same::real / r_len::real) as lr_diff
                 ,
                similarity_score
         FROM x
     ),
     result as (
         select with_r2l_l2r.*, (ltr + rtl ) / 2 as lr_avg
         from with_r2l_l2r
--              where
--                    lr_diff < 0.3
--                ltr > 0.4
--                or rtl > 0.4
     )
select *
from result


WITH
    /*
   Load data to the PG cache to warm up the index.
   */
    warm_up as (
        select (
                       (select pg_prewarm('btiapp_billstagetitle')) +
                       (select pg_prewarm('title_ngram_length_idx')) +
                       (select pg_prewarm('id_title_gist_trgm_idx')) +
                       (select pg_prewarm('id_title_trgm_title_ts_idx'))
                   )
                   as pre_warmed_blocks
    ),
    limit_num as (
        /*
         Limit the number of rows to be processed.
        */
--         select 100000 as n
        /* To process all rows uncomment the following line */
        select (select count(*) from btiapp_billstagetitle) as n
    ),
    offset_num as (select 0 as n),
    left_titles AS (
        SELECT id,
               bill_basic_id,
               title
            /*,
            title_ngrams_length,
            title_n_grams */
        FROM btiapp_billstagetitle
            /* To play with specific bill id uncomment the following line
            where id = '{bill_id}'
            */

            /* Uses the index title_ngram_length_idx */
--         order by cardinality(regexp_split_to_array(title_n_grams, '\|')) desc
        offset (select n from offset_num) limit (select n from limit_num)
    ),
    right_titles AS (
        SELECT id, bill_basic_id, title -- , title_n_grams, title_ngrams_length
        FROM btiapp_billstagetitle
    ),
    p as (
        select lt.id                                                      as lt_id,
               rt.id                                                      as rt_id,
               lt.bill_basic_id                                           as lb_id,
               rt.bill_basic_id                                           as rb_id,
               lt.title                                                   as lt,
               rt.title                                                   as rt,
--                lt.title_n_grams                                           as lt_n_g,
--                rt.title_n_grams                                           as rt_n_g,
               concat(GREATEST(lt.id, rt.id), '<->', LEAST(lt.id, rt.id)) as uid
        from left_titles lt
           , right_titles rt
            /*
            Requires composite index for fields:
               id, title gin_trgm, to_tsvector(title)
            */
        WHERE true
          and lt.id <> rt.id
            /* Possibly might decrease calculation time:
            and lt.id > rt.id
             */
            /* Filter by trigrams hash */
          and lt.title % rt.title
          and (
                    lt.title %>> rt.title
                or rt.title %>> lt.title
            )
        /* If trigram hash comparison returns values greater than 0.5,
           then do full text search:
           from left to right and vice versa.
           TODO: investigate if we can decrease the number of rows to be processed.
       */
--           and (
--                     to_tsvector(rt.title) @@ lt.title_n_grams::tsquery
--                 or to_tsvector(lt.title) @@ rt.title_n_grams::tsquery
--             )
    ),
    comp as (
        select
--                (select pre_warmed_blocks from warm_up),
uid,
lt_id,
rt_id,
lb_id,
rb_id,
            /*
    https://www.postgresql.org/docs/current/textsearch-controls.html#TEXTSEARCH-RANKING
   */
--        ts_rank_cd(
--                to_tsvector('english', rt),
--                to_tsquery('english', lt_n_g),
--                32
--            )              AS ltr_rank,
--        ts_rank_cd(
--                to_tsvector('english', lt),
--                to_tsquery('english', rt_n_g),
--                32
--            )              AS rtl_rank,
/*
https://www.postgresql.org/docs/9.0/pgtrgm.html
*/
strict_word_similarity(lt, rt) AS ltr_rank,
strict_word_similarity(rt, lt) AS rtl_rank
        from p
    )
select *
from comp;
