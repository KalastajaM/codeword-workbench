#!/usr/bin/env python3
"""Coverage smoke test; this is not a benchmark of complete puzzle accuracy."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.candidates import find_candidates
from app.morphology import MorphologyIndex
from app.dictionaries import get_dictionary
from app.solver import default_rules

words=get_dictionary('fi',ROOT/'data')['words']
index=MorphologyIndex(ROOT/'data/morphology/fi.sqlite')
results=[]
for word in ['TALOJEN','TALOSSA','ÄITIEN','ÄIDILLÄ','KAUNIIMPIEN','KOIRILLA','KISSOJEN','JUOKSEN','MENEN','YÖN','KÄSISSÄ']:
    p=dict(rows=1,cols=len(word),language='fi',useDictionary=True,rules=default_rules('fi'),cells=[dict(black=False,number='',letter=c if i!=len(word)//2 else '') for i,c in enumerate(word)])
    old=find_candidates(p,words,[0]);new=find_candidates(p,words,[0],morphology=index)
    results.append(dict(target=word,pattern=new['words'][0]['pattern'],wordListFound=word in old['words'][0]['candidates'],morphologyFound=word in new['words'][0]['candidates'],seconds=new['stats']['elapsedSeconds']))
report=dict(scope='Hand-selected word-form coverage, one missing character. Not puzzle solution accuracy or representative language coverage.',results=results)
(ROOT/'data/morphology/benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
