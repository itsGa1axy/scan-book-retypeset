"""25 real CLI regression scenarios with generated PDFs and temporary outputs."""
import pymupdf as fitz
import json
import subprocess
import sys
import hashlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_regressions(D):
    P=sys.executable

    def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    def good(path):
     d=fitz.open()
     for i in range(3):
      p=d.new_page(width=300,height=400);p.insert_font(fontname='test',fontfile=str(D/'fixture-font.ttf'))
      p.insert_text((30,70),f'Chapter {i+1}: readable text 0123456789.',fontname='test',fontsize=12)
     d.set_toc([[1,'Chapter',1],[2,'Section',2],[3,'Subsection',3]])
     d.set_page_labels([{'startpage':0,'prefix':'','style':'r','firstpagenum':1},{'startpage':1,'prefix':'','style':'D','firstpagenum':1}])
     d[0].insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(30,60,120,75),'uri':'https://example.com/reference'})
     d[1].insert_link({'kind':fitz.LINK_GOTO,'from':fitz.Rect(30,60,120,75),'page':2,'to':fitz.Point(30,60)})
     d.subset_fonts();d.save(path);d.close()

    def variant(name,fn):
     with fitz.open(D/'source.pdf') as d:
      fn(d);d.save(D/name)

    (D/'fixture-font.ttf').write_bytes(fitz.Font('tiro').buffer)
    good(D/'source.pdf');shutil.copy2(D/'source.pdf',D/'correct.pdf')
    variant('no-outline.pdf',lambda d:d.set_toc([]))
    variant('flat-outline.pdf',lambda d:d.set_toc([[1,'Chapter',1],[1,'Section',2],[1,'Subsection',3]]))
    variant('bad-target.pdf',lambda d:d.set_toc([[1,'Chapter',1],[2,'Section',3],[3,'Subsection',3]]))
    variant('no-labels.pdf',lambda d:d.set_page_labels([]))
    variant('no-links.pdf',lambda d:d[0].delete_link(d[0].get_links()[0]))
    def tag(d):
     r=d.get_new_xref();d.update_object(r,'<< /Type /StructTreeRoot /K [] >>');d.xref_set_key(d.pdf_catalog(),'StructTreeRoot',f'{r} 0 R');d.xref_set_key(d.pdf_catalog(),'MarkInfo','<< /Marked true >>')
    variant('source-tag-presence.pdf',tag)
    variant('source-ocg.pdf',lambda d:d.add_ocg('Annotations',on=False))
    with fitz.open(D/'source.pdf') as s,fitz.open() as d:
     for q in s:
      p=d.new_page(width=300,height=400)
      p.insert_image(p.rect,stream=q.get_pixmap().tobytes('png'))
      p.insert_font(fontname='test',fontfile=str(D/'fixture-font.ttf'))
      p.insert_text((30,70),'Fake hidden text',fontname='test',fontsize=12,render_mode=3)
     d.save(D/'raster-hidden.pdf')
    with fitz.open() as d:
     for i in range(3):d.new_page(width=300,height=400).insert_text((30,70),'Unembedded standard font')
     d.save(D/'unembedded.pdf')
    with fitz.open() as d:
     d.new_page(width=300,height=400);d.save(D/'blank.pdf')
    with fitz.open() as d:
     d.new_page(width=301,height=400);d.save(D/'different-size.pdf')
    initial=digest(D/'source.pdf');results=[]

    def cli(name,script,args,expected,code=None):
     proc=subprocess.run([P,str(ROOT/'scripts'/script),*map(str,args)],text=True,capture_output=True)
     ok=proc.returncode==expected
     if code:
      report=json.loads((D/f'{name}.json').read_text());ok=ok and code in [i['code'] for i in report['issues']]
     results.append({'test':name,'exit_code':proc.returncode,'passed':ok,'stdout':proc.stdout.strip(),'stderr':proc.stderr.strip()})
     if not ok:print(json.dumps(results[-1],ensure_ascii=False));raise AssertionError(name)

    def audit(name,candidate='correct.pdf',code=None,source='source.pdf',expected=None,extra=()):
     cli(name,'pdf_audit.py',[D/source,D/candidate,'--source-pages','1-3','--report',D/f'{name}.json',*extra],expected if expected is not None else (1 if code else 0),code)

    cli('probe','pdf_probe.py',[D/'source.pdf','--pages','1,3','--output',D/'probe.json','--render-dir',D/'previews'],0)
    audit('correct')
    cli('compare','pdf_compare.py',[D/'source.pdf',D/'correct.pdf','--source-pages','1-3','--output',D/'comparison.pdf'],0)
    assert len(fitz.open(D/'comparison.pdf'))==3
    for nm,code in [('no-outline','outline-node-or-hierarchy-missing'),('flat-outline','outline-node-or-hierarchy-missing'),('bad-target','outline-destination-mismatch'),('no-labels','page-label-mismatch'),('no-links','link-target-missing'),('raster-hidden','hidden-text-in-output'),('unembedded','font-program-not-embedded-or-unreadable')]:
     audit(nm,nm+'.pdf',code)
    audit('tags-removed',source='source-tag-presence.pdf',code='document-structure-entry-removed')
    audit('ocg-removed',source='source-ocg.pdf',code='document-structure-entry-removed')
    cli('empty-needs-exception','pdf_audit.py',[D/'blank.pdf',D/'blank.pdf','--source-pages','1','--report',D/'empty-needs-exception.json'],1,'no-visible-text-candidates')
    cli('blank-exception','pdf_audit.py',[D/'blank.pdf',D/'blank.pdf','--source-pages','1','--report',D/'blank-exception.json','--allow-no-text-pages','1'],0)
    cli('blank-compare','pdf_compare.py',[D/'blank.pdf',D/'blank.pdf','--source-pages','1','--output',D/'blank-comparison.pdf'],0)
    cli('dimension-mismatch','pdf_compare.py',[D/'blank.pdf',D/'different-size.pdf','--source-pages','1','--output',D/'should-not-exist.pdf'],2)
    for nm,pages in [('duplicate','1,1'),('out-of-range','0,4'),('descending','3-1')]:
     cli(nm,'pdf_probe.py',[D/'source.pdf','--pages',pages,'--output',D/f'{nm}.json'],2)
    cli('no-overwrite','pdf_probe.py',[D/'source.pdf','--pages','1','--output',D/'probe.json'],2)
    cli('input-protected','pdf_probe.py',[D/'source.pdf','--pages','1','--output',D/'source.pdf'],2)
    os.link(D/'source.pdf',D/'hardlink.pdf')
    cli('hardlink-protected','pdf_probe.py',[D/'source.pdf','--pages','1','--output',D/'hardlink.pdf'],2)
    cli('count-mismatch','pdf_audit.py',[D/'source.pdf',D/'correct.pdf','--source-pages','1-2','--report',D/'count-mismatch.json'],2)
    with fitz.open(D/'source.pdf') as source,fitz.open() as target:
     target.insert_pdf(source,from_page=2,to_page=2)
     target.set_toc([[1,'Chapter',-1],[2,'Section',-1],[3,'Subsection',1]])
     target.set_page_labels([{'startpage':0,'prefix':'','style':'D','firstpagenum':2}])
     target.save(D/'subset-correct.pdf')
    cli('partial-page-outline-ancestors','pdf_audit.py',[D/'source.pdf',D/'subset-correct.pdf','--source-pages','3','--report',D/'subset-audit.json'],0)
    assert json.loads((D/'subset-audit.json').read_text())['expected_outline_subset']==[[1,'Chapter',-1],[2,'Section',-1],[3,'Subsection',1]]
    with fitz.open(D/'source.pdf') as d:
     d[2].insert_link({'kind':fitz.LINK_LAUNCH,'from':fitz.Rect(20,20,50,40),'file':'//example.invalid/reference'})
     d.save(D/'source-launch.pdf')
    audit('nonstandard-link-loss',source='source-launch.pdf',code='link-target-missing')
    assert digest(D/'source.pdf')==initial
    (D/'skill-tools-validation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print('Passed',len(results),'CLI checks; source hash unchanged')

    return results


class CLIRegressionTests(unittest.TestCase):
    def test_25_cli_scenarios(self):
        with tempfile.TemporaryDirectory() as scratch:
            results = run_regressions(Path(scratch))
            self.assertEqual(len(results), 25)
            self.assertTrue(all(item['passed'] for item in results))


if __name__ == '__main__':
    unittest.main()
