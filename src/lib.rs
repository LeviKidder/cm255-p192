//! Experimental benchmark configuration, NOT production cryptography.
//! This source was prepared against arkworks 0.6.0 documentation. See STATUS.json:
//! the Rust project has NOT been compiled or timed in the preparation environment.
use ark_ff::{Fp256, MontBackend, MontConfig, PrimeField};

#[derive(MontConfig)]
#[modulus = "29174178740360681578648524088242709404630849926127992935865410422826357227521"]
#[generator = "3"]
pub struct Cm255Config;
pub type Cm255 = Fp256<MontBackend<Cm255Config, 4>>;

/// Reproducible test-data generator, explicitly NOT a cryptographic RNG.
pub struct SplitMix64(pub u64);
impl SplitMix64 {
    pub fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^ (z >> 31)
    }
}

/// Identical byte streams for all fields, reduced modulo their respective primes.
/// These are dense, non-secret benchmark operands, not uniformly sampled keys.
pub fn inputs<F: PrimeField>(len: usize, seed: u64) -> Vec<F> {
    let mut rng = SplitMix64(seed);
    (0..len).map(|_| {
        let mut bytes = [0u8; 32];
        for chunk in bytes.chunks_exact_mut(8) {
            chunk.copy_from_slice(&rng.next_u64().to_le_bytes());
        }
        F::from_le_bytes_mod_order(&bytes)
    }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use ark_ff::{AdditiveGroup, FftField, Field};
    use ark_poly::{EvaluationDomain, Radix2EvaluationDomain};

    fn parse<F: PrimeField>(s: &str) -> F {
        s.parse::<F>().unwrap_or_else(|_| panic!("invalid field value: {s}"))
    }
    fn check_vectors<F: PrimeField>(name: &str) {
        let mut count = 0usize;
        for line in include_str!("../checks/arithmetic_vectors.csv").lines().skip(1) {
            let v: Vec<_> = line.split(',').collect();
            if v[0] != name { continue; }
            let a = parse::<F>(v[1]);
            let b = parse::<F>(v[2]);
            assert_eq!(a + b, parse::<F>(v[3]), "{name} addition");
            assert_eq!(a - b, parse::<F>(v[4]), "{name} subtraction");
            assert_eq!(a * b, parse::<F>(v[5]), "{name} multiplication");
            assert_eq!(a.square(), parse::<F>(v[6]), "{name} square");
            if v[7] == "none" { assert!(a.inverse().is_none()); }
            else { assert_eq!(a.inverse(), Some(parse::<F>(v[7])), "{name} inverse"); }
            count += 1;
        }
        assert!(count >= 128, "missing independent arithmetic vectors for {name}");
    }
    fn check_fft<F: PrimeField>() {
        for log in 0..=6 {
            let n = 1usize << log;
            let dom = Radix2EvaluationDomain::<F>::new(n).unwrap();
            let input = inputs::<F>(n, 20261007);
            let mut actual = input.clone();
            dom.fft_in_place(&mut actual);
            // Independent O(n^2) direct evaluation, not a second FFT.
            for (i, x) in dom.elements().enumerate() {
                let expected = input.iter().rev().fold(F::ZERO, |acc, c| acc * x + c);
                assert_eq!(actual[i], expected, "DFT comparison, n={n}, i={i}");
            }
            dom.ifft_in_place(&mut actual);
            assert_eq!(actual, input, "round trip, n={n}");
        }
        for log in [10, 16] {
            let n = 1usize << log;
            let dom = Radix2EvaluationDomain::<F>::new(n).unwrap();
            assert_eq!(dom.group_gen.pow([n as u64]), F::ONE);
            assert_ne!(dom.group_gen.pow([(n / 2) as u64]), F::ONE);
            let input = inputs::<F>(n, 0xabc123);
            let mut actual = input.clone();
            dom.fft_in_place(&mut actual);
            dom.ifft_in_place(&mut actual);
            assert_eq!(actual, input);
        }
    }
    fn check_product<F: PrimeField>() {
        let n = 32;
        let dom = Radix2EvaluationDomain::<F>::new(n).unwrap();
        let a = inputs::<F>(n / 2, 17);
        let b = inputs::<F>(n / 2, 19);
        let mut expected = vec![F::ZERO; n];
        for (i, x) in a.iter().enumerate() {
            for (j, y) in b.iter().enumerate() { expected[i + j] += *x * y; }
        }
        let mut u = a;
        let mut v = b;
        u.resize(n, F::ZERO);
        v.resize(n, F::ZERO);
        dom.fft_in_place(&mut u);
        dom.fft_in_place(&mut v);
        for (x, y) in u.iter_mut().zip(v.iter()) { *x *= y; }
        dom.ifft_in_place(&mut u);
        assert_eq!(u, expected);
    }

    #[test] fn cm255_parameters() {
        assert_eq!(Cm255::MODULUS_BIT_SIZE, 255);
        assert_eq!(Cm255::TWO_ADICITY, 192);
        let mut root = Cm255::TWO_ADIC_ROOT_OF_UNITY;
        for _ in 0..191 { root.square_in_place(); }
        assert_eq!(root, -Cm255::ONE);
        assert_eq!(root.square(), Cm255::ONE);
    }
    #[test] fn cm255_vectors() { check_vectors::<Cm255>("CM255-p192"); }
    #[test] fn bls_vectors() { check_vectors::<ark_bls12_381::Fr>("BLS12-381-Fr"); }
    #[test] fn bn_vectors() { check_vectors::<ark_bn254::Fr>("BN254-Fr"); }
    #[test] fn cm255_fft() { check_fft::<Cm255>(); }
    #[test] fn bls_fft() { check_fft::<ark_bls12_381::Fr>(); }
    #[test] fn bn_fft() { check_fft::<ark_bn254::Fr>(); }
    #[test] fn cm255_product() { check_product::<Cm255>(); }
    #[test] fn bls_product() { check_product::<ark_bls12_381::Fr>(); }
    #[test] fn bn_product() { check_product::<ark_bn254::Fr>(); }
}
