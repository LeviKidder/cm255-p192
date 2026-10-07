#!/usr/bin/env python3
"""Self-test the Python result analyzer with clearly synthetic temporary data.

These are NOT arithmetic benchmark results. Temporary fixtures are deleted.
"""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from summarize import summarize

class AnalysisTests(unittest.TestCase):
    def fixture(self, root):
        meta = {'completion_status': 'completed', 'requested_runs': 3,
                'rounds': 3, 'sizes': [8], 'modes': ['portable']}
        (root/'environment.json').write_text(json.dumps(meta))
        for run in range(3):
            with (root/f'portable_run{run}.csv').open('w', newline='') as f:
                w=csv.writer(f)
                w.writerow(['backend','run','round','position','field','metric','size','operations','elapsed_ns','checksum'])
                for metric in ['mul','fft','ifft','poly_product']:
                    for r in range(3):
                        for pos,(name,time) in enumerate([('CM255-p192',200),('BLS12-381-Fr',250),('BN254-Fr',180)]):
                            w.writerow(['portable',run,r,pos,name,metric,64 if metric=='mul' else 8,
                                        1,time*(100+run),'synthetic_test_only'])
    def test_wins_and_losses(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            with contextlib.redirect_stdout(io.StringIO()):
                times, comparisons=summarize(root)
            self.assertEqual(len(times),12)
            self.assertEqual(len(comparisons),8)
            for r in comparisons:
                if r['baseline']=='BLS12-381-Fr':
                    self.assertAlmostEqual(r['median_paired_time_reduction_pct'],20)
                else:
                    self.assertAlmostEqual(r['median_paired_time_reduction_pct'],-100/9)
    def test_reject_incomplete_status(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            (root/'environment.json').write_text('{"completion_status":"failed"}')
            with self.assertRaises(ValueError): summarize(root)
    def test_reject_missing_run(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.fixture(root)
            (root/'portable_run2.csv').unlink()
            with self.assertRaises(ValueError): summarize(root)

if __name__=='__main__': unittest.main()
