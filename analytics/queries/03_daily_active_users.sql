-- Daily active users (people who did something themselves, not system events like expiry)
SELECT
    date(ts) AS day,
    COUNT(DISTINCT user_id) AS active_users
FROM events
WHERE user_id IS NOT NULL
  AND event_type IN ('signup_completed', 'profile_updated', 'profile_viewed', 'like', 'pass',
                     'first_message_sent', 'message_sent', 'report', 'block')
GROUP BY day
ORDER BY day;
