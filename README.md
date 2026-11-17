# Computational Intelligence Assignment - Group 19

JC4004 Tablut AI 小组作业。成员 2（kaaxi）负责 `Team19_search.py` 中的博弈搜索模块。

## 搜索模块更新

- 实现固定深度 Minimax + Alpha-Beta 剪枝，进攻方最大化、防守方最小化。
- 对局入口默认搜索 2 层（一方走一步、对方回应一步）；实验接口可指定深度。
- 支持终局评分、真实历史和搜索路径中的重复局面判和，以及超时后返回合法候选。
- 保留原棋盘、权重和真实对局历史，返回标准走法 `[[r1, c1], [r2, c2]]`。

当前是固定深度版本，尚未加入迭代加深和走法排序。正式对局入口依赖成员 1、3 提供的模块。

## 谁需要接入

| 成员 | 与搜索模块的关系 |
| --- | --- |
| 成员 1：规则引擎 | 在 `Team19_engine.py` 提供 `get_legal_moves`、`apply_move`、`check_winner`、`compute_hash`，供搜索调用。移动应返回新棋盘，哈希须包含行棋方。 |
| 成员 3：评估函数 | 在 `Team19_eval.py` 提供 `evaluate_board(board, weights=None)`。正分利进攻方、负分利防守方；非终局估值应在正负 100000 之间。 |
| 成员 4：Player 与时间管理 | 在 `Team19.py` 中调用 `choose_best_move`，负责提供本步截止时间和真实历史，再把返回走法交给官方框架。 |
| 成员 5：实验与离线调参 | 可调用 `search_fixed_depth`，固定搜索深度并传入不同权重；通过返回分数、访问节点数和剪枝次数比较实验结果。 |

### 成员 4 的调用入口

```python
from Team19_search import choose_best_move

move = choose_best_move(board, is_attacker, deadline, game_history, weights=None)
```

- `is_attacker=True` 为进攻方，`False` 为防守方。
- `deadline` 是 `time.perf_counter()` 的绝对时间戳，由成员 4 按本局剩余总时间分配，并预留返回开销。
- `game_history` 是包含行棋方的真实状态哈希集合；根局面可以已经记录其中。
- 输入应为未终局且有合法走法的棋盘；终局或无合法走法时抛出 `ValueError`。超时会丢弃本层的部分结果，返回预存的合法候选。

### 成员 5 的实验接口

```python
from Team19_search import SearchFunctions, search_fixed_depth

callbacks = SearchFunctions(
    get_legal_moves, apply_move, check_winner, evaluate_board, compute_hash
)
result = search_fixed_depth(
    board, is_attacker, depth=2, functions=callbacks,
    weights=weights, game_history=game_history,
)
```

回调函数由规则引擎和评估模块提供。`result` 包含 `move`、`score`、`nodes_visited`、`cutoffs`；如传入 `deadline` 并超时，该实验接口抛出 `SearchTimeout`。深度为 0 或根局面已终局时，`move` 为 `None`。

## 验证

使用 Python 3.12，在仓库根目录运行：

```powershell
python -m unittest discover -s tests -v
```

28 项测试已通过：包括 160 组随机树与穷举 Minimax 对照、官方裁判下的一步捕王/逃生及阻止对手逃生、超时和重复状态处理。剪枝示例在结果不变时，将访问节点从 15 个降为 11 个。

测试仅使用标准库和仓库内的官方框架，可在正式队友模块接入前运行。课程依赖清单见 `requirements.txt`。

## 分支与使用

- `kaaxi`：成员 2（kaaxi）的搜索模块开发分支。
- `Jason`：仓库原有开发分支。
- `main`：约定用于最终集成的分支。

```bash
git clone --branch kaaxi https://github.com/QLxie2023/Computational-Intelligence-Assignment.git
cd Computational-Intelligence-Assignment
```
