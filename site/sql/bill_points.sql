-- Members' NOMINATE positions and their vote on one roll call. $1 chamber, $2 congress, $3 rollnumber
SELECT v.icpsr, m.bioname, coalesce(m.party_name, 'Party code ' || m.party_code) AS party, m.party_code,
       m.nominate_dim1, m.nominate_dim2, v.position
FROM votes v JOIN members m ON m.icpsr = v.icpsr AND m.congress = v.congress AND m.chamber = v.chamber
WHERE v.chamber = $1 AND v.congress = $2 AND v.rollnumber = $3
ORDER BY v.icpsr
