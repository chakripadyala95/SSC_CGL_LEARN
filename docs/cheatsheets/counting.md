# Counting Figures: cheat sheet

- [Systematic triangle count](/formulas/counting#triangles): $\text{Label every point, then count triangles region by region or size by size; an apex joined to a base cut into } n \text{ parts gives } \tfrac{n(n+1)}{2}.$
  - Shortcut: Apex over a base with $n$ parts: $\frac{n(n+1)}{2}$ triangles; a square with both diagonals: 8.
- [Square count by size](/formulas/counting#squares): $\text{Count squares size by size; an } n\times n \text{ grid has } \sum_{k=1}^{n} k^2 = \frac{n(n+1)(2n+1)}{6} \text{ squares.}$
  - Shortcut: Grid: $1, 5, 14, 30, 55$ squares for $n = 1..5$.
- [Line and shape enumeration](/formulas/counting#lines-shapes): $\text{Label points and list each line or shape once by its end points, grouped by direction or size.}$
  - Shortcut: On one line cut into $n$ equal parts with arcs on every run of parts, there are $n + (n-1) + \dots + 1 = \frac{n(n+1)}{2}$ semicircles.
