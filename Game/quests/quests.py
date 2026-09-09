from Server.database import get_connection


def get_quests():
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT *
            FROM quests
            ORDER BY id
            """
        ).fetchall()

        return [dict(row) for row in rows]


def get_player_quests(player_id: int):
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT
                pq.*,
                q.name,
                q.description,
                q.reward_money,
                q.reward_item,
                q.reward_quantity
            FROM player_quests pq
            JOIN quests q
                ON q.id = pq.quest_id
            WHERE pq.player_id = ?
            ORDER BY q.id
            """,
            (player_id,),
        ).fetchall()

        return [dict(row) for row in rows]
