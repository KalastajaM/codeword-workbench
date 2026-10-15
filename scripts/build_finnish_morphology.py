#!/usr/bin/env python3
"""Build a bounded, reproducible local Kotus/Omorfi surface-form index."""
import argparse
import csv
import hashlib
import json
import multiprocessing as mp
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.dictionaries import normalize, ALPHABETS

CASES = 'NOM GEN PAR INE ELA ILL ADE ABL ALL ESS TRA ABE INS COM'.split()

def pattern(word):
    seen = {}
    return '.'.join(str(seen.setdefault(c, len(seen))) for c in word)


def initialise(folder):
    global analyser, generator
    import hfst
    analyser = hfst.HfstInputStream(str(Path(folder)/'omorfi.analyse.hfst')).read()
    generator = hfst.HfstInputStream(str(Path(folder)/'omorfi.generate.hfst')).read()


def generate_batch(seeds):
    rows = set(); missing = []
    for lemma, pos in seeds:
        word = normalize(lemma)
        rows.add((word, lemma, pos, 'Kotus 2024 headword'))
        generated = False
        descriptions = set()
        for analysis, weight in analyser.lookup(lemma):
            ids = re.findall(r'\[WORD_ID=([^]]+)\]', analysis)
            if ids != [lemma]: continue  # Do not treat a compound parse as the seed lemma.
            if re.search(r'\[UPOS=(NOUN|ADJ|PROPN|NUM|PRON)\]', analysis) and '[CASE=NOM]' in analysis:
                for number in ('SG', 'PL'):
                    for case in CASES:
                        text = re.sub(r'\[NUM=(SG|PL)\]', '[NUM='+number+']', analysis)
                        descriptions.add(text.replace('[CASE=NOM]', '[CASE='+case+']'))
            elif '[UPOS=VERB]' in analysis:
                prefix = analysis.split('[VOICE=')[0]
                for tense in ('PRESENT', 'PAST'):
                    for person in ('SG1','SG2','SG3','PL1','PL2','PL3'):
                        descriptions.add(prefix+'[VOICE=ACT][MOOD=INDV][TENSE='+tense+'][PERS='+person+']')
        for description in sorted(descriptions):
            for surface, weight in generator.lookup(description):
                text = normalize(surface)
                if not text or len(text)>40 or not set(text)<=set(ALPHABETS['fi']): continue
                rows.add((text, lemma, description, 'Omorfi 0.9.12 generated from Kotus 2024'))
                generated = True
        if not generated and pos in ('substantiivi','adjektiivi','verbi'): missing.append(lemma)
    return list(rows), missing


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'data/dictionary-build/sources/nykysuomensanalista2024.txt')
    parser.add_argument('--folder',type=Path,default=ROOT/'data/morphology')
    parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args(); folder=args.folder; folder.mkdir(parents=True,exist_ok=True)
    seeds=[]
    with args.source.open(encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream,delimiter='\t'):
            lemma=row['Hakusana']; text=normalize(lemma)
            if text and len(text)<=40 and set(text)<=set(ALPHABETS['fi']): seeds.append((lemma,row['Sanaluokka']))
    seeds=sorted(set(seeds)); temp=folder/'fi.build.sqlite'; target=folder/'fi.sqlite'
    if temp.exists(): temp.unlink()
    db=sqlite3.connect(temp)
    db.execute('CREATE TABLE forms(word TEXT, length INTEGER, pattern TEXT, lemma TEXT, analysis TEXT, source TEXT, PRIMARY KEY(word,lemma,analysis,source)) WITHOUT ROWID')
    db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT)')
    missing=[]; completed=0; started=time.monotonic()
    with mp.get_context('spawn').Pool(args.workers,initialise,(str(folder),)) as pool:
        for rows, omitted in pool.imap(generate_batch,[seeds[i:i+100] for i in range(0,len(seeds),100)]):
            db.executemany('INSERT OR IGNORE INTO forms VALUES(?,?,?,?,?,?)',[(w,len(w),pattern(w),l,a,s) for w,l,a,s in rows])
            missing.extend(omitted); completed+=100
            if completed%5000==0:
                db.commit();print(f'{min(completed,len(seeds))}/{len(seeds)} headwords processed, {time.monotonic()-started:.0f}s',flush=True)
    db.execute('CREATE INDEX form_length ON forms(length,word)')
    db.execute('CREATE INDEX form_pattern ON forms(length,pattern,word)')
    metadata=dict(runtime='hfst 3.16.0.1',model='Omorfi 0.9.12',source='Kotus Nykysuomen sanalista 2024',
        coverage='Headwords; nominal singular/plural cases; active indicative present/past verbs. No possessive suffixes, clitics or productive compound expansion. Model gaps remain.',
        sourceSha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        generatorSha256=hashlib.sha256((folder/'omorfi.generate.hfst').read_bytes()).hexdigest(),
        headwords=len(seeds),withoutGeneratedForms=len(missing),forms=db.execute('SELECT count(DISTINCT word) FROM forms').fetchone()[0])
    db.executemany('INSERT INTO metadata VALUES(?,?)',[(k,json.dumps(v,ensure_ascii=False)) for k,v in metadata.items()]);db.commit();db.close();temp.replace(target)
    (folder/'build-report.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2))
    (folder/'without-generated-forms.txt').write_text('\n'.join(missing))
    print(json.dumps(metadata,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
