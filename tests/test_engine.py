"""Tests for the Group 19 rule and state engine (member 1).

Run from the repository root with the official framework in place::

    python -m unittest discover -s tests -v

The boundary cases required by the brief are listed first, followed by a
differential suite that compares every result with the official ``Tablut.py``
referee.  Only the standard library is used.
"""

from __future__ import annotations

import contextlib
import io
import random
import unittest

from Team19_engine import (
    ATTACKER,
    CASTLE,
    CASTLE_COL,
    CASTLE_ROW,
    DEFENDER,
    DRAW,
    EMPTY,
    KING,
    SIZE,
    WIN_ATTACKER,
    WIN_DEFENDER,
    apply_move,
    check_winner,
    compute_hash,
    get_legal_moves,
)

try:  # The official framework file is provided with the coursework.
    import Tablut
except ImportError:  # pragma: no cover - only when the file is missing
    Tablut = None

INITIAL_BOARD = [
    [".", ".", ".", "A", "A", "A", ".", ".", "."],
    [".", ".", ".", ".", "A", ".", ".", ".", "."],
    [".", ".", ".", ".", "D", ".", ".", ".", "."],
    ["A", ".", ".", ".", "D", ".", ".", ".", "A"],
    ["A", "A", "D", "D", "K", "D", "D", "A", "A"],
    ["A", ".", ".", ".", "D", ".", ".", ".", "A"],
    [".", ".", ".", ".", "D", ".", ".", ".", "."],
    [".", ".", ".", ".", "A", ".", ".", ".", "."],
    [".", ".", ".", "A", "A", "A", ".", ".", "."],
]


def empty_board() -> list[list[str]]:
    """Return a 9x9 board with every square empty."""
    return [[EMPTY for _ in range(SIZE)] for _ in range(SIZE)]


def board_with(pieces: dict[tuple[int, int], str]) -> list[list[str]]:
    """Build a board from ``{(row, col): cell}`` and fill in the castle.

    The castle holds ``X`` whenever no king is placed on it, as the official
    representation requires.
    """
    board = empty_board()
    for (row_index, col_index), cell in pieces.items():
        board[row_index][col_index] = cell
    if (CASTLE_ROW, CASTLE_COL) not in pieces:
        board[CASTLE_ROW][CASTLE_COL] = CASTLE
    return board


def snapshot(board: list[list[str]]) -> list[list[str]]:
    """Return a deep copy of a board for before/after comparisons."""
    return [row[:] for row in board]


# ---------------------------------------------------------------------------
# Move generation
# ---------------------------------------------------------------------------

class TestLegalMoves(unittest.TestCase):
    """``get_legal_moves`` must accept exactly the moves the referee accepts."""

    def test_castle_is_crossed_but_never_occupied(self):
        board = board_with(
            {
                (2, 2): KING,          # king already left the castle
                (4, 2): ATTACKER,
                (4, 4): CASTLE,
            }
        )
        moves = get_legal_moves(board, True)
        destinations = {tuple(move[1]) for move in moves if move[0] == [4, 2]}
        self.assertIn((4, 5), destinations, "the castle must be crossable")
        self.assertIn((4, 8), destinations)
        self.assertNotIn((4, 4), destinations, "no piece may stop on the castle")

    def test_a_piece_cannot_jump_over_a_blocker(self):
        board = board_with(
            {
                (2, 2): KING,
                (4, 0): ATTACKER,
                (4, 2): DEFENDER,
            }
        )
        row_destinations = {
            tuple(move[1])
            for move in get_legal_moves(board, True)
            if move[0] == [4, 0] and move[1][0] == 4
        }
        self.assertEqual(row_destinations, {(4, 1)})
        self.assertNotIn((4, 3), row_destinations)

    def test_both_sides_are_generated_for_defenders(self):
        board = board_with(
            {
                (4, 4): KING,
                (1, 1): DEFENDER,
            }
        )
        origins = {tuple(move[0]) for move in get_legal_moves(board, False)}
        self.assertEqual(origins, {(4, 4), (1, 1)})
        self.assertEqual(get_legal_moves(board, True), [], "no attackers on this board")

    def test_legal_moves_do_not_touch_the_board(self):
        before = snapshot(INITIAL_BOARD)
        moves = get_legal_moves(INITIAL_BOARD, True)
        self.assertEqual(INITIAL_BOARD, before)
        self.assertEqual(moves, get_legal_moves(INITIAL_BOARD, True))
        for move in moves:
            self.assertEqual(len(move), 2)
            self.assertEqual(len(move[0]), 2)

    def test_defenders_may_cross_the_empty_castle_but_not_stop_on_it(self):
        board = board_with({(2, 2): KING, (4, 2): DEFENDER, (4, 4): CASTLE})
        destinations = {
            tuple(move[1]) for move in get_legal_moves(board, False) if move[0] == [4, 2]
        }
        self.assertNotIn((4, 4), destinations)
        self.assertIn((4, 5), destinations)


# ---------------------------------------------------------------------------
# Captures, including every special case named in the brief
# ---------------------------------------------------------------------------

class TestCaptures(unittest.TestCase):

    def test_king_is_captured_when_the_castle_is_ringed_by_attackers(self):
        """Four attackers around the castle take the king in one move."""
        board = board_with(
            {
                (4, 4): KING,
                (3, 4): ATTACKER,
                (5, 4): ATTACKER,
                (4, 3): ATTACKER,
                (4, 7): ATTACKER,
            }
        )
        new_board = apply_move(board, [[4, 7], [4, 5]], True)
        self.assertEqual(new_board[4][4], EMPTY)
        self.assertEqual(check_winner(new_board, False, True), WIN_ATTACKER)
        self.assertEqual(board[4][4], KING, "the input board must stay untouched")

    def test_king_beside_the_castle_needs_three_attackers(self):
        """Beside the castle the empty castle acts as the fourth hostile square."""
        board = board_with(
            {
                (4, 3): KING,
                (4, 4): CASTLE,
                (3, 3): ATTACKER,
                (5, 3): ATTACKER,
                (4, 1): ATTACKER,
            }
        )
        new_board = apply_move(board, [[4, 1], [4, 2]], True)
        self.assertEqual(new_board[4][3], EMPTY, "king should be surrounded and taken")
        self.assertEqual(check_winner(new_board, False, True), WIN_ATTACKER)

    def test_king_beside_the_castle_survives_with_only_two_attackers(self):
        board = board_with(
            {
                (4, 3): KING,
                (4, 4): CASTLE,
                (3, 3): ATTACKER,
                (4, 1): ATTACKER,
                (0, 0): ATTACKER,
            }
        )
        new_board = apply_move(board, [[4, 1], [4, 2]], True)
        self.assertEqual(new_board[4][3], KING)

    def test_king_away_from_the_castle_is_taken_between_two_attackers(self):
        board = board_with(
            {
                (2, 3): KING,
                (2, 4): ATTACKER,
                (2, 1): ATTACKER,
            }
        )
        new_board = apply_move(board, [[2, 1], [2, 2]], True)
        self.assertEqual(new_board[2][3], EMPTY)
        self.assertEqual(check_winner(new_board, False, True), WIN_ATTACKER)

    def test_king_away_from_the_castle_survives_without_support(self):
        board = board_with({(2, 4): KING, (2, 2): ATTACKER, (7, 0): ATTACKER})
        new_board = apply_move(board, [[2, 2], [2, 3]], True)
        self.assertEqual(new_board[2][4], KING, "a single attacker cannot take the king")
        self.assertEqual(new_board[2][3], ATTACKER, "the moved attacker is not captured")

    def test_defender_is_taken_against_the_empty_castle(self):
        """The empty castle is hostile, so it completes an attacker sandwich."""
        board = board_with(
            {
                (2, 2): KING,
                (4, 4): CASTLE,
                (4, 3): DEFENDER,
                (4, 0): ATTACKER,
            }
        )
        new_board = apply_move(board, [[4, 0], [4, 2]], True)
        self.assertEqual(new_board[4][3], EMPTY, "castle must support the capture")

    def test_defender_is_safe_without_the_castle_support(self):
        board = board_with(
            {
                (2, 2): KING,
                (4, 3): DEFENDER,
                (4, 0): ATTACKER,
            }
        )
        board[4][4] = EMPTY
        new_board = apply_move(board, [[4, 0], [4, 2]], True)
        self.assertEqual(new_board[4][3], DEFENDER)

    def test_castle_counts_as_a_friend_for_defender_captures(self):
        board = board_with(
            {
                (2, 2): KING,
                (4, 4): CASTLE,
                (4, 5): ATTACKER,
                (4, 8): DEFENDER,
            }
        )
        new_board = apply_move(board, [[4, 8], [4, 6]], False)
        self.assertEqual(new_board[4][5], EMPTY)

    def test_defender_beside_the_castle_king_is_taken_by_three_attackers(self):
        """Three attackers around the castle let one attacker take the guard."""
        board = board_with(
            {
                (4, 4): KING,
                (3, 4): ATTACKER,
                (5, 4): ATTACKER,
                (4, 5): ATTACKER,
                (4, 3): DEFENDER,
                (4, 0): ATTACKER,
            }
        )
        new_board = apply_move(board, [[4, 0], [4, 2]], True)
        self.assertEqual(new_board[4][3], EMPTY, "the guard beside the king is taken")
        self.assertEqual(new_board[4][4], KING, "the king itself survives this move")

    def test_defender_beside_the_castle_king_is_safe_with_two_attackers(self):
        board = board_with(
            {
                (4, 4): KING,
                (3, 4): ATTACKER,
                (4, 5): ATTACKER,
                (4, 3): DEFENDER,
                (4, 0): ATTACKER,
            }
        )
        new_board = apply_move(board, [[4, 0], [4, 2]], True)
        self.assertEqual(new_board[4][3], DEFENDER, "two attackers are not enough")

    def test_one_move_can_capture_two_defenders(self):
        board = board_with(
            {
                (6, 6): KING,
                (2, 0): ATTACKER,
                (2, 4): ATTACKER,
                (2, 1): DEFENDER,
                (2, 3): DEFENDER,
                (0, 2): ATTACKER,
            }
        )
        new_board = apply_move(board, [[0, 2], [2, 2]], True)
        self.assertEqual(new_board[2][1], EMPTY)
        self.assertEqual(new_board[2][3], EMPTY)
        self.assertEqual(new_board[2][2], ATTACKER)

    def test_a_piece_moving_into_an_attackers_camp_is_not_captured(self):
        """Captures are evaluated around the mover only, never around it."""
        board = board_with(
            {
                (6, 6): KING,
                (2, 1): DEFENDER,
                (2, 3): DEFENDER,
                (0, 2): ATTACKER,
            }
        )
        new_board = apply_move(board, [[0, 2], [2, 2]], True)
        self.assertEqual(new_board[2][2], ATTACKER, "the mover cannot be taken on its turn")
        self.assertEqual(new_board[2][1], DEFENDER)
        self.assertEqual(new_board[2][3], DEFENDER)

    def test_king_leaving_the_castle_leaves_a_hostile_castle(self):
        board = board_with(
            {
                (4, 4): KING,
                (2, 4): ATTACKER,
                (3, 3): ATTACKER,
                (5, 3): ATTACKER,
            }
        )
        new_board = apply_move(board, [[4, 4], [4, 3]], False)
        self.assertEqual(new_board[4][4], CASTLE)
        self.assertEqual(new_board[4][3], KING)


# ---------------------------------------------------------------------------
# Terminal states and draw handling
# ---------------------------------------------------------------------------

class TestTerminalStates(unittest.TestCase):

    def test_king_on_an_edge_square_wins_for_the_defenders(self):
        board = board_with({(1, 4): KING, (6, 0): DEFENDER, (8, 8): ATTACKER})
        new_board = apply_move(board, [[1, 4], [0, 4]], False)
        self.assertEqual(check_winner(new_board, True, True), WIN_DEFENDER)

    def test_king_on_the_last_column_also_ends_the_game(self):
        board = board_with({(4, 7): KING, (8, 8): ATTACKER, (0, 0): DEFENDER})
        board[4][4] = EMPTY
        new_board = apply_move(board, [[4, 7], [4, 8]], False)
        self.assertEqual(check_winner(new_board, True, True), WIN_DEFENDER)

    def test_no_king_means_the_attackers_won(self):
        board = board_with({(4, 3): ATTACKER, (5, 4): ATTACKER})
        board[4][4] = EMPTY
        self.assertEqual(check_winner(board, False, True), WIN_ATTACKER)

    def test_one_remaining_attacker_loses_the_game(self):
        """The check comes after the capture resolution of the same move."""
        board = board_with(
            {
                (4, 4): KING,
                (2, 1): DEFENDER,
                (2, 5): DEFENDER,
                (2, 2): ATTACKER,
                (7, 4): ATTACKER,
            }
        )
        new_board = apply_move(board, [[2, 5], [2, 3]], False)
        self.assertEqual(new_board[2][2], EMPTY)
        self.assertEqual(check_winner(new_board, True, False), WIN_DEFENDER)
        self.assertEqual(check_winner(new_board, True, True), WIN_DEFENDER)

    def test_a_side_without_moves_draws(self):
        board = board_with(
            {
                (4, 4): KING,
                (0, 0): ATTACKER,
                (0, 1): DEFENDER,
                (1, 0): DEFENDER,
                (8, 8): ATTACKER,
                (8, 7): DEFENDER,
                (7, 8): DEFENDER,
            }
        )
        self.assertEqual(get_legal_moves(board, True), [])
        self.assertEqual(check_winner(board, True, False), DRAW)

    def test_the_default_flag_never_reports_a_draw(self):
        """A caller that has not checked for moves can only rule out wins."""
        board = board_with(
            {
                (4, 4): KING,
                (0, 0): ATTACKER,
                (0, 1): DEFENDER,
                (1, 0): DEFENDER,
                (8, 8): ATTACKER,
                (8, 7): DEFENDER,
                (7, 8): DEFENDER,
            }
        )
        self.assertIsNone(check_winner(board, True))

    def test_a_normal_position_is_not_terminal(self):
        self.assertIsNone(check_winner(INITIAL_BOARD, False, True))
        self.assertIsNone(check_winner(INITIAL_BOARD, True, True))


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

class TestHash(unittest.TestCase):

    def test_the_side_to_move_is_part_of_the_hash(self):
        self.assertNotEqual(
            compute_hash(INITIAL_BOARD, True), compute_hash(INITIAL_BOARD, False)
        )

    def test_the_hash_changes_with_the_board(self):
        moved = apply_move(INITIAL_BOARD, get_legal_moves(INITIAL_BOARD, True)[0], True)
        self.assertNotEqual(
            compute_hash(INITIAL_BOARD, False), compute_hash(moved, False)
        )

    def test_the_castle_marker_does_not_change_the_hash(self):
        board = board_with({(2, 2): KING})
        without_castle = snapshot(board)
        without_castle[CASTLE_ROW][CASTLE_COL] = EMPTY
        self.assertEqual(compute_hash(board, True), compute_hash(without_castle, True))

    def test_the_hash_is_stable_when_other_modules_reseed_random(self):
        expected = compute_hash(INITIAL_BOARD, True)
        random.seed(12345)
        random.getrandbits(64)
        self.assertEqual(expected, compute_hash(INITIAL_BOARD, True))


# ---------------------------------------------------------------------------
# Input validation and immutability of apply_move
# ---------------------------------------------------------------------------

class TestApplyMoveContract(unittest.TestCase):

    def test_apply_move_returns_an_independent_board(self):
        before = snapshot(INITIAL_BOARD)
        new_board = apply_move(INITIAL_BOARD, [[0, 3], [1, 3]], True)
        self.assertEqual(INITIAL_BOARD, before)
        self.assertNotEqual(id(INITIAL_BOARD), id(new_board))
        for original_row, new_row in zip(INITIAL_BOARD, new_board):
            self.assertNotEqual(id(original_row), id(new_row))

    def test_illegal_moves_raise_value_error(self):
        cases = [
            ([[0, 3], [1, 2]], "diagonal slide"),
            ([[4, 0], [4, 4]], "occupied destination"),
            ([[4, 2], [4, 3]], "defender moved by the attacking side"),
            ([[0, 0], [0, 1]], "empty origin"),
            ([[0, 3], [0, 3]], "zero length move"),
            ([[0, 3], [0, 10]], "off the board"),
            ([[0, 3]], "malformed move"),
            ([[0, 3], [0, 2], [0, 1]], "wrong number of coordinates"),
        ]
        for move, label in cases:
            with self.assertRaises(ValueError, msg=label):
                apply_move(INITIAL_BOARD, move, True)

    def test_a_blocked_path_raises_value_error(self):
        board = board_with({(2, 2): KING, (4, 0): ATTACKER, (4, 2): DEFENDER})
        with self.assertRaises(ValueError):
            apply_move(board, [[4, 0], [4, 3]], True)


# ---------------------------------------------------------------------------
# Differential tests against the official referee
# ---------------------------------------------------------------------------

@unittest.skipUnless(Tablut is not None, "official Tablut.py is not next to the tests")
class TestAgreementWithOfficialReferee(unittest.TestCase):
    """Every answer must match ``Tablut.py``, which adjudicates the tournament."""

    @staticmethod
    def _referee():
        game = Tablut.Tablut()
        game.past_positions = []
        game.winner = None
        return game

    def _official_outcome(self, game, board, is_attacker_next):
        game.board = snapshot(board)
        game.past_positions = []
        game.winner = None
        with contextlib.redirect_stdout(io.StringIO()):
            finished = game.check_if_game_over(is_attacker_next)
        if not finished:
            return None
        return game.winner if game.winner in (WIN_ATTACKER, WIN_DEFENDER) else DRAW

    def _our_outcome(self, board, is_attacker_next):
        moves = get_legal_moves(board, is_attacker_next)
        return check_winner(board, is_attacker_next, bool(moves))

    def test_hashes_match_the_official_function(self):
        rng = random.Random(11)
        game = self._referee()
        boards = [INITIAL_BOARD]
        for _ in range(20):
            board = empty_board()
            for row_index in range(SIZE):
                for col_index in range(SIZE):
                    board[row_index][col_index] = rng.choice(
                        [EMPTY, EMPTY, EMPTY, ATTACKER, DEFENDER, CASTLE]
                    )
            boards.append(board)
        for board in boards:
            for is_attacker in (True, False):
                game.board = snapshot(board)
                self.assertEqual(
                    compute_hash(board, is_attacker),
                    game.compute_zobrist_hash(is_attacker),
                )

    def test_legal_move_sets_match_the_official_referee(self):
        rng = random.Random(3)
        game = self._referee()
        boards = [INITIAL_BOARD]
        for _ in range(2):
            board = snapshot(INITIAL_BOARD)
            for _ in range(12):
                moves = get_legal_moves(board, True) or get_legal_moves(board, False)
                if not moves:
                    break
                board = apply_move(board, rng.choice(moves), True)
            boards.append(board)

        coordinates = [(row_index, col_index) for row_index in range(SIZE)
                       for col_index in range(SIZE)]
        for board in boards:
            for is_attacker in (True, False):
                ours = {
                    (move[0][0], move[0][1], move[1][0], move[1][1])
                    for move in get_legal_moves(board, is_attacker)
                }
                theirs = set()
                for r1, c1 in coordinates:
                    for r2, c2 in coordinates:
                        game.board = snapshot(board)
                        if game.make_move(is_attacker, [[r1, c1], [r2, c2]]):
                            theirs.add((r1, c1, r2, c2))
                self.assertEqual(ours, theirs, msg=f"legal move mismatch for {is_attacker}")

    def test_random_games_match_the_official_referee_for_5000_steps(self):
        """Random play: identical boards, hashes and verdicts at every step."""
        rng = random.Random(20261118)
        game = self._referee()
        board = snapshot(INITIAL_BOARD)
        is_attacker = True
        steps = 0
        games = 0
        verdicts = {}

        while steps < 5000:
            ours = self._our_outcome(board, is_attacker)
            theirs = self._official_outcome(game, board, is_attacker)
            self.assertEqual(ours, theirs, msg=f"verdict mismatch after {steps} steps")
            if ours is not None:
                verdicts[ours] = verdicts.get(ours, 0) + 1
                games += 1
                board = snapshot(INITIAL_BOARD)
                is_attacker = True
                continue

            before = snapshot(board)
            moves = get_legal_moves(board, is_attacker)
            self.assertTrue(moves)
            move = rng.choice(moves)

            game.board = snapshot(board)
            self.assertTrue(
                game.make_move(is_attacker, move),
                msg=f"engine produced an illegal move at step {steps}",
            )
            new_board = apply_move(board, move, is_attacker)
            self.assertEqual(new_board, game.board, msg=f"board mismatch at step {steps}")
            self.assertEqual(board, before, "get_legal_moves and apply_move must be pure")
            for side in (True, False):
                self.assertEqual(
                    compute_hash(new_board, side), game.compute_zobrist_hash(side)
                )

            board = new_board
            is_attacker = not is_attacker
            steps += 1

        self.assertGreater(games, 5, "random games should finish repeatedly")


if __name__ == "__main__":
    unittest.main()
