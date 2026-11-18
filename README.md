# Computational Intelligence Assignment - Group 19

JC4004 Tablut AI 小组作业。9x9 非对称棋：进攻方 16 枚 `A` 围捕国王，防守方 8 枚 `D` 与 1 枚 `K` 护送国王到任意边缘格；每方每局 60 秒，局面重复立即判和。

## 规则与状态引擎（成员 1）

`Team19_engine.py` 提供四个无状态函数，名字与 `docs/INTERFACES.md` 逐字一致：

| 函数 | 返回值 | 说明 |
| --- | --- | --- |
| `compute_hash(board, is_attacker)` | `int` | Zobrist 哈希（种子 42），含行棋方；空城堡 `X` 不参与 |
| `get_legal_moves(board, is_attacker)` | `[[[r1, c1], [r2, c2]], …]` | 行优先、上左下右；可穿过 `X`，只能停在 `.` |
| `apply_move(board, move, is_attacker)` | 新棋盘 | 浅拷贝结算，不修改入参；非法走法抛 `ValueError` |
| `check_winner(board, is_attacker, has_legal_moves=True)` | `"A"` / `"D"` / `"DRAW"` / `None` | 判胜顺序与官方裁判一致 |

### 用法

```python
from Team19_engine import compute_hash, get_legal_moves, apply_move, check_winner

state_hash = compute_hash(board, is_attacker)               # 记录历史、判重复局面
moves = get_legal_moves(board, is_attacker)                 # 当前一方的全部合法走法
next_board = apply_move(board, moves[0], is_attacker)       # 推进一步局面
winner = check_winner(next_board, not is_attacker, has_legal_moves=True)
```

`board` 是 9×9 字符矩阵：`A` 进攻方、`D` 防守方、`K` 国王、`.` 空格、`X` 已空出的城堡。`is_attacker=True` 表示轮到进攻方。除入参外不保留任何内部状态，可重复、并行调用。

### 与官方裁判一致的规则

- **走子**：横竖滑行，可穿过空城堡但不能停留；路径上只允许 `.` 与 `X`。
- **吃子**：只结算刚落子的棋子四邻；攻方吃 `D` 需 `A` 或 `X` 支撑，守方与国王吃 `A` 需 `D`、`K` 或 `X` 支撑。
- **国王**：在城堡及紧邻核心区需四面被围，离开后两面夹击即可。
- **判胜**：国王在边缘 → `D`；国王消失 → `A`；进攻方少于 2 枚 → `D`；无合法走法 → `DRAW`。
- **棋盘**：`apply_move` 返回的棋盘与入参不共享任何行，复制用 `[row[:] for row in board]` 而非 `copy.deepcopy`。

## 其他成员如何调用

| 成员 | 调用方式 |
| --- | --- |
| 成员 2：搜索 | 以 `SearchFunctions(get_legal_moves, apply_move, check_winner, evaluate_board, compute_hash)` 注入回调 |
| 成员 3：评估 | 提供 `evaluate_board(board, weights=None)`，正分利进攻方、负分利防守方 |
| 成员 4：Player | 调用 `choose_best_move(board, is_attacker, deadline, game_history, weights=None)` |
| 成员 5：实验 | 调用 `search_fixed_depth(board, is_attacker, depth, functions, weights, game_history)` |

```python
from Team19_search import choose_best_move

move = choose_best_move(board, is_attacker, deadline, game_history)
```

`deadline` 为 `time.perf_counter()` 的绝对时间戳；`game_history` 是含行棋方的哈希集合；终局或无合法走法时抛 `ValueError`。

## 测试

```powershell
python -m unittest discover -s tests -t .
```

40 个用例（引擎 35 + 接口契约 5）。与官方 `Tablut.py` 对拍 5 000 步零差异，独立脚本跑到 30 000 步 / 287 局仍零差异；`apply_move` 约 48.8 万次/秒，`get_legal_moves` 约 3.9 万次/秒。详见 `MEMBER1_REPORT.md`。

## 分支

`main` 最终集成 · `Jason` 成员 1 引擎（本分支）· `kaaxi` 成员 2 搜索
