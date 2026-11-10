-- Members who voted against the majority of their own party's yea/nay votes on one roll call.
-- A party split exactly evenly has no majority, so none of its members are listed.
-- $1 chamber, $2 congress, $3 rollnumber
WITH pv AS (
  SELECT v.icpsr, v.position, m.party_code, coalesce(m.party_name, 'Party code ' || m.party_code) AS party,
         m.bioname, m.state_abbrev
  FROM votes v JOIN members m ON m.icpsr = v.icpsr AND m.congress = v.congress AND m.chamber = v.chamber
  WHERE v.chamber = $1 AND v.congress = $2 AND v.rollnumber = $3 AND v.position <> 0
), maj AS (
  SELECT party_code, sign(sum(position)) AS party_majority FROM pv GROUP BY party_code
)
SELECT pv.icpsr, pv.bioname, pv.party, pv.state_abbrev, pv.position, maj.party_majority
FROM pv JOIN maj USING (party_code)
WHERE maj.party_majority <> 0 AND pv.position = -maj.party_majority
ORDER BY pv.party, pv.bioname
