-- Conversations: of matches with a first message, how many got a reply, and how long did they run?
WITH started AS (
    SELECT json_extract(properties, '$.match_id') AS match_id, user_id AS first_sender
    FROM events
    WHERE event_type = 'first_message_sent'
),
per_match AS (
    SELECT
        s.match_id,
        COUNT(m.event_id) AS messages,
        MAX(CASE WHEN m.user_id <> s.first_sender THEN 1 ELSE 0 END) AS replied
    FROM started s
    LEFT JOIN events m
        ON m.event_type = 'message_sent'
       AND json_extract(m.properties, '$.match_id') = s.match_id
    GROUP BY s.match_id
)
SELECT
    COUNT(*) AS conversations,
    SUM(replied) AS got_a_reply,
    ROUND(100.0 * SUM(replied) / NULLIF(COUNT(*), 0), 1) AS reply_pct,
    SUM(CASE WHEN messages >= 10 THEN 1 ELSE 0 END) AS ten_plus_messages,
    ROUND(AVG(messages), 1) AS avg_messages
FROM per_match;
