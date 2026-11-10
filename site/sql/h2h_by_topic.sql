-- Head-to-head split by topic: the reference the browser's pair computation (site/js/compute.js) is tested against.
-- Topic: PAP major topic code ('pap') or resolved CRS policy area ('crs'); '' = not coded.
-- $1 icpsr_a, $2 icpsr_b, $3 chamber, $4 congress_from, $5 congress_to, $6 contested_threshold, $7 scheme
SELECT CASE WHEN $7 = 'pap' THEN coalesce(CAST(r.pap_majortopic AS VARCHAR), '')
            ELSE coalesce(r.crs_policy_area_resolved, '') END AS topic,
       count(*) AS shared_all,
       count(*) FILTER (WHERE a.position = b.position) AS agree_all,
       count(*) FILTER (WHERE r.minority_share >= $6) AS shared_contested,
       count(*) FILTER (WHERE r.minority_share >= $6 AND a.position = b.position) AS agree_contested
FROM votes a
JOIN votes b ON b.chamber = a.chamber AND b.congress = a.congress AND b.rollnumber = a.rollnumber
JOIN rollcalls r ON r.chamber = a.chamber AND r.congress = a.congress AND r.rollnumber = a.rollnumber
WHERE a.icpsr = $1 AND b.icpsr = $2 AND a.chamber = $3 AND a.congress BETWEEN $4 AND $5
  AND a.position <> 0 AND b.position <> 0
GROUP BY 1
ORDER BY 1
