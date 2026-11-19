"""Local replay records for the browser practice board."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

import play_human as practice


LOG_DIR = Path(__file__).resolve().with_name("game_logs")


def summarize(game: practice.Game) -> dict:
    stats = game.ai_turns
    return {
        "aiTurns": len(stats),
        "depths": dict(Counter(turn.depth for turn in stats)),
        "fallbacks": sum(turn.fallback for turn in stats),
        "errors": sum(turn.error for turn in stats),
        "slowest": max((turn.elapsed for turn in stats), default=0),
    }


def ai_points(game: practice.Game) -> int | None:
    if game.outcome is None:
        return None
    winner = game.referee.winner
    return 1 if winner is None else 2 * int(winner != practice.side_code(game.human_attacker))


def position(game: practice.Game) -> dict:
    return {
        "board": ["".join(row) for row in game.referee.board],
        "sideToMove": practice.side_code(game.attackers_turn),
        "hash": f"{game.referee.compute_zobrist_hash(game.attackers_turn):016x}",
    }


def clocks(game: practice.Game) -> dict:
    return {"refereeRemaining": game.remaining, "playerRemaining": game.player.remaining}


def encode(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


class MatchLog:
    def __init__(self, game: practice.Game, *, source: str = "web", resumed_from: str | None = None):
        started = datetime.now(UTC)
        self.started = started.isoformat()
        self.source = source
        self.resumed_from = resumed_from
        self.initial = position(game)
        self.turns: list[dict] = []
        self.name = f"tablut-{started:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.json"

    def add_move(self, game: practice.Game, *, live: bool = True) -> None:
        event = game.last_move
        if event is None:
            raise ValueError("No move to record.")
        played_by_human = game.attackers_turn != game.human_attacker
        self.turns.append({
            "ply": len(game.moves),
            "side": practice.side_code(not game.attackers_turn),
            "actor": "human" if played_by_human else "ai",
            **asdict(event),
            "positionAfter": position(game),
            "clocksAfter": clocks(game) if live else None,
        })

    def undo(self, plies: int) -> None:
        del self.turns[plies:]

    def repetition(self, game: practice.Game) -> dict | None:
        if game.outcome != "repeated position" or not self.turns:
            return None
        last = self.turns[-1]
        target = last["positionAfter"]
        positions = [self.initial, *(turn["positionAfter"] for turn in self.turns[:-1])]
        for first, previous in enumerate(positions):
            # Compare both the complete board and the side to move before
            # describing the referee's repeated-hash decision to the player.
            if previous == target:
                return {"firstPly": first, "repeatedPly": last["ply"], "sideToMove": target["sideToMove"]}
        return None

    def data(self, game: practice.Game, reports: list[dict]) -> dict:
        by_ply = {report["ply"]: report for report in reports if report["move"] is not None}
        points = ai_points(game)
        return {
            "schema": "team19.tablut.replay",
            "version": 1,
            "source": self.source,
            "recordingStartedUtc": self.started,
            "resumedFrom": self.resumed_from,
            "humanSide": practice.side_code(game.human_attacker),
            "budgetSeconds": game.budget,
            "scorePerspective": "positive favours attackers",
            "initial": self.initial,
            "turns": [
                {**turn, "analysis": by_ply.get(turn["ply"])}
                for turn in self.turns
            ],
            "final": {
                "position": position(game),
                "clocks": clocks(game),
                "finished": game.outcome is not None,
                "winner": game.referee.winner,
                "reason": game.outcome,
                "repetition": self.repetition(game),
                "forfeit": game.forfeit,
                "points": {"ai": points, "human": 2 - points} if points is not None else None,
                "aiTurnStats": [asdict(turn) for turn in game.ai_turns],
                "summary": summarize(game),
                "failedAiAttempt": reports[-1] if game.forfeit and reports else None,
            },
        }

    def save(self, game: practice.Game, reports: list[dict]) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        contents = encode(self.data(game, reports))
        temporary = None
        try:
            with NamedTemporaryFile(dir=LOG_DIR, prefix=".tablut-", suffix=".tmp", delete=False) as pending:
                temporary = Path(pending.name)
                pending.write(contents)
            temporary.replace(LOG_DIR / self.name)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
