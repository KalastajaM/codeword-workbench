"""Extract a Swedish word-form list from SALDO's full-form lexicon (saldom.xml).

SALDO (Språkbanken Text, University of Gothenburg) is licensed CC BY 4.0:
https://spraakbanken.gu.se/en/resources/saldom

Keeps complete written forms (lemmas and inflections) that fit the app's
Swedish alphabet. Skips compound-only parts (msd c, ci, cm, sms), which are
not standalone words, and multi-word or hyphenated entries. Usage:
  python3 scripts/extract_saldo_forms.py saldom.xml out.txt
"""
import re
import sys
import unicodedata

ALPHABET = set('ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ')
COMPOUND_ONLY = {'c', 'ci', 'cm', 'sms'}
FEAT = re.compile(r'<feat att="(writtenForm|msd)" val="([^"]*)"/>')


def forms(path):
    """Yield (form, msd) pairs for WordForm elements, streaming line by line."""
    inside = False
    written = None
    with open(path, encoding='utf-8') as source:
        for line in source:
            if '<WordForm>' in line:
                inside, written = True, None
            elif '</WordForm>' in line:
                inside = False
            elif inside:
                match = FEAT.search(line)
                if match and match.group(1) == 'writtenForm':
                    written = match.group(2)
                elif match and written is not None:
                    yield written, match.group(2)


def main():
    source, target = sys.argv[1:3]
    words = set()
    seen = skipped = 0
    for form, msd in forms(source):
        seen += 1
        word = unicodedata.normalize('NFC', form.strip().upper())
        if msd in COMPOUND_ONLY or not word or len(word) > 100 or not set(word) <= ALPHABET:
            skipped += 1
            continue
        words.add(word)
    with open(target, 'w', encoding='utf-8') as out:
        out.write('\n'.join(sorted(words)) + '\n')
    print(f'{seen} word forms read, {skipped} skipped, {len(words)} unique words written')


if __name__ == '__main__':
    main()
