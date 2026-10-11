# Number System: cheat sheet

- [Divisibility rules (2, 3, 4, 5, 8, 9)](/formulas/number-system#divisibility-rules): $2/5/10: last digit;\ 4: last two digits;\ 8: last three digits;\ 3/9: digit sum;\ \text{largest } n\text{-digit multiple of } d=(10^n-1)-((10^n-1)\bmod d)$
  - Shortcut: Digit sum gives the remainder too: $N \bmod 9 = (\text{digit sum}) \bmod 9$, and the same for 3.
- [Divisibility by 11](/formulas/number-system#divisibility-by-11): $11\mid N \iff (\text{sum of odd-place digits}) - (\text{sum of even-place digits}) \equiv 0 \pmod{11}$
  - Shortcut: Counted from the units digit, the alternating sum is also $N \bmod 11$ (add 11 if it is negative).
- [Divisibility by composite numbers](/formulas/number-system#divisibility-composite): $\text{If } n=ab,\ \gcd(a,b)=1:\ n\mid N \iff a\mid N \text{ and } b\mid N\ (6=2\cdot3,\ 36=4\cdot9,\ 40=8\cdot5)$
  - Shortcut: Split $n$ into coprime prime-power parts and apply [[f:number-system.divisibility-rules]] to each: $72 = 8\times9$, $88 = 8\times11$.
- [Divisibility of a^n - b^n](/formulas/number-system#an-bn-divisibility): $(a-b)\mid a^n-b^n \ \forall n;\ (a+b)\mid a^n-b^n \text{ for even } n;\ (a+b)\mid a^n+b^n \text{ for odd } n$
  - Shortcut: $x^n - 1$ is divisible by $x - 1$; for even $n$ also by $x + 1$ and by $x^2 - 1$.
- [Remainder cycles of powers](/formulas/number-system#remainder-cyclicity): $a^n \bmod m \text{ repeats with a cycle; reduce } n \text{ modulo the cycle length}$
  - Shortcut: Write $a = km \pm 1$: then $a^n \equiv (\pm1)^n$. Last digits repeat every 4: use $n \bmod 4$ (0 means 4).
- [Remainder rules (substitution, divisor factor)](/formulas/number-system#remainder-theorem): $(a\cdot b)\bmod m=(a\bmod m)(b\bmod m)\bmod m;\ N\equiv r \pmod D,\ d\mid D \Rightarrow N\equiv r \pmod d$
  - Shortcut: Replace every number by its remainder (or by a small negative one, e.g. $17 \equiv -1 \pmod{18}$), work, then reduce once.
- [Comparing fractions](/formulas/number-system#compare-fractions): $\frac ab > \frac cd \iff ad > bc\ (b,d>0)$
  - Shortcut: Same numerator: smaller denominator wins. Same gap to 1 ($\frac{b-g}{b}$): larger denominator wins, e.g. $\frac{79}{90} > \frac{33}{44}$.
- [Sums of first n naturals, squares, cubes](/formulas/number-system#natural-number-sums): $\Sigma k=\frac{n(n+1)}2;\ \Sigma k^2=\frac{n(n+1)(2n+1)}6;\ \Sigma k^3=\left(\frac{n(n+1)}2\right)^2$
  - Shortcut: Average of $1..n$ is $\frac{n+1}{2}$; average of the first $n$ squares is $\frac{(n+1)(2n+1)}{6}$.
- [LCM and HCF](/formulas/number-system#lcm-hcf): $\mathrm{LCM}(a,b)\times\mathrm{HCF}(a,b)=ab;\ \text{events repeating every } t_1,t_2 \text{ coincide every } \mathrm{LCM}(t_1,t_2)$
  - Shortcut: $\mathrm{LCM} = \frac{ab}{\mathrm{HCF}}$; for lap times, LCM of the lap times gives the first meeting at the start.
