-- Roll calls of one chamber and Congress, with everything the list and bill view show. $1 chamber, $2 congress
SELECT rollnumber, date, bill_number, vote_question, coalesce(vote_desc, dtl_desc) AS description, vote_result,
       yea_n, nay_n, not_voting_n, minority_share, crs_policy_area_resolved, crs_source, pap_majortopic, pap_subtopic,
       nominate_mid_1, nominate_mid_2, nominate_spread_1, nominate_spread_2
FROM rollcalls WHERE chamber = $1 AND congress = $2
ORDER BY rollnumber
