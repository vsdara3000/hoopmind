import os
import re
from groq import Groq
from dotenv import load_dotenv
from sqlalchemy import text
from app.database import SessionLocal

load_dotenv()
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

SCHEMA_PROMPT = """You are an NBA stats analyst with access to a PostgreSQL database.
Generate a single valid SQL SELECT query to answer the user's question.

SCHEMA:
players: id, first_name, last_name, full_name, is_active, team_id
teams: id, full_name, abbreviation, nickname, city, state, year_founded
games: id, date, home_team_id, away_team_id, home_team_score, away_team_score,
       home_team_wins, season, postseason,
       home_team_fg_pct, away_team_fg_pct, home_team_fg3_pct, away_team_fg3_pct,
       home_team_reb, away_team_reb, home_team_ast, away_team_ast,
       home_team_tov, away_team_tov, home_team_stl, away_team_stl,
       home_team_blk, away_team_blk
player_game_stats: id, player_id, game_id, team_id, min (text MM:SS string), pts, reb, ast, stl, blk,
                   fgm, fga, fg_pct, fg3m, fg3a, fg3_pct, ftm, fta, ft_pct,
                   oreb, dreb, turnover, pf
season_averages: id, player_id, season, games_played, min, pts, reb, ast,
                 stl, blk, fg_pct, fg3_pct, ft_pct

CRITICAL RULES:
- SELECT only. No INSERT, UPDATE, DELETE, DROP.
- Always use table aliases. Example: SELECT p.first_name, pgs.pts
- NEVER use unaliased column names like "pts" or "min" - always use alias.pts, alias.min
- ALWAYS use alias.column_name in SUM, AVG, COUNT functions
- player_game_stats.min is TEXT in MM:SS format. Do NOT use pgs.min, SUM(pgs.min), AVG(pgs.min), pgs.min::float, or HAVING clauses on pgs.min unless the user explicitly asks about minutes.
- Do NOT add a minutes-played qualifier for scoring, rebounds, assists, shooting, leaders, or average-stat questions. Use games played or attempts as qualifiers instead.
- For regular-season questions, add g.postseason = FALSE. Only use g.postseason = TRUE when the user says playoffs or postseason.
- For player per-game stats from player_game_stats: use decimal division, e.g. SUM(pgs.pts)::float / NULLIF(COUNT(DISTINCT pgs.game_id), 0). NEVER divide two integers directly.
- For shooting percentages: use decimal division over makes and attempts, e.g. SUM(pgs.fgm)::float / NULLIF(SUM(pgs.fga), 0). Do NOT average per-game pct columns for season/career percentages.
- Aggregate filters like SUM(pgs.fga) >= 300 must go in HAVING after GROUP BY, never in WHERE.
- For scoring/rebounds/assists leaders, do not add a HAVING qualifier unless the user asks for official qualification. If qualification is needed for regular-season per-game leaders, use HAVING COUNT(DISTINCT pgs.game_id) >= 58.
- For "best", "highest", "leader", or ranked shooting percentage queries, default to qualified leaders unless the user asks for unqualified/raw leaders. Use these exact minimums:
  regular-season FG%: HAVING SUM(pgs.fga) >= 300
  regular-season 3P%: HAVING SUM(pgs.fg3a) >= 200
  regular-season FT%: HAVING SUM(pgs.fta) >= 125
  playoff FG%: HAVING SUM(pgs.fga) >= 50
  playoff 3P%: HAVING SUM(pgs.fg3a) >= 10
  playoff FT%: HAVING SUM(pgs.fta) >= 50
  Always ORDER BY the calculated percentage DESC NULLS LAST.
- For team per-game stats, use the team totals in games via UNION ALL, then AVG the per-game team totals. Example for assists:
  SELECT t.full_name, AVG(ts.ast)::float AS avg_assists
  FROM (
    SELECT g.home_team_id AS team_id, g.home_team_ast AS ast FROM games g WHERE g.season = 2024 AND g.postseason = FALSE
    UNION ALL
    SELECT g.away_team_id AS team_id, g.away_team_ast AS ast FROM games g WHERE g.season = 2024 AND g.postseason = FALSE
  ) ts
  JOIN teams t ON ts.team_id = t.id
  WHERE t.year_founded IS NOT NULL
  GROUP BY t.full_name
  ORDER BY avg_assists DESC NULLS LAST
- NEVER join teams with "g.home_team_id = t.id OR g.away_team_id = t.id" for team per-game stats.
- NEVER calculate a team's per-game stat as SUM(g.home_team_stat) + SUM(g.away_team_stat), AVG(g.home_team_stat + g.away_team_stat), or any combined home+away game total.
- Do NOT compute team per-game stats as AVG(player_game_stats.stat) / COUNT(games).
- Filter by season using the games alias, e.g. WHERE g.season = 2024 (integer)
- Real teams only: WHERE teams.year_founded IS NOT NULL
- LIMIT 50 unless asked for more.
- Return ONLY raw SQL. No markdown, backticks, explanation."""


def clean_sql(sql: str) -> str:
    """Normalize model SQL output and remove known unsafe generated clauses."""
    sql = sql.strip()
    if sql.startswith("```"):
        sql = sql.lstrip("`").lstrip("sql").lstrip("\n")
        sql = sql.rstrip("`").rstrip("\n").strip()

    # The DB stores pgs.min as MM:SS text, and the model sometimes invents a
    # minutes-played qualifier. For non-minute questions this clause is both
    # unnecessary and invalid.
    sql = re.sub(
        r"\nHAVING\s+SUM\(\s*pgs\.min(?:::float|::numeric|::double\s+precision)?\s*\)\s*>\s*0\s*",
        "\n",
        sql,
        flags=re.IGNORECASE,
    )
    return sql


def uses_combined_home_away_team_totals(sql: str) -> bool:
    """Detect team-stat SQL that totals both teams in each game for one team."""
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
    combines_home_away_stat = any(
        home_col in normalized and away_col in normalized
        for home_col, away_col in stat_pairs
    )
    return has_or_team_join and combines_home_away_stat


def uses_aggregate_in_where(sql: str) -> bool:
    """Detect invalid aggregate filters before GROUP BY."""
    normalized = re.sub(r"\s+", " ", sql.lower())
    where_match = re.search(r"\bwhere\b(.*?)(\bgroup\s+by\b|\border\s+by\b|\blimit\b|$)", normalized)
    return bool(where_match and re.search(r"\b(sum|avg|count|min|max)\s*\(", where_match.group(1)))


def execute_sql(sql: str) -> list[dict]:
    """Execute a SQL query and return results as a list of dicts."""
    sql = clean_sql(sql)
    
    db = SessionLocal()
    try:
        result = db.execute(text(sql))
        columns = result.keys()
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return rows
    finally:
        db.close()


def retry_sql(messages: list[dict], sql: str, feedback: str) -> str:
    retry_messages = messages + [
        {"role": "assistant", "content": sql},
        {"role": "user", "content": feedback},
    ]

    retry_response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=retry_messages,
        max_tokens=500,
        temperature=0
    )
    return clean_sql(retry_response.choices[0].message.content.strip())


def generate_and_execute(question: str, history: list) -> dict:
    """
    Generate a SQL query from a natural language question,
    execute it, and return the results.

    If execution fails, feeds the error back to Groq for a retry.
    Returns a dict with 'sql' and 'results' keys.
    """
    messages = [
        {"role": "system", "content": SCHEMA_PROMPT}
    ]

    for m in history[-4:]:
        messages.append({"role": m["role"], "content": m["content"]})

    messages.append({"role": "user", "content": question})

    # first attempt
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        max_tokens=500,
        temperature=0
    )
    sql = response.choices[0].message.content.strip()

    sql = clean_sql(sql)

    if uses_combined_home_away_team_totals(sql):
        sql = retry_sql(
            messages,
            sql,
            "That query incorrectly combines both teams' game totals for each team. Fix it using a UNION ALL subquery with one row per team-game: one SELECT for home_team_id with the home_team stat, and one SELECT for away_team_id with the away_team stat. Then JOIN teams on the subquery team_id and AVG only that team's stat. Return ONLY the corrected query."
        )

    if uses_aggregate_in_where(sql):
        sql = retry_sql(
            messages,
            sql,
            "That query incorrectly places an aggregate function such as SUM, AVG, or COUNT in WHERE. Move aggregate filters to HAVING after GROUP BY. For shooting percentage leader qualifiers, use the exact HAVING threshold from the system rules. Return ONLY the corrected query."
        )

    # validate it's a SELECT
    if not sql.upper().startswith("SELECT"):
        raise ValueError(f"Invalid SQL generated: {sql[:100]}")

    # try to execute
    try:
        results = execute_sql(sql)
        if not results:
            sql = retry_sql(
                messages,
                sql,
                "That query executed but returned zero rows. Fix the SQL and return ONLY the corrected query with no markdown, backticks, or explanation. Relax unnecessary HAVING clauses and qualifiers. Do not use pgs.min. For scoring leaders, do not require minutes or attempts. For playoff three-point percentage, use HAVING SUM(pgs.fg3a) >= 10 at most."
            )

            if not sql.upper().startswith("SELECT"):
                raise ValueError(f"Empty-result retry generated invalid SQL: {sql[:100]}")

            results = execute_sql(sql)
        return {"sql": sql, "results": results}

    except Exception as e:
        print(f"SQL execution failed: {e}")
        print(f"Failed SQL: {sql}")

        # retry — feed error back to Groq
        sql = retry_sql(
            messages,
            sql,
            f"That query failed with this error: {str(e)}. Fix the SQL and return ONLY the corrected query with no markdown, backticks, or explanation. Put aggregate filters in HAVING, not WHERE. Do not use pgs.min, SUM(pgs.min), or pgs.min::float unless the question explicitly asks about minutes."
        )

        if not sql.upper().startswith("SELECT"):
            raise ValueError(f"Retry also generated invalid SQL: {sql[:100]}")

        results = execute_sql(sql)
        return {"sql": sql, "results": results}
