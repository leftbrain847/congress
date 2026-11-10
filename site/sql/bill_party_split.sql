-- Split of one roll call by party. $1 chamber, $2 congress, $3 rollnumber
SELECT coalesce(m.party_name, 'Party code ' || m.party_code) AS party, m.party_code,
       count(*) FILTER (WHERE v.position = 1) AS yea,
       count(*) FILTER (WHERE v.position = -1) AS nay,
       count(*) FILTER (WHERE v.position = 0) AS not_voting
FROM votes v JOIN members m ON m.icpsr = v.icpsr AND m.congress = v.congress AND m.chamber = v.chamber
WHERE v.chamber = $1 AND v.congress = $2 AND v.rollnumber = $3
GROUP BY ALL
ORDER BY count(*) DESC, party
