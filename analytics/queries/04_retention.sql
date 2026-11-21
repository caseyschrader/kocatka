-- Retention by signup day: did people come back on day 1, day 7, or ever?
WITH signups AS (
    SELECT user_id, MIN(date(ts)) AS cohort
    FROM events
    WHERE event_type = 'signup_completed'
    GROUP BY user_id
),
activity AS (
    SELECT DISTINCT user_id, date(ts) AS day
    FROM events
    WHERE user_id IS NOT NULL
      AND event_type IN ('profile_updated', 'profile_viewed', 'like', 'pass',
                         'first_message_sent', 'message_sent', 'report', 'block')
),
per_user AS (
    SELECT
        s.cohort,
        s.user_id,
        MAX(CASE WHEN a.day = date(s.cohort, '+1 day') THEN 1 ELSE 0 END) AS d1,
        MAX(CASE WHEN a.day = date(s.cohort, '+7 day') THEN 1 ELSE 0 END) AS d7,
        MAX(CASE WHEN a.day > s.cohort THEN 1 ELSE 0 END) AS came_back
    FROM signups s
    LEFT JOIN activity a ON a.user_id = s.user_id
    GROUP BY s.cohort, s.user_id
)
SELECT
    cohort,
    COUNT(*) AS signups,
    SUM(d1) AS day1,
    SUM(d7) AS day7,
    SUM(came_back) AS came_back_ever,
    ROUND(100.0 * SUM(came_back) / COUNT(*), 1) AS came_back_pct
FROM per_user
GROUP BY cohort
ORDER BY cohort;
