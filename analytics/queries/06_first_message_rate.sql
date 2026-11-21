-- First-message rate: of matches that reached an outcome, how many got a first message in 24 hours?
-- Still-pending matches are left out of the rate. Closed means ended by a block, report or ban.
WITH matches AS (
    SELECT
        json_extract(properties, '$.match_id') AS match_id,
        json_extract(properties, '$.same_gender') AS same_gender
    FROM events
    WHERE event_type = 'match_created'
),
outcomes AS (
    SELECT
        json_extract(properties, '$.match_id') AS match_id,
        MAX(CASE WHEN event_type = 'first_message_sent' THEN 1 ELSE 0 END) AS written,
        MAX(CASE WHEN event_type = 'match_expired' THEN 1 ELSE 0 END) AS expired,
        MAX(CASE WHEN event_type = 'match_closed' THEN 1 ELSE 0 END) AS closed,
        MAX(CASE WHEN event_type = 'first_message_sent'
                 THEN json_extract(properties, '$.seconds_since_match') END) AS seconds_to_first
    FROM events
    WHERE event_type IN ('first_message_sent', 'match_expired', 'match_closed')
    GROUP BY match_id
)
SELECT
    CASE WHEN m.same_gender = 1 THEN 'same gender' ELSE 'woman and man' END AS pair,
    COUNT(*) AS matches,
    SUM(COALESCE(o.written, 0)) AS first_message,
    SUM(CASE WHEN o.expired = 1 AND COALESCE(o.written, 0) = 0 THEN 1 ELSE 0 END) AS expired,
    SUM(CASE WHEN o.closed = 1 AND COALESCE(o.written, 0) = 0 THEN 1 ELSE 0 END) AS closed_before_message,
    SUM(CASE WHEN o.match_id IS NULL THEN 1 ELSE 0 END) AS still_pending,
    ROUND(100.0 * SUM(COALESCE(o.written, 0))
        / NULLIF(SUM(COALESCE(o.written, 0))
                 + SUM(CASE WHEN o.expired = 1 AND COALESCE(o.written, 0) = 0 THEN 1 ELSE 0 END), 0), 1)
        AS first_message_pct,
    ROUND(AVG(o.seconds_to_first) / 3600.0, 1) AS avg_hours_to_first
FROM matches m
LEFT JOIN outcomes o ON o.match_id = m.match_id
GROUP BY pair
ORDER BY pair;
