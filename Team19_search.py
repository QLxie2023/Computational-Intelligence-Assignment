"""Fixed-depth Alpha-Beta search for Group 19, owned by member 2.

Scores always use the attacker's perspective. The core accepts rule and
evaluation functions so it can be tested before teammate modules are available.
The Player adapter currently searches two plies; iterative deepening and move
ordering can be added around this core later.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import time


Board = list[list[str]]
Move = list[list[int]]
Weights = list[float] | None

WIN_SCORE = 100_000.0
DEFAULT_DEPTH = 2
_TERMINAL_SCORES = {"A": WIN_SCORE, "D": -WIN_SCORE, "DRAW": 0.0}


class SearchTimeout(TimeoutError):
    """A depth was interrupted; its partial result must be discarded."""


@dataclass(frozen=True)
class SearchFunctions:
    """Functions supplied by members 1 and 3, or by a test fixture.

    All callbacks must leave their arguments unchanged. apply_move returns an
    independent board. check_winner accepts the actual availability of moves
    as its third argument. compute_hash, when supplied, includes the side to
    move and enables repetition checks against both history and the path.
    """

    get_legal_moves: Callable[[Board, bool], list[Move]]
    apply_move: Callable[[Board, Move, bool], Board]
    check_winner: Callable[[Board, bool, bool], str | None]
    evaluate_board: Callable[[Board, Weights], float]
    compute_hash: Callable[[Board, bool], int] | None = None


@dataclass(frozen=True)
class SearchResult:
    """A completed fixed-depth result; no move is chosen at depth zero or a terminal.

    nodes_visited includes the root, leaves and repeated positions. cutoffs
    counts bounds that actually skip at least one remaining sibling.
    """

    move: Move | None
    score: float
    nodes_visited: int
    cutoffs: int


def search_fixed_depth(
    board: Board,
    is_attacker: bool,
    depth: int,
    *,
    functions: SearchFunctions,
    weights: Weights = None,
    deadline: float | None = None,
    game_history: set[int] | None = None,
) -> SearchResult:
    """Search at most depth individual moves with an initially unbounded window.

    Attackers maximize; defenders minimize. Wins score +/- WIN_SCORE and draws
    score zero. Other leaves use evaluate_board(board, weights); its finite
    heuristic scores should lie strictly between the two win scores.

    Terminal and no-move checks precede horizon evaluation. Repetition checks
    also precede evaluation when a hasher is supplied. The current root may
    already occur in game_history without being treated as a new repetition.

    No board, weight list or real-game history is modified by the search.
    A deadline is an absolute time.perf_counter() timestamp. An interruption
    raises SearchTimeout rather than returning a partially searched root.
    Callbacks are synchronous, so their running time cannot be preempted.
    """
    if type(depth) is not int or depth < 0:
        raise ValueError("depth must be a non-negative integer")
    if deadline is not None and math.isnan(deadline):
        raise ValueError("deadline must not be NaN")
    if game_history and functions.compute_hash is None:
        raise ValueError("compute_hash is required when game_history is non-empty")

    history = game_history if game_history is not None else set()
    search_path: set[int] = set()
    nodes_visited = 0
    cutoffs = 0

    def check_deadline() -> None:
        if deadline is not None and time.perf_counter() >= deadline:
            raise SearchTimeout("Fixed-depth search exceeded its deadline")

    def visit(
        position: Board,
        attackers_turn: bool,
        remaining: int,
        alpha: float,
        beta: float,
        *,
        is_root: bool = False,
    ) -> tuple[float, Move | None]:
        nonlocal nodes_visited, cutoffs
        check_deadline()
        nodes_visited += 1
        moves = functions.get_legal_moves(position, attackers_turn)
        check_deadline()
        winner = functions.check_winner(position, attackers_turn, bool(moves))
        check_deadline()
        if winner is not None:
            if winner not in _TERMINAL_SCORES:
                raise ValueError(f"Unexpected winner marker: {winner!r}")
            return _TERMINAL_SCORES[winner], None
        if not moves:
            return 0.0, None

        position_hash = None
        if functions.compute_hash is not None:
            position_hash = functions.compute_hash(position, attackers_turn)
            check_deadline()
            if not is_root and (
                position_hash in history or position_hash in search_path
            ):
                return 0.0, None
            search_path.add(position_hash)

        try:
            if remaining == 0:
                check_deadline()
                score = float(functions.evaluate_board(position, weights))
                check_deadline()
                if not math.isfinite(score):
                    raise ValueError("evaluate_board must return a finite score")
                return score, None

            best_score = -math.inf if attackers_turn else math.inf
            best_move = None
            for index, move in enumerate(moves):
                check_deadline()
                child = functions.apply_move(position, move, attackers_turn)
                score, _ = visit(child, not attackers_turn, remaining - 1, alpha, beta)
                # Keep the first tie: a pruned child may return only a bound.
                if best_move is None or (
                    score > best_score if attackers_turn else score < best_score
                ):
                    best_score = score
                    best_move = move
                if attackers_turn:
                    alpha = max(alpha, best_score)
                else:
                    beta = min(beta, best_score)
                if alpha >= beta and index + 1 < len(moves):
                    cutoffs += 1
                    break
            return best_score, best_move
        finally:
            if position_hash is not None:
                search_path.remove(position_hash)

    score, move = visit(board, is_attacker, depth, -math.inf, math.inf, is_root=True)
    return SearchResult(move, score, nodes_visited, cutoffs)


def _load_functions() -> SearchFunctions:
    """Import real teammate modules only when the Player adapter is called."""
    from Team19_engine import apply_move, check_winner, compute_hash, get_legal_moves
    from Team19_eval import evaluate_board

    return SearchFunctions(
        get_legal_moves=get_legal_moves,
        apply_move=apply_move,
        check_winner=check_winner,
        evaluate_board=evaluate_board,
        compute_hash=compute_hash,
    )


def choose_best_move(
    board: Board,
    is_attacker: bool,
    deadline: float,
    game_history: set[int],
    weights: Weights = None,
) -> Move:
    """Return a legal move from one fixed-depth search using the shared API.

    Requires the real Team19_engine and Team19_eval modules and a nonterminal
    board with legal moves. A timeout discards the entire incomplete depth and
    returns the first legal move. This stage does not use iterative deepening.
    """
    functions = _load_functions()
    legal_moves = functions.get_legal_moves(board, is_attacker)
    winner = functions.check_winner(board, is_attacker, bool(legal_moves))
    if winner is not None or not legal_moves:
        raise ValueError("choose_best_move requires a nonterminal board with legal moves")
    fallback = [coordinate[:] for coordinate in legal_moves[0]]
    try:
        result = search_fixed_depth(
            board,
            is_attacker,
            DEFAULT_DEPTH,
            functions=functions,
            weights=weights,
            deadline=deadline,
            game_history=game_history,
        )
    except SearchTimeout:
        return fallback
    if result.move is None:
        raise RuntimeError("A completed search on a playable root did not choose a move")
    return [coordinate[:] for coordinate in result.move]
