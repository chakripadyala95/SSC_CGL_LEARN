# Series: cheat sheet

- [Repeating block fill-in](/formulas/series#repeating-block): $\text{Remove spaces, pick a block length } p\text{, write the series in rows of } p\text{; every column must hold one letter.}$
  - Shortcut: Fill only the first two or three blanks from the columns, then eliminate options that disagree; usually one survives.
- [Position-wise letter steps](/formulas/series#letter-position-steps): $t_{n+1}[i]=t_n[i]+d_i\pmod{26},\ \ A=1,\dots,Z=26$
  - Shortcut: Solve only the position where the options differ most; often one position eliminates three options.
- [Split letter and number streams](/formulas/series#alphanumeric-split): $\text{term} = \underbrace{L_1L_2\dots}_{\text{letter steps}}\ \underbrace{N}_{\text{number series}}$
  - Shortcut: Check the number first: it is the fastest to compute and usually leaves one or two options.
- [First differences](/formulas/series#first-differences): $d_n=t_{n+1}-t_n;\ \ t_{\text{next}}=t_{\text{last}}+d_{\text{next}}$
- [Second-order differences](/formulas/series#second-differences): $\Delta^2_n=d_{n+1}-d_n=\text{const}\ \Rightarrow\ d_{\text{next}}=d_{\text{last}}+\Delta^2$
  - Shortcut: Constant $\Delta^2 = 2$ with $d_n$ odd numbers means the terms are $n^2 + c$ (here $n^2+1$).
- [Prime-number pattern](/formulas/series#prime-pattern): $\text{Differences (or terms) } = p_k, p_{k+1}, p_{k+2},\dots\ \text{(consecutive primes, rising or falling)}$
- [Squares and cubes pattern](/formulas/series#square-cube-pattern): $\text{Terms or differences} = n^2,\ n^3,\ n^2\pm n,\ n^2\pm1\ \text{for } n \text{ in an AP}$
- [Multiply then add pattern](/formulas/series#multiply-add): $t_{n+1}=t_n\times m_n \pm c_n,\ \ m_n,\ c_n\ \text{constant or rising by a fixed step}$
- [Alternating two-series pattern](/formulas/series#alternating): $\text{Odd places: } t_1,t_3,t_5,\dots;\ \ \text{even places: } t_2,t_4,t_6,\dots\ \text{each with its own rule}$
