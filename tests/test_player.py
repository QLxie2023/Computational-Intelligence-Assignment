"""Player regressions exercised against the course referee."""

from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import Tablut
import Team19


def referee_move(board, move, is_attacker):
    referee = Tablut.Tablut()
    referee.board = [row[:] for row in board]
    if not referee.make_move(is_attacker, move):
        raise ValueError("Illegal test move")
    return referee.board


def referee_hash(board, is_attacker):
    referee = Tablut.Tablut()
    referee.board = board
    return referee.compute_zobrist_hash(is_attacker)


class PlayerTests(unittest.TestCase):
    def setUp(self):
        self.referee = Tablut.Tablut()
        self.referee.past_positions = [self.referee.compute_zobrist_hash(True)]
        self.enterContext(patch.object(Tablut, "TIME_BUDGET", 10.0))
        self.clock = SimpleNamespace(now=0.0)
        self.enterContext(patch.object(Team19, "time", SimpleNamespace(perf_counter=lambda: self.clock.now)))
        self.player = Team19.Player()
        self.player._apply_move = referee_move
        self.player._compute_hash = referee_hash
        self.player._check_winner = None

    def apply_nonterminal(self, is_attacker, move):
        self.assertTrue(self.referee.make_move(is_attacker, move))
        self.assertFalse(self.referee.check_if_game_over(not is_attacker))

    def test_opening_like_defender_turn_preserves_budget_and_history(self):
        replies = iter(([[2, 4], [2, 3]], [[2, 3], [2, 4]], [[3, 4], [3, 3]]))
        histories = []

        def select(board, is_attacker, deadline, history, weights):
            self.assertFalse(is_attacker)
            histories.append(history)
            self.clock.now += 0.1
            self.assertLess(self.clock.now, deadline)
            return next(replies)

        self.player._choose_best_move = select
        for attacker_move in ([[0, 3], [0, 2]], [[0, 5], [0, 6]], [[0, 2], [0, 3]]):
            self.apply_nonterminal(True, attacker_move)
            reply = self.player.play_defender(self.referee.board)
            self.assertEqual(histories[-1], set(self.referee.past_positions))
            self.apply_nonterminal(False, reply)

        self.assertEqual(self.player.moves_played, 3)
        self.assertAlmostEqual(self.player.remaining, 9.7)

    def test_reused_defender_resets_for_a_new_standard_opening(self):
        for budget, attacker_move in ((10, [[0, 3], [0, 2]]), (60, [[0, 5], [0, 6]])):
            self.referee = Tablut.Tablut()
            self.referee.past_positions = [self.referee.compute_zobrist_hash(True)]
            self.apply_nonterminal(True, attacker_move)
            Tablut.TIME_BUDGET = budget

            def select(board, is_attacker, deadline, history, weights):
                self.assertEqual(history, set(self.referee.past_positions))
                self.clock.now += 0.1
                return [[2, 4], [2, 3]]

            self.player._choose_best_move = select
            reply = self.player.play_defender(self.referee.board)
            self.apply_nonterminal(False, reply)
            self.assertEqual(self.player.moves_played, 1)
            self.assertAlmostEqual(self.player.remaining, budget - 0.1)

    def test_explicit_reset_clears_state_and_reads_new_budget(self):
        self.player._choose_best_move = Mock(return_value=[[0, 3], [0, 2]])
        self.player.play_attacker(self.referee.board)
        self.assertTrue(self.player.history)
        Tablut.TIME_BUDGET = 60
        self.player.reset_game()
        self.assertEqual(self.player.moves_played, 0)
        self.assertEqual(self.player.remaining, 60)
        self.assertEqual(self.player.history, set())

    def test_invalid_engine_move_is_never_used_as_fallback(self):
        illegal = [[0, 0], [0, 1]]
        engine = SimpleNamespace(
            get_legal_moves=lambda *_: [illegal], apply_move=referee_move,
            compute_hash=referee_hash, check_winner=lambda *_: None,
        )
        search = SimpleNamespace(choose_best_move=lambda *_: illegal)
        with patch.dict("sys.modules", {"Team19_engine": engine, "Team19_search": search}):
            player = Team19.Player()
        move = player.play_attacker(self.referee.board)
        self.assertTrue(self.referee.make_move(True, move))

    def test_malformed_or_failing_search_uses_a_legal_fallback(self):
        cases = (
            Mock(return_value=[[0.25, 5], [0, 6]]),
            Mock(return_value=[[0, 5], [0, 6], [4, 4]]),
            Mock(side_effect=RuntimeError("failed search")),
        )
        for search in cases:
            with self.subTest(search=search):
                player = Team19.Player()
                player._choose_best_move = search
                referee = Tablut.Tablut()
                move = player.play_attacker(referee.board)
                self.assertEqual(move, [[0, 3], [0, 0]])
                self.assertTrue(referee.make_move(True, move))
                if isinstance(search.side_effect, RuntimeError):
                    self.assertIs(player.last_error, search.side_effect)

    def test_low_budget_skips_search_and_tactical_fallback(self):
        self.apply_nonterminal(True, [[0, 3], [0, 2]])
        self.apply_nonterminal(False, [[2, 4], [2, 3]])
        self.player._last_board = self.referee.board
        self.player._last_is_attacker = True
        self.player.moves_played = 30
        self.player.remaining = 0.06
        self.player._choose_best_move = Mock()

        def slow_apply(board, move, is_attacker):
            self.clock.now += 0.002
            return referee_move(board, move, is_attacker)

        self.player._apply_move = Mock(side_effect=slow_apply)
        self.player._check_winner = Mock(return_value=None)
        self.player._compute_hash = Mock(side_effect=referee_hash)
        move = self.player.play_attacker(self.referee.board)
        self.player._choose_best_move.assert_not_called()
        self.player._check_winner.assert_not_called()
        self.player._apply_move.assert_not_called()
        self.player._compute_hash.assert_not_called()
        self.assertLess(self.clock.now, 0.06)
        self.assertTrue(self.referee.make_move(True, move))

    def test_tactical_fallback_stops_at_the_search_deadline(self):
        self.player._choose_best_move = Mock(side_effect=RuntimeError("failed search"))

        def slow_apply(board, move, is_attacker):
            self.clock.now += 0.1
            return referee_move(board, move, is_attacker)

        self.player._apply_move = Mock(side_effect=slow_apply)
        self.player._check_winner = Mock(return_value=None)
        move = self.player.play_attacker(self.referee.board)
        self.assertEqual(self.player._check_winner.call_count, 1)
        self.assertEqual(self.player._apply_move.call_count, 3)
        self.assertTrue(self.referee.make_move(True, move))

    def test_without_teammate_modules_finishes_a_game(self):
        output = StringIO()
        missing = {"Team19_engine": None, "Team19_eval": None, "Team19_search": None}
        with patch.dict("sys.modules", missing), redirect_stdout(output):
            self.referee.play(Team19.Player(), Team19.Player())
        result = output.getvalue()
        self.assertIn("Game over", result)
        for error in ("Illegal move", "exceeded time", "Exception caught"):
            self.assertNotIn(error, result)


if __name__ == "__main__":
    unittest.main()
