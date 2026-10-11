# Coding-Decoding: cheat sheet

- [Letter position shift](/formulas/coding#letter-position-shift): $\text{code}_i = \text{word}_i + d_i \pmod{26},\ d_i \text{ constant, alternating } (+a, -a) \text{ or increasing } (+1, +2, +3, \dots)$
  - Shortcut: Check the first two letters of every option against the first two shifted letters; usually only one option survives.
- [Reverse then shift](/formulas/coding#reverse-then-shift): $\text{code} = \text{shift}(\text{reverse}(\text{word})):\ \text{if no direct shift fits, reverse the word and find the shifts again}$
- [Vowel/consonant rule](/formulas/coding#vowel-consonant-shift): $\text{code}_i = \text{word}_i + d_v \text{ if vowel (A, E, I, O, U)},\ \text{word}_i + d_c \text{ if consonant},\ d_v \neq d_c \text{ (often } d_v = 0\text{)}$
- [Letter rearrangement](/formulas/coding#letter-rearrangement): $\text{code} = \text{word with its letters reordered by a fixed position map (reverse, reverse all but last, halves swapped, pairs swapped)}$
- [Common element elimination](/formulas/coding#common-element-elimination): $\text{word in sentences } S_1 \text{ and } S_2 \Rightarrow \text{its code is in } \text{codes}(S_1) \cap \text{codes}(S_2);\ \text{remove codes of sentences without it}$
- [Letter position values](/formulas/coding#letter-position-value): $\text{each letter} \to p \text{ (A=1, ..., Z=26) or } 27 - p \text{ (Z=1, ..., A=26)}, \text{ possibly } \pm c;\ \text{write the numbers side by side}$
- [Sum/count of letter values](/formulas/coding#position-sum-rule): $\text{code} = f(S, n),\ S = \textstyle\sum p \text{ (or } \sum (27-p)\text{)},\ n = \text{number of letters};\ \text{test } S,\ S \pm k,\ S \cdot n,\ n \cdot k$
- [Reverse alphabet positions](/formulas/coding#reverse-alphabet-position): $r(\text{letter}) = 27 - p:\ \text{Z}=1, \text{Y}=2, \dots, \text{A}=26;\ \text{used per letter or summed}$
  - Shortcut: Sum of reverse values $= 27n - (\text{forward sum})$: SET $= 81 - 44 = 37$.
