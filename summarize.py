#!/usr/bin/env python3
"""Summarize actual completed runs. Refuses missing/partial results.

Median-of-process-medians prevents treating all within-process samples as
independent machines. The min/max ratios are descriptive, not a confidence
interval. Both wins and losses are emitted; there is no best-run selection.
The best-backend table fixes one backend per field/workload from all process
medians, then reports paired process ratios for those selections.
"""
import argparse
import csv
import json
from pathlib import Path
import statistics
from collections import defaultdict

FIELDS = ('CM255-p192', 'BLS12-381-Fr', 'BN254-Fr')

def summarize(path):
    path = Path(path)
    metadata = json.loads((path / 'environment.json').read_text())
    if metadata.get('completion_status') != 'completed':
        raise ValueError('Cannot summarize an unexecuted or incomplete benchmark')
    samples = defaultdict(list)
    seen = set()
    for f in sorted(path.glob('*_run*.csv')):
        with f.open(newline='') as h:
            for row in csv.DictReader(h):
                ident = (row['backend'], row['field'], row['metric'], int(row['size']),
                         int(row['run']), int(row['round']))
                if ident in seen:
                    raise ValueError(f'duplicate observation {ident}')
                seen.add(ident)
                operations, elapsed = int(row['operations']), int(row['elapsed_ns'])
                if operations <= 0 or elapsed <= 0:
                    raise ValueError('invalid timing observation')
                samples[ident[:-1]].append(elapsed / operations)
    if not samples:
        raise ValueError('No benchmark measurements found')
    runs = int(metadata['requested_runs'])
    rounds = int(metadata['rounds'])
    expected_groups = len(metadata['modes']) * runs * len(FIELDS) * (1 + 3 * len(metadata['sizes']))
    if len(samples) != expected_groups or any(len(v) != rounds for v in samples.values()):
        raise ValueError('Incomplete samples: rerun rather than report a partial subset')
    per_run = {k: statistics.median(v) for k, v in samples.items()}
    groups = defaultdict(dict)
    for (backend, field, metric, size, run), value in per_run.items():
        groups[(backend, metric, size, field)][run] = value
    timing_rows = []
    for (backend, metric, size, field), values in sorted(groups.items()):
        if set(values) != set(range(runs)):
            raise ValueError('missing process run')
        scale = 1 if metric == 'mul' else 1e6
        vals = [x / scale for x in values.values()]
        timing_rows.append({'backend': backend, 'metric': metric, 'size': size, 'field': field,
            'unit': 'ns/multiply' if metric == 'mul' else 'ms/workload',
            'median_of_process_medians': statistics.median(vals),
            'min_process_median': min(vals), 'max_process_median': max(vals),
            'processes': runs, 'samples_per_process': rounds})
    comparison_rows = []
    for backend, metric, size, field in sorted(groups):
        if field == FIELDS[0]:
            continue
        base = groups[(backend, metric, size, field)]
        cm = groups[(backend, metric, size, FIELDS[0])]
        ratios = [base[r] / cm[r] for r in range(runs)]
        ratio = statistics.median(ratios)
        comparison_rows.append({'backend': backend, 'metric': metric, 'size': size, 'baseline': field,
            'median_paired_speed_ratio_baseline_over_cm255': ratio,
            'median_paired_time_reduction_pct': 100 * (1 - 1 / ratio),
            'median_paired_throughput_increase_pct': 100 * (ratio - 1),
            'min_process_speed_ratio': min(ratios), 'max_process_speed_ratio': max(ratios),
            'direction': 'CM255 lower time in every process' if min(ratios) > 1 else
                         'CM255 higher time in every process' if max(ratios) < 1 else 'mixed/tied'})
    selected = {}
    workloads = sorted({(metric, size, field) for _, metric, size, field in groups})
    for metric, size, field in workloads:
        candidates = [
            (statistics.median(groups[(backend, metric, size, field)].values()), backend)
            for backend in metadata['modes']
        ]
        selected[(metric, size, field)] = min(candidates)[1]
    best_backend_rows = []
    for metric, size, field in workloads:
        if field == FIELDS[0]:
            continue
        cm_backend = selected[(metric, size, FIELDS[0])]
        base_backend = selected[(metric, size, field)]
        cm = groups[(cm_backend, metric, size, FIELDS[0])]
        base = groups[(base_backend, metric, size, field)]
        ratios = [base[r] / cm[r] for r in range(runs)]
        ratio = statistics.median(ratios)
        best_backend_rows.append({'metric': metric, 'size': size, 'baseline': field,
            'cm255_backend': cm_backend, 'baseline_backend': base_backend,
            'median_paired_speed_ratio_baseline_over_cm255': ratio,
            'median_paired_time_reduction_pct': 100 * (1 - 1 / ratio),
            'median_paired_throughput_increase_pct': 100 * (ratio - 1),
            'min_process_speed_ratio': min(ratios), 'max_process_speed_ratio': max(ratios),
            'direction': 'CM255 lower time in every process' if min(ratios) > 1 else
                         'CM255 higher time in every process' if max(ratios) < 1 else 'mixed/tied'})
    for name, rows in [('timings.csv', timing_rows), ('comparisons.csv', comparison_rows),
                       ('best_backend_comparisons.csv', best_backend_rows)]:
        with (path / name).open('w', newline='') as h:
            w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    lines = ['# arkworks benchmark results', '',
        'Actual observations from this directory, not predictions. ',
        'Each timing is the median of independent-process medians. ',
        'A positive reduction means CM255 took less time; a negative reduction means it lost.', '',
        '| Backend | Workload | Size | Baseline | CM255 time reduction | Process speed-ratio range |',
        '|---|---|---:|---|---:|---:|']
    for row in comparison_rows:
        lines.append(f"| {row['backend']} | {row['metric']} | {row['size']} | {row['baseline']} | "
                     f"{row['median_paired_time_reduction_pct']:+.2f}% | "
                     f"{row['min_process_speed_ratio']:.3f}–{row['max_process_speed_ratio']:.3f} |")
    lines.extend(['', '## Fastest backend selected per field', '',
        'The backend is selected once per field/workload from its five process medians; '
        'ratios remain paired by process.', '',
        '| Workload | Size | Baseline | CM255 backend | Baseline backend | CM255 time reduction | Process speed-ratio range |',
        '|---|---:|---|---|---|---:|---:|'])
    for row in best_backend_rows:
        lines.append(f"| {row['metric']} | {row['size']} | {row['baseline']} | "
                     f"{row['cm255_backend']} | {row['baseline_backend']} | "
                     f"{row['median_paired_time_reduction_pct']:+.2f}% | "
                     f"{row['min_process_speed_ratio']:.3f}–{row['max_process_speed_ratio']:.3f} |")
    lines.extend(['', 'This is a field/FFT benchmark, not an end-to-end prover, elliptic-curve, '
                  'security, or constant-time audit. No production readiness is implied.'])
    (path / 'SUMMARY.md').write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return timing_rows, comparison_rows

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    summarize(p.parse_args().directory)
