"""Guard the engine against drifting away from docs/INTERFACES.md.

The Markdown specification is the contract the other four members integrate
against, so its function names, parameter names, defaults and return types are
checked here rather than trusted to memory.  If anyone renames a parameter or
adds a convenience function, this test fails before the search module does.
"""

from __future__ import annotations

import inspect
import unittest

import Team19_engine

# Transcribed from docs/INTERFACES.md, section "成员 1 提供的规则接口".
SPECIFICATION = {
    "compute_hash": {
        "parameters": ["board", "is_attacker"],
        "defaults": {},
        "returns": "int",
    },
    "get_legal_moves": {
        "parameters": ["board", "is_attacker"],
        "defaults": {},
        "returns": "list[list[list[int]]]",
    },
    "apply_move": {
        "parameters": ["board", "move", "is_attacker"],
        "defaults": {},
        "returns": "list[list[str]]",
    },
    "check_winner": {
        "parameters": ["board", "is_attacker_next", "has_legal_moves"],
        "defaults": {"has_legal_moves": True},
        "returns": "str | None",
    },
}


def normalize(text) -> str:
    """Compare annotations as text, ignoring quotes and spaces."""
    return str(text).replace(" ", "").replace("'", "").replace('"', "")


class TestInterfaceNames(unittest.TestCase):
    """Names and signatures must match the Markdown document exactly."""

    def test_every_documented_function_exists(self):
        for name in SPECIFICATION:
            self.assertTrue(
                hasattr(Team19_engine, name), f"{name} is missing from Team19_engine"
            )
            self.assertTrue(
                inspect.isfunction(getattr(Team19_engine, name)),
                f"{name} must be a plain function",
            )

    def test_no_undocumented_public_function_is_exported(self):
        exported = sorted(
            name
            for name, value in vars(Team19_engine).items()
            if inspect.isfunction(value) and not name.startswith("_")
        )
        self.assertEqual(exported, sorted(SPECIFICATION))

    def test_parameter_names_order_and_defaults(self):
        for name, spec in SPECIFICATION.items():
            signature = inspect.signature(getattr(Team19_engine, name))
            self.assertEqual(
                list(signature.parameters),
                spec["parameters"],
                f"{name} has different parameter names or order",
            )
            for parameter_name, parameter in signature.parameters.items():
                self.assertIs(
                    parameter.kind,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    f"{name}.{parameter_name} must be a normal positional parameter",
                )
                if parameter_name in spec["defaults"]:
                    self.assertEqual(
                        parameter.default,
                        spec["defaults"][parameter_name],
                        f"{name}.{parameter_name} has the wrong default",
                    )
                else:
                    self.assertIs(
                        parameter.default,
                        inspect.Parameter.empty,
                        f"{name}.{parameter_name} must not have a default",
                    )

    def test_parameter_and_return_annotations(self):
        for name, spec in SPECIFICATION.items():
            signature = inspect.signature(getattr(Team19_engine, name))
            annotations = {
                parameter_name: normalize(parameter.annotation)
                for parameter_name, parameter in signature.parameters.items()
            }
            self.assertTrue(
                all(annotations.values()), f"{name} must annotate every parameter"
            )
            self.assertEqual(
                normalize(signature.return_annotation),
                normalize(spec["returns"]),
                f"{name} must be annotated as returning {spec['returns']}",
            )

    def test_the_documented_calls_can_be_made_by_keyword(self):
        """The document shows named parameters, so keyword calls must work."""
        board = [
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
        is_attacker = True
        moves = Team19_engine.get_legal_moves(board=board, is_attacker=is_attacker)
        self.assertTrue(moves)
        move = moves[0]
        child = Team19_engine.apply_move(board=board, move=move, is_attacker=is_attacker)
        self.assertEqual(
            Team19_engine.check_winner(
                board=child, is_attacker_next=False, has_legal_moves=True
            ),
            None,
        )
        self.assertIsInstance(
            Team19_engine.compute_hash(board=board, is_attacker=is_attacker), int
        )


if __name__ == "__main__":
    unittest.main()
