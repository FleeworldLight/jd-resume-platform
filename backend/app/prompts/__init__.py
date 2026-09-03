"""Prompt 集中导出。"""
from app.prompts.customize_v1 import CUSTOMIZE_PROMPT_V1
from app.prompts.gap_analysis_v1 import GAP_ANALYSIS_PROMPT_V1
from app.prompts.jd_extract_v1 import JD_EXTRACT_PROMPT_V1
from app.prompts.predict_v1 import PREDICT_PROMPT_V1

__all__ = [
    "JD_EXTRACT_PROMPT_V1",
    "GAP_ANALYSIS_PROMPT_V1",
    "CUSTOMIZE_PROMPT_V1",
    "PREDICT_PROMPT_V1",
]
