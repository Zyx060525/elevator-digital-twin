"""
增强版模型 —— 真实物理尺寸 + 楼层上下客动态 + 简化社会力移动

相比基础版（model.py）的三点深化：
1. 真实物理尺寸：电梯轿厢用"米"建模（宽/深 + 网格粒度），社交距离、交流范围均为米制，
   实现"物理世界 -> 数字孪生"的真实映射。
2. 楼层上下客动态：乘客携带目标楼层，电梯周期性到站，到站乘客下车、新乘客上车，
   模拟真实人流动态（而非静态固定人数）。
3. 简化社会力：乘客移动由"社交排斥势(1/d) + 交流吸引势(d)"合成驱动，替代简单的最远距离规则。

核心洞察（可量化验证）：
   在真实电梯尺寸下，标准社交距离（如 1.0m）在物理上无法满足——即使乘客最大化距离，
   平均最近邻距离仍远小于 1m；交流行为会进一步压缩该距离。

运行：python -m elevator_twin.model_enhanced
"""
import numpy as np
from mesa import Agent, Model
from mesa.datacollection import DataCollector
from mesa.space import MultiGrid
from mesa.time import RandomActivation

from elevator_twin.model import euclid


class EnhancedPassenger(Agent):
    """增强版乘客：携带目标楼层，受社会力驱动移动。"""

    def __init__(self, unique_id, model, comfort_distance_m, chat_willingness, target_floor):
        super().__init__(unique_id, model)
        self.comfort_distance = comfort_distance_m  # 最小舒适社交距离（米）
        self.chat_willingness = chat_willingness
        self.target_floor = target_floor            # 目标楼层
        self.in_chat = False
        self.chat_partner = None
        self.pos = None

    def _dist(self, pos):
        return euclid(self.pos, pos) * self.model.cell_size

    def step(self):
        # 1) 解除失效交流
        if self.in_chat and self.chat_partner is not None:
            if self._dist(self.chat_partner.pos) > self.model.chat_range_m:
                self._end_chat()
        # 2) 建立交流
        if not self.in_chat:
            partner = self._find_chat_partner()
            if partner is not None:
                self._start_chat(partner)
        # 3) 社会力移动
        self._social_force_move()

    def _find_chat_partner(self):
        best, best_d = None, float("inf")
        for other in self.model.schedule.agents:
            if other is self or other.in_chat or other.pos is None:
                continue
            d = euclid(self.pos, other.pos) * self.model.cell_size
            if d < best_d:
                best, best_d = other, d
        if best is None or best_d > self.model.chat_range_m:
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

    def _social_force_move(self):
        cells = self.model.empty_cells()
        if not cells:
            return
        best, best_potential = None, self._potential(self.pos)
        for cell in cells:
            p = self._potential(cell)
            if p < best_potential:  # 势能越低越优
                best, best_potential = cell, p
        if best is not None:
            self.model.move(self, best)

    def _potential(self, cell):
        pot = 0.0
        cs = self.model.cell_size
        for other in self.model.schedule.agents:
            if other is self or other.pos is None:
                continue
            d = euclid(cell, other.pos) * cs
            # 社交排斥势：越近越大（1/d）
            pot += self.model.repulsion_strength / max(d, 0.1)
        if self.in_chat and self.chat_partner is not None:
            d = euclid(cell, self.chat_partner.pos) * cs
            # 交流吸引势：越远越大
            pot += self.model.attraction_strength * d
        return pot


class EnhancedElevatorModel(Model):
    """增强版电梯轿厢模型：真实尺寸 + 上下客 + 社会力。"""

    def __init__(
        self,
        width_m=1.6,
        depth_m=1.4,
        cell_size=0.4,
        n_floors=6,
        board_interval=5,
        max_passengers=6,
        comfort_distance_m=1.0,
        chat_willingness_mean=0.5,
        chat_range_m=0.8,
        chat_threshold=1.0,
        repulsion_strength=1.0,
        attraction_strength=0.5,
        seed=None,
    ):
        super().__init__(seed=seed)
        self.cell_size = cell_size
        self.width = max(1, int(width_m / cell_size))
        self.height = max(1, int(depth_m / cell_size))
        self.n_floors = n_floors
        self.board_interval = board_interval
        self.max_passengers = max_passengers
        self.comfort_distance = comfort_distance_m
        self.chat_range_m = chat_range_m
        self.chat_threshold = chat_threshold
        self.repulsion_strength = repulsion_strength
        self.attraction_strength = attraction_strength
        self.chat_willingness_mean = chat_willingness_mean

        self.current_floor = 1
        self.step_count = 0
        self._next_id = 0

        self.grid = MultiGrid(self.width, self.height, torus=False)
        self.schedule = RandomActivation(self)

        for _ in range(max_passengers):
            self._add_passenger()

        self.datacollector = DataCollector(
            model_reporters={
                "avg_nearest_distance_m": avg_nearest_distance_m,
                "min_nearest_distance_m": min_nearest_distance_m,
                "violation_rate": violation_rate,
                "chat_pairs": chat_pairs,
                "current_passengers": current_passengers,
                "current_floor": current_floor,
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

    def move(self, agent, new_pos):
        self.grid.move_agent(agent, new_pos)
        agent.pos = new_pos

    def nearest_neighbor_distance(self, agent):
        d = float("inf")
        for other in self.schedule.agents:
            if other is agent or other.pos is None:
                continue
            d = min(d, euclid(agent.pos, other.pos) * self.cell_size)
        return None if d == float("inf") else d

    def _add_passenger(self):
        i = self._next_id
        self._next_id += 1
        chat = float(np.clip(self.random.gauss(self.chat_willingness_mean, 0.2), 0.0, 1.0))
        target = self.random.randint(2, self.n_floors + 1)  # 目标楼层（至少上一层）
        p = EnhancedPassenger(i, self, self.comfort_distance, chat, target)
        self.schedule.add(p)
        self._place_randomly(p)

    def _board_alight(self):
        # 下客：目标楼层 == 当前楼层的乘客离开
        alighting = [a for a in self.schedule.agents if a.target_floor == self.current_floor]
        for a in alighting:
            # 先解除交流关系，避免悬空引用（MESA remove 会把 agent.pos 置 None）
            if a.in_chat and a.chat_partner is not None:
                a._end_chat()
            self.grid.remove_agent(a)
            self.schedule.remove(a)
        # 上客：随机数量（不超过额定人数与剩余容量）
        room = min(self.max_passengers - len(self.schedule.agents), len(self.empty_cells()))
        if room > 0:
            for _ in range(self.random.randint(0, room)):
                self._add_passenger()
        # 楼层循环
        self.current_floor = self.current_floor % self.n_floors + 1

    def grid_snapshot(self):
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
        if self.step_count > 0 and self.step_count % self.board_interval == 0:
            self._board_alight()
        self.schedule.step()
        self.step_count += 1


# ---------- 指标函数 ----------

def _distances(model):
    out = []
    for a in model.schedule.agents:
        d = model.nearest_neighbor_distance(a)
        if d is not None:
            out.append(d)
    return out


def avg_nearest_distance_m(model):
    d = _distances(model)
    return float(np.mean(d)) if d else 0.0


def min_nearest_distance_m(model):
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


def current_passengers(model):
    return len(model.schedule.agents)


def current_floor(model):
    return model.current_floor


if __name__ == "__main__":
    model = EnhancedElevatorModel(seed=42)
    print("电梯尺寸 %.1fm x %.1fm, 网格 %dx%d, 额定 %d 人, 社交距离 %.1fm"
          % (1.6, 1.4, model.width, model.height, model.max_passengers, model.comfort_distance))
    for step in range(1, 31):
        model.step()
        r = model.datacollector.get_model_vars_dataframe().iloc[-1]
        if step == 1 or step % 5 == 0:
            print(f"step={step:2d} floor={int(r['current_floor'])} "
                  f"n={int(r['current_passengers'])} "
                  f"avg_dist={r['avg_nearest_distance_m']:.3f}m "
                  f"min_dist={r['min_nearest_distance_m']:.3f}m "
                  f"violation={r['violation_rate']:.3f} chat={int(r['chat_pairs'])}")
    print("结束空间快照：")
    for row in model.grid_snapshot():
        print("  " + row)
