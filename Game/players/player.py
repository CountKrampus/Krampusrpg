from Server.database import get_connection


def get_player(player_id: int):
    with get_connection() as db:
        row = db.execute(
            """
            SELECT
                p.*,
                pp.current_region,
                pp.current_area,
                pp.money,
                pp.badges
            FROM players p
            LEFT JOIN player_progress pp
                ON pp.player_id = p.id
            WHERE p.id = ?
            """,
            (player_id,),
        ).fetchone()

        return dict(row) if row else None
