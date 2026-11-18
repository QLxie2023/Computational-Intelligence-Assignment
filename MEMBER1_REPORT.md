# 成员 1 负责的报告段落（草稿）

对应任务卡：Section 1 Introduction（约 200 词）+ Section 3 Implementation details 中
关于状态表示、Zobrist 哈希与规则引擎设计的约 100 词。文末附上可直接引用的验证数据，
供 Section 4 Conclusions 使用。

---

## Section 1. Introduction (about 200 words)

Tablut is an asymmetric two-player board game played on a 9x9 grid, with 81 squares
and an initial army of 16 attackers, 8 defenders and one king. The attackers win by
capturing the king; the defenders win by escorting the king to any edge square, or
by surviving until fewer than two attackers remain. Because the two sides have
different goals and different material, the game is deliberately unbalanced, so
identical positions must never be scored from a single fixed point of view.

The game is computationally awkward for several reasons. Pieces slide any number of
empty squares along a row or column, so the number of legal moves is typically well
above a hundred, and the branching factor stays large deep into the tree. The rule
set is also unusual: the central castle may be crossed but never occupied, captures
are resolved only around the piece that has just moved, the king must be surrounded
on all four sides while in or beside the castle but only on two sides elsewhere, and
any repetition of a position ends the game in an immediate draw. Under a hard budget
of 60 seconds per player per game, a bot can therefore only search a shallow tree, and
every mistake in move generation or terminal detection is punished at once. This
report describes a Group 19 engine that removes that risk by reproducing the official
referee's behaviour exactly, and an Alpha-Beta search built on top of it.

## Section 3 excerpt. State representation and rule engine (about 100 words)

**State representation.** A position is a 9x9 list of characters (`A`, `D`, `K`, `.`
and `X` for the vacated castle) together with the side to move. `Team19_engine.py`
exposes four stateless functions: `compute_hash`, `get_legal_moves`, `apply_move`
and `check_winner`. Hashing follows the mandated Zobrist scheme with seed 42, drawing
one 64-bit key per (square, piece, side) triple in the referee's exact order and
mixing in the side to move, so a repeated board with a different player to move hashes
differently. `apply_move` copies rows with `[row[:] for row in board]` rather than
`copy.deepcopy`, plays the move in the copy, resolves all captures of the arriving
piece in place and returns a board that shares no rows with its input. Terminal states
are evaluated in the referee's order: king on an edge, missing king, fewer than two
attackers, then no legal moves, which yields the draw marker.

---

## 验证数据（可直接写进 Section 4 / 测试部分）

| 项目 | 结果 |
| --- | --- |
| 特殊规则单元测试 | 31 个用例全部通过（4 面围王、王邻堡 3 面围捕、空城堡夹吃、堡旁卫兵特殊被吃、一步双吃、主动移入敌阵不被反吃、仅剩 1 攻方判守方胜、无合法走法判和等） |
| 与官方 `Tablut.py` 随机对拍 | 30 000 步 / 287 局零差异（逐步比对棋盘、双方哈希、胜负与和棋判定） |
| 合法走法集合比对 | 抽 3 个局面 × 2 个行棋方，穷举 81×81 组坐标，与官方 `make_move` 判定完全一致 |
| `apply_move` 吞吐 | 约 48.8 万次/秒（约 2.05 µs/次，单核，含合法性校验） |
| `get_legal_moves` 吞吐 | 约 3.9 万次/秒 |
| `compute_hash` 吞吐 | 约 15.7 万次/秒 |
| 与 `Team19_search.py` 联调 | 固定深度 2 搜索返回合法走法；迭代加深自对弈 50 步全部为官方裁判接受的合法走法 |

测试命令（仓库根目录，需官方 `Tablut.py` 与 `requirements.txt` 一致的环境）：

```powershell
python -m unittest discover -s tests -t . -v
```

> 说明：上表性能为 Python 3.13、单核、本机实测值，报告中引用时可以注明运行环境。
> 若老师要求 Section 3 更短，可只保留 "State representation." 一段并把哈希细节降到一句。
