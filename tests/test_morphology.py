from contextlib import closing
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from app.morphology import MorphologyIndex
from app.candidates import find_candidates
from app.solver import default_rules

class MorphologyTests(unittest.TestCase):
    def test_inflected_search_and_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fi.sqlite'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE forms(word,length,pattern,lemma,analysis,source)')
                db.execute('INSERT INTO forms VALUES(?,?,?,?,?,?)',('TALOJEN',7,'0.1.2.3.4.5.6','talo','[NUM=PL][CASE=GEN]','Omorfi test fixture'))
            p=dict(rows=1,cols=7,language='fi',useDictionary=True,rules=default_rules('fi'),cells=[dict(black=False,number='',letter=c if c!='?' else '') for c in 'TALO?EN'])
            r=find_candidates(p,['TALO'],[0],morphology=MorphologyIndex(path))
            self.assertEqual(r['words'][0]['candidates'],['TALOJEN'])
            evidence=r['words'][0]['candidateDetails']['TALOJEN']
            self.assertEqual(evidence[0]['lemma'],'talo')
            self.assertIn('[CASE=GEN]',evidence[0]['analysis'])
            p['useMorphology']=False
            self.assertFalse(find_candidates(p,['TALO'],[0],morphology=MorphologyIndex(path))['words'][0]['candidates'])
            p['useMorphology']=True
            p['rules']['forbiddenPatterns']=['OJ']
            self.assertFalse(find_candidates(p,['TALO'],[0],morphology=MorphologyIndex(path))['words'][0]['candidates'])

    def test_number_pattern_and_deadline(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fi.sqlite'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('CREATE TABLE forms(word,length,pattern,lemma,analysis,source)')
                for word,pattern in [('ÄIDIT','0.1.2.1.3'),('ÄITIN','0.1.2.3.4')]:
                    db.execute('INSERT INTO forms VALUES(?,?,?,?,?,?)',(word,5,pattern,'äiti','','fixture'))
            p=dict(rows=1,cols=5,language='fi',useDictionary=True,rules=default_rules('fi'),cells=[dict(black=False,number=str(n),letter='') for n in [1,2,3,2,4]])
            index=MorphologyIndex(path)
            r=find_candidates(p,[],[0],morphology=index)
            self.assertEqual(r['words'][0]['candidates'],['ÄIDIT'])
            words,truncated=index.match(p,dict(cells=list(range(5)),before=False,after=False),['']*5,p['rules'],time.monotonic()-1)
            self.assertEqual(words,[]);self.assertTrue(truncated)

if __name__=='__main__': unittest.main()
