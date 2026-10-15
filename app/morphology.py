"""Read-only, bounded queries against an explicitly built Finnish form index."""
from contextlib import closing
import re
import sqlite3
import time
from pathlib import Path


def pattern(items):
    seen={}
    return '.'.join(str(seen.setdefault(c,len(seen))) for c in items)


def describe(analysis):
    labels={'NOUN':'noun','ADJ':'adjective','VERB':'verb','PROPN':'proper noun',
            'SG':'singular','PL':'plural','NOM':'nominative','GEN':'genitive',
            'PAR':'partitive','INE':'inessive','ELA':'elative','ILL':'illative',
            'ADE':'adessive','ABL':'ablative','ALL':'allative','ESS':'essive',
            'TRA':'translative','ABE':'abessive','INS':'instructive','COM':'comitative',
            'ACT':'active','INDV':'indicative','PRESENT':'present','PAST':'past'}
    tags=re.findall(r'\[([^=]+)=([^]]+)\]',analysis)
    return ' · '.join(labels.get(value,value.lower()) for key,value in tags
                      if key in ('UPOS','NUM','CASE','VOICE','MOOD','TENSE','PERS','STYLE')) or analysis


class MorphologyIndex:
    def __init__(self,path):
        self.path=Path(path)

    def connect(self):
        return sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)

    def match(self,puzzle,slot,base,rules,deadline,limit=10000):
        if time.monotonic()>=deadline: return [],True
        if slot['before'] or slot['after']: return [],True
        indices=slot['cells']; clauses=['length=?']; args=[len(indices)]
        numbers=[puzzle['cells'][i].get('number','') for i in indices]
        if all(numbers) and rules['uniqueLetters'] and rules['maxLettersPerNumber']==1:
            clauses.append('pattern=?');args.append(pattern([str(int(n)) for n in numbers]))
        for position,i in enumerate(indices):
            if base[i]: clauses.append('substr(word,?,1)=?');args.extend([position+1,base[i]])
        words=[]
        with closing(self.connect()) as db:
            db.set_progress_handler(lambda: int(time.monotonic()>=deadline),1000)
            try:
                for row in db.execute('SELECT DISTINCT word FROM forms WHERE '+' AND '.join(clauses)+' ORDER BY word LIMIT ?',args+[limit+1]):
                    if time.monotonic()>=deadline: return words,True
                    if len(words)==limit: return words,True
                    words.append(row[0])
            except sqlite3.OperationalError as error:
                if 'interrupted' in str(error): return words,True
                raise
        return words,False

    def details(self,words):
        details={}
        with closing(self.connect()) as db:
            for word in words:
                rows=db.execute('SELECT lemma,analysis,source FROM forms WHERE word=? ORDER BY source,lemma,analysis LIMIT 6',(word,)).fetchall()
                if rows: details[word]=[dict(lemma=l,analysis=a,description=describe(a),source=s) for l,a,s in rows]
        return details
