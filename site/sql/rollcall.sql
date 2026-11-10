-- One roll call. $1 chamber, $2 congress, $3 rollnumber
SELECT * FROM rollcalls WHERE chamber = $1 AND congress = $2 AND rollnumber = $3
