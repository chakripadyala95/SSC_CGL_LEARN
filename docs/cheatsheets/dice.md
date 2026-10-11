# Dice/Cube: cheat sheet

- [Common face rule](/formulas/dice#common-face-opposite): $\text{If a face appears in the same position in two views, the faces in matching positions are opposite each other.}$
  - Shortcut: Same face, same position → the other two pairs of positions give opposite faces directly.
- [Adjacent-face elimination](/formulas/dice#adjacency-elimination): $\text{Every face shown together with face } X \text{ is adjacent to it; the one face never seen with } X \text{ is opposite } X.$
  - Shortcut: Start with the face that appears in the most views; it usually has 4 neighbours shown.
- [Cyclic order of faces](/formulas/dice#cyclic-order): $\text{Read the visible faces of each view in clockwise order, line the views up on a shared face, and fill the ring round it.}$
  - Shortcut: With the common face in the same slot, ring order is view 1 (left, right) then view 2 (left, right); 1st and 3rd are opposite, 2nd and 4th are opposite.
- [Cube net opposite faces](/formulas/dice#cube-net-opposites): $\text{In a net, two squares in one straight row or column with exactly one square between them are opposite; touching squares are never opposite.}$
  - Shortcut: Alternate squares in a straight line are opposite; the two squares left after that are each other's opposite.
- [Painted cube counting](/formulas/dice#painted-cube-count): $n\times n\times n \text{ painted cube cut into } n^3 \text{ unit cubes: 3 faces} = 8,\ \text{2 faces} = 12(n-2),\ \text{1 face} = 6(n-2)^2,\ \text{0 faces} = (n-2)^3$
  - Shortcut: Corners 8, edges $12(n-2)$, faces $6(n-2)^2$, core $(n-2)^3$: one number per part of the cube.
