-- How agreement on contested votes is spread across every pair of members in one chamber and Congress, for the
-- head-to-head context strip. Pairs with fewer than $2 shared contested votes are left out. Groups: pairs from the
-- same party and pairs from different parties. Runs on a one-partition connection.
-- $1 contested_threshold, $2 min_shared_votes
WITH pairs AS (
  SELECT a.chamber, a.congress, a.icpsr AS ia, b.icpsr AS ib,
         count(*) AS n,
         count(*) FILTER (WHERE a.position = b.position) AS agree
  FROM votes a
  JOIN votes b ON b.chamber = a.chamber AND b.congress = a.congress AND b.rollnumber = a.rollnumber AND a.icpsr < b.icpsr
  JOIN rollcalls r ON r.chamber = a.chamber AND r.congress = a.congress AND r.rollnumber = a.rollnumber
  WHERE a.position <> 0 AND b.position <> 0 AND r.minority_share >= $1
  GROUP BY ALL
), labeled AS (
  SELECT p.agree::DOUBLE / p.n AS pct,
         CASE WHEN ma.party_code = mb.party_code THEN 'same_party' ELSE 'different_party' END AS grp
  FROM pairs p
  JOIN members ma ON ma.icpsr = p.ia AND ma.congress = p.congress AND ma.chamber = p.chamber
  JOIN members mb ON mb.icpsr = p.ib AND mb.congress = p.congress AND mb.chamber = p.chamber
  WHERE p.n >= $2
)
SELECT grp, count(*) AS pairs,
       quantile_cont(pct, 0.10) AS p10, quantile_cont(pct, 0.25) AS p25, quantile_cont(pct, 0.50) AS p50,
       quantile_cont(pct, 0.75) AS p75, quantile_cont(pct, 0.90) AS p90
FROM labeled
GROUP BY grp
ORDER BY grp
