# CM255 p192 sparse prime field benchmark

CM255-p192 is an experimental 255-bit prime field designed for fast modular
arithmetic and radix-2 FFTs. On one Intel Core Ultra 7 258V, its stock arkworks
implementation completed million-element polynomial products about 18–21%
faster than the fastest BLS12-381 Fr and BN254 Fr configurations measured.

The field modulus is

```text
p = 1 + 0x4080000040000801 × 2^192
  = 29174178740360681578648524088242709404630849926127992935865410422826357227521
```

It is a proven Proth prime with 2-adicity 192. In four 64-bit limbs its modulus
is `[1, 0, 0, 0x4080000040000801]`. The two zero middle limbs and trivial low
limb let LLVM remove work from arkworks' generated portable Montgomery
reduction.

## Result

These are medians of five independent process medians, with 21 samples per
field and workload. Each field is shown using its fastest measured stock
arkworks backend.

| Workload | CM255-p192 | BLS12-381 Fr | BN254 Fr |
|---|---:|---:|---:|
| Multiplication | 25.394 ns | 38.598 ns | 34.806 ns |
| 1,048,576-point FFT | 591.719 ms | 748.519 ms | 713.916 ms |
| 1,048,576-point inverse FFT | 663.436 ms | 745.427 ms | 749.616 ms |
| 1,048,576-point polynomial product | 1,761.468 ms | 2,226.787 ms | 2,137.526 ms |

CM255's fastest path was arkworks' portable backend. Against the same portable
backend, its million-element polynomial product took 20.90% less time than
BLS12-381 Fr and 17.32% less than BN254 Fr.

Arkworks' generic ADX/BMI2 assembly backend did **not** preserve the full
advantage. It does not specialize reduction around CM255's zero modulus limbs.
A future sparse assembly implementation may help, but none is measured here.

## Why this may matter

Large finite-field FFTs and polynomial products are core operations in many
zero-knowledge proof and verifiable-computation systems. A field-level gain of
this size could reduce proving time, server usage, and energy when those
operations dominate the application.

CM255 is not a drop-in replacement for fields tied to existing elliptic curves,
pairings, blockchains, or verifier standards. Its clearest potential use is in a
new or field-flexible system whose protocol can choose a 255-bit prime field.

## Reproduce

Requirements: current stable 64-bit Rust/Cargo, Python 3.10 or newer, a working
linker, and roughly 1 GiB of free memory.

```sh
python verify_parameters.py
python run_benchmarks.py --cpu 0 --runs 5 --rounds 21 --require-asm
```

The runner tests both backends before measuring, alternates backend order,
rotates field order, pins execution to one CPU on Linux and Windows, rejects
incomplete runs, and retains every win and loss. Omit `--require-asm` on a host
without x86-64 ADX/BMI2.

## Evidence and limits

- [Benchmark interpretation](BENCHMARK_RESULT_2026-10-07.md)
- [Complete result summary](results/full_pinned_cpu0_20261007/SUMMARY.md)
- [Absolute timings](results/full_pinned_cpu0_20261007/timings.csv)
- [Same-backend comparisons](results/full_pinned_cpu0_20261007/comparisons.csv)
- [Fastest-backend comparisons](results/full_pinned_cpu0_20261007/best_backend_comparisons.csv)
- [Parameter and arithmetic checks](checks/)

The completed run used arkworks 0.6.0, Rust 1.99.0, LLVM 23.1.1, Windows 11,
`-C target-cpu=native`, and logical CPU 0. All arithmetic, FFT, and polynomial
correctness tests passed under both backends.

This is one-machine field-arithmetic evidence, not an end-to-end prover result,
security audit, elliptic-curve construction, pairing implementation, or claim
of production readiness. Replication on Linux, AMD, ARM, and additional compiler
versions is encouraged.

## License

MIT. You may use, modify, publish, and sell this work, including commercially,
provided the license notice remains with substantial copies.

## Search terms

Arkworks, finite fields, Montgomery reduction, sparse prime, Proth prime,
zero-knowledge proofs, FFT, NTT, polynomial commitments, verifiable computation.
