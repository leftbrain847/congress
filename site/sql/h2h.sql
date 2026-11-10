-- Head-to-head: per Congress, roll calls where BOTH members voted yea or nay (present / not voting excluded).
-- A roll call is contested when minority_share (smaller side / (yea + nay)) >= the contested threshold.
-- $1 icpsr_a, $2 icpsr_b, $3 chamber, $4 congress_from, $5 congress_to, $6 contested_threshold
SELECT a.congress,
       count(*) AS shared_all,
       count(*) FILTER (WHERE a.position = b.position) AS agree_all,
       count(*) FILTER (WHERE r.minority_share >= $6) AS shared_contested,
       count(*) FILTER (WHERE r.minority_share >= $6 AND a.position = b.position) AS agree_contested
FROM votes a
JOIN votes b ON b.chamber = a.chamber AND b.congress = a.congress AND b.rollnumber = a.rollnumber
JOIN rollcalls r ON r.chamber = a.chamber AND r.congress = a.congress AND r.rollnumber = a.rollnumber
WHERE a.icpsr = $1 AND b.icpsr = $2 AND a.chamber = $3 AND a.congress BETWEEN $4 AND $5
  AND a.position <> 0 AND b.position <> 0
GROUP BY a.congress
ORDER BY a.congress
