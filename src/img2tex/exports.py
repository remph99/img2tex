"""Offline formula exports, rejecting structures a target cannot preserve."""

import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from latex2mathml.converter import convert_to_element

MATHML_NS = "http://www.w3.org/1998/Math/MathML"
OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_ENVIRONMENTS = {"matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix", "cases", "array"}
_ARITY = {"mfrac": 2, "mroot": 2, "msub": 2, "msup": 2, "msubsup": 3}
_TEXT_NODES = {"mi", "mn", "mo", "mtext"}
_BASIC_NODES = (
    _TEXT_NODES | set(_ARITY) | {"math", "mrow", "mstyle", "msqrt", "mspace", "mtable", "mtr", "mtd"}
)
_FUNCTIONS = {
    "cosh",
    "lim",
    "arcsin",
    "gcd",
    "exp",
    "min",
    "csc",
    "arctan",
    "sin",
    "sec",
    "det",
    "tanh",
    "cos",
    "tan",
    "ln",
    "arccos",
    "cot",
    "log",
    "max",
    "dim",
    "sinh",
}
_ASCII_SYMBOLS = {
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
    "ε": "varepsilon",
    "ϵ": "epsilon",
    "ζ": "zeta",
    "η": "eta",
    "θ": "theta",
    "ϑ": "vartheta",
    "ι": "iota",
    "κ": "kappa",
    "λ": "lambda",
    "μ": "mu",
    "ν": "nu",
    "ξ": "xi",
    "π": "pi",
    "ρ": "rho",
    "σ": "sigma",
    "τ": "tau",
    "υ": "upsilon",
    "ϕ": "phi",
    "φ": "varphi",
    "χ": "chi",
    "ψ": "psi",
    "ω": "omega",
    "Γ": "Gamma",
    "Δ": "Delta",
    "Θ": "Theta",
    "Λ": "Lambda",
    "Ξ": "Xi",
    "Π": "Pi",
    "Σ": "Sigma",
    "Υ": "Upsilon",
    "Φ": "Phi",
    "Ψ": "Psi",
    "Ω": "Omega",
    "−": "-",
    "≤": "<=",
    "≥": ">=",
    "≠": "!=",
    "≈": "~~",
    "≡": "-=",
    "∞": "oo",
    "×": "xx",
    "⋅": "*",
    "÷": "-:",
    "±": "+-",
    "∓": "-+",
    "∑": "sum",
    "∏": "prod",
    "∫": "int",
    "∮": "oint",
    "∂": "del",
    "∇": "grad",
    "∈": "in",
    "∉": "!in",
    "⊂": "sub",
    "⊆": "sube",
    "⊃": "sup",
    "⊇": "supe",
    "∪": "uu",
    "∩": "nn",
    "→": "->",
    "←": "larr",
    "↔": "harr",
    "⇒": "rArr",
    "⇐": "lArr",
    "⇔": "hArr",
    "∅": "O/",
    "∀": "AA",
    "∃": "EE",
    "¬": "not",
    "∧": "and",
    "∨": "or",
    "…": "...",
    "⋯": "cdots",
    "⋮": "vdots",
    "⋱": "ddots",
    "/": "//",
}


def _prevalidate(latex: str) -> str:
    if not isinstance(latex, str) or not latex.strip():
        raise ValueError("Formula is empty.")
    latex = latex.strip()
    # The parser deliberately recovers some broken input. Check boundaries first.
    depth = 0
    environments = []
    for match in re.finditer(r"\\(?:begin|end)\s*\{([^{}]*)\}|\\[a-zA-Z]+|\\.|[{}$%#&]", latex):
        token = match.group()
        if token.startswith((r"\begin", r"\end")) and match.group(1) is not None:
            name = match.group(1)
            if name not in _ENVIRONMENTS:
                raise ValueError(f"Unsupported LaTeX environment: {name}")
            if token.startswith(r"\begin"):
                environments.append(name)
            elif not environments or environments.pop() != name:
                raise ValueError("LaTeX environments do not match.")
        elif token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unmatched LaTeX brace.")
        elif token in {"$", "%", "#"}:
            raise ValueError("Use a formula without document delimiters, comments, or macro parameters.")
        elif token == "&" and not environments:
            # Text may legitimately contain a literal ampersand; XML escapes it.
            if not re.search(r"\\(?:text|mbox|hbox)\s*\{", latex[: match.start()]):
                raise ValueError("Alignment marker outside a matrix.")
        elif token in {r"\def", r"\newcommand", r"\renewcommand", r"\providecommand", r"\let"}:
            raise ValueError(f"Unsupported LaTeX command: {token}")
    if depth or environments:
        raise ValueError("Unclosed LaTeX brace or environment.")
    return latex


def _style_groups(latex: str) -> str:
    # The tokenizer eagerly turns \mathrm{x} into an unstyled x. Scoped
    # declarations retain original letters and mathvariant on structural tokens.
    def replace(match: re.Match) -> str:
        declaration = {"mathrm": "rm", "mathbf": "bf"}.get(match.group(1))
        if declaration is None:
            return match.group()
        if match.group(2) is None:
            raise ValueError("Unsupported unbraced style argument; use braces around the formula.")
        return "{\\" + declaration + " "

    return re.sub(r"\\([a-zA-Z]+)(\s*\{)?|\\.", replace, latex)


def _tree(latex: str) -> ET.Element:
    latex = _prevalidate(latex)
    try:
        root = convert_to_element(_style_groups(latex))
        for node in root.iter():
            if node.tag in _TEXT_NODES and len(node):
                raise ValueError(f"Unsupported nested MathML token structure: {node.tag}")
            # latex2mathml stores numeric character references in element text.
            # Serialize ourselves: its string API unescapes literal '<' and '&'.
            if node.text:
                node.text = re.sub(
                    r"&#(?:x[0-9a-fA-F]+|[0-9]+);", lambda m: html.unescape(m.group()), node.text
                )
            if node.tag in {"mi", "mo"} and re.search(r"\\[a-zA-Z]+", node.text or ""):
                raise ValueError(f"Unsupported LaTeX command: {node.text}")
            if node.tag in _ARITY and (
                len(node) != _ARITY[node.tag] or any(not "".join(child.itertext()).strip() for child in node)
            ):
                raise ValueError(f"Incomplete formula structure: {node.tag}")
            if node.tag == "msqrt" and not "".join(node.itertext()).strip():
                raise ValueError("Square root has no argument.")
            if node.tag == "mtable":
                widths = {len(row) for row in node}
                if len(widths) != 1 or not widths or 0 in widths:
                    raise ValueError("Matrix rows must have the same nonzero number of columns.")
        if not "".join(root.itertext()).strip():
            raise ValueError("Formula has no mathematical content.")
        return root
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Invalid or unsupported LaTeX: {type(exc).__name__}") from exc


def to_mathml(latex: str) -> str:
    """Return namespace-qualified Presentation MathML without network access."""
    return ET.tostring(_tree(latex), encoding="unicode")


def _check_target(root: ET.Element, target: str) -> None:
    for node in root.iter():
        if node.tag not in _BASIC_NODES:
            raise ValueError(f"Unsupported {target} structure: {node.tag}")
        if any(key in node.attrib for key in ("mathcolor", "mathbackground", "columnlines", "rowlines")):
            raise ValueError(f"Unsupported {target} styling: {node.tag}")
        if "mathvariant" in node.attrib and not (
            target == "DOCX" and node.tag in _TEXT_NODES and node.get("mathvariant") in {"normal", "bold"}
        ):
            raise ValueError(f"Unsupported {target} math variant: {node.get('mathvariant')}")
        if node.tag == "mfrac" and "linethickness" in node.attrib:
            raise ValueError(f"Unsupported {target} fraction line thickness.")


class _TextExport:
    def __init__(self, typst: bool):
        self.typst = typst

    def row(self, children: list[ET.Element]) -> str:
        parts = []
        index = 0
        while index < len(children):
            child = children[index]
            if (
                child.tag == "mo"
                and child.text in {"(", "[", "{", "|", "‖"}
                and index + 1 < len(children)
                and children[index + 1].tag == "mtable"
            ):
                left = child.text or ""
                right = ""
                end = index + 2
                if (
                    end < len(children)
                    and children[end].tag == "mo"
                    and children[end].text in {")", "]", "}", "|", "‖"}
                ):
                    right = children[end].text
                    end += 1
                if (left, right) not in {
                    ("(", ")"),
                    ("[", "]"),
                    ("{", "}"),
                    ("|", "|"),
                    ("‖", "‖"),
                    ("{", ""),
                }:
                    raise ValueError("Unsupported matrix delimiters.")
                parts.append(self.table(children[index + 1], left, right))
                index = end
            else:
                parts.append(self.node(child))
                index += 1
        return " ".join(part for part in parts if part)

    def table(self, node: ET.Element, left: str = "", right: str = "") -> str:
        rows = [[self.row(list(cell)) for cell in row] for row in node]
        if self.typst:
            if left == "{" and not right:
                return "cases(" + ", ".join(" & ".join(row) for row in rows) + ")"
            delim = json.dumps(left, ensure_ascii=False) if left else "#none"
            return f"mat(delim: {delim}, " + "; ".join(", ".join(row) for row in rows) + ")"
        if left == "‖":
            raise ValueError("Unsupported AsciiMath double-bar matrix delimiters.")
        return (left or "{:") + ",".join("(" + ",".join(row) + ")" for row in rows) + (right or ":}")

    def node(self, node: ET.Element) -> str:
        tag = node.tag
        if tag in {"math", "mrow", "mstyle", "mtd"}:
            return self.row(list(node))
        if tag == "mspace":
            return ""
        if tag == "mtable":
            return self.table(node)
        if tag == "mtext":
            text = (node.text or "").replace("\u00a0", " ")
            if not self.typst and any(c in text for c in '\\"'):
                raise ValueError("Unsupported AsciiMath text quoting.")
            return json.dumps(text, ensure_ascii=False)
        if tag in {"mi", "mn", "mo"}:
            text = node.text or ""
            if text in _FUNCTIONS or re.fullmatch(r"[a-zA-Z0-9]+(?:\.[0-9]+)?", text):
                if len(text) > 1 and text.isalpha() and text not in _FUNCTIONS:
                    raise ValueError(f"Unsupported multi-letter identifier: {text}")
                return text
            if self.typst:
                if text in {",", ";", "#", "$", "&", "_", "^", "\\", '"'}:
                    return "\\" + text
                return "slash" if text == "/" else text.replace("−", "-")
            if text in _ASCII_SYMBOLS:
                return _ASCII_SYMBOLS[text]
            if text in {"+", "-", "=", "<", ">", "(", ")", "[", "]", "{", "}", "|", "!", ".", ":"}:
                return text
            if text in {",", ";"}:
                return json.dumps(text)
            raise ValueError(f"Unsupported AsciiMath symbol: {text}")
        args = [self.node(child) for child in node]
        if tag == "mfrac":
            return f"frac({args[0]}, {args[1]})" if self.typst else f"({args[0]})/({args[1]})"
        if tag == "msqrt":
            return "sqrt(" + self.row(list(node)) + ")"
        if tag == "mroot":
            return f"root({args[1]}, {args[0]})" if self.typst else f"root({args[1]})({args[0]})"
        if tag in {"msub", "msup", "msubsup"}:
            if self.typst:
                if tag == "msubsup":
                    return f"attach({args[0]}, br: {args[1]}, tr: {args[2]})"
                position = "br" if tag == "msub" else "tr"
                return f"attach({args[0]}, {position}: {args[1]})"
            base = args[0] if node[0].tag in {"mi", "mn", "mo"} else "{:" + args[0] + ":}"
            if tag == "msubsup":
                return base + f"_({args[1]})^({args[2]})"
            return base + ("_" if tag == "msub" else "^") + f"({args[1]})"
        raise ValueError(f"Unsupported text export structure: {tag}")


def to_asciimath(latex: str) -> str:
    """Return AsciiMath for the supported structural subset."""
    root = _tree(latex)
    _check_target(root, "AsciiMath")
    return _TextExport(typst=False).node(root)


def to_typst(latex: str) -> str:
    """Return a Typst math-mode body (without dollar delimiters)."""
    root = _tree(latex)
    _check_target(root, "Typst")
    return _TextExport(typst=True).node(root)


def write_docx(latex: str, path: Path) -> None:
    """Write an editable Office equation, never an image replacement."""
    import mathml2omml
    from docx import Document
    from docx.oxml import OxmlElement, parse_xml

    root = _tree(latex)
    _check_target(root, "DOCX")
    try:
        omml = mathml2omml.convert(ET.tostring(root, encoding="unicode"))
        equation = parse_xml(omml.replace("<m:oMath>", f'<m:oMath xmlns:m="{OMML_NS}">', 1))
        # Explicitly hide the empty degree of square roots in Office editors.
        for radical in equation.iter(f"{{{OMML_NS}}}rad"):
            if radical.find(f"{{{OMML_NS}}}deg") is None:
                properties = OxmlElement("m:radPr")
                hidden = OxmlElement("m:degHide")
                hidden.set(f"{{{OMML_NS}}}val", "1")
                properties.append(hidden)
                radical.insert(0, properties)
                radical.insert(1, OxmlElement("m:deg"))
        document = Document()
        document.add_paragraph()._p.append(equation)
    except Exception as exc:
        raise ValueError(f"Unsupported DOCX formula: {exc}") from exc
    document.save(str(path))
