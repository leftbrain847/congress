-- Every Congress a member served, both chambers. $1 icpsr
SELECT congress, chamber, bioname, coalesce(party_name, 'Party code ' || party_code) AS party, state_abbrev,
       district_code, bioguide_id, born, died, nominate_dim1, nominate_dim2
FROM members WHERE icpsr = $1
ORDER BY congress, chamber
