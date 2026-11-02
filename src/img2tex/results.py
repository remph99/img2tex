"""Conservative extraction of a formula from generated text."""

import re


def normalize_latex(raw: str) -> str:
    text = raw.strip()
    if "<think>" in text or "</think>" in text:
        raise ValueError("模型返回了思考文本，请检查非思考模板。")
    fence = re.fullmatch(r"```(?:latex|tex)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    for start, end in [("$$", "$$"), (r"\[", r"\]"), (r"\(", r"\)"), ("$", "$")]:
        if text.startswith(start) and text.endswith(end) and len(text) >= len(start) + len(end):
            inside = text[len(start):-len(end)]
            # Do not strip a pair from "$x$ + $y$" or mismatched nested delimiters.
            if start == "$" and re.search(r"(?<!\\)\$", inside):
                continue
            text = inside.strip()
            break
    if not text:
        raise ValueError("未识别到公式，请选择包含公式的清晰图片。")
    return text
