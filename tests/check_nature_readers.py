"""Check the two Nature regression readers generated from user-supplied PDFs."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import sys

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from reader import verify


CASES = {
    's41586-026-10377-y': {
        'pages': 29,
        'main': 5,
        'extended': 10,
        'references': 71,
        'cross_page': {'figure 3': (4, 5), 'figure 5': (7, 8), 'extended data figure 5': (19, 20)},
    },
    's41592-023-02007-6': {
        'pages': 23,
        'main': 4,
        'extended': 9,
        'references': 35,
        'cross_page': {'figure 3': (4, 5)},
    },
}


def digest(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def check(stem, html, replay, work):
    expected = CASES[stem]
    data = html.read_text(encoding='utf-8')
    verify(data)
    dom = BeautifulSoup(data, 'html.parser')
    report = json.loads((work / 'extraction.json').read_text(encoding='utf-8'))
    assert len(report['pages']) == expected['pages']
    assert not report['unmatched_captions']
    assert not report['unlabelled_pictures']
    assert all(caption['clean_end'] for caption in report['caption_audit'])
    assert len(dom.select('#rail figure[id^="figure-"]')) == expected['main']
    assert len(dom.select('#rail figure[id^="extended-data-figure-"]')) == expected['extended']
    end_of_article = 25 if expected['pages'] == 29 else 20
    assert [page['page'] for page in report['pages'] if page['facsimile']] == list(
        range(end_of_article + 1, expected['pages'] + 1)
    )
    pairs = {entry['label']: (entry['asset_page'], entry['caption_page'])
             for entry in report['paired_captions']}
    for label, pair in expected['cross_page'].items():
        assert pairs[label] == pair, label
    assert len(dom.select('li.ref-entry')) == expected['references']
    if expected['pages'] == 29:
        for number, author in [(34, 'adams'), (35, 'forrest'), (63, 'schmidt'), (69, 'kanehisa')]:
            for ref in dom.find_all('a', class_='cite', string=str(number)):
                assert ref['href'].startswith('#ref-' + author), (number, ref['href'])
    else:
        figure = dom.select_one('#extended-data-figure-5 img')
        assert int(figure['width']) > 800, 'Multi-panel plate cropped to one column'
    assert dom.select_one('section.abstract h2').get_text(strip=True) == 'Abstract'
    assert digest(html) == digest(replay)
    print(f'{stem}: {expected["pages"]} pages, {expected["references"]} references, SHA-256 {digest(html)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stem', choices=CASES)
    parser.add_argument('html', type=Path)
    parser.add_argument('replay', type=Path)
    parser.add_argument('work', type=Path)
    options = parser.parse_args()
    check(options.stem, options.html, options.replay, options.work)
