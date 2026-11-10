-- One member's positions in one chamber and Congress. $1 icpsr, $2 chamber, $3 congress
SELECT r.rollnumber, r.date, r.bill_number, r.vote_question, coalesce(r.vote_desc, r.dtl_desc) AS description,
       v.position, r.yea_n, r.nay_n, r.minority_share
FROM votes v JOIN rollcalls r USING (chamber, congress, rollnumber)
WHERE v.icpsr = $1 AND v.chamber = $2 AND v.congress = $3
ORDER BY r.rollnumber
