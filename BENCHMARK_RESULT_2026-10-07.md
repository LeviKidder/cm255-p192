# CM255-p192 arkworks benchmark result — 2026-10-07

## Outcome

The earlier CM255-p192 advantage survives stock arkworks 0.6.0, but through
arkworks' portable, compiler-specialized Montgomery path rather than its generic
ADX/BMI2 assembly path.

- With all three fields on the stock portable backend, CM255 was consistently
  faster for multiplication, FFT, IFFT, and polynomial multiplication.
- With all three fields on the stock assembly backend, CM255 kept a multiplication
  advantage and was roughly competitive on forward FFT, but lost on inverse FFT
  and full polynomial multiplication.
- Selecting the fastest measured backend separately for each field, CM255's
  portable backend was still fastest on the large practical workloads tested.

This resolves the original framework-level question positively, with an important
qualification: the win is not evidence that arkworks' current generic assembly
kernel benefits from the sparse modulus.

## Completed protocol

- CPU: Intel Core Ultra 7 258V, logical CPU 0
- OS: Windows 11 10.0.26200
- Compiler: rustc 1.99.0, LLVM 23.1.1, x86_64-pc-windows-gnu
- Flags: `-C target-cpu=native`
- Features confirmed: x86-64 ADX and BMI2
- Backends: portable and `ark-ff/asm`
- Five independent processes per backend
- 21 samples per field/workload/process
- Sizes: 4,096; 16,384; 65,536; 262,144; 1,048,576
- Single-threaded, pinned to logical CPU 0
- Backend order alternated and field order rotated

All ten Rust tests passed under both backends. Those tests covered 1,131
independently generated arithmetic fixtures, direct small-DFT comparisons,
large FFT round trips, root-order checks, and polynomial products against
schoolbook convolution. The result analyzer also passed its synthetic self-tests
and rejected incomplete runs before the completed experiment.

## Same-backend results

Values below are paired median time reductions. Positive means CM255 took less
time than the named baseline.

| Backend | Workload | Size | vs BLS12-381 Fr | vs BN254 Fr |
|---|---|---:|---:|---:|
| portable | multiply | 64 lanes | +36.91% | +31.27% |
| portable | FFT | 65,536 | +27.47% | +21.95% |
| portable | IFFT | 65,536 | +18.01% | +15.37% |
| portable | polynomial product | 65,536 | +23.85% | +18.33% |
| portable | FFT | 1,048,576 | +24.33% | +22.07% |
| portable | IFFT | 1,048,576 | +16.51% | +12.24% |
| portable | polynomial product | 1,048,576 | +20.90% | +17.32% |
| assembly | multiply | 64 lanes | +14.24% | +7.06% |
| assembly | FFT | 1,048,576 | +3.25% | -1.66% |
| assembly | IFFT | 1,048,576 | -16.12% | -16.97% |
| assembly | polynomial product | 1,048,576 | -4.97% | -8.73% |

Portable CM255 beat both portable baselines at every tested size for all four
workload categories. The complete table, including losses and process-ratio
ranges, is in `SUMMARY.md` and `comparisons.csv`.

## Fastest measured backend per field

These central timings are medians of the five process medians. Each field is
represented by its faster measured backend for that workload.

| Workload | CM255 best | BLS12-381 best | BN254 best | CM255 reduction vs BLS | CM255 reduction vs BN254 |
|---|---:|---:|---:|---:|---:|
| multiply | 25.394 ns | 38.598 ns | 34.806 ns | 34.21% | 27.04% |
| 1M FFT | 591.719 ms | 748.519 ms | 713.916 ms | 20.95% | 17.12% |
| 1M IFFT | 663.436 ms | 745.427 ms | 749.616 ms | 11.00% | 11.50% |
| 1M polynomial product | 1,761.468 ms | 2,226.787 ms | 2,137.526 ms | 20.90% | 17.59% |

CM255's selected backend was portable in every row. The selected BLS/BN backend
varied by workload. `best_backend_comparisons.csv` additionally reports paired
per-process ratios and their ranges. Cross-backend comparisons at small sizes
were noisier; the million-element results are the more meaningful practical
comparison.

## Why portable wins while generic assembly does not

The derived portable multiplication code contains the modulus limbs as compile-time
constants. CM255's modulus has the four-limb form `[1, 0, 0, c]`, allowing LLVM to
remove work associated with the two zero middle limbs and the trivial low limb.

Arkworks' `ark-ff-asm` path instead selects a generic four-limb ADX/BMI2 macro.
That macro is parameterized by a modulus pointer and limb count; it does not
generate a CM255-specific sparse reduction. Enabling it therefore replaces the
path that benefits most from CM255's structure. A custom sparse assembly backend
might improve CM255 further, but this benchmark does not measure one.

## Harness corrections made before the completed run

1. Added the direct `ark-std = 0.6.0` dependency required by the downstream
   expansion of arkworks' assembly macro. The original portable build passed,
   but the original assembly manifest did not compile without this declaration.
2. Added Windows `GetProcessAffinityMask`/`SetProcessAffinityMask` support so the
   timed child processes were genuinely pinned and the affinity was recorded.
3. Extended the analyzer with the fastest-backend-per-field comparison promised
   by the original README.

The original ZIP was SHA-256 verified before these changes. The failed pre-fix
smoke attempts and the successful smoke run remain in `results/` for audit.

## Limits

This is one CPU, one Rust/LLVM toolchain, five process medians, and warm-buffer
single-threaded workloads. The process ranges are descriptive rather than
confidence intervals. Absolute timings varied with system conditions, so paired
same-process ratios are the primary same-backend evidence.

The result establishes a stock-arkworks field-arithmetic/FFT advantage on this
machine. It does not establish an end-to-end prover improvement, elliptic-curve
security, pairing compatibility, constant-time audit, or production readiness.
