"""Behavioral tests for fixed-depth search and the shared Player adapter.

Tree boards contain a node label in [0][0]; they are not real Tablut positions.
The independent oracle walks the node data directly, without Alpha-Beta bounds
or the search callbacks. The final tests use the unmodified official referee.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
import random
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

import Team19_search as search


@dataclass(frozen=True)
class Node:
    children: tuple[str, ...] = ()
    score: float = 0.0
    winner: str | None = None
    blocked: bool = False
    side: bool | None = None


def tree_move(index: int) -> search.Move:
    return [[0, 0], [0, index + 1]]


class TreeGame:
    def __init__(self, nodes: dict[str, Node]):
        self.nodes = nodes
        self.ids = {name: index for index, name in enumerate(nodes)}
        self.evaluated: list[tuple[str, search.Weights]] = []

    @staticmethod
    def board(name: str) -> search.Board:
        board = [["."] * 9 for _ in range(9)]
        board[0][0] = name
        return board

    def get_legal_moves(self, board: search.Board, is_attacker: bool) -> list[search.Move]:
        node = self.nodes[board[0][0]]
        if node.side is not None:
            assert node.side == is_attacker, "Search did not alternate the side to move"
        if node.winner is not None or node.blocked:
            return []
        # Heuristic frontier nodes are still playable; no-move positions draw.
        # Their continuation must never be expanded at the requested horizon.
        return [tree_move(i) for i in range(len(node.children) or 1)]

    def apply_move(self, board: search.Board, move: search.Move, is_attacker: bool) -> search.Board:
        node = self.nodes[board[0][0]]
        if node.side is not None:
            assert node.side == is_attacker
        if not node.children:
            raise AssertionError("Search expanded beyond the artificial tree horizon")
        return self.board(node.children[move[1][1] - 1])

    def check_winner(self, board: search.Board, next_attacker: bool, has_moves: bool) -> str | None:
        node = self.nodes[board[0][0]]
        assert has_moves == (node.winner is None and not node.blocked)
        if node.side is not None:
            assert node.side == next_attacker
        return node.winner if node.winner is not None else (None if has_moves else "DRAW")

    def evaluate_board(self, board: search.Board, weights: search.Weights) -> float:
        name = board[0][0]
        node = self.nodes[name]
        assert node.winner is None and not node.blocked, "A terminal was evaluated heuristically"
        self.evaluated.append((name, weights))
        return node.score + (weights[0] if weights else 0.0)

    def compute_hash(self, board: search.Board, is_attacker: bool) -> int:
        return self.ids[board[0][0]] * 2 + int(is_attacker)

    def functions(self, *, hashing: bool = False) -> search.SearchFunctions:
        return search.SearchFunctions(
            self.get_legal_moves, self.apply_move, self.check_winner,
            self.evaluate_board, self.compute_hash if hashing else None,
        )


def exhaustive_minimax(
    nodes: dict[str, Node], name: str, is_attacker: bool, depth: int,
) -> tuple[float, int | None, int]:
    """Independent full enumeration: (value, best child index, visited nodes)."""
    node = nodes[name]
    if node.winner is not None:
        return {"A": 100_000.0, "D": -100_000.0, "DRAW": 0.0}[node.winner], None, 1
    if node.blocked:
        return 0.0, None, 1
    if depth == 0:
        return node.score, None, 1
    if not node.children:
        raise AssertionError("Oracle exhausted the tree before its horizon")
    descendants = [exhaustive_minimax(nodes, child, not is_attacker, depth - 1)
                   for child in node.children]
    values = [result[0] for result in descendants]
    value = max(values) if is_attacker else min(values)
    return value, values.index(value), 1 + sum(result[2] for result in descendants)


def random_tree(seed: int, depth: int, is_attacker: bool) -> TreeGame:
    rng = random.Random(seed)
    nodes: dict[str, Node] = {}

    def build(name: str, remaining: int, side: bool, *, root: bool = False) -> None:
        score = rng.randint(-50, 50)
        if not root and rng.random() < 0.12:
            nodes[name] = Node(score=score, winner=rng.choice(("A", "D", "DRAW")), side=side)
        elif not root and rng.random() < 0.08:
            nodes[name] = Node(score=score, blocked=True, side=side)
        elif remaining == 0:
            nodes[name] = Node(score=score, side=side)
        else:
            children = tuple(f"{name}.{i}" for i in range(rng.randint(1, 4)))
            nodes[name] = Node(children, score=score, side=side)
            for child in children:
                build(child, remaining - 1, not side)

    build("root", depth, is_attacker, root=True)
    return TreeGame(nodes)


def teammate_modules(game: TreeGame) -> dict[str, ModuleType]:
    """Provide fake modules only inside a test, never as production files."""
    engine = ModuleType("Team19_engine")
    evaluator = ModuleType("Team19_eval")
    for name in ("get_legal_moves", "apply_move", "check_winner", "compute_hash"):
        setattr(engine, name, getattr(game, name))
    evaluator.evaluate_board = game.evaluate_board
    return {"Team19_engine": engine, "Team19_eval": evaluator}


class AlphaBetaTests(unittest.TestCase):
    def test_one_ply_maximizes_for_attackers_and_minimizes_for_defenders(self):
        for side, index, score in ((True, 1, 4), (False, 0, -7)):
            with self.subTest(is_attacker=side):
                game = TreeGame({"root": Node(("a", "b", "c")),
                                 "a": Node(score=-7), "b": Node(score=4), "c": Node(score=2)})
                result = search.search_fixed_depth(game.board("root"), side, 1, functions=game.functions())
                self.assertEqual((result.move, result.score), (tree_move(index), score))

    def test_two_plies_account_for_the_opponents_best_reply(self):
        for side, sign in ((True, 1), (False, -1)):
            with self.subTest(is_attacker=side):
                game = TreeGame({
                    "root": Node(("greedy", "safe"), side=side),
                    "greedy": Node(("g1", "g2"), score=10 * sign, side=not side),
                    "safe": Node(("s1", "s2"), score=sign, side=not side),
                    "g1": Node(score=-9 * sign, side=side),
                    "g2": Node(score=10 * sign, side=side),
                    "s1": Node(score=2 * sign, side=side),
                    "s2": Node(score=3 * sign, side=side),
                })
                shallow = search.search_fixed_depth(game.board("root"), side, 1, functions=game.functions())
                deeper = search.search_fixed_depth(game.board("root"), side, 2, functions=game.functions())
                self.assertEqual(shallow.move, tree_move(0))
                self.assertEqual((deeper.move, deeper.score), (tree_move(1), 2 * sign))

    def test_depth_zero_returns_only_the_current_evaluation(self):
        game = TreeGame({"root": Node(("child",), score=8), "child": Node(score=-20)})
        result = search.search_fixed_depth(game.board("root"), True, 0, functions=game.functions())
        self.assertEqual((result.move, result.score, result.nodes_visited, result.cutoffs), (None, 8, 1, 0))

    def test_terminals_are_scored_before_the_horizon_or_no_move_draw(self):
        for winner, score in (("A", 100_000.0), ("D", -100_000.0), ("DRAW", 0.0)):
            for depth in (0, 3):
                with self.subTest(winner=winner, depth=depth):
                    game = TreeGame({"root": Node(winner=winner, score=987)})
                    result = search.search_fixed_depth(game.board("root"), True, depth, functions=game.functions())
                    self.assertIsNone(result.move)
                    self.assertEqual(result.score, score)
                    self.assertEqual(game.evaluated, [])

    def test_immediate_wins_override_heuristics_for_both_sides(self):
        for side, winner, score in ((True, "A", 100_000.0), (False, "D", -100_000.0)):
            with self.subTest(is_attacker=side):
                game = TreeGame({"root": Node(("ordinary", "win")),
                                 "ordinary": Node(score=999 if side else -999),
                                 "win": Node(winner=winner)})
                result = search.search_fixed_depth(game.board("root"), side, 1, functions=game.functions())
                self.assertEqual((result.move, result.score), (tree_move(1), score))

    def test_no_move_child_is_a_draw_even_at_the_horizon(self):
        for side in (True, False):
            with self.subTest(is_attacker=side):
                game = TreeGame({"root": Node(("stuck", "loss")),
                                 "stuck": Node(score=999, blocked=True),
                                 "loss": Node(score=-5 if side else 5)})
                result = search.search_fixed_depth(game.board("root"), side, 1, functions=game.functions())
                self.assertEqual((result.move, result.score), (tree_move(0), 0.0))

    def test_pruning_preserves_result_and_reduces_visited_nodes(self):
        for side, sign in ((True, 1), (False, -1)):
            with self.subTest(is_attacker=side):
                nodes = {"root": Node(("l", "r")), "l": Node(("ll", "lr")),
                         "r": Node(("rl", "rr")), "ll": Node(("a", "b")),
                         "lr": Node(("c", "d")), "rl": Node(("e", "f")),
                         "rr": Node(("g", "h"))}
                nodes.update({label: Node(score=value * sign)
                              for label, value in zip("abcdefgh", (3, 5, 6, 9, 1, 2, 4, 7))})
                game = TreeGame(nodes)
                result = search.search_fixed_depth(game.board("root"), side, 3, functions=game.functions())
                expected, index, full_nodes = exhaustive_minimax(nodes, "root", side, 3)
                self.assertEqual((result.move, result.score), (tree_move(index), expected))
                self.assertEqual((full_nodes, result.nodes_visited, result.cutoffs), (15, 11, 2))

    def test_a_cutoff_bound_that_ties_does_not_replace_the_proven_best_move(self):
        for side, sign in ((True, 1), (False, -1)):
            with self.subTest(is_attacker=side):
                game = TreeGame({
                    "root": Node(("good", "bad")),
                    "good": Node(("g1", "g2")), "bad": Node(("b1", "b2")),
                    "g1": Node(score=5 * sign), "g2": Node(score=9 * sign),
                    "b1": Node(score=5 * sign), "b2": Node(score=-10 * sign),
                })
                result = search.search_fixed_depth(game.board("root"), side, 2, functions=game.functions())
                self.assertEqual((result.move, result.score), (tree_move(0), 5 * sign))
                self.assertNotIn("b2", [name for name, _ in game.evaluated])

    def test_equal_moves_keep_the_first_legal_move(self):
        game = TreeGame({"root": Node(("a", "b")), "a": Node(score=4), "b": Node(score=4)})
        for side in (True, False):
            result = search.search_fixed_depth(game.board("root"), side, 1, functions=game.functions())
            self.assertEqual(result.move, tree_move(0))

    def test_matches_exhaustive_minimax_on_160_seeded_trees(self):
        for seed in range(20):
            for depth in range(1, 5):
                for side in (True, False):
                    with self.subTest(seed=seed, depth=depth, is_attacker=side):
                        game = random_tree(seed * 100 + depth, depth, side)
                        score, index, full_nodes = exhaustive_minimax(game.nodes, "root", side, depth)
                        result = search.search_fixed_depth(game.board("root"), side, depth, functions=game.functions())
                        self.assertEqual((result.move, result.score), (tree_move(index), score))
                        self.assertLessEqual(result.nodes_visited, full_nodes)

    def test_preserves_inputs_and_passes_weights_to_the_evaluator(self):
        game = TreeGame({"root": Node(("a", "b")), "a": Node(score=2), "b": Node(score=5)})
        board, weights = game.board("root"), [0.5]
        history = {game.compute_hash(board, True)}
        snapshot = deepcopy((board, weights, history))
        result = search.search_fixed_depth(board, True, 1, functions=game.functions(hashing=True),
                                           weights=weights, game_history=history)
        self.assertEqual(result.score, 5.5)
        self.assertTrue(all(actual_weights is weights for _, actual_weights in game.evaluated))
        self.assertEqual((board, weights, history), snapshot)

    def test_rejects_invalid_depths_and_nonfinite_evaluations(self):
        game = TreeGame({"root": Node(score=2)})
        for depth in (-1, 1.5, True):
            with self.subTest(depth=depth), self.assertRaises(ValueError):
                search.search_fixed_depth(game.board("root"), True, depth, functions=game.functions())
        for score in (math.nan, math.inf, -math.inf):
            bad = TreeGame({"root": Node(score=score)})
            with self.subTest(score=score), self.assertRaises(ValueError):
                search.search_fixed_depth(bad.board("root"), True, 0, functions=bad.functions())


class RepetitionTests(unittest.TestCase):
    def test_real_history_draws_are_avoided_when_ahead_and_chosen_when_behind(self):
        for side, advantage in ((True, 2), (False, -2)):
            for ordinary_score in (advantage, -advantage):
                with self.subTest(is_attacker=side, ordinary_score=ordinary_score):
                    game = TreeGame({"root": Node(("repeat", "ordinary")),
                                     "repeat": Node(score=99), "ordinary": Node(score=ordinary_score)})
                    history = {game.compute_hash(game.board("repeat"), not side)}
                    result = search.search_fixed_depth(game.board("root"), side, 1,
                                                       functions=game.functions(hashing=True), game_history=history)
                    ahead = ordinary_score == advantage
                    self.assertEqual(result.move, tree_move(1 if ahead else 0))
                    self.assertEqual(result.score, ordinary_score if ahead else 0.0)
                    self.assertNotIn("repeat", [name for name, _ in game.evaluated])

    def test_root_in_real_history_is_not_itself_a_new_repetition(self):
        game = TreeGame({"root": Node(("child",)), "child": Node(score=7)})
        for side in (True, False):
            history = {game.compute_hash(game.board("root"), side)}
            result = search.search_fixed_depth(game.board("root"), side, 1,
                                               functions=game.functions(hashing=True), game_history=history)
            self.assertEqual(result.score, 7)

    def test_path_cycle_is_a_draw(self):
        game = TreeGame({"root": Node(("loop", "safe")), "loop": Node(("root",)),
                         "safe": Node(("loss",)), "loss": Node(score=-3)})
        result = search.search_fixed_depth(game.board("root"), True, 2, functions=game.functions(hashing=True))
        self.assertEqual((result.move, result.score), (tree_move(0), 0.0))

    def test_same_board_with_different_side_is_not_a_repetition(self):
        game = TreeGame({"root": Node(("root",), score=7)})
        history = {game.compute_hash(game.board("root"), True)}
        for depth, expected in ((1, 7), (2, 0)):
            with self.subTest(depth=depth):
                result = search.search_fixed_depth(game.board("root"), True, depth,
                                                   functions=game.functions(hashing=True), game_history=history)
                self.assertEqual(result.score, expected)

    def test_shared_position_in_a_sibling_branch_is_not_a_path_cycle(self):
        game = TreeGame({"root": Node(("left", "right")), "left": Node(("shared", "bad")),
                         "right": Node(("shared", "good")), "shared": Node(score=2),
                         "bad": Node(score=-5), "good": Node(score=1)})
        result = search.search_fixed_depth(game.board("root"), True, 2, functions=game.functions(hashing=True))
        self.assertEqual((result.move, result.score), (tree_move(1), 1))
        self.assertEqual([name for name, _ in game.evaluated].count("shared"), 2)

    def test_win_takes_precedence_over_history_repetition(self):
        for side, winner, score in ((True, "A", 100_000.0), (False, "D", -100_000.0)):
            game = TreeGame({"root": Node(("win",)), "win": Node(winner=winner)})
            history = {game.compute_hash(game.board("win"), not side)}
            result = search.search_fixed_depth(game.board("root"), side, 1,
                                               functions=game.functions(hashing=True), game_history=history)
            self.assertEqual(result.score, score)

    def test_nonempty_history_requires_a_compatible_hasher(self):
        game = TreeGame({"root": Node(score=2)})
        with self.assertRaises(ValueError):
            search.search_fixed_depth(game.board("root"), True, 0,
                                      functions=game.functions(), game_history={123})


class AdapterAndDeadlineTests(unittest.TestCase):
    def test_public_entry_loads_teammate_functions_and_passes_history_and_weights(self):
        game = TreeGame({"root": Node(("left", "right")), "left": Node(("repeat",)),
                         "right": Node(("safe",)), "repeat": Node(score=99), "safe": Node(score=2)})
        board, weights = game.board("root"), [0.5]
        history = {game.compute_hash(board, True), game.compute_hash(game.board("repeat"), True)}
        snapshot = deepcopy((board, weights, history))
        with patch.dict(sys.modules, teammate_modules(game)):
            move = search.choose_best_move(board, True, math.inf, history, weights)
        self.assertEqual(move, tree_move(1))
        self.assertEqual((board, weights, history), snapshot)
        self.assertTrue(all(actual is weights for _, actual in game.evaluated))

    def test_public_entry_rejects_terminal_or_no_move_roots(self):
        for node in (Node(blocked=True), Node(winner="A")):
            game = TreeGame({"root": node})
            with patch.dict(sys.modules, teammate_modules(game)), self.assertRaises(ValueError):
                search.choose_best_move(game.board("root"), True, math.inf, set())

    def test_expired_core_deadline_raises_without_evaluating(self):
        game = TreeGame({"root": Node(score=3)})
        with patch("Team19_search.time.perf_counter", return_value=10), self.assertRaises(search.SearchTimeout):
            search.search_fixed_depth(game.board("root"), True, 0, functions=game.functions(), deadline=9)
        self.assertEqual(game.evaluated, [])

    def test_core_discards_a_depth_that_times_out_inside_evaluation(self):
        game = TreeGame({"root": Node(("child",)), "child": Node(score=8)})
        clock = [0.0]
        original = game.evaluate_board

        def slow_evaluation(board, weights):
            clock[0] = 2.0
            return original(board, weights)

        game.evaluate_board = slow_evaluation
        with patch("Team19_search.time.perf_counter", side_effect=lambda: clock[0]):
            with self.assertRaises(search.SearchTimeout):
                search.search_fixed_depth(game.board("root"), True, 1, functions=game.functions(), deadline=1)

    def test_public_timeout_returns_fallback_instead_of_partially_best_move(self):
        game = TreeGame({"root": Node(("a", "b", "c")), "a": Node(("a0",)),
                         "b": Node(("b0",)), "c": Node(("c0",)),
                         "a0": Node(score=1), "b0": Node(score=9), "c0": Node(score=99)})
        clock = [0.0]
        original = game.evaluate_board

        def delayed_last_leaf(board, weights):
            if board[0][0] == "c0":
                clock[0] = 2.0
            return original(board, weights)

        game.evaluate_board = delayed_last_leaf
        with patch.dict(sys.modules, teammate_modules(game)):
            with patch("Team19_search.time.perf_counter", side_effect=lambda: clock[0]):
                move = search.choose_best_move(game.board("root"), True, 1, set())
        self.assertEqual([name for name, _ in game.evaluated], ["a0", "b0", "c0"])
        self.assertEqual(move, tree_move(0))

    def test_public_entry_returns_legal_fallback_when_deadline_is_already_expired(self):
        game = TreeGame({"root": Node(("child",)), "child": Node(score=3)})
        with patch.dict(sys.modules, teammate_modules(game)):
            with patch("Team19_search.time.perf_counter", return_value=10):
                move = search.choose_best_move(game.board("root"), True, 9, set())
        self.assertEqual(move, tree_move(0))
        self.assertEqual(game.evaluated, [])


class OfficialRules:
    """Test-only adapter; all explored moves and outcomes use official Tablut."""

    @staticmethod
    def game(board):
        from Tablut import Tablut
        game = Tablut()
        game.board = [row[:] for row in board]
        return game

    @staticmethod
    def get_legal_moves(board, is_attacker):
        own = {"A"} if is_attacker else {"D", "K"}
        moves = []
        for row in range(9):
            for col in range(9):
                if board[row][col] not in own:
                    continue
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    r, c = row + dr, col + dc
                    while 0 <= r < 9 and 0 <= c < 9 and board[r][c] in (".", "X"):
                        if board[r][c] == ".":
                            moves.append([[row, col], [r, c]])
                        r, c = r + dr, c + dc
        return moves

    def apply_move(self, board, move, is_attacker):
        game = self.game(board)
        if not game.make_move(is_attacker, move):
            raise AssertionError(f"Test adapter generated an illegal move: {move}")
        return game.board

    def check_winner(self, board, is_attacker_next, has_legal_moves):
        game = self.game(board)
        if game.check_if_game_over(is_attacker_next):
            return game.winner or "DRAW"
        assert has_legal_moves
        return None

    def compute_hash(self, board, is_attacker):
        return self.game(board).compute_zobrist_hash(is_attacker)

    def functions(self):
        return search.SearchFunctions(self.get_legal_moves, self.apply_move,
                                      self.check_winner, lambda board, weights: 0.0,
                                      self.compute_hash)


class OfficialTacticalTests(unittest.TestCase):
    @staticmethod
    def board(pieces):
        board = [["."] * 9 for _ in range(9)]
        board[4][4] = "X"
        for (row, col), piece in pieces.items():
            board[row][col] = piece
        return board

    def test_attacker_finds_one_move_king_capture(self):
        board = self.board({(2, 4): "K", (2, 3): "A", (0, 5): "A"})
        original = deepcopy(board)
        rules = OfficialRules()
        result = search.search_fixed_depth(board, True, 1, functions=rules.functions())
        self.assertEqual((result.move, result.score), ([[0, 5], [2, 5]], 100_000.0))
        child = rules.apply_move(board, result.move, True)
        self.assertEqual(rules.check_winner(child, False, True), "A")
        self.assertEqual(board, original)

    def test_defender_finds_one_move_king_escape(self):
        board = self.board({(1, 2): "K", (6, 6): "A", (7, 7): "A"})
        rules = OfficialRules()
        result = search.search_fixed_depth(board, False, 1, functions=rules.functions())
        self.assertEqual(result.score, -100_000.0)
        child = rules.apply_move(board, result.move, False)
        self.assertEqual(rules.check_winner(child, True, True), "D")

    def test_two_plies_block_an_opponents_immediate_king_escape(self):
        board = self.board({(1, 4): "K", (1, 3): "D", (1, 5): "D", (2, 4): "D",
                            (0, 1): "A", (7, 7): "A"})
        rules = OfficialRules()
        shallow = search.search_fixed_depth(board, True, 1, functions=rules.functions())
        result = search.search_fixed_depth(board, True, 2, functions=rules.functions())
        self.assertNotEqual(shallow.move, [[0, 1], [0, 4]])
        self.assertEqual(result.move, [[0, 1], [0, 4]])
        self.assertEqual(result.score, 0.0)
        child = rules.apply_move(board, result.move, True)
        for move in rules.get_legal_moves(child, False):
            reply = rules.apply_move(child, move, False)
            self.assertNotEqual(rules.check_winner(reply, True, True), "D")


if __name__ == "__main__":
    unittest.main()
