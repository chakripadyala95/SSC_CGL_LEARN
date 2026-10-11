# Alphabet/Word order: cheat sheet

- [Sort and compare positions](/formulas/alphabet#sorted-position-compare): $\text{unchanged} = \#\{i : w_i = \text{sorted}(w)_i\},\ \text{changed} = n - \text{unchanged}$
- [Letters between / gap count](/formulas/alphabet#letters-between): $\text{letters between } X \text{ and } Y = |p_X - p_Y| - 1,\ \text{anchors } E=5,\ J=10,\ O=15,\ T=20,\ Y=25$
- [Opposite letter pairs](/formulas/alphabet#opposite-letter): $\text{opp}(p) = 27 - p:\ A\!-\!Z,\ B\!-\!Y,\ C\!-\!X,\ \dots,\ M\!-\!N$
  - Shortcut: Memory pairs: AZ, BY, CX, DW, EV, FU, GT, HS, IR, JQ, KP, LO, MN.
- [Dictionary order](/formulas/alphabet#dictionary-order): $\text{compare from the left; the first differing letter decides; if one word is the start of the other, the shorter comes first}$
