#!/usr/bin/env python3
"""Standalone exact arithmetic checks. No third-party packages required.

The large field prime is proved using Proth's theorem. The smaller primes in
its cofactor are certified recursively by full n-1 factorization and modular
order witnesses. None of these checks is a Rust benchmark.
"""
import json
from math import gcd
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def require(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    cert = json.loads((ROOT / 'checks' / 'cofactor_certificates.json').read_text())
    done = {2}
    def prove(n):
        if n in done:
            return
        entry = cert[str(n)]
        fac = {int(q): int(e) for q, e in entry['factors'].items()}
        product = 1
        for q, e in fac.items():
            require(e > 0 and 1 < q < n, 'invalid certificate factor')
            prove(q)
            product *= q ** e
        require(product == n - 1, f'incomplete n-1 factorization for {n}')
        a = entry['base']
        require(pow(a, n - 1, n) == 1, 'failed Fermat equation')
        for q in fac:
            require(gcd(pow(a, (n - 1) // q, n) - 1, n) == 1, 'failed order witness')
        done.add(n)

    c = 0x4080000040000801
    p = 1 + (c << 192)
    factors = [5, 19, 48923313858106271]
    for q in factors:
        prove(q)
    require(c == factors[0] * factors[1] * factors[2], 'cofactor factorization mismatch')
    require(c & 1 and 0 < c < (1 << 192), 'Proth size/parity conditions')
    require(pow(3, (p - 1) // 2, p) == p - 1, 'Proth certificate failed')
    require(p.bit_length() == 255, 'wrong bit length')
    require((p - 1) & -(p - 1) == 1 << 192, 'wrong 2-adicity')
    require(p == 29174178740360681578648524088242709404630849926127992935865410422826357227521,
            'modulus mismatch')
    for q in [2, *factors]:
        require(pow(3, (p - 1) // q, p) != 1, f'3 has insufficient order at factor {q}')
    root = pow(3, c, p)
    require(pow(root, 1 << 192, p) == 1, 'root order upper bound')
    require(pow(root, 1 << 191, p) == p - 1, 'root not primitive')
    x = 102185291209127780448137731705682407317
    y = 96778987907671452183687963870034497754
    require(p == x * x + 2 * y * y, 'CM representation mismatch')
    result = {
        'modulus': str(p), 'cofactor': c,
        'cofactor_factorization': {str(q): 1 for q in factors},
        'bits': 255, 'two_adicity': 192, 'proth_base': 3, 'proth_check': True,
        'generator': 3, 'generator_full_order_proved': True,
        'root_2_192': str(root), 'cm_x': str(x), 'cm_y': str(y),
        'checks_performed': 'Python integer arithmetic only',
        'rust_harness_compiled_by_this_script': False,
        'arkworks_benchmark_executed_by_this_script': False,
    }
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
