-- Safety and churn by day
SELECT
    date(ts) AS day,
    SUM(CASE WHEN event_type = 'report' THEN 1 ELSE 0 END) AS reports,
    SUM(CASE WHEN event_type = 'block' THEN 1 ELSE 0 END) AS blocks,
    SUM(CASE WHEN event_type = 'user_banned' THEN 1 ELSE 0 END) AS bans,
    SUM(CASE WHEN event_type = 'account_deleted' THEN 1 ELSE 0 END) AS deletions
FROM events
WHERE event_type IN ('report', 'block', 'user_banned', 'account_deleted')
GROUP BY day
ORDER BY day;
