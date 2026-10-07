//! No custom FFT, reduction code, foreign functions, or parallel feature.
//! Timing observations are written only when this binary actually runs.
use ark_ff::{AdditiveGroup, Field, PrimeField};
use ark_poly::{EvaluationDomain, Radix2EvaluationDomain};
use cm255_arkworks_bench::{inputs, Cm255};
use std::{env, hint::black_box, process, time::{Duration, Instant}};

trait Case {
    fn name(&self) -> &'static str;
    fn reset(&mut self);
    fn timed(&mut self) -> Duration;
    fn units(&self) -> u64;
    fn checksum(&self) -> String;
}

struct MulCase<F: PrimeField> {
    name: &'static str,
    init: Vec<F>,
    a: Vec<F>,
    b: Vec<F>,
    iterations: usize,
}
impl<F: PrimeField> Case for MulCase<F> {
    fn name(&self) -> &'static str { self.name }
    fn reset(&mut self) { self.a.copy_from_slice(&self.init); }
    fn timed(&mut self) -> Duration {
        let a = black_box(&mut self.a);
        let b = black_box(&self.b);
        let start = Instant::now();
        for _ in 0..self.iterations {
            for (x, y) in a.iter_mut().zip(b.iter()) { *x *= y; }
        }
        black_box(&*a);
        start.elapsed()
    }
    fn units(&self) -> u64 { (self.iterations * self.a.len()) as u64 }
    fn checksum(&self) -> String { self.a[0].into_bigint().to_string() }
}
fn mul_case<F: PrimeField>(name: &'static str, iterations: usize) -> Box<dyn Case> {
    let init = inputs::<F>(64, 0x103050709);
    Box::new(MulCase { name, a: init.clone(), init,
        b: inputs::<F>(64, 0x2468abcd), iterations })
}

#[derive(Clone, Copy)]
enum Transform { Fft, Ifft, Product }
struct FftCase<F: PrimeField> {
    name: &'static str,
    dom: Radix2EvaluationDomain<F>,
    init_a: Vec<F>,
    init_b: Vec<F>,
    a: Vec<F>,
    b: Vec<F>,
    which: Transform,
}
impl<F: PrimeField> Case for FftCase<F> {
    fn name(&self) -> &'static str { self.name }
    fn reset(&mut self) {
        self.a.copy_from_slice(&self.init_a);
        self.b.copy_from_slice(&self.init_b);
    }
    fn timed(&mut self) -> Duration {
        let a = black_box(&mut self.a);
        let b = black_box(&mut self.b);
        let dom = black_box(&self.dom);
        let start = Instant::now();
        match self.which {
            Transform::Fft => dom.fft_in_place(a),
            Transform::Ifft => dom.ifft_in_place(a),
            Transform::Product => {
                dom.fft_in_place(a);
                dom.fft_in_place(b);
                for (x, y) in a.iter_mut().zip(b.iter()) { *x *= y; }
                dom.ifft_in_place(a);
            }
        }
        black_box(&*a);
        black_box(&*b);
        start.elapsed()
    }
    fn units(&self) -> u64 { 1 }
    fn checksum(&self) -> String { self.a[0].into_bigint().to_string() }
}
fn fft_case<F: PrimeField>(name: &'static str, n: usize, which: Transform) -> Box<dyn Case> {
    let dom = Radix2EvaluationDomain::<F>::new(n).expect("unsupported FFT size");
    assert_eq!(dom.size(), n);
    assert_eq!(dom.group_gen.pow([n as u64]), F::ONE);
    if n > 1 { assert_ne!(dom.group_gen.pow([(n / 2) as u64]), F::ONE); }
    let len = if matches!(which, Transform::Product) { n / 2 } else { n };
    let mut init_a = inputs::<F>(len, 0x1020304050607080);
    init_a.resize(n, F::ZERO);
    let init_b = if matches!(which, Transform::Product) {
        let mut b = inputs::<F>(len, 0x8172635445362718);
        b.resize(n, F::ZERO);
        b
    } else { Vec::new() };
    // Sanity check in this executable as well as the independent cargo tests.
    // It is not timed. No unchecked FFT output is admitted into the benchmark.
    let mut check = init_a.clone();
    dom.fft_in_place(&mut check);
    dom.ifft_in_place(&mut check);
    assert_eq!(check, init_a, "FFT round trip: {name}, n={n}");
    Box::new(FftCase { name, dom, a: init_a.clone(), b: init_b.clone(), init_a, init_b, which })
}

fn measure(cases: &mut [Box<dyn Case>], backend: &str, run: usize,
           metric: &str, n: usize, rounds: usize) {
    for _ in 0..2 {
        for case in cases.iter_mut() { case.reset(); black_box(case.timed()); }
    }
    for round in 0..rounds {
        // Rotate first/second/third position across both rounds and processes.
        for pos in 0..cases.len() {
            let idx = (round + run + pos) % cases.len();
            let case = &mut cases[idx];
            case.reset();  // Allocation, input generation and copying are NOT timed.
            let elapsed = case.timed().as_nanos();
            println!("{backend},{run},{round},{pos},{},{metric},{n},{},{elapsed},{}",
                     case.name(), case.units(), case.checksum());
        }
    }
}
fn usage() {
    eprintln!("Usage: cm255-arkworks-bench [--rounds 21] [--run 0] [--sizes 4096,16384,65536,262144,1048576] [--mul-iterations 8192]");
}
fn positive(s: &str, label: &str) -> usize {
    s.parse::<usize>().ok().filter(|n| *n > 0)
        .unwrap_or_else(|| { eprintln!("Invalid {label}: {s}"); process::exit(2) })
}
fn main() {
    let mut rounds = 21;
    let mut run = 0usize;
    let mut sizes = vec![4096usize, 16384, 65536, 262144, 1048576];
    let mut mul_iterations = 8192usize;
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--help" || arg == "-h" { usage(); return; }
        let val = args.next().unwrap_or_else(|| { usage(); process::exit(2) });
        match arg.as_str() {
            "--rounds" => rounds = positive(&val, "rounds"),
            "--run" => run = val.parse().unwrap_or_else(|_| { usage(); process::exit(2) }),
            "--mul-iterations" => mul_iterations = positive(&val, "mul iterations"),
            "--sizes" => sizes = val.split(',').map(|s| positive(s, "size")).collect(),
            _ => { usage(); process::exit(2); }
        }
    }
    assert!(!sizes.is_empty());
    assert!(sizes.iter().all(|&n| n >= 2 && n.is_power_of_two() && n <= (1 << 22)),
            "use power-of-two sizes from 2 through 2^22; larger sizes need deliberate memory planning");
    let asm_active = cfg!(all(feature = "asm", target_arch = "x86_64", target_feature = "adx", target_feature = "bmi2"));
    if cfg!(feature = "asm") && !asm_active {
        eprintln!("asm feature requested without x86-64 ADX/BMI2 compiler target features; refusing a mislabeled run");
        process::exit(2);
    }
    let backend = if asm_active { "asm" } else { "portable" };
    eprintln!("backend={backend}; rounds={rounds}; run={run}; single_thread=true; arkworks=0.6.0; custom_kernel=false");
    println!("backend,run,round,position,field,metric,size,operations,elapsed_ns,checksum");
    let mut cases = vec![mul_case::<Cm255>("CM255-p192", mul_iterations),
        mul_case::<ark_bls12_381::Fr>("BLS12-381-Fr", mul_iterations),
        mul_case::<ark_bn254::Fr>("BN254-Fr", mul_iterations)];
    measure(&mut cases, backend, run, "mul", 64, rounds);
    drop(cases);
    for n in sizes {
        for (metric, which) in [("fft", Transform::Fft), ("ifft", Transform::Ifft), ("poly_product", Transform::Product)] {
            let mut cases = vec![fft_case::<Cm255>("CM255-p192", n, which),
                fft_case::<ark_bls12_381::Fr>("BLS12-381-Fr", n, which),
                fft_case::<ark_bn254::Fr>("BN254-Fr", n, which)];
            measure(&mut cases, backend, run, metric, n, rounds);
        }
    }
}
