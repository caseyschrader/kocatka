-- Why signups stopped
SELECT
    json_extract(properties, '$.reason') AS reason,
    COUNT(*) AS times
FROM events
WHERE event_type = 'signup_stopped'
GROUP BY reason
ORDER BY times DESC;
