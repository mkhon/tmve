import sys
import math
import sqlite3
from itertools import imap

import numpy as np
from numpy import argsort, asarray

### utility functions ###

def generic_generator(*args):
    """
    A helpful abstraction to pass results to sqlite3.executemany
    """
    for zips in zip(*args):
        yield zips

def file_generator(fhandle):
    """
    A generator for an open file handle that strips lines
    """
    for line in fhandle:
        yield line.strip()

### score functions ###

#NOTE: equivalency between this definition of Bhattacharyya distance
# and Hellinger distance is
# 1 - np.exp(-bc_distance(a,b)) == .5 * hellinger_distance(a,b)
# so in effect, including both is redundant...

def bhatt_distance(a, b):
    """
    Returns the Bhattacharyya distance between to discrete distributions.

    a is expected to be a 1d array (eg., a single document),
    b is expected to be a 2d array with observations over rows
    (eg., the rest of the documents in the corpus).
    """
    return -np.log(np.dot(b**.5, a**.5))

def euclidean_distance(a, b, axis=1):
    """
    Returns the Euclidean distance between two discrete distributions.

    a is expected to be a 1d array (eg., a single document),
    b is expected to be a 2d array with observations over rows
    (eg., the rest of the documents in the corpus).
    """
    return np.sum((a-b)**2, axis=axis)**.5
    #NOTE: the below be preferred for "big" comparisons in dim 1 of b
    #return np.apply_along_axis(np.linalg.norm, axis, doca-docb)

# careful, this isn't metric - doesn't satisfy triangle inequality
def kl_distance(a, b, axis=1):
    """
    Measure of relative entropy between two discrete distributions.

    a is expected to be a 1d array (eg., a single document),
    b is expected to be a 2d array with observations over rows
    (eg., the rest of the documents in the corpus).
    """
    return np.sum(a*(np.log(a)-np.log(b)), axis=axis)

def cosine_distance(a, b, axis=1):
    """
    Cosine distance between two vectors.

    Notes
    -----
    Closer to 1 means distance is smaller.
    """
    a_norm = np.dot(a,a)**.5
    b_norm = np.sum(b**2, axis=axis)**.5
    return np.dot(b,a)/(a_norm*b_norm)

def hellinger_distance(doca, docb, axis=1):
    """
    Returns the Hellinger Distance between documents.

    doca is expected to be a 1d array (ie., a single document),
    docb is expected to be a 2d array(ie., the rest of the documents in the
    corpus).

    Note that this expects to be given proper probability distributions.
    """
    return np.sum((doca**.5 - docb**.5)**2, axis=axis)

def get_topic_score(topica, topicb, axis=1):
    """
    Returns discrete Hellinger distance between topics

    topica is expected to be a 1d array, while topicb can be 2d.
    """
    score = np.sum((np.abs(topica)**.5 - np.abs(topicb)**.5)**2, axis=axis)
    return 0.5 * score / (100. * len(topica))

def get_term_score(terma, termb, axis=1):
    """
    Returns sum of squares distance of term pairs

    terma is expected to be a 1d array, while termb can be 2d.
    """
    return np.sum((terma - termb)**2, axis=axis)

### write relations to db functions ###

def write_doc_doc(con, cur, gamma_file):
    cur.execute('CREATE TABLE doc_doc (id INTEGER PRIMARY KEY, doc_a INTEGER, '
                'doc_b INTEGER, score FLOAT)')
    cur.execute('CREATE INDEX doc_doc_idx1 ON doc_doc(doc_a)')
    cur.execute('CREATE INDEX doc_doc_idx2 ON doc_doc(doc_b)')
    con.commit()

    gamma = np.loadtxt(gamma_file)
    theta = gamma / gamma.sum(axis=1, keepdims=True)

    # get the closest 100 relations per document
    for a in range(len(theta)):
        doc = theta[a]
        # index below by a, because already compared before a
        distance = hellinger_distance(doc, theta[a:])
        # drop zeros
        distance[distance == 0] = np.inf
        min_doc_idx = np.argsort(distance)[:100]

        # generator of many results
        res = generic_generator((str(a),)*100, map(str, min_doc_idx),
                distance[min_doc_idx])

        execution_string = 'INSERT INTO doc_doc (id, doc_a, doc_b, score) '
        execution_string += 'VALUES(NULL, ?, ?, ?)'

        cur.executemany(execution_string, res)

    con.commit()

def write_doc_topic(con, cur, gamma_file):
    cur.execute('CREATE TABLE doc_topic (id INTEGER PRIMARY KEY, doc INTEGER, '
                'topic INTEGER, score FLOAT)')
    cur.execute('CREATE INDEX doc_topic_idx1 ON doc_topic(doc)')
    cur.execute('CREATE INDEX doc_topic_idx2 ON doc_topic(topic)')
    con.commit()

    docs = np.loadtxt(gamma_file)
    # for each line in the gamma file
    for doc_no,doc in enumerate(open(gamma_file, 'r')):
        doc = map(float, doc.split())
        ins = 'INSERT INTO doc_topic (id, doc, topic, score) '
        ins += 'VALUES(NULL, ?, ?, ?)'
        res = generic_generator((doc_no,)*len(doc), range(len(doc)), doc)
        cur.executemany(ins, res)

    con.commit()

def write_topics(con, cur, beta_file, vocab):
    """
    For each topic, write the first 3 most probably words to db
    """
    cur.execute('CREATE TABLE topics (id INTEGER PRIMARY KEY, title VARCHAR(100))')
    con.commit()

    #NOTE: What is the following line for and why doesn't it raise an error?
    topics_file = open(filename, 'a')

    for topic in open(beta_file, 'r'):
        topic = map(float, topic.split())
        index = argsort(topic)[::-1] # reverse argsort
        ins = 'INSERT INTO topics (id, title) VALUES(NULL, ?)'
        buf = "{%s, %s, %s}" % (vocab[index[0]],
                                vocab[index[1]],
                                vocab[index[2]])
        cur.execute(ins, [buffer(buf)])

    con.commit()

def write_topic_term(con, cur, beta_file):
    cur.execute('CREATE TABLE topic_term (id INTEGER PRIMARY KEY, topic INTEGER, '
                'term INTEGER, score FLOAT)')
    cur.execute('CREATE INDEX topic_term_idx1 ON topic_term(topic)')
    cur.execute('CREATE INDEX topic_term_idx2 ON topic_term(term)')
    con.commit()

    topic_term_file = open(filename, 'a')

    for topic_no,topic in enumerate(open(beta_file, 'r')):
        topic = asarray(topic.split(), dtype=float)
        index = argsort(topic)[::-1] # reverse argsort
        res = generic_generator((str(topic_no),) * len(topic),
                                map(str,index), topic[index])
        ins = 'INSERT INTO topic_term (id, topic, term, score) '
        ins += 'VALUES(NULL, ?, ?, ?)'
        cur.executemany(ins, res)

    con.commit()

def write_topic_topic(con, cur, beta_file):
    cur.execute('CREATE TABLE topic_topic (id INTEGER PRIMARY KEY, '
                'topic_a INTEGER, topic_b INTEGER, score FLOAT)')
    cur.execute('CREATE INDEX topic_topic_idx1 ON topic_topic(topic_a)')
    cur.execute('CREATE INDEX topic_topic_idx2 ON topic_topic(topic_b)')
    con.commit()

    # for each line in the beta file
    read_file = open(beta_file, 'r')
    topics = []
    for topic in read_file:
        topics.append(map(float, topic.split()))
    topics = np.asarray(topics)

    for topica_count,topic in enumerate(topics):
        #index by count because distance is symmetric
        scores = get_topic_score(topic, topics[topica_count:])
        res = generic_generator((topica_count,)*len(scores),
                                range(len(scores)),
                                scores)
        ins = 'INSERT INTO topic_topic (id, topic_a, topic_b, score) '
        ins += 'VALUES(NULL, ?, ?, ?)'
        con.executemany(ins, res)
    con.commit()

def write_term_term(con, cur, beta_file, no_vocab):
    cur.execute('CREATE TABLE term_term (id INTEGER PRIMARY KEY, '
                'term_a INTEGER, term_b INTEGER, score FLOAT)')
    cur.execute('CREATE INDEX term_term_idx1 ON term_term(term_a)')
    cur.execute('CREATE INDEX term_term_idx2 ON term_term(term_b)')
    con.commit()

    v = []
    for topic in file(beta_file, 'r'):
        v.append(map(float, topic.split()))
    v = np.exp(v)**.5

    for a in range(len(v)):
        terma = v[a]
        score = get_term_score(terma, v[a:])
        # drop zeros
        score[score == 0] = np.inf
        min_score_idx = np.argsort(score)[:100]
        res = generic_generator((str(a),)*len(score),
                                map(str, min_score_idx),
                                score[min_score_idx])
        ins = 'INSERT INTO term_term (id, term_a, term_b, score) '
        ins += 'VALUES(NULL, ?, ?, ?)'
        cur.executemany(ins, res)

    con.commit()

def write_doc_term(con, cur, wordcount_file, no_words):
    cur.execute('CREATE TABLE doc_term (id INTEGER PRIMARY KEY, doc INTEGER, '
                'term INTEGER, score FLOAT)')
    cur.execute('CREATE INDEX doc_term_idx1 ON doc_term(doc)')
    cur.execute('CREATE INDEX doc_term_idx2 ON doc_term(term)')
    con.commit()

    for doc_no, doc in enumerate(open(wordcount_file, 'r')):
        doc = doc.split()[1:]
        terms = {}
        for term in doc:
            terms[int(term.split(':')[0])] = int(term.split(':')[1])

        keys = terms.keys()


        res = generic_generator((doc_no,)*len(keys),
                                keys, (terms[i] for i in keys))
        execution_str = 'INSERT INTO doc_term (id, doc, term, score) '
        execution_str += 'VALUES(NULL, ?, ?, ?)'
        cur.executemany(execution_str, res)

    con.commit()

def write_terms(con, cur, terms_file):
    cur.execute('CREATE TABLE terms (id INTEGER PRIMARY KEY, title VARCHAR(100))')
    con.commit()

    res = file_generator(open(terms_file, 'r'))
    cur.executemany('INSERT INTO terms (id, title) VALUES(NULL, ?)',
                    ([i] for i in imap(buffer, res))) # each term must be a list
    con.commit()

def write_docs(con, cur, docs_file):
    cur.execute('CREATE TABLE docs (id INTEGER PRIMARY KEY, title VARCHAR(100))')
    con.commit()

    res = file_generator(open(docs_file, 'r'))
    cur.executemany('INSERT INTO docs (id, title) VALUES(NULL, ?)',
                    ([i] for i in imap(buffer, res))) # each should be a list

    con.commit()


### main ###

if (__name__ == '__main__'):
    if (len(sys.argv) != 7):
       print 'usage: python generate_csvs.py <db-filename> <doc-wordcount-file> <beta-file> <gamma-file> <vocab-file> <doc-file>\n'
       sys.exit(1)

    filename = sys.argv[1]
    doc_wordcount_file = sys.argv[2]
    beta_file = sys.argv[3]
    gamma_file = sys.argv[4]
    vocab_file = sys.argv[5]
    doc_file = sys.argv[6]

    # connect to database, which is presumed to not already exist
    con = sqlite3.connect(filename)
    cur = con.cursor()

    # pre-process vocab, since several of the below functions need it in this format
    vocab = open(vocab_file, 'r').readlines()
    vocab = map(lambda x: x.strip(), vocab)

    # write the relevant rlations to the database, see individual functions for details
    print "writing terms to db..."
    write_terms(con, cur, vocab_file)

    print "writing docs to db..."
    write_docs(con, cur, doc_file)

    print "writing doc_doc to db..."
    write_doc_doc(con, cur, gamma_file)

    print "writing doc_topic to db..."
    write_doc_topic(con, cur, gamma_file)

    print "writing topics to db..."
    write_topics(con, cur, beta_file, vocab)

    print "writing topic_term to db..."
    write_topic_term(con, cur, beta_file)

    print "writing topic_topic to db..."
    write_topic_topic(con, cur, beta_file)

    print "writing term_term to db..."
    write_term_term(con, cur, beta_file, len(vocab))

    print "writing doc_term to db..."
    write_doc_term(con, cur, doc_wordcount_file, len(vocab))

