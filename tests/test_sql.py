from app.services.sql import generate_and_execute

def test_scoring_leader():
    result = generate_and_execute("Who led the NBA in scoring in 2024?", [])
    assert result["results"], "Should return results"
    assert "Shai" in str(result["results"][0].values()) or "Gilgeous" in str(result["results"][0].values())

def test_player_stats():
    result = generate_and_execute("What were LeBron James stats in the 2024 regular season?", [])
    assert result["results"], "Should return results"
    row = result["results"][0]
    # LeBron averaged around 24 ppg
    pts = row.get("avg_pts") or row.get("pts")
    assert pts is not None
    assert 20 < float(pts) < 35, f"LeBron pts out of expected range: {pts}"

def test_team_query():
    result = generate_and_execute("Which team scored the most points per game in 2024?", [])
    assert result["results"], "Should return results"

def test_playoff_query():
    result = generate_and_execute("Who averaged the most points in the 2024 playoffs?", [])
    assert result["results"], "Should return results"

def test_sql_is_select():
    result = generate_and_execute("Who led the NBA in assists in 2024?", [])
    assert result["sql"].strip().upper().startswith("SELECT")

def test_no_empty_results_for_known_player():
    result = generate_and_execute("What were Nikola Jokic's stats in the 2024 season?", [])
    print(f"\nSQL: {result['sql']}")
    print(f"Results: {result['results']}")
    assert result["results"], "Jokic should have stats in 2024"