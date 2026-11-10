-- Congresses in which both members served in the chamber. $1 icpsr_a, $2 icpsr_b, $3 chamber
SELECT congress FROM (
  SELECT congress FROM members WHERE icpsr = $1 AND chamber = $3
  INTERSECT
  SELECT congress FROM members WHERE icpsr = $2 AND chamber = $3
) ORDER BY congress
