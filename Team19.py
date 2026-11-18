"""Player adapter for Group 19, owned by member 4.

The referee in Tablut.py only ever calls play_attacker and play_defender. This
module owns everything around the search module: the time budget of a whole
game, the real game history, and the guarantee that a legal move is returned
even when a teammate module is missing or raises an exception.

Two facts from Tablut.py drive the design:

* the budget is per game, not per move, so every call must ask for a share of
  what is still left instead of a fixed thinking time;
* past_positions is seeded with the hash of the initial position and then
  extended once per move, always keyed by the side to move next. The same
  positions are recorded here so that repetition draws line up with the
  referee.

Missing modules are tolerated on purpose: the first week integration can run
end to end before the engine, evaluator and search are all present, and a
late integration mistake costs weaker moves rather than a forfeit.
"""

from __future__ import annotations

import math
import time

_INITIAL_BOARD = (
    (".", ".", ".", "A", "A", "A", ".", ".", "."),
    (".", ".", ".", ".", "A", ".", ".", ".", "."),
    (".", ".", ".", ".", "D", ".", ".", ".", "."),
    ("A", ".", ".", ".", "D", ".", ".", ".", "A"),
    ("A", "A", "D", "D", "K", "D", "D", "A", "A"),
    ("A", ".", ".", ".", "D", ".", ".", ".", "A"),
    (".", ".", ".", ".", "D", ".", ".", ".", "."),
    (".", ".", ".", ".", "A", ".", ".", ".", "."),
    (".", ".", ".", "A", "A", "A", ".", ".", "."),
)

# The referee may shorten TIME_BUDGET when it tests all the bots.
_DEFAULT_TIME_BUDGET = 60.0
# Never handed to the search; covers building and returning the move.
_RETURN_RESERVE = 0.05
# A share below this is not worth a search at all.
_MIN_THINK_TIME = 0.02
# A single move may never take more than this share of what is left, so the
# budget is drawn down geometrically and can never be spent by one decision.
_MAX_STEP_FRACTION = 0.20
# Roughly two own moves per piece left on the board; only used to estimate how
# many shares are still to be handed out.
_MOVES_PER_PIECE = 2.0
_MIN_EXPECTED_MOVES = 16


def _import_member(module_name: str, attribute: str):
    """Return one callable from a teammate module, or None if it is absent."""
    try:
        module = __import__(module_name, fromlist=[attribute])
    except Exception:
        return None
    member = getattr(module, attribute, None)
    return member if callable(member) else None


def _read_time_budget() -> float:
    """Read the referee's per-game budget instead of assuming sixty seconds."""
    try:
        budget = float(getattr(__import__("Tablut"), "TIME_BUDGET", _DEFAULT_TIME_BUDGET))
    except Exception:
        return _DEFAULT_TIME_BUDGET
    return budget if math.isfinite(budget) and budget > 0.0 else _DEFAULT_TIME_BUDGET


def _load_weights() -> list[float] | None:
    """Tuned weights from member 5 if they were exported, else the default.

    Returning None is meaningful: the evaluator then applies its own defaults,
    so this file works before member 5 has produced any tuned vector.
    """
    sources = (("Team19_weights", "WEIGHTS"), ("Team19_eval", "DEFAULT_WEIGHTS"))
    for module_name, attribute in sources:
        try:
            module = __import__(module_name, fromlist=[attribute])
            weights = [float(weight) for weight in getattr(module, attribute)]
        except Exception:
            continue
        if weights:
            return weights
    return None


class Player:
    """Referee-facing player: one instance may be reused across games."""

    def __init__(self):
        # Loaded once here, never inside the timed methods.
        self._choose_best_move = _import_member("Team19_search", "choose_best_move")
        self._get_legal_moves = _import_member("Team19_engine", "get_legal_moves")
        self._apply_move = _import_member("Team19_engine", "apply_move")
        self._check_winner = _import_member("Team19_engine", "check_winner")
        self._compute_hash = _import_member("Team19_engine", "compute_hash")

        self.weights = _load_weights()
        self.total_budget = _read_time_budget()
        self.remaining = self.total_budget
        self.moves_played = 0
        self.history: set[int] = set()
        self._last_board: list[list[str]] | None = None
        # Last exception that forced a fallback move, kept for debugging.
        self.last_error: BaseException | None = None

    # =================================================
    # Referee entry points
    def play_attacker(self, board: list[list[str]]) -> list[list[int]]:
        return self._play(board, True)

    def play_defender(self, board: list[list[str]]) -> list[list[int]]:
        return self._play(board, False)

    def _play(self, board: list[list[str]], is_attacker: bool) -> list[list[int]]:
        """Always returns a move; the charged time is what was really used."""
        started = time.perf_counter()
        position = [list(row) for row in board]
        try:
            return self._select_move(position, is_attacker, started)
        except Exception as error:
            # Swallowing the error is what keeps the referee alive, but it must
            # stay observable: a silent fallback hides real bugs, so the last
            # failure is kept here for tests and debugging.
            self.last_error = error
            # Last resort: an independent generator cannot fail, so at least
            # the referee receives a syntactically valid move.
            move = self._emergency_move(position, is_attacker)
            self.moves_played += 1
            self._last_board = position
            return move
        finally:
            self.remaining = max(0.0, self.remaining - (time.perf_counter() - started))

    # =================================================
    # One decision
    def _select_move(
        self, position: list[list[str]], is_attacker: bool, started: float,
    ) -> list[list[int]]:
        self._start_new_game_if_needed(position)

        legal = self._legal_moves(position, is_attacker)
        self._record_opponent_position(position, is_attacker)

        chosen = None
        step_budget = self._step_budget(position)
        if step_budget > 0.0 and legal and self._choose_best_move is not None:
            try:
                candidate = self._choose_best_move(
                    position, is_attacker, started + step_budget, set(self.history),
                    self.weights,
                )
            except Exception:
                candidate = None
            chosen = self._match_legal_move(candidate, legal)

        if chosen is None:
            chosen = self._fallback_move(position, is_attacker, legal)

        after_move = self._record_own_position(position, chosen, is_attacker)
        self.moves_played += 1
        self._last_board = position if after_move is None else after_move
        return [[int(chosen[0][0]), int(chosen[0][1])],
                [int(chosen[1][0]), int(chosen[1][1])]]

    # =================================================
    # Time budget
    def _step_budget(self, board: list[list[str]]) -> float:
        """Share of the remaining game budget this move may spend.

        The share shrinks as the pool shrinks and as moves are used up, so the
        budget is never exhausted by a single decision. Actual time used is
        charged afterwards, which means unused allocation simply carries over.
        """
        available = self.remaining - _RETURN_RESERVE
        if available <= _MIN_THINK_TIME:
            return 0.0
        expected_moves = max(_MIN_EXPECTED_MOVES, int(_MOVES_PER_PIECE * _piece_count(board)))
        moves_left = max(1, expected_moves - self.moves_played)
        fair_share = available / moves_left
        step = min(max(fair_share, _MIN_THINK_TIME), available * _MAX_STEP_FRACTION)
        return step if step >= _MIN_THINK_TIME else 0.0

    # =================================================
    # Game history
    def _start_new_game_if_needed(self, board: list[list[str]]) -> None:
        if self._starts_a_new_game(board):
            self._reset_game()

    def _starts_a_new_game(self, board: list[list[str]]) -> bool:
        """Detect a fresh game on a reused instance.

        Only signals that cannot fire inside a single game are used, because
        the two failure modes are not equally bad: a missed reset keeps a dead
        time budget and stale history, while a spurious reset refills the
        budget mid-game and lets the referee flag a timeout.

        * The first board ever seen is a new game by definition.
        * The referee always starts from the initial position, so an exact
          match is conclusive -- this is what the attacker sees.
        * The defender is handed that position after one attacker move, which
          is still recognisable: the initial board with a single attacker
          piece relocated.
        * Pieces are never added during a game, so a rising count means a
          reset as well. (Captures only make it fall.)

        An earlier version compared boards square by square and expected one
        or two newly occupied squares. That broke when the opponent stepped
        onto the square we had just vacated: the square stays occupied
        throughout, so the only "new" square was our own landing square and a
        mid-game board was wrongly treated as a new game.
        """
        if self._last_board is None:
            return True
        if self._is_initial_board(board):
            return True
        if self._is_opening_reply(board):
            return True
        return _piece_count(board) > _piece_count(self._last_board)

    @staticmethod
    def _is_opening_reply(board: list[list[str]]) -> bool:
        """True for the initial position with exactly one move played.

        Either side may move first in a harness, so the move is not assumed to
        be the attacker's. A first move cannot capture, so exactly two squares
        differ: the origin is now empty and another square holds the piece
        that used to stand on it, on a shared rank or file.
        """
        if len(board) != len(_INITIAL_BOARD):
            return False
        if any(len(row) != len(_INITIAL_BOARD[index]) for index, row in enumerate(board)):
            return False
        changed = [(row, col) for row in range(len(board))
                   for col in range(len(board[row]))
                   if board[row][col] != _INITIAL_BOARD[row][col]]
        if len(changed) != 2:
            return False
        (first_row, first_col), (second_row, second_col) = changed
        for start, end in (((first_row, first_col), (second_row, second_col)),
                           ((second_row, second_col), (first_row, first_col))):
            if board[start[0]][start[1]] != ".":
                continue
            if board[end[0]][end[1]] != _INITIAL_BOARD[start[0]][start[1]]:
                continue
            if start[0] == end[0] or start[1] == end[1]:
                return True
        return False

    def _reset_game(self) -> None:
        self.total_budget = _read_time_budget()
        self.remaining = self.total_budget
        self.moves_played = 0
        self.history = set()
        start_hash = self._position_hash([list(row) for row in _INITIAL_BOARD], True)
        if start_hash is not None:
            self.history.add(start_hash)

    def _record_opponent_position(self, board: list[list[str]], is_attacker: bool) -> None:
        position_hash = self._position_hash(board, is_attacker)
        if position_hash is not None:
            self.history.add(position_hash)

    def _record_own_position(
        self, board: list[list[str]], move: list[list[int]], is_attacker: bool,
    ) -> list[list[str]] | None:
        """Record the position our move leads to and return it, if possible."""
        if self._apply_move is None:
            return None
        try:
            new_board = self._apply_move(
                board, [[move[0][0], move[0][1]], [move[1][0], move[1][1]]], is_attacker,
            )
        except Exception:
            return None
        position_hash = self._position_hash(new_board, not is_attacker)
        if position_hash is not None:
            self.history.add(position_hash)
        return [list(row) for row in new_board]

    def _position_hash(self, board: list[list[str]], is_attacker: bool) -> int | None:
        if self._compute_hash is None:
            return None
        try:
            return int(self._compute_hash(board, is_attacker))
        except Exception:
            return None

    # =================================================
    # Legal moves and fallbacks
    def _legal_moves(self, board: list[list[str]], is_attacker: bool) -> list[list[list[int]]]:
        """Engine moves first; an independent generator validates them.

        A move the engine offers but the independent rules reject would lose
        the game on the referee's illegal-move check, so it is dropped. When
        the two disagree completely the engine list is trusted as a whole.
        """
        engine_moves = []
        if self._get_legal_moves is not None:
            try:
                engine_moves = list(self._get_legal_moves(board, is_attacker))
            except Exception:
                engine_moves = []

        reference = self._reference_legal_moves(board, is_attacker)
        if not engine_moves:
            return [[[start[0], start[1]], [end[0], end[1]]] for start, end in sorted(reference)]
        if not reference:
            return engine_moves
        verified = [move for move in engine_moves
                    if self._as_pair(move) in reference]
        return verified or engine_moves

    @staticmethod
    def _reference_legal_moves(board: list[list[str]], is_attacker: bool) -> set:
        """Movement rules of the referee, independent of the engine module."""
        own = ("A",) if is_attacker else ("D", "K")
        rows = len(board)
        cols = len(board[0]) if rows else 0
        moves = set()
        for row in range(rows):
            for col in range(cols):
                if board[row][col] not in own:
                    continue
                for delta_row, delta_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    target_row, target_col = row + delta_row, col + delta_col
                    while (0 <= target_row < rows and 0 <= target_col < cols
                           and board[target_row][target_col] in (".", "X")):
                        if board[target_row][target_col] == ".":
                            moves.add(((row, col), (target_row, target_col)))
                        target_row += delta_row
                        target_col += delta_col
        return moves

    @staticmethod
    def _as_pair(move) -> tuple | None:
        try:
            return ((int(move[0][0]), int(move[0][1])),
                    (int(move[1][0]), int(move[1][1])))
        except Exception:
            return None

    def _match_legal_move(self, candidate, legal: list[list[list[int]]]):
        """Reject anything the search returns that is not in the verified list."""
        if candidate is None:
            return None
        wanted = self._as_pair(candidate)
        if wanted is None:
            return None
        for move in legal:
            if self._as_pair(move) == wanted:
                return move
        return None

    def _fallback_move(
        self, board: list[list[str]], is_attacker: bool, legal: list[list[list[int]]],
    ) -> list[list[int]]:
        if not legal:
            # No legal move: the referee ends the game as a draw regardless.
            return [[0, 0], [0, 1]]
        winning = self._winning_move(board, is_attacker, legal)
        return winning if winning is not None else legal[0]

    def _winning_move(self, board: list[list[str]], is_attacker: bool, legal):
        """Deepest fallback: still finish off an opponent when it is free."""
        if self._apply_move is None or self._check_winner is None:
            return None
        target = "A" if is_attacker else "D"
        for move in legal:
            try:
                child = self._apply_move(
                    board, [[move[0][0], move[0][1]], [move[1][0], move[1][1]]], is_attacker,
                )
                winner = self._check_winner(child, not is_attacker, True)
            except Exception:
                return None
            if winner == target:
                return move
        return None

    def _emergency_move(self, board, is_attacker: bool) -> list[list[int]]:
        try:
            reference = self._reference_legal_moves(
                [list(row) for row in board], is_attacker,
            )
        except Exception:
            return [[0, 0], [0, 1]]
        if not reference:
            return [[0, 0], [0, 1]]
        start, end = min(reference)
        return [[int(start[0]), int(start[1])], [int(end[0]), int(end[1])]]

    @staticmethod
    def _is_initial_board(board: list[list[str]]) -> bool:
        if len(board) != len(_INITIAL_BOARD):
            return False
        return all(tuple(row) == _INITIAL_BOARD[index] for index, row in enumerate(board))


def _count(board: list[list[str]], piece: str) -> int:
    return sum(row.count(piece) for row in board)


def _piece_count(board: list[list[str]]) -> int:
    return sum(_count(board, piece) for piece in ("A", "D", "K"))


# ==== End of file
