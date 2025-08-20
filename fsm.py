from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from transitions import Machine
import math

def _round_to_base(x: float, base: int) -> int:
    return int(base * round(x / base))

@dataclass
class NegotiationCtx:
    # —— 不变/配置 —— #
    list_price: int = 500          # 标价
    bar_price: int = 400           # 绝对底线（永不低于）
    stop_floor: int = 420          # 停降价位（触及后不再降）
    max_concessions: int = 5       # 最大让价次数
    # step_schedule: List[int] = field(default_factory=lambda: [20,10,5,3,2])
    jump_improve_threshold: int = 20  # 跳步触发：用户改善幅度≥此值
    psych_zone_price: int = 450       # 跳步触发：用户出价≤此价位

    fraction_towards_user: float = 1/2   # 从 AI 价向用户价推进的比例（0~1）
    round_base: int = 5                 # 取整基数：整十=10，整五=5
    min_tick: int = 10                   # 最小让步跳动，避免“没降价”的取整

    # —— 运行态 —— #
    k: int = 0                           # 已让次数
    ai_offer: int = field(init=False)    # 当前AI报价
    last_user_offer: Optional[int] = None
    ended: bool = False
    history: List[Dict[str, Any]] = field(default_factory=list)  # 每轮记录

    def __post_init__(self):
        self.ai_offer = self.list_price

class NegotiationModel:
    states = ["INIT", "ANCHOR", "WAIT_USER", "CONCESSION", "HOLD", "ACCEPT", "REJECT", "END"]

    def __init__(self, ctx: NegotiationCtx):
        self.ctx = ctx
        self.user_offer: Optional[int] = None  # 本轮用户最新出价

        self.machine = Machine(
            model=self,
            states=NegotiationModel.states,
            initial="INIT",
            ignore_invalid_triggers=True
        )

        # —— 转移表 —— #
        self.machine.add_transition("start", "INIT", "ANCHOR", after="after_anchor")
        self.machine.add_transition("user_quote", "WAIT_USER", "CONCESSION",
                                    conditions=["can_concede"],
                                    after="after_concession")
        self.machine.add_transition("user_quote", "WAIT_USER", "HOLD",
                                    conditions=["should_hold"],
                                    after="after_hold")
        self.machine.add_transition("user_quote", "WAIT_USER", "ACCEPT",
                                    conditions=["user_accepts"],
                                    after="after_accept")

        # CONCESSION 结束后一般回 WAIT_USER（在 after_concession 内部决定）
        self.machine.add_transition("confirm", "*", "ACCEPT", after="after_accept")
        self.machine.add_transition("giveup",  "*", "REJECT", after="after_reject")
        self.machine.add_transition("timeout", "*", "REJECT", after="after_reject")

        # 终态
        self.machine.add_transition("to_end", "ACCEPT", "END", after="after_end")
        self.machine.add_transition("to_end", "REJECT", "END", after="after_end")

    # ========== 条件（guards） ==========
    def user_accepts(self) -> bool:
        return self.user_offer is not None and self.user_offer >= self.ctx.ai_offer

    def reached_stop(self) -> bool:
        return self.ctx.ai_offer <= self.ctx.stop_floor

    def over_limit(self) -> bool:
        return self.ctx.k >= self.ctx.max_concessions

    def should_jump(self) -> bool:
        lo = self.ctx.last_user_offer
        if lo is None or self.user_offer is None:
            return False
        return (self.user_offer - lo) >= self.ctx.jump_improve_threshold or \
               (self.user_offer <= self.ctx.psych_zone_price)

    def has_budget(self) -> bool:
        return self.ctx.ai_offer > max(self.ctx.stop_floor, self.ctx.bar_price)

    def can_concede(self) -> bool:
        # 可以进入 CONCESSION 的前提：未停、未超限、未成交且有空间
        return (not self.user_accepts()) and (not self.reached_stop()) and \
               (not self.over_limit()) and self.has_budget()

    def should_hold(self) -> bool:
        # 达停/超限/无空间 → HOLD
        return (self.reached_stop() or self.over_limit() or (not self.has_budget())) and (not self.user_accepts())

    # ========== 事件回调（after/enter） ==========
    def after_anchor(self):
        # 开场锚定：此处可做轻微让步或说明价值，随后等待用户
        self.to_WAIT_USER()

    # def after_concession(self):
    #     # 计算让价
    #     step = self.ctx.step_schedule[min(self.ctx.k, len(self.ctx.step_schedule)-1)]
    #     if self.should_jump():
    #         delta = max(0, self.ctx.ai_offer - self.ctx.stop_floor)  # 合并到停降
    #     else:
    #         delta = step

    #     new_price = self.ctx.ai_offer - delta
    #     # 双护栏
    #     new_price = max(new_price, self.ctx.stop_floor, self.ctx.bar_price)

    #     self.ctx.k += 1
    #     self.ctx.ai_offer = new_price
    #     self.ctx.last_user_offer = self.user_offer
    #     self.ctx.history.append({"phase":"CONCESSION", "user": self.user_offer, "ai": self.ctx.ai_offer})

    #     # 若触停或用尽 → HOLD；否则回 WAIT_USER
    #     if self.reached_stop() or self.over_limit():
    #         self.to_HOLD()
    #     else:
    #         self.to_WAIT_USER()




    def after_concession(self):
        # —— 计算 2/3 位点（可配置）——
        ai = self.ctx.ai_offer
        u  = self.user_offer

        # 兜底：若没有用户数值出价，退回原 step_schedule 逻辑
        if u is None:
            step = self.ctx.step_schedule[min(self.ctx.k, len(self.ctx.step_schedule)-1)]
            candidate = ai - step
        else:
            gap = ai - u
            if gap <= 0:
                # 用户 >= AI，按接受处理（也可直接 self.confirm()）
                self.after_accept()
                return
            # 从用户价往上推 2/3*gap（更靠近 AI）
            raw_target = u + self.ctx.fraction_towards_user * gap
            candidate  = _round_to_base(raw_target, self.ctx.round_base)

            # 不得升价：若取整后未降价（≥ ai），强制降一个最小跳动
            if candidate >= ai:
                candidate = ai - self.ctx.min_tick

        # —— 双护栏：不得低于停降/底线 —— #
        floor = max(self.ctx.stop_floor, self.ctx.bar_price)
        candidate = max(candidate, floor)

        # —— 状态更新 —— #
        self.ctx.k += 1
        self.ctx.ai_offer = candidate
        self.ctx.last_user_offer = u
        self.ctx.history.append({"phase": "CONCESSION", "user": u, "ai": self.ctx.ai_offer})

        # —— 停降即停 / 否则继续等待用户 —— #
        if self.reached_stop() or self.over_limit():
            self.to_HOLD()
        else:
            self.to_WAIT_USER()

    def after_hold(self):
        # 记录持价
        self.ctx.last_user_offer = self.user_offer
        self.ctx.history.append({"phase":"HOLD", "user": self.user_offer, "ai": self.ctx.ai_offer})

    def after_accept(self):
        self.ctx.ended = True
        self.ctx.last_user_offer = self.user_offer
        self.ctx.history.append({"phase":"ACCEPT", "user": self.user_offer, "ai": self.ctx.ai_offer})

    def after_reject(self):
        self.ctx.ended = True
        self.ctx.history.append({"phase":"REJECT", "user": self.user_offer, "ai": self.ctx.ai_offer})

    def after_end(self):
        self.ctx.history.append({"phase":"END", "user": self.user_offer, "ai": self.ctx.ai_offer})

    # ========== 对外接口 ==========
    def input_user_price(self, price: int) -> Dict[str, Any]:
        """
        外部调用：输入用户出价 → 推动状态机一次（从 WAIT_USER 发起 user_quote）
        返回：快照/合同（见下）
        """
        self.user_offer = int(price)
        if self.state == "INIT":
            self.start()  # 进入 WAIT_USER
        if self.state == "ANCHOR":
            self.to_WAIT_USER()
        if self.state == "WAIT_USER":
            # 将按 guards 自动进入 CONCESSION / HOLD / ACCEPT
            self.user_quote()
        # 若已在 HOLD 且用户仍压价，可选择继续 WAIT_USER 或策略性让出非价格福利（此处略）
        return self.snapshot()

    def confirm_deal(self) -> Dict[str, Any]:
        self.confirm()
        return self.snapshot()

    # ========== 输出：快照 / 合同（供语言层使用） ==========
    def snapshot(self) -> Dict[str, Any]:
        """
        轻量快照（给调试/追踪）
        """
        return {
            "state": self.state,
            "ai_offer": self.ctx.ai_offer,
            "user_offer": self.user_offer,
            "k": self.ctx.k,
            "reached_stop_floor": self.reached_stop(),
            "ended": self.ctx.ended
        }

    def contract(self, value_reasons: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        语言层的“话术合同”（Language Contract）。
        """
        if value_reasons is None:
            value_reasons = ["正品保障与售后", "做工与用料优于同级", "现货可加急（以政策为准）"]

        phase_map = {"INIT":"INIT","ANCHOR":"ANCHOR","WAIT_USER":"WAIT_USER",
                     "CONCESSION":"CONCESSION","HOLD":"HOLD","ACCEPT":"ACCEPT","REJECT":"REJECT","END":"END"}

        return {
            "state": {
                "phase": phase_map.get(self.state, self.state),
                "reason": "auto_by_fsm",
                "reached_stop_floor": self.reached_stop(),
                "can_negotiate": (not self.reached_stop()) and (not self.ctx.ended)
            },
            "pricing": {
                "list_price": self.ctx.list_price,
                "bar_price": self.ctx.bar_price,
                "stop_floor": self.ctx.stop_floor,
                "user_offer": self.user_offer,
                "ai_offer": self.ctx.ai_offer,
                "max_concessions": self.ctx.max_concessions,
                "used_concessions": self.ctx.k
            },
            "actions": {
                "allowed": ["HOLD","ACCEPT"] if self.reached_stop() else ["CONCESSION","HOLD","ACCEPT"],
                "forbidden": ["LOWER_PRICE"] if self.reached_stop() else []
            },
            "product": {
                "title": "演示商品",
                "value_reasons": value_reasons
            },
            "persona": {"style": "analytic", "politeness": "medium", "token_budget": 256},
            "nlg": {"tone": "professional", "length_hint": "2-4 sentences", "cta": "若确认可立即锁单并优先发货"},
            "hard_guards": {
                "must_not_price_below": max(self.ctx.stop_floor, self.ctx.bar_price),
                "must_not_change_state": True
            }
        }
