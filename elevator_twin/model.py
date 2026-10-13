"""
电梯场域数字孪生 —— 多智能体社交距离与交流行为仿真（核心模型）

核心命题：
    高密度密闭微空间（电梯轿厢）中，"物理距离—社会距离(社交距离偏好)—交流行为"
    三者耦合。本模型基于 MESA 构建乘客多智能体，量化"交流行为对社交距离的调制作用"。

模型规则（每个仿真步，每个乘客依次执行）：
    1) 解除失效交流：若交流对象已远离(距离 > chat_range)，解除关系。
    2) 建立交流：若最近邻在交流范围内，且双方交流意愿之和达阈值，则结成"交流对"。
    3) 移动决策：
       - 交流中乘客：靠近交流对象(保持相邻) —— 交流行为压缩社交距离。
       - 未交流乘客：在空闲格中选"到最近邻距离"最大的位置 —— 社交距离最大化。
    4) 满载(无空闲格)时保持原位 —— 边界处理。

指标（DataCollector 记录）：
    avg_nearest_distance : 平均最近邻距离（格）
    min_nearest_distance : 全局最小最近邻距离（格）
    violation_rate       : 社交距离违规率（最近邻 < 自身舒适距离的乘客占比）
    chat_pairs           : 当前交流对数量
    chat_pair_distance   : 交流对平均距离（格）
"""
import math

import numpy as np
from mesa import Agent, Model
from mesa.datacollection import DataCollector
from mesa.space import MultiGrid
from mesa.time import RandomActivation


def euclid(a, b):
    """两个格坐标 (x, y) 之间的欧氏距离。"""
    return math.hypot(a[0] - b[0], a[1] - b[1])


class Passenger(Agent):
    """电梯乘客智能体。"""

    def __init__(self, unique_id, model, comfort_distance, chat_willingness):
        super().__init__(unique_id, model)
        self.comfort_distance = comfort_distance   # 最小舒适社交距离（格）
        self.chat_willingness = chat_willingness   # 交流意愿 [0, 1]
        self.in_chat = False                       # 是否处于交流中
        self.chat_partner = None                   # 交流对象 Passenger / None
        self.pos = None                            # 当前格坐标 (x, y)

    def step(self):
        # 1) 解除失效交流
        if self.in_chat and self.chat_partner is not None:
            if euclid(self.pos, self.chat_partner.pos) > self.model.chat_range:
                self._end_chat()

        # 2) 尝试建立交流
        if not self.in_chat:
            partner = self._find_chat_partner()
            if partner is not None:
                self._start_chat(partner)

        # 3) 移动决策
        if self.in_chat:
            self._move_toward_partner()
        else:
            self._move_to_maximize_distance()

    def _find_chat_partner(self):
        """返回最近邻（若满足交流条件），否则 None。"""
        best, best_d = None, float("inf")
        for other in self.model.schedule.agents:
            if other is self or other.in_chat or other.pos is None:
                continue
            d = euclid(self.pos, other.pos)
            if d < best_d:
                best, best_d = other, d
        if best is None or best_d > self.model.chat_range:
            return None
        if self.chat_willingness + best.chat_willingness >= self.model.chat_threshold:
            return best
        return None

    def _start_chat(self, other):
        self.in_chat = True
        self.chat_partner = other
        other.in_chat = True
        other.chat_partner = self

    def _end_chat(self):
        other = self.chat_partner
        if other is not None:
            other.in_chat = False
            other.chat_partner = None
        self.in_chat = False
        self.chat_partner = None

    def _move_toward_partner(self):
        partner = self.chat_partner
        if partner is None:
            return
        if euclid(self.pos, partner.pos) <= 1.5:
            return  # 已相邻（含对角），保持
        candidates = self.model.empty_cells_near(partner.pos, radius=2)
        if not candidates:
            return
        best = min(candidates, key=lambda c: euclid(c, partner.pos))
        if euclid(best, partner.pos) < euclid(self.pos, partner.pos):
            self.model.move(self, best)

    def _move_to_maximize_distance(self):
        cells = self.model.empty_cells()
        if not cells:
            return  # 满载，保持原位
        best, best_score = None, self._min_distance_at(self.pos)
        for cell in cells:
            s = self._min_distance_at(cell)
            if s > best_score:
                best, best_score = cell, s
        if best is not None:
            self.model.move(self, best)

    def _min_distance_at(self, cell):
        d = float("inf")
        for other in self.model.schedule.agents:
            if other is self or other.pos is None:
                continue
            d = min(d, euclid(cell, other.pos))
        return d


class ElevatorModel(Model):
    """电梯轿厢多智能体模型。"""

    def __init__(
        self,
        width=4,
        height=4,
        n_passengers=8,
        comfort_distance=1.5,
        chat_willingness_mean=0.5,
        chat_range=1.5,
        chat_threshold=1.0,
        seed=None,
    ):
        super().__init__(seed=seed)
        self.width = width
        self.height = height
        self.n_passengers = n_passengers
        self.comfort_distance = comfort_distance
        self.chat_range = chat_range
        self.chat_threshold = chat_threshold

        capacity = width * height
        if n_passengers < 0:
            raise ValueError(f"乘客数不能为负：{n_passengers}")
        if n_passengers > capacity:
            raise ValueError(f"乘客数 {n_passengers} 超过轿厢容量 {capacity}")

        self.grid = MultiGrid(width, height, torus=False)
        self.schedule = RandomActivation(self)

        for i in range(n_passengers):
            chat = float(np.clip(self.random.gauss(chat_willingness_mean, 0.2), 0.0, 1.0))
            p = Passenger(i, self, comfort_distance, chat)
            self.schedule.add(p)
            self._place_randomly(p)

        self.datacollector = DataCollector(
            model_reporters={
                "avg_nearest_distance": avg_nearest_distance,
                "min_nearest_distance": min_nearest_distance,
                "violation_rate": violation_rate,
                "chat_pairs": chat_pairs,
                "chat_pair_distance": chat_pair_distance,
            }
        )
        self.running = True

    def _place_randomly(self, agent):
        pos = self.random.choice(self.empty_cells())
        self.grid.place_agent(agent, pos)
        agent.pos = pos

    def empty_cells(self):
        return [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if self.grid.is_cell_empty((x, y))
        ]

    def empty_cells_near(self, pos, radius=1):
        return [
            (x, y)
            for x in range(self.width)
            for y in range(self.height)
            if (x, y) != pos
            and euclid((x, y), pos) <= radius
            and self.grid.is_cell_empty((x, y))
        ]

    def move(self, agent, new_pos):
        self.grid.move_agent(agent, new_pos)
        agent.pos = new_pos

    def nearest_neighbor_distance(self, agent):
        d = float("inf")
        for other in self.schedule.agents:
            if other is agent or other.pos is None:
                continue
            d = min(d, euclid(agent.pos, other.pos))
        return None if d == float("inf") else d

    def grid_snapshot(self):
        """返回空间快照（P=普通乘客, C=交流中乘客, .=空位）。"""
        rows = []
        for y in range(self.height):
            row = []
            for x in range(self.width):
                cell = self.grid.get_cell_list_contents((x, y))
                if not cell:
                    row.append(".")
                else:
                    row.append("C" if cell[0].in_chat else "P")
            rows.append("".join(row))
        return rows

    def step(self):
        self.datacollector.collect(self)
        self.schedule.step()


# ---------- 指标函数（供 DataCollector 使用） ----------

def _distances(model):
    out = []
    for a in model.schedule.agents:
        d = model.nearest_neighbor_distance(a)
        if d is not None:
            out.append(d)
    return out


def avg_nearest_distance(model):
    d = _distances(model)
    return float(np.mean(d)) if d else 0.0


def min_nearest_distance(model):
    d = _distances(model)
    return float(min(d)) if d else 0.0


def violation_rate(model):
    n = len(model.schedule.agents)
    if n == 0:
        return 0.0
    v = 0
    for a in model.schedule.agents:
        d = model.nearest_neighbor_distance(a)
        if d is not None and d < a.comfort_distance:
            v += 1
    return v / n


def chat_pairs(model):
    seen = set()
    for a in model.schedule.agents:
        if a.in_chat and a.chat_partner is not None:
            seen.add(tuple(sorted((a.unique_id, a.chat_partner.unique_id))))
    return len(seen)


def chat_pair_distance(model):
    seen = set()
    ds = []
    for a in model.schedule.agents:
        if a.in_chat and a.chat_partner is not None:
            pair = tuple(sorted((a.unique_id, a.chat_partner.unique_id)))
            if pair not in seen:
                seen.add(pair)
                ds.append(euclid(a.pos, a.chat_partner.pos))
    return float(np.mean(ds)) if ds else 0.0

