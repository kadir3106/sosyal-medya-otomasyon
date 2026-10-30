"""Conservative recovery cost / attempt budgets."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RecoveryBudget:
    max_attempts_per_beat: int = 3
    max_motion_graphic_renders: int = 4
    max_ai_generation_calls: int = 1
    max_generation_cost_per_video: float = 0.50
    max_generation_cost_per_beat: float = 0.25
    live_generation: bool = False

    motion_renders_used: int = 0
    ai_calls_used: int = 0
    cost_spent_video: float = 0.0
    cost_spent_by_beat: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_config(cls) -> "RecoveryBudget":
        from app.config import config

        return cls(
            max_attempts_per_beat=int(config.RECOVERY_MAX_ATTEMPTS_PER_BEAT),
            max_motion_graphic_renders=int(config.RECOVERY_MAX_MOTION_GRAPHIC_RENDERS),
            max_ai_generation_calls=int(config.RECOVERY_MAX_AI_GENERATION_CALLS),
            max_generation_cost_per_video=float(config.RECOVERY_MAX_GENERATION_COST_PER_VIDEO),
            max_generation_cost_per_beat=float(config.RECOVERY_MAX_GENERATION_COST_PER_BEAT),
            live_generation=bool(config.STAGE_E_LIVE_GENERATION),
        )

    def can_render_motion(self) -> bool:
        return self.motion_renders_used < self.max_motion_graphic_renders

    def can_generate(
        self,
        *,
        beat_id: str,
        estimated_cost: float,
    ) -> tuple[bool, str]:
        if not self.live_generation:
            return False, "live_generation_disabled"
        if self.ai_calls_used >= self.max_ai_generation_calls:
            return False, "max_ai_generation_calls"
        if self.cost_spent_video + estimated_cost > self.max_generation_cost_per_video + 1e-9:
            return False, "max_generation_cost_per_video"
        beat_spent = self.cost_spent_by_beat.get(beat_id, 0.0)
        if beat_spent + estimated_cost > self.max_generation_cost_per_beat + 1e-9:
            return False, "max_generation_cost_per_beat"
        return True, ""

    def record_motion(self) -> None:
        self.motion_renders_used += 1

    def record_generation(self, *, beat_id: str, cost: float) -> None:
        self.ai_calls_used += 1
        self.cost_spent_video += float(cost or 0.0)
        self.cost_spent_by_beat[beat_id] = self.cost_spent_by_beat.get(beat_id, 0.0) + float(
            cost or 0.0
        )
