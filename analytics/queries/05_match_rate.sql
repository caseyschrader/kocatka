-- Likes, matches and match rate by day
SELECT
    date(ts) AS day,
    SUM(CASE WHEN event_type = 'profile_viewed' THEN 1 ELSE 0 END) AS views,
    SUM(CASE WHEN event_type = 'like' THEN 1 ELSE 0 END) AS likes,
    SUM(CASE WHEN event_type = 'pass' THEN 1 ELSE 0 END) AS passes,
    SUM(CASE WHEN event_type = 'match_created' THEN 1 ELSE 0 END) AS matches,
    ROUND(100.0 * SUM(CASE WHEN event_type = 'match_created' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN event_type = 'like' THEN 1 ELSE 0 END), 0), 1) AS matches_per_100_likes
FROM events
WHERE event_type IN ('profile_viewed', 'like', 'pass', 'match_created')
GROUP BY day
ORDER BY day;
