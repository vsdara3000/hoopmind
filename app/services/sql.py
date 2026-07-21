import re
from sqlalchemy import text
from app.database import SessionLocal
from app.services.llm import chat

SCHEMA_PROMPT = """You are an NBA stats analyst with access to a PostgreSQL database.
Generate a single valid SQL SELECT query to answer the user's question.

SCHEMA:
players: id, first_name, last_name, full_name, is_active, team_id
teams: id, full_name, abbreviation, nickname, city, state, year_founded
games: id, date, home_team_id, away_team_id, home_team_score, away_team_score,
       home_team_wins(bool), season(int), postseason(bool),
       home_team_fg_pct, away_team_fg_pct, home_team_fg3_pct, away_team_fg3_pct,
       home_team_reb, away_team_reb, home_team_ast, away_team_ast,
       home_team_tov, away_team_tov, home_team_stl, away_team_stl,
       home_team_blk, away_team_blk
       NOTE: games has NO ft_pct, NO fga, NO fg3a, NO ftm, NO fta columns.
player_game_stats: id, player_id, game_id, team_id, min(TEXT MM:SS), pts, reb, ast, stl, blk,
                   fgm, fga, fg_pct, fg3m, fg3a, fg3_pct, ftm, fta, ft_pct,
                   oreb, dreb, turnover, pf
season_averages: id, player_id, season(int), games_played, min, pts, reb, ast,
                 stl, blk, fg_pct, fg3_pct, ft_pct

RULES:
- SELECT only. No INSERT/UPDATE/DELETE/DROP.
- Always use table aliases (p, t, g, pgs, sa). Never use unaliased column names.
- pgs.min is TEXT (MM:SS). Never SUM, AVG, cast, or filter on pgs.min. Exclude it unless user asks about minutes.
- Player searches: ILIKE '%name%' on both first_name and last_name, OR match full_name.
- Player stats: always return aggregated averages not individual rows unless asked for game log.
- Per-game averages: SUM(pgs.pts)::float / NULLIF(COUNT(DISTINCT pgs.game_id), 0).
- Shooting %: SUM(pgs.fgm)::float / NULLIF(SUM(pgs.fga), 0). Never AVG(pgs.fg_pct).
- Aggregate filters go in HAVING, never WHERE.
- Regular season: g.postseason = FALSE. Playoffs: g.postseason = TRUE.
- season 2023 = 2023-24 season, season 2024 = 2024-25 season.
- home_team_wins is BOOLEAN. Never compare it to an integer.
- Real teams only: WHERE t.year_founded IS NOT NULL.
- games table has NO ft_pct, fga, fg3a, ftm, fta columns. For team FT% use player_game_stats.
- For team FG% use AVG(ts.fg_pct) via UNION ALL. For team FT% aggregate from pgs grouped by team/game.
- Home vs away player splits: use CASE WHEN g.home_team_id = pgs.team_id THEN ... END. Count games with COUNT(CASE WHEN g.home_team_id = pgs.team_id THEN 1 END).
- For team per-game stats use UNION ALL pattern only:
  SELECT t.full_name, AVG(ts.stat) FROM (
    SELECT g.home_team_id AS team_id, g.home_team_stat AS stat FROM games g WHERE ...
    UNION ALL
    SELECT g.away_team_id, g.away_team_stat FROM games g WHERE ...
  ) ts JOIN teams t ON ts.team_id = t.id WHERE t.year_founded IS NOT NULL GROUP BY t.full_name
- Never JOIN teams with OR condition (home_team_id = t.id OR away_team_id = t.id).
- Never compute team stats as combined home+away totals in same row.
- Qualified shooting % minimums (HAVING):
  RS FG%: fga>=300 | RS 3P%: fg3a>=200 | RS FT%: fta>=125
  PO FG%: fga>=50 | PO 3P%: fg3a>=10 | PO FT%: fta>=50
- RS per-game leaders: HAVING COUNT(DISTINCT pgs.game_id) >= 58.
- Always wrap OR player name conditions in parentheses: WHERE (first_name ILIKE '%x%' AND last_name ILIKE '%y%') AND other_conditions. Never use OR without parentheses when mixing with AND filters on other columns.
- season_averages columns (pts, reb, ast, stl, blk, fg_pct, fg3_pct, ft_pct) are already per-game averages. SELECT them directly. Never divide by games_played.
- For team stats with multiple columns, use a single query from player_game_stats grouped by team_id and game_id, then average across games. Never generate multiple UNION ALL blocks per stat column.
- Some player names have accented characters (e.g. Jokić, Dončić). Always wrap name searches with unaccent(): WHERE unaccent(p.first_name) ILIKE unaccent('%Jokic%') AND unaccent(p.last_name) ILIKE unaccent('%Jokic%'). This ensures accent-insensitive matching.
- Always wrap ALL WHERE conditions in parentheses when using OR: WHERE ((condition1) OR (condition2)) AND other_filter. Never let OR conditions bleed into AND filters.
- LIMIT 50 unless asked for more.
- Return ONLY raw SQL. No markdown, backticks, explanation. First char must be S."""


def clean_sql(sql: str) -> str:
    """Remove markdown fencing and invalid generated clauses."""
    sql = sql.strip()
    if sql.startswith("```"):
        sql = sql.lstrip("`").lstrip("sql").lstrip("\n")
        sql = sql.rstrip("`").rstrip("\n").strip()

    # remove invalid minutes-based HAVING clauses
    sql = re.sub(
        r"\nHAVING\s+SUM\(\s*pgs\.min(?:::float|::numeric|::double\s+precision)?\s*\)\s*>\s*0\s*",
        "\n",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def uses_combined_home_away_team_totals(sql: str) -> bool:
    """Detect team-stat SQL that combines both teams' totals per game row."""
    normalized = re.sub(r"\s+", " ", sql.lower())
    has_or_team_join = (
        "home_team_id = t.id or" in normalized
        and "away_team_id = t.id" in normalized
    )
    stat_pairs = [
        ("home_team_ast", "away_team_ast"),
        ("home_team_reb", "away_team_reb"),
        ("home_team_tov", "away_team_tov"),
        ("home_team_stl", "away_team_stl"),
        ("home_team_blk", "away_team_blk"),
        ("home_team_score", "away_team_score"),
    ]
    combines_home_away = any(
        home in normalized and away in normalized
        for home, away in stat_pairs
    )
    return has_or_team_join and combines_home_away


def uses_aggregate_in_where(sql: str) -> bool:
    """Detect aggregate functions incorrectly placed in WHERE clause."""
    normalized = re.sub(r"\s+", " ", sql.lower())
    where_match = re.search(
        r"\bwhere\b(.*?)(\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", normalized
    )
    return bool(
        where_match and re.search(r"\b(sum|avg|count|min|max)\s*\(", where_match.group(1))
    )


def uses_home_team_wins_as_integer(sql: str) -> bool:
    """Detect queries comparing boolean home_team_wins to an integer."""
    normalized = re.sub(r"\s+", " ", sql.lower())
    return bool(re.search(r"home_team_wins\s*=\s*\d", normalized))


def uses_nonexistent_games_columns(sql: str) -> bool:
    """Detect references to columns that don't exist in the games table."""
    normalized = sql.lower()
    invalid_columns = [
        "g.home_team_fga", "g.away_team_fga",
        "g.home_team_fg3a", "g.away_team_fg3a",
        "g.home_team_ftm", "g.away_team_ftm",
        "g.home_team_fta", "g.away_team_fta",
        "g.home_team_ft_pct", "g.away_team_ft_pct",
    ]
    return any(col in normalized for col in invalid_columns)


def execute_sql(sql: str) -> list[dict]:
    """Execute a SQL query and return results as a list of dicts."""
    sql = clean_sql(sql)
    with SessionLocal() as db:
        result = db.execute(text(sql))
        columns = result.keys()
        return [dict(zip(columns, row)) for row in result.fetchall()]


def retry_sql(messages: list[dict], sql: str, feedback: str) -> str:
    """Send a retry request to Groq with specific feedback about what to fix."""
    retry_messages = messages + [
        {"role": "assistant", "content": sql},
        {"role": "user", "content": feedback},
    ]
    return clean_sql(chat(retry_messages, max_tokens=800, temperature=0))


# (validator, feedback) pairs applied to generated SQL before execution
VALIDATORS = [
    (
        uses_combined_home_away_team_totals,
        "That query incorrectly combines both teams' stats per game row. "
        "Fix it using UNION ALL: one SELECT for home_team_id with home stat, "
        "one SELECT for away_team_id with away stat. AVG only that team's stat. "
        "Return ONLY corrected SQL.",
    ),
    (
        uses_aggregate_in_where,
        "That query places an aggregate (SUM/AVG/COUNT) in WHERE. "
        "Move aggregate filters to HAVING after GROUP BY. "
        "Return ONLY corrected SQL.",
    ),
    (
        uses_home_team_wins_as_integer,
        "home_team_wins is BOOLEAN (true/false), not an integer. "
        "Fix the comparison and return ONLY corrected SQL.",
    ),
    (
        uses_nonexistent_games_columns,
        "The games table has NO ft_pct, fga, fg3a, ftm, or fta columns. "
        "For team FT% use player_game_stats grouped by team_id and game_id. "
        "For team FG% use home_team_fg_pct / away_team_fg_pct via UNION ALL. "
        "Return ONLY corrected SQL.",
    ),
]


def _require_select(sql: str, context: str):
    """Raise if the SQL is not a SELECT statement."""
    if not sql.upper().startswith("SELECT"):
        raise ValueError(f"{context}: {sql[:100]}")


def generate_and_execute(question: str, history: list) -> dict:
    """
    Generate SQL from a natural language question, validate it,
    execute it against Postgres, and return results.
    Includes pre-execution validators and an error retry loop.
    """
    messages = [{"role": "system", "content": SCHEMA_PROMPT}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history[-4:]]
    messages.append({"role": "user", "content": question})

    sql = clean_sql(chat(messages, max_tokens=800, temperature=0))

    for check, feedback in VALIDATORS:
        if check(sql):
            sql = retry_sql(messages, sql, feedback)

    _require_select(sql, "Invalid SQL generated")

    try:
        results = execute_sql(sql)

        if not results:
            sql = retry_sql(
                messages, sql,
                "That query returned zero rows. Relax unnecessary HAVING qualifiers. "
                "Do not filter on pgs.min. For playoff 3P% use HAVING SUM(pgs.fg3a) >= 10 at most. "
                "Return ONLY corrected SQL."
            )
            _require_select(sql, "Empty-result retry generated invalid SQL")
            results = execute_sql(sql)

        return {"sql": sql, "results": results}

    except Exception as e:
        print(f"SQL execution failed: {e}")
        print(f"Failed SQL: {sql}")

        sql = retry_sql(
            messages, sql,
            f"That query failed: {str(e)}. Fix it. "
            "Put aggregate filters in HAVING not WHERE. "
            "Never use pgs.min in SUM/AVG. "
            "games has no ft_pct, fga, fg3a, ftm, fta columns. "
            "home_team_wins is BOOLEAN. "
            "Return ONLY corrected SQL."
        )
        _require_select(sql, "Retry generated invalid SQL")

        return {"sql": sql, "results": execute_sql(sql)}