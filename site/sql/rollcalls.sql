-- Roll calls of one chamber and Congress. $1 chamber, $2 congress
SELECT rollnumber, date, bill_number, vote_question, coalesce(vote_desc, dtl_desc) AS description, vote_result,
       yea_n, nay_n, not_voting_n, minority_share, crs_policy_area_resolved, crs_source, pap_majortopic
FROM rollcalls WHERE chamber = $1 AND congress = $2
ORDER BY rollnumber
