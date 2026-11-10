-- Head-to-head vote by vote: every roll call both members voted yea or nay on, with both positions. The reference
-- the browser's list (site/js/compute.js pairVotes) is tested against.
-- $1 icpsr_a, $2 icpsr_b, $3 chamber, $4 congress_from, $5 congress_to
SELECT a.congress, a.rollnumber, a.position AS position_a, b.position AS position_b
FROM votes a
JOIN votes b ON b.chamber = a.chamber AND b.congress = a.congress AND b.rollnumber = a.rollnumber
WHERE a.icpsr = $1 AND b.icpsr = $2 AND a.chamber = $3 AND a.congress BETWEEN $4 AND $5
  AND a.position <> 0 AND b.position <> 0
ORDER BY a.congress DESC, a.rollnumber DESC
