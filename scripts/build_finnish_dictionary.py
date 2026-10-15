"""Combine downloaded Finnish word lists into one importable text file.

Sources (download them yourself; see docs/dictionaries.md for links and licences):
  --kotus2024   Kotus Nykysuomen sanalista 2024, tab-separated (CC BY 4.0)
  --kotus2006   Kotus nykysuomen sanalista v1 XML, 2006 (GNU LGPL)
  --joukahainen Joukahainen XML from the Voikko project (GNU GPL 2+)

Give any subset. Entries are normalized to uppercase NFC, restricted to the
app's Finnish alphabet (A-Z, Å, Ä, Ö) and deduplicated. Nothing is transliterated
and no inflections are generated. Usage:
  python3 scripts/build_finnish_dictionary.py --kotus2024 nykysuomensanalista2024.txt \
      --kotus2006 kotus-sanalista_v1.xml --joukahainen joukahainen.xml -o finnish.txt
"""
import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.dictionaries import ALPHABETS, MAX_WORDS, normalize  # noqa: E402


def kotus2024(path):
    with open(path, encoding='utf-8-sig', newline='') as stream:
        return [row['Hakusana'] for row in csv.DictReader(stream, delimiter='\t')]


def kotus2006(path):
    return [node.text or '' for node in ET.parse(path).findall('./st/s')]


def joukahainen(path):
    """Word forms without the = and | structure markers; prefix-only entries are skipped."""
    words = []
    for word in ET.parse(path).findall('./word'):
        if {node.text for node in word.findall('./classes/wclass')} == {'prefix'}:
            continue
        words += [(form.text or '').replace('=', '').replace('|', '') for form in word.findall('./forms/form')]
    return words


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--kotus2024', type=Path)
    parser.add_argument('--kotus2006', type=Path)
    parser.add_argument('--joukahainen', type=Path)
    parser.add_argument('-o', '--output', type=Path, required=True)
    args = parser.parse_args()
    readers = [(args.kotus2024, kotus2024), (args.kotus2006, kotus2006), (args.joukahainen, joukahainen)]
    if not any(path for path, _ in readers):
        parser.error('give at least one source file')
    alphabet = set(ALPHABETS['fi'])
    words = set()
    for path, read in readers:
        if not path:
            continue
        entries = [normalize(text) for text in read(path)]
        accepted = [w for w in entries if w and len(w) <= 100 and set(w) <= alphabet]
        words.update(accepted)
        print(f'{path.name}: {len(entries)} entries, {len(accepted)} usable', file=sys.stderr)
    if len(words) > MAX_WORDS:
        print(f'warning: {len(words)} words exceeds the import limit of {MAX_WORDS}', file=sys.stderr)
    args.output.write_text('\n'.join(sorted(words)) + '\n', encoding='utf-8')
    print(f'{args.output}: {len(words)} unique words', file=sys.stderr)


if __name__ == '__main__':
    main()
