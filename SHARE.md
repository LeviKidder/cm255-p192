# Sharing CM255 p192

## GitHub description

Experimental 255-bit prime field with 192-bit 2-adicity. Stock arkworks tests on
one Intel CPU show about 18–21% faster million-element polynomial products than
the fastest measured BLS12-381 Fr and BN254 Fr configurations.

## Short post

I tested an experimental sparse 255-bit prime field in stock arkworks 0.6.0.
CM255-p192 uses the modulus `[1, 0, 0, c]`, which lets LLVM simplify Montgomery
reduction. On an Intel Core Ultra 7 258V it completed 1M-element polynomial
products about 18–21% faster than the fastest BLS12-381 Fr and BN254 Fr
configurations measured. Code, correctness tests, raw results, and caveats are
included. Replications welcome.

## One sentence explanation

This is a candidate number system for making some new zero-knowledge proof and
verifiable-computing systems faster and cheaper, provided they are free to choose
their underlying field.

## Suggested topics

`arkworks` `zero-knowledge` `finite-fields` `FFT` `NTT` `Montgomery-reduction`
`cryptography` `verifiable-computation` `Rust`
