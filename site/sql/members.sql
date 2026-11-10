-- Members of one chamber in one Congress. $1 chamber, $2 congress
SELECT icpsr, bioname, coalesce(party_name, 'Party code ' || party_code) AS party, party_code, state_abbrev,
       district_code, nominate_dim1, nominate_dim2
FROM members WHERE chamber = $1 AND congress = $2
ORDER BY bioname
