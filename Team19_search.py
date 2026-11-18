"""Alpha-Beta search for Group 19, owned by member 2.

Scores always use the attacker's perspective. The core accepts rule and
evaluation functions so it can be tested before teammate modules are available.
The Player adapter uses iterative deepening; experiments can fix the depth.
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
_MAX_ITERATIVE_DEPTH = 64
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
    result, _ = _search_depth(
        board, is_attacker, depth, functions, weights, deadline, game_history,
    )
    return result


def _search_depth(
    board: Board,
    is_attacker: bool,
    depth: int,
    functions: SearchFunctions,
    weights: Weights,
    deadline: float | None,
    game_history: set[int] | None,
    *,
    playable_root_moves: list[Move] | None = None,
) -> tuple[SearchResult, bool]:
    """Return the depth result and whether any scored leaf used the heuristic."""
    if deadline is not None and math.isnan(deadline):
        raise ValueError("deadline must not be NaN")
    if game_history and functions.compute_hash is None:
        raise ValueError("compute_hash is required when game_history is non-empty")

    history = game_history if game_history is not None else set()
    search_path: set[int] = set()
    nodes_visited = 0
    cutoffs = 0
    evaluated_horizon = False

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
        nonlocal nodes_visited, cutoffs, evaluated_horizon
        check_deadline()
        nodes_visited += 1
        if is_root and playable_root_moves is not None:
            moves = playable_root_moves
        else:
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
                evaluated_horizon = True
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
    check_deadline()
    return SearchResult(move, score, nodes_visited, cutoffs), evaluated_horizon


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
    """Return the move from the deepest completed Alpha-Beta iteration.

    Requires the real Team19_engine and Team19_eval modules and a nonterminal
    board with legal moves. The same absolute deadline applies to every depth.
    If depth one cannot finish, return the first legal move. Search also stops
    when the result is proven without heuristic leaves or at the recursion guard.
    """
    functions = _load_functions()
    legal_moves = functions.get_legal_moves(board, is_attacker)
    winner = functions.check_winner(board, is_attacker, bool(legal_moves))
    if winner is not None or not legal_moves:
        raise ValueError("choose_best_move requires a nonterminal board with legal moves")
    best_move = legal_moves[0]
    root_order = legal_moves
    for depth in range(1, _MAX_ITERATIVE_DEPTH + 1):
        try:
            result, evaluated_horizon = _search_depth(
                board, is_attacker, depth, functions, weights, deadline, game_history,
                playable_root_moves=root_order,
            )
        except SearchTimeout:
            break
        if result.move is None:
            raise RuntimeError("A completed search on a playable root did not choose a move")
        best_move = result.move
        if not evaluated_horizon:
            break
        if best_move != root_order[0]:
            root_order = [best_move] + [move for move in legal_moves if move != best_move]
    return [coordinate[:] for coordinate in best_move]
