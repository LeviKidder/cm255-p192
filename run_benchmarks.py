#!/usr/bin/env python3
"""Build, test, and time arkworks itself. Requires Rust/Cargo and registry access.

Does not install software, create a cloud machine, or upload results.
Stops rather than fabricate results if any build/test/benchmark fails.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent

def windows_kernel32():
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.GetProcessAffinityMask.argtypes = [ctypes.c_void_p,
                                                ctypes.POINTER(ctypes.c_size_t),
                                                ctypes.POINTER(ctypes.c_size_t)]
    kernel32.GetProcessAffinityMask.restype = ctypes.c_int
    kernel32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    kernel32.SetProcessAffinityMask.restype = ctypes.c_int
    return kernel32

def get_affinity():
    if hasattr(os, 'sched_getaffinity'):
        return sorted(os.sched_getaffinity(0))
    if os.name == 'nt':
        kernel32 = windows_kernel32()
        process_mask = ctypes.c_size_t()
        system_mask = ctypes.c_size_t()
        if not kernel32.GetProcessAffinityMask(kernel32.GetCurrentProcess(),
                                               ctypes.byref(process_mask),
                                               ctypes.byref(system_mask)):
            raise OSError(ctypes.get_last_error(), 'GetProcessAffinityMask failed')
        return [i for i in range(process_mask.value.bit_length())
                if process_mask.value & (1 << i)]
    return None

def set_affinity(cpus):
    if hasattr(os, 'sched_setaffinity'):
        os.sched_setaffinity(0, set(cpus))
    elif os.name == 'nt':
        kernel32 = windows_kernel32()
        mask = sum(1 << cpu for cpu in cpus)
        if not kernel32.SetProcessAffinityMask(kernel32.GetCurrentProcess(), mask):
            raise OSError(ctypes.get_last_error(), 'SetProcessAffinityMask failed')
    else:
        raise RuntimeError('CPU affinity is unavailable on this system')

def checked(command, *, env=None, log=None):
    print('+ ' + ' '.join(map(str, command)), flush=True)
    proc = subprocess.run(command, cwd=ROOT, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if log:
        Path(log).write_text(proc.stdout, encoding='utf-8')
    if proc.returncode:
        print(proc.stdout, file=sys.stderr)
        raise RuntimeError(f'Command failed ({proc.returncode}): {command[0]}')
    return proc.stdout

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=5)
    parser.add_argument('--rounds', type=int, default=21)
    parser.add_argument('--sizes', default='4096,16384,65536,262144,1048576')
    parser.add_argument('--mul-iterations', type=int, default=8192)
    parser.add_argument('--cpu', type=int, default=None, help='affinity CPU; default first permitted CPU')
    parser.add_argument('--require-asm', action='store_true')
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    if min(args.runs, args.rounds, args.mul_iterations) < 1:
        parser.error('runs, rounds and mul-iterations must be positive')
    sizes = [int(s) for s in args.sizes.split(',')]
    if not sizes or any(n < 2 or n > 2**22 or n & (n - 1) for n in sizes):
        parser.error('sizes must be powers of two from 2 through 2^22')
    for executable in ('cargo', 'rustc'):
        if not shutil.which(executable):
            raise RuntimeError(f'{executable} is missing. No arkworks timings were produced.')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = (args.output or ROOT / 'results' / stamp).resolve()
    out.mkdir(parents=True, exist_ok=False)
    metadata = {'started_utc': stamp, 'platform': platform.platform(),
                'requested_runs': args.runs, 'rounds': args.rounds, 'sizes': sizes,
                'completion_status': 'started', 'parallel_feature': False,
                'notes': 'Stock MontConfig/MontBackend and stock ark-poly for all fields'}
    try:
        env = os.environ.copy()
        # Deliberately use identical flags, including native CPU tuning, in both builds.
        env['RUSTFLAGS'] = '-C target-cpu=native'
        metadata['RUSTFLAGS'] = env['RUSTFLAGS']
        metadata['rustc'] = checked(['rustc', '-vV'])
        metadata['cargo'] = checked(['cargo', '--version'])
        cfg = checked(['rustc', '--print', 'cfg', '-C', 'target-cpu=native'])
        (out / 'rustc_cfg.txt').write_text(cfg)
        native_asm = all(x in cfg for x in ['target_arch="x86_64"',
                         'target_feature="adx"', 'target_feature="bmi2"'])
        if args.require_asm and not native_asm:
            raise RuntimeError('Host/compiler target does not expose x86-64 ADX and BMI2')
        modes = ['portable', 'asm'] if native_asm else ['portable']
        metadata['modes'] = modes
        metadata['asm_skipped_reason'] = None if native_asm else 'No native x86-64 ADX/BMI2 target'
        cpuinfo = Path('/proc/cpuinfo')
        if cpuinfo.exists():
            (out / 'cpuinfo.txt').write_text(cpuinfo.read_text())
        if not (ROOT / 'Cargo.lock').exists():
            checked(['cargo', 'generate-lockfile'], env=env, log=out / 'resolve.log')
        shutil.copyfile(ROOT / 'Cargo.lock', out / 'Cargo.lock')
        checked([sys.executable, 'verify_parameters.py'], log=out / 'parameter_checks.json')
        binaries = {}
        for mode in modes:
            features = ['--features', 'asm'] if mode == 'asm' else []
            target = ROOT / 'target' / mode
            common = ['--release', '--locked', '--no-default-features', '--target-dir', str(target)] + features
            checked(['cargo', 'test'] + common, env=env, log=out / f'tests_{mode}.log')
            checked(['cargo', 'build'] + common, env=env, log=out / f'build_{mode}.log')
            checked(['cargo', 'tree', '--locked', '-e', 'features', '--no-default-features'] + features,
                    env=env, log=out / f'features_{mode}.txt')
            suffix = '.exe' if os.name == 'nt' else ''
            binaries[mode] = target / 'release' / ('cm255-arkworks-bench' + suffix)
        allowed = get_affinity()
        cpu = args.cpu if args.cpu is not None else (allowed[0] if allowed else None)
        if cpu is not None and (allowed is None or cpu not in allowed):
            raise RuntimeError('Requested CPU affinity is unavailable on this system')
        metadata['affinity_cpu'] = cpu
        metadata['original_affinity'] = allowed
        for run in range(args.runs):
            # Alternate backend order; field order is additionally rotated inside Rust.
            order = modes if run % 2 == 0 else list(reversed(modes))
            for mode in order:
                cmd = [str(binaries[mode]), '--run', str(run), '--rounds', str(args.rounds),
                       '--sizes', args.sizes, '--mul-iterations', str(args.mul_iterations)]
                print(f'Running {mode}, process {run + 1}/{args.runs}', flush=True)
                if cpu is not None:
                    set_affinity({cpu})
                try:
                    with (out / f'{mode}_run{run}.csv').open('w') as stdout, \
                         (out / f'{mode}_run{run}.log').open('w') as stderr:
                        proc = subprocess.run(cmd, cwd=ROOT, env=env, stdout=stdout, stderr=stderr)
                finally:
                    if allowed is not None:
                        set_affinity(allowed)
                if proc.returncode:
                    raise RuntimeError(f'{mode} benchmark failed; inspect its .log; do not use partial results')
        metadata['completion_status'] = 'completed'
        metadata['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (out / 'environment.json').write_text(json.dumps(metadata, indent=2) + '\n')
        checked([sys.executable, 'summarize.py', str(out)], log=out / 'summary_console.txt')
        print(f'Completed. Measurements and source lockfile: {out}')
    except Exception as exc:
        metadata['completion_status'] = 'failed'
        metadata['error'] = str(exc)
        (out / 'environment.json').write_text(json.dumps(metadata, indent=2) + '\n')
        raise

if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError) as exc:
        sys.exit(str(exc))
