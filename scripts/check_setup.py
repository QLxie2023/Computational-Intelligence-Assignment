"""Check the Group 19 development setup without third-party packages."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)
    print(f"[PASS] {message}")


def main() -> None:
    print(f"Python: {sys.version.split()[0]}")
    print(f"Interpreter: {sys.executable}")
    require(sys.version_info >= (3, 10), "Python supports the planned annotations")

    for filename in ("Tablut.py", "Team00.py", "requirements.txt", "Team19_search.py"):
        require((ROOT / filename).is_file(), f"Repository contains {filename}")

    # Import from this checkout, including when invoked from another directory.
    sys.path.insert(0, str(ROOT))
    import Tablut as official
    from Team00 import Player
    import Team19_search as search

    require(
        callable(getattr(Player, "play_attacker", None))
        and callable(getattr(Player, "play_defender", None)),
        "Official manual Player exposes both required methods",
    )
    require(
        callable(getattr(search, "choose_best_move", None)),
        "Search interface imports without unfinished teammate modules",
    )

    game = official.Tablut()
    require(
        len(game.board) == 9 and all(len(row) == 9 for row in game.board),
        "Official initial board is 9 by 9",
    )
    counts = Counter(cell for row in game.board for cell in row)
    require(
        counts == Counter({"A": 16, "D": 8, "K": 1, ".": 56}),
        "Official initial board has 16 attackers, 8 defenders and 1 king",
    )
    initial_hash = game.compute_zobrist_hash(True)
    require(
        initial_hash == game.compute_zobrist_hash(True)
        and initial_hash != game.compute_zobrist_hash(False),
        "Official position hash is stable and distinguishes the side to move",
    )
    game.past_positions = [initial_hash]
    require(
        game.make_move(True, [[0, 3], [0, 2]])
        and not game.check_if_game_over(False),
        "Official framework accepts an opening attacker move",
    )
    require(
        game.make_move(False, [[2, 4], [2, 3]])
        and not game.check_if_game_over(True),
        "Official framework accepts a defender reply",
    )
    print(f"Official total time budget per player per game: {official.TIME_BUDGET} s")
    print("Setup checks passed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[FAIL] {error}", file=sys.stderr)
        raise SystemExit(1) from error
