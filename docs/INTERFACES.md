# Group 19：搜索模块接口约定草案

这是第一步的协作草案。

## 1. 文件与职责

| 成员 | 文件 | 对搜索模块提供或调用的内容 |
| --- | --- | --- |
| 1 | `Team19_engine.py` | 状态哈希、合法走法、移动与吃子、终局判断 |
| 2（用户） | `Team19_search.py` | 根据棋盘、预算、历史及权重返回走法 |
| 3 | `Team19_eval.py` | 统一评分及默认权重 |
| 4 | `Team19.py` | 官方 `Player` 接口、时间分配、真实历史及兜底 |
| 5 | `offline_arena_ga.py` | 对战实验、基线与离线调参 |

当前只建立成员 2 的入口骨架，不创建其他成员的占位模块，以便后续直接接入其交付文件。

## 2. 共同数据约定

- `board`：9×9 的 `list[list[str]]`，元素为 `A`、`D`、`K`、`.`、`X`。
- `move`：恰好两个坐标对，形如 `[[r1, c1], [r2, c2]]`，索引从 0 开始；返回值使用列表。
- `is_attacker=True`：本次轮到进攻方；`False`：本次轮到防守方。
- 所有对外函数均不原地修改传入的棋盘。`apply_move` 返回独立的新棋盘，搜索不得改写 `game_history`。
- 正分始终利好进攻方，负分始终利好防守方；进攻方取最大值，防守方取最小值。
- 进攻方胜 `+100000.0`，防守方胜 `-100000.0`，平局 `0.0`。建议非终局估值严格处于两个胜负分数之间，避免普通估值超过必胜分数；此细节请成员 3 确认。

## 3. 成员 1 提供的规则接口

```python
# Team19_engine.py
def compute_hash(board: list[list[str]], is_attacker: bool) -> int: ...

def get_legal_moves(
    board: list[list[str]], is_attacker: bool
) -> list[list[list[int]]]: ...

def apply_move(
    board: list[list[str]], move: list[list[int]], is_attacker: bool
) -> list[list[str]]: ...

def check_winner(
    board: list[list[str]],
    is_attacker_next: bool,
    has_legal_moves: bool = True,
) -> str | None: ...
```

- `compute_hash`：包含棋盘及下一行棋方。分工方案要求复用官方 `ZOBRIST_SEED = 42` 的哈希逻辑；搜索与真实历史使用同一实现。
- `get_legal_moves`：返回当前方全部合法走法，无合法走法时为 `[]`。
- `apply_move`：输入合法走法，完成移动与吃子并返回新棋盘；不负责维护真实历史。
- `check_winner`：返回 `A`、`D`、`DRAW` 或 `None`。其中 `None` 表示未结束，`DRAW` 表示无合法走法导致的和棋。搜索已有走法列表时可传入 `bool(moves)`；默认参数 `True` 不能代替实际的无合法走法检查。
- 重复状态需要真实历史或搜索路径，因此由搜索和 `Player` 配合处理，不要求这个无历史参数的函数检查重复。
- 空城堡 `X` 可穿过但不能停留；具体吃子和胜负规则与官方框架对齐。

## 4. 成员 3 提供的评估接口

```python
# Team19_eval.py
DEFAULT_WEIGHTS: list[float]

def evaluate_board(
    board: list[list[str]], weights: list[float] | None = None
) -> float: ...
```

- `weights=None` 使用该模块的默认权重。
- 返回值始终使用进攻方正分的统一视角，不根据当前行棋方翻转符号。
- 搜索负责将已判定终局映射为胜负分数，评估函数主要处理非终局棋盘。

## 5. 成员 2 提供的搜索入口

```python
# Team19_search.py
def choose_best_move(
    board: list[list[str]],
    is_attacker: bool,
    deadline: float,
    game_history: set[int],
    weights: list[float] | None = None,
) -> list[list[int]]: ...
```

- 常规调用场景是尚未终局且至少存在一个合法走法的棋盘。
- `deadline` 是 `time.perf_counter()` 的绝对时间戳；不能传入“还剩几秒”，也不能使用 `time.time()` 生成这个时间戳。
- 成员 4 分配本步时间并预留返回开销；成员 2 在搜索中检查截止时间并及时停止。60 秒是官方每方每局的累计预算，不能直接作为每步预算。
- 计划实现从深度 1 开始的迭代加深 Alpha-Beta；只有一层完整搜索结束才更新对外保留的最优走法。
- 搜索一开始保存合法候选作为兜底，避免第一层未完成时没有结果。已经过期或不足以生成候选的预算无法保证在截止前完成返回，需与成员 4 一起验证边界行为。
- 无合法走法时没有符合返回格式的合法走法；这一入口的异常或返回策略尚未约定，见第 8 节。

## 6. 历史与重复状态

| 数据 | 维护者 | 含义 |
| --- | --- | --- |
| `game_history` | 成员 4 | 本局真实发生的状态哈希集合 |
| `search_path` | 成员 2 | 当前搜索递归分支的状态哈希集合 |

每个哈希都包含下一行棋方。子节点使用 `compute_hash(new_board, not is_attacker)`，不能沿用父节点的行棋方。

根局面可以已存在于 `game_history` 中；进入搜索时不能因此直接将根判和。根哈希加入当前搜索路径，推演完成一步后再检查新状态是否重复。递归回溯时移除当前路径记录，不能让其他分支被误判为重复。

按官方 `check_if_game_over` 的顺序，先处理国王逃脱/被捕及进攻者不足等胜负，再处理无合法走法和重复状态；重复判和不覆盖已经确定的胜负。

## 7. 成员 4 调用示意

下面是接口示意，依赖模块全部交付后才能执行，不是当前阶段的完整 `Player`：

```python
import time

from Team19_engine import compute_hash
from Team19_search import choose_best_move

# step_budget 由成员 4 根据每局剩余总时间计算，并预留返回开销。
deadline = time.perf_counter() + step_budget
game_history.add(compute_hash(board, is_attacker))
move = choose_best_move(board, is_attacker, deadline, game_history)
```

成员 4 对外仍使用 `Player.play_attacker(board)` 和 `Player.play_defender(board)`。`play_rebel` / `play_officer` 是说明中的遗留名称，不是实际框架调用的接口。

## 8. 成员 1、3、4 核对

>我负责 `Team19_search.py`。我已把现有分工里的接口整理为 `docs/INTERFACES.md`，请成员 1、3、4 核对。
>
> 成员 1：请确认 `Team19_engine.py` 提供 `compute_hash`、`get_legal_moves`、`apply_move`、`check_winner`；哈希包含下一行棋方，与官方固定种子的哈希一致；移动返回新棋盘；终局返回 `A` / `D` / `DRAW` / `None`。
>
> 成员 3：请确认 `evaluate_board(board, weights=None)` 返回进攻方正分的统一评分，`None` 使用默认权重；请确认普通估值不超过胜负分数范围。
>
> 成员 4：请按 `choose_best_move(board, is_attacker, deadline, game_history, weights=None)` 调用；`deadline` 使用 `time.perf_counter()` 的绝对时间，真实历史包含行棋方。我会在搜索中单独维护递归路径。
>
> 两个边界细节还需一起确认：无合法走法时这个搜索入口如何返回或抛出异常；根局面是否已加入 `game_history`（搜索会兼容根已在历史中的情况）。如果你们已开始实现且签名不同，请告知实际签名，我们先对齐再联调。
