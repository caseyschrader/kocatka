-- Signup funnel by day
-- Started and stopped are logged before consent, without a user id, so these are counts of attempts, not people.
SELECT
    date(ts) AS day,
    SUM(CASE WHEN event_type = 'signup_started' THEN 1 ELSE 0 END) AS started,
    SUM(CASE WHEN event_type = 'signup_stopped' THEN 1 ELSE 0 END) AS stopped,
    SUM(CASE WHEN event_type = 'signup_completed' THEN 1 ELSE 0 END) AS completed,
    ROUND(100.0 * SUM(CASE WHEN event_type = 'signup_completed' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN event_type = 'signup_started' THEN 1 ELSE 0 END), 0), 1) AS completed_pct
FROM events
WHERE event_type IN ('signup_started', 'signup_stopped', 'signup_completed')
GROUP BY day
ORDER BY day;
