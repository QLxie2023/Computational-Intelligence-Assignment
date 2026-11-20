"""Stress-test Team19.Player with the unmodified course referee.

This offline utility reuses the same two Player instances within each worker,
calls reset_game() before every game, and audits the exact history passed to
search. It uses only the standard library and writes results under the ignored
tools/game_logs directory by default.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import Tablut
import Team19


FAULT_MARKERS = {
    "timeouts": "exceeded time limit",
    "illegal_moves": "Illegal move",
    "crashes": "Exception caught",
}


class MonitoredPlayer:
    """Time referee calls and audit search without changing Player itself."""

    def __init__(self, player: Team19.Player, referee: Tablut.Tablut, side: str):
        self.player = player
        self.referee = referee
        self.side = side
        self.move_times: list[float] = []
        self.search_fallbacks = 0
        self.search_errors: list[str] = []
        self.history_mismatches: list[dict] = []
        self.raised_errors: list[str] = []
        self._original_search = player._choose_best_move
        if not callable(self._original_search):
            raise RuntimeError("Team19_search.choose_best_move is not loaded")
        player._choose_best_move = self._audited_search

    def close(self) -> None:
        self.player._choose_best_move = self._original_search

    def _audited_search(self, board, is_attacker, deadline, history, weights):
        expected = set(self.referee.past_positions)
        if set(history) != expected:
            self.history_mismatches.append({
                "round": self.referee.rounds_played + 1,
                "missing": len(expected - set(history)),
                "foreign": len(set(history) - expected),
            })
        try:
            return self._original_search(
                board, is_attacker, deadline, history, weights,
            )
        except Exception as error:
            self.search_fallbacks += 1
            self.search_errors.append(f"{type(error).__name__}: {error}")
            raise

    def _timed_play(self, board, is_attacker: bool):
        started = time.perf_counter()
        try:
            if is_attacker:
                return self.player.play_attacker(board)
            return self.player.play_defender(board)
        except Exception as error:
            self.raised_errors.append(f"{type(error).__name__}: {error}")
            raise
        finally:
            self.move_times.append(time.perf_counter() - started)

    def play_attacker(self, board):
        return self._timed_play(board, True)

    def play_defender(self, board):
        return self._timed_play(board, False)


def _reset_violations(player: Team19.Player, budget: float) -> list[str]:
    violations = []
    if player.history:
        violations.append("history not empty")
    if player.moves_played != 0:
        violations.append("moves_played not zero")
    if abs(player.remaining - budget) > 1e-9:
        violations.append("remaining budget not restored")
    if player.last_error is not None:
        violations.append("last_error not cleared")
    return violations


def _terminal_reason(output: str, winner: str | None) -> str:
    if "exceeded time limit" in output:
        return "timeout"
    if "Illegal move" in output:
        return "illegal_move"
    if "Exception caught" in output:
        return "crash"
    if "Repeated position found" in output:
        return "repetition_draw"
    if "Player cannot move" in output:
        return "no_legal_move_draw"
    if winner == "A":
        return "attackers_win"
    if winner == "D":
        return "defenders_win"
    return "draw"


def run_game(game_number: int, budget: float, attacker, defender) -> dict:
    attacker.reset_game()
    defender.reset_game()
    reset_violations = {
        "attacker": _reset_violations(attacker, budget),
        "defender": _reset_violations(defender, budget),
    }
    referee = Tablut.Tablut()
    monitored_attacker = MonitoredPlayer(attacker, referee, "attacker")
    monitored_defender = MonitoredPlayer(defender, referee, "defender")
    output = io.StringIO()
    started = time.perf_counter()
    try:
        with redirect_stdout(output):
            referee.play(monitored_attacker, monitored_defender)
    finally:
        monitored_attacker.close()
        monitored_defender.close()
    elapsed = time.perf_counter() - started
    referee_output = output.getvalue()
    monitors = (monitored_attacker, monitored_defender)
    faults = {
        name: referee_output.count(marker)
        for name, marker in FAULT_MARKERS.items()
    }
    history_mismatches = sum(len(m.history_mismatches) for m in monitors)
    search_fallbacks = sum(m.search_fallbacks for m in monitors)
    raised_errors = sum(len(m.raised_errors) for m in monitors)
    reset_errors = sum(len(items) for items in reset_violations.values())
    clean = not any(faults.values()) and not any((
        history_mismatches, search_fallbacks, raised_errors, reset_errors,
    ))
    return {
        "game": game_number,
        "budget_seconds": budget,
        "winner": referee.winner,
        "terminal_reason": _terminal_reason(referee_output, referee.winner),
        "rounds": referee.rounds_played,
        "elapsed_seconds": round(elapsed, 6),
        "clean": clean,
        "faults": faults,
        "history_mismatches": history_mismatches,
        "search_fallbacks": search_fallbacks,
        "raised_errors": raised_errors,
        "reset_violations": reset_violations,
        "sides": {
            monitor.side: {
                "moves": len(monitor.move_times),
                "search_fallbacks": monitor.search_fallbacks,
                "search_errors": monitor.search_errors,
                "history_mismatches": monitor.history_mismatches,
                "raised_errors": monitor.raised_errors,
                "total_move_seconds": round(sum(monitor.move_times), 6),
                "max_move_seconds": round(max(monitor.move_times, default=0.0), 6),
                "remaining_seconds": round(monitor.player.remaining, 6),
                "history_size": len(monitor.player.history),
            }
            for monitor in monitors
        },
        "referee_output": referee_output.strip().splitlines(),
    }


def run_chunk(payload: tuple[float, list[int]]) -> list[dict]:
    """Run a sequential series so each worker reuses its two Player objects."""
    budget, game_numbers = payload
    Tablut.TIME_BUDGET = budget
    attacker = Team19.Player()
    defender = Team19.Player()
    for player in (attacker, defender):
        if not all(callable(member) for member in (
            player._choose_best_move, player._apply_move,
            player._check_winner, player._compute_hash,
        )):
            raise RuntimeError("All formal Team19 modules must be importable")
    return [run_game(number, budget, attacker, defender) for number in game_numbers]


def _summary(budget: float, games: int, workers: int, results: list[dict],
             wall_seconds: float) -> dict:
    fault_counts = Counter()
    reasons = Counter()
    winners = Counter()
    for result in results:
        fault_counts.update(result["faults"])
        reasons[result["terminal_reason"]] += 1
        winners[result["winner"] or "DRAW"] += 1
    side_maxima = [
        side["max_move_seconds"]
        for result in results for side in result["sides"].values()
    ]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version,
        "budget_seconds_per_side": budget,
        "games": games,
        "workers": workers,
        "player_reuse": "Two persistent Player instances per worker; reset_game() before every game",
        "clean_games": sum(result["clean"] for result in results),
        "fault_counts": dict(fault_counts),
        "history_mismatches": sum(r["history_mismatches"] for r in results),
        "search_fallbacks": sum(r["search_fallbacks"] for r in results),
        "raised_errors": sum(r["raised_errors"] for r in results),
        "reset_violations": sum(
            sum(len(items) for items in r["reset_violations"].values())
            for r in results
        ),
        "winners": dict(winners),
        "terminal_reasons": dict(reasons),
        "wall_seconds": round(wall_seconds, 6),
        "mean_game_seconds": round(
            sum(r["elapsed_seconds"] for r in results) / games, 6,
        ),
        "max_game_seconds": round(max(r["elapsed_seconds"] for r in results), 6),
        "max_single_move_seconds": round(max(side_maxima), 6),
        "results": sorted(results, key=lambda result: result["game"]),
    }


def run_suite(budget: float, games: int, workers: int) -> dict:
    worker_count = min(workers, games)
    chunks = [
        (budget, list(range(worker + 1, games + 1, worker_count)))
        for worker in range(worker_count)
    ]
    results: list[dict] = []
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(run_chunk, chunk) for chunk in chunks]
        for future in as_completed(futures):
            chunk_results = future.result()
            results.extend(chunk_results)
            print(
                f"Completed {len(results)}/{games} games at {budget:g}s",
                flush=True,
            )
    return _summary(budget, games, worker_count, results, time.perf_counter() - started)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, required=True,
                        help="Total seconds per side per game")
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--output", type=Path,
                        help="JSON result path; defaults to tools/game_logs")
    args = parser.parse_args()
    if args.budget <= 0 or args.games <= 0 or args.workers <= 0:
        parser.error("--budget, --games and --workers must be positive")
    return args


def main() -> int:
    args = parse_args()
    output = args.output
    if output is None:
        output = ROOT / "tools" / "game_logs" / (
            f"player_stress_{args.budget:g}s_{args.games}games.json"
        )
    if not output.is_absolute():
        output = ROOT / output
    summary = run_suite(args.budget, args.games, args.workers)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    clean = summary["clean_games"] == args.games
    print(json.dumps({key: value for key, value in summary.items() if key != "results"},
                     indent=2, ensure_ascii=False), flush=True)
    print(f"Results: {output}", flush=True)
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
