# Computational Intelligence Assignment - Group 19

JC4004 Tablut AI 小组作业。成员 2（kaaxi）负责 `Team19_search.py` 中的博弈搜索模块，成员 4 负责 `Team19.py` 中的 `Player`、时间预算与兜底逻辑。

## 网页人机对弈

在浏览器里和 Team19 下棋，查看每手的搜索深度、用时和候选步，并保存复盘记录。以下命令从仓库根目录运行。

### 准备 Python 环境

使用 **Python 3.12**，并从 `requirements.txt` 安装课程依赖。下面的 `tablut` 是示例环境名，可以换成自己的名字。已有 Python 3.12 环境时，直接激活它并检查依赖即可。

```powershell
conda create -n tablut python=3.12 pip
conda activate tablut
python --version
python -m pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cu121
python -m pip check
```

课程依赖清单中的 PyTorch 固定为 CUDA 12.1 版本，安装时需要对应平台的轮子。网页工具本身只用 Python 3.12 标准库，单独运行网页对弈时，有 Python 3.12 即可启动。

### 启动并下棋

```powershell
python tools/play_web.py --open
```

浏览器会打开 [本地对弈室](http://127.0.0.1:8019/)。首次打开默认你执守方，Team19 先走，AI 的整局预算是 60 秒。保持终端运行，结束后在终端按 `Ctrl+C` 停止服务。

- 点击 **新对局** 选择攻方或守方，也可以切换到 10 秒预算。
- 点击自己的棋子，再点绿色落点完成走棋。**悔棋** 会恢复到你上一次落子前，包括棋盘、历史和用时。
- 在 **AI 分析** 查看搜索轨迹、候选步、七项局面估值和棋谱。点击候选步可以预览它在落子前的棋盘上的起点和终点，再点 **返回实战** 继续。
- 终局会显示胜负、积分和判定原因。局面重复时，棋谱会标记该局面首次出现和再次出现的手数。

### 复盘日志与存档

- 网页每局的 JSON 复盘日志自动写入 `tools/game_logs/`，每手落子后更新。日志包含棋谱、逐手棋盘、吃子、AI 用时和各手的搜索、候选与估值分析。点击 **导出复盘** 可下载当前记录，终局后也能导出。
- **存档** 将进行中的局面写入 `tools/saved_positions/`。用 **读档** 选择它，可以恢复棋盘、历史和预算，接着下棋。

## 搜索模块更新

- 实现 Minimax + Alpha-Beta 剪枝，进攻方最大化、防守方最小化。
- 对局入口从深度 1 开始迭代加深，超时返回最后一个完整深度的最佳走法；实验接口仍可指定固定深度。
- 支持终局评分、真实历史和搜索路径中的重复局面判和，以及超时后返回合法候选。
- 保留原棋盘、权重和真实对局历史，返回标准走法 `[[r1, c1], [r2, c2]]`。

从第 2 层起，根节点先试上一层选中的走法。其余候选和内部节点优先尝试国王逃脱或被吃的走法，再按吃子数、国王向最近边缘缩短的格数排序，同优先级沿用引擎顺序。搜索从本步剩余时间中留出 10% 用于返回，最多留 5 毫秒。

## Player 模块更新（成员 4）

`Team19.py` 提供裁判调用的 `Player.play_attacker(board)` 和 `Player.play_defender(board)`。自写的对战脚本可以在复用实例时调用 `Player.reset_game()`。

- **时间预算**：每局从 `Tablut.TIME_BUDGET` 读取预算。按剩余时间和预计剩余手数分配本步搜索份额，搜索最多使用可用时间的 20%，另留 0.05 秒用于返回。份额低于 0.02 秒时直接返回合法步，跳过搜索和推演。
- **真实历史**：开局记录初始盘，之后按下一步行棋方记录走前、走后的哈希，与裁判的 `past_positions` 口径一致。守方遇到类似开局的盘面时，先检查上一盘面能否通过攻方一步走到。若裁判只传棋盘，有些换局无法和普通走棋区分。批量对战应每局新建 `Player` 或显式调用 `reset_game()`。
- **兜底链**：独立按裁判规则生成合法候选，用它校验搜索结果。搜索失败后，在本步截止时间内可以尝试一步制胜；预算不足时直接返回预先选好的合法步。
- **依赖缺失可运行**：规则引擎、评估、搜索任一模块 import 失败都不会中断对局，只是棋力下降。权重按 `Team19_weights.WEIGHTS` → `Team19_eval.DEFAULT_WEIGHTS` → 交由评估模块自己的默认值 的顺序加载。

## 谁需要接入

| 成员 | 与搜索模块的关系 |
| --- | --- |
| 成员 1：规则引擎 | 在 `Team19_engine.py` 提供 `get_legal_moves`、`apply_move`、`check_winner`、`compute_hash`，供搜索调用。移动应返回新棋盘，哈希须包含行棋方。 |
| 成员 3：评估函数 | 在 `Team19_eval.py` 提供 `evaluate_board(board, weights=None)`。正分利进攻方、负分利防守方；非终局估值应在正负 100000 之间。 |
| 成员 4：Player 与时间管理（已交付） | `Team19.py` 调用 `choose_best_move`，负责提供本步截止时间和真实历史，再把返回走法交给官方框架；成员 1、3 的模块缺失时仍可跑完整局。 |
| 成员 5：实验与离线调参（待交付） | 可调用 `search_fixed_depth`，固定搜索深度并传入不同权重；通过返回分数、访问节点数和剪枝次数比较实验结果。 |

### 成员 4 的调用入口

```python
from Team19_search import choose_best_move

move = choose_best_move(board, is_attacker, deadline, game_history, weights=None)
```

- `is_attacker=True` 为进攻方，`False` 为防守方。
- `deadline` 是 `time.perf_counter()` 的绝对时间戳，由成员 4 按本局剩余总时间分配，并预留返回开销。
- `game_history` 是包含行棋方的真实状态哈希集合；根局面可以已经记录其中。
- 输入应为未终局且有合法走法的棋盘；终局或无合法走法时抛出 `ValueError`。深度 1 未完成时返回第一个合法走法；搜索还会在分数已不依赖估值或达到 64 层保护上限时停止。

`Team19.py` 使用本步开始时的 `time.perf_counter()` 加上本步份额作为 `deadline`，并传入真实历史的副本和构造时加载的权重（无可用权重时为 `None`）。返回值经合法走法校验后交给裁判。

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

固定深度默认按引擎顺序搜索。做排序对照时，在同一局面、深度、历史和权重下额外传入 `tactical_ordering=True`。两次的根节点评分应相同，同分走法可能不同。

## 验证

使用 Python 3.12，在仓库根目录运行：

```powershell
python -m unittest discover -s tests -v
```

测试覆盖 160 组随机树与穷举 Minimax 的对照、官方裁判下的一步捕王/逃生及阻止对手逃生、迭代加深的超时回退和重复状态处理。剪枝示例在结果不变时，将访问节点从 15 个降为 11 个。

`tests/test_player.py` 用官方裁判验证守方的开局误判、跨局重置、搜索结果的合法性、低预算兜底和缺少队友模块时的完整对局。正式估值接入后仍需做 10 秒与 60 秒两档的批量验收。

测试仅使用标准库和仓库内的官方框架，可在正式队友模块接入前运行。课程依赖清单见 `requirements.txt`。

## 本地跑一局

官方 `Tablut.py` 的 `__main__` 里两个席位都写死了 `Team00`，且属于课程原始文件，不建议改动。本地自测时用一段脚本直接构造裁判即可，`Team19.py` 与 `Tablut.py` 放在同一目录：

```python
import Tablut
import Team19

game = Tablut.Tablut()
game.play(Team19.Player(), Team19.Player())
```

若要观察被缩短的预算（课程测试时的情形），在脚本里把 `Tablut.TIME_BUDGET` 改小即可，`Team19.py` 每次开局都会重新读取。

缺少正式搜索依赖时，双方会使用兜底走法。对局可以跑通，棋力需在各模块接入后评估。

## 分支与使用

- `kaaxi`：成员 2（kaaxi）的搜索模块开发分支。
- `Jason`：仓库原有开发分支。
- `main`：约定用于最终集成的分支。

```bash
git clone --branch kaaxi https://github.com/SCNU-ABD-23CS/Computational-Intelligence-Assignment.git
cd Computational-Intelligence-Assignment
```
