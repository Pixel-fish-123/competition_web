"""玩法插件基类（todo 12）：对局玩法插件的统一契约。

每个具体玩法（如 triangle_occupy，todo 13）通过继承
:class:`GameplayPlugin` 实现五个抽象方法，并注册进插件注册表
（app.plugins.registry）。后端通过 ``/api/gameplay/<name>/*`` 路由统一
调用插件方法，与具体玩法解耦。

约定：
- 所有方法收到的是服务端持久化的对局状态 ``state``（dict），方法返回
  新状态，由路由层负责存储；方法自身不得修改传入的 ``state``。
- 非法输入统一抛 :class:`ValueError`，路由层会将其转换为 HTTP 400。
- ``session_id`` 由路由层分配并透传，插件不应自行生成或依赖其格式。
"""

from abc import ABC, abstractmethod


class GameplayPlugin(ABC):
    """对局玩法插件抽象基类。

    属性:
        name: 插件唯一名称（注册表键，也是路由前缀的一部分）。
        version: 插件版本号（语义化版本，如 "1.0.0"）。
    """

    name: str
    version: str

    @abstractmethod
    def create_session(self, match_id: int, config: dict) -> dict:
        """创建一局对局会话，返回初始状态 dict。

        参数:
            match_id: 比赛对局 id（由比赛/对局模型分配）。
            config: 玩法配置（歌曲库、时长、难度等），由比赛配置传入。
        返回:
            初始会话状态 dict（后续透传给 get_state / submit_result 等）。
        异常:
            ValueError: 配置缺失或非法（如缺少必须字段、值越界）。
        """

    @abstractmethod
    def get_state(self, session_id: int, state: dict) -> dict:
        """返回当前会话状态，用于广播/客户端轮询。

        默认可原样返回存储的 ``state``；需要时（如把内部字段裁剪为
        客户端可见的公开视图）可在此加工。不得修改传入的 ``state``。
        """

    @abstractmethod
    def submit_result(
        self, session_id: int, state: dict, participant_id: int, payload: dict
    ) -> dict:
        """应用一次玩家/裁判操作，返回更新后的状态 dict。

        参数:
            participant_id: 操作者（选手或裁判）用户 id。
            payload: 操作内容（如落子坐标、得分提交）。
        返回:
            更新后的会话状态 dict。
        异常:
            ValueError: 操作非法（非本局参与者、状态机不允许等）。
        """

    @abstractmethod
    def validate_result(
        self, session_id: int, state: dict, participant_id: int, payload: dict
    ) -> bool:
        """操作合法性校验：身份 / 时间窗 / 频率 / 值域。

        注意（Metis E7）：仅做值域等结构性校验，不校验"得分真实性"
        （得分是否与谱面/规则一致不属于本层职责）。
        """

    @abstractmethod
    def end_session(self, session_id: int, state: dict) -> dict:
        """结束对局，返回最终结果 dict。

        返回 dict 必须包含键：winner（participant_id 或 None）、
        is_draw（bool）、score_a、score_b。
        """
