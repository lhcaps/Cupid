"""VisionCombatLab (VCL) — Screen/video analysis + HSM combat automation for GPO Cupid Dungeon."""
import sys
from pathlib import Path

_root = Path(__file__).parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
