"""Behavioral checks for local, editable formula exports."""

import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

import pytest

from img2tex.exports import to_asciimath, to_mathml, to_typst, write_docx

MML = {"m": "http://www.w3.org/1998/Math/MathML"}
OMML = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}


def test_mathml_preserves_fraction_root_scripts_and_namespace():
    root = ET.fromstring(to_mathml(r"\frac{x_1^2+1}{\sqrt[3]{y}}"))
    assert root.tag == "{" + MML["m"] + "}math"
    assert root.find(".//m:mfrac", MML) is not None
    assert root.find(".//m:msubsup", MML) is not None
    assert root.find(".//m:mroot", MML) is not None


@pytest.mark.parametrize(
    "convert,want",
    [
        (to_asciimath, "(a + b)/(sqrt(x))"),
        (to_typst, "frac(a + b, sqrt(x))"),
    ],
)
def test_fraction_and_sqrt_keep_numerator_group(convert, want):
    assert convert(r"\frac{a+b}{\sqrt{x}}") == want


@pytest.mark.parametrize(
    "convert,want",
    [
        (to_asciimath, "x_(i + 1)^(n + 2)"),
        (to_typst, "attach(x, br: i + 1, tr: n + 2)"),
    ],
)
def test_scripts_keep_multi_token_arguments(convert, want):
    assert convert(r"x_{i+1}^{n+2}") == want


@pytest.mark.parametrize(
    "convert,want",
    [
        (to_asciimath, "[(a,b),(c,d)]"),
        (to_typst, 'mat(delim: "[", a, b; c, d)'),
    ],
)
def test_matrix_keeps_rows_columns_and_brackets(convert, want):
    assert convert(r"\begin{bmatrix}a&b\\c&d\end{bmatrix}") == want


@pytest.mark.parametrize(
    "convert,want",
    [
        (to_asciimath, "{(x^(2),x >= 0),(- x,x < 0):}"),
        (to_typst, "cases(attach(x, tr: 2) & x ≥ 0, - x & x < 0)"),
    ],
)
def test_cases_keep_conditions_and_one_sided_brace(convert, want):
    latex = r"\begin{cases}x^2 & x\ge 0\\-x & x<0\end{cases}"
    assert convert(latex) == want


@pytest.mark.parametrize(
    "latex",
    [
        "",
        "   ",
        r"\frac{x}",
        r"\sqrt",
        r"x^{2",
        r"x}2",
        r"x^",
        r"x^^2",
        r"\definitelyUnknown{x}",
        r"\begin{matrix}a&b\end{cases}",
        r"\left(x+1",
        r"\right)",
        r"\frac{}{x}",
        r"\begin{matrix}a&b\\c\end{matrix}",
    ],
)
@pytest.mark.parametrize("convert", [to_mathml, to_asciimath, to_typst])
def test_malformed_or_unknown_latex_is_rejected(latex, convert):
    with pytest.raises(ValueError):
        convert(latex)


@pytest.mark.parametrize("convert", [to_asciimath, to_typst])
@pytest.mark.parametrize("latex", [r"\overbrace{x+y}^{n}", r"\phantom{x}", r"\color{red}{x}"])
def test_unsupported_structures_are_rejected_instead_of_flattened(convert, latex):
    with pytest.raises(ValueError, match="unsupported|Unsupported|不支持"):
        convert(latex)


@pytest.mark.parametrize("latex", [r"\mathop{x}+1", r"\mathbin{x}+y", r"\mathrel{R}"])
@pytest.mark.parametrize("convert", [to_mathml, to_asciimath, to_typst])
def test_nested_token_elements_are_rejected_instead_of_losing_content(convert, latex):
    with pytest.raises(ValueError, match="Unsupported.*token"):
        convert(latex)


@pytest.mark.parametrize("latex", [r"\mathop{x}+1", r"\mathbin{x}+y", r"\mathrel{R}"])
def test_docx_rejects_nested_token_elements_before_writing(tmp_path, latex):
    path = tmp_path / "unsupported.docx"
    with pytest.raises(ValueError, match="Unsupported.*token"):
        write_docx(latex, path)
    assert not path.exists()


@pytest.mark.parametrize(
    "latex,want",
    [
        (r"x^2", "attach(x, tr: 2)"),
        (r"x_i", "attach(x, br: i)"),
        (r"{a+b}^2", "attach(a + b, tr: 2)"),
        (r"\left(x+1\right)^2", "attach(( x + 1 ), tr: 2)"),
        (r"\frac{x_i}{y^2}", "frac(attach(x, br: i), attach(y, tr: 2))"),
    ],
)
def test_typst_attachments_do_not_add_visible_base_parentheses(latex, want):
    assert to_typst(latex) == want


def test_mathml_escapes_text_and_keeps_greek_symbols():
    root = ET.fromstring(to_mathml(r"\alpha < \beta"))
    assert "".join(root.itertext()) == "α<β"


def test_mathml_text_remains_well_formed_xml():
    root = ET.fromstring(to_mathml(r"\text{a & b < c}"))
    assert "".join(root.itertext()).replace("\u00a0", " ") == "a & b < c"


@pytest.mark.parametrize(
    "convert,want",
    [
        (to_asciimath, "x + {:(1,2):}"),
        (to_typst, "x + mat(delim: #none, 1, 2)"),
    ],
)
def test_plain_matrix_after_operator_does_not_consume_operator(convert, want):
    assert convert(r"x+\begin{matrix}1&2\end{matrix}") == want


@pytest.mark.parametrize("convert,want", [(to_asciimath, "a // b"), (to_typst, "a slash b")])
def test_literal_slash_does_not_become_a_stacked_fraction(convert, want):
    assert convert("a/b") == want


@pytest.mark.parametrize(
    "convert,want",
    [
        (to_asciimath, "root(3)(x + 1)"),
        (to_typst, "root(3, x + 1)"),
    ],
)
def test_root_index_and_whole_radicand_are_preserved(convert, want):
    assert convert(r"\sqrt[3]{x+1}") == want


@pytest.mark.parametrize("convert", [to_asciimath, to_typst])
def test_semantic_font_variants_are_rejected_instead_of_erased(convert):
    with pytest.raises(ValueError, match="Unsupported"):
        convert(r"\rm x")


def test_typst_preserves_blackboard_bold_as_a_unicode_symbol():
    assert to_typst(r"\mathbb{R}") == "ℝ"


@pytest.mark.parametrize("convert", [to_asciimath, to_typst])
@pytest.mark.parametrize("latex", [r"\mathrm{x^2+y^2=z^2}", r"\mathbf{E}=\mathbf{m}\mathbf{c}^2"])
def test_text_formats_reject_styles_they_cannot_preserve(convert, latex):
    with pytest.raises(ValueError, match="Unsupported"):
        convert(latex)


@pytest.mark.parametrize(
    "latex,variant,letters,script_count",
    [
        (r"\mathrm{x^2+y^2=z^2}", "normal", ["x", "y", "z"], 3),
        (r"\mathbf{E}=\mathbf{m}\mathbf{c}^2", "bold", ["E", "m", "c"], 1),
    ],
)
def test_mathml_style_commands_preserve_identifiers_and_scripts(latex, variant, letters, script_count):
    root = ET.fromstring(to_mathml(latex))
    identifiers = root.findall(".//m:mi", MML)
    assert [node.text for node in identifiers] == letters
    assert all(node.get("mathvariant") == variant for node in identifiers)
    assert len(root.findall(".//m:msup", MML)) == script_count
    assert root.find(".//m:mtext", MML) is None


def test_mathml_font_scope_stops_after_group_and_respects_nested_override():
    root = ET.fromstring(to_mathml(r"\mathrm{a\mathbf{b}c}+d"))
    assert [(node.text, node.get("mathvariant")) for node in root.findall(".//m:mi", MML)] == [
        ("a", "normal"),
        ("b", "bold"),
        ("c", "normal"),
        ("d", None),
    ]


@pytest.mark.parametrize("command,variant", [(r"\mathrm", "normal"), (r"\mathbf", "bold")])
def test_mathml_styled_fraction_keeps_nested_scripts(command, variant):
    root = ET.fromstring(to_mathml(command + r"{\frac{x_1}{y^2}}"))
    assert root.find(".//m:mfrac", MML) is not None
    assert root.find(".//m:msub", MML) is not None
    assert root.find(".//m:msup", MML) is not None
    assert all(node.get("mathvariant") == variant for node in root.findall(".//m:mi", MML))


@pytest.mark.parametrize(
    "latex,style,letters,script_count",
    [
        (r"\mathrm{x^2+y^2=z^2}", "p", ["x", "y", "z"], 3),
        (r"\mathbf{E}=\mathbf{m}\mathbf{c}^2", "b", ["E", "m", "c"], 1),
    ],
)
def test_docx_style_commands_create_editable_run_styles(tmp_path, latex, style, letters, script_count):
    path = tmp_path / "styled.docx"
    write_docx(latex, path)
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        assert not any(name.startswith("word/media/") for name in archive.namelist())
    styles = {}
    for run in root.findall(".//m:r", OMML):
        text = "".join(run.find("m:t", OMML).itertext())
        if text in letters:
            styles[text] = run.find("m:rPr/m:sty", OMML).get("{" + OMML["m"] + "}val")
    assert styles == dict.fromkeys(letters, style)
    assert len(root.findall(".//m:sSup", OMML)) == script_count


def test_asciimath_groups_compound_script_base_without_visible_brackets():
    assert to_asciimath(r"{a+b}^2") == "{:a + b:}^(2)"


def test_docx_does_not_erase_unsupported_color(tmp_path: Path):
    with pytest.raises(ValueError, match="Unsupported"):
        write_docx(r"\color{red}{x}", tmp_path / "color.docx")


def test_docx_contains_editable_omml_not_an_image(tmp_path: Path):
    path = tmp_path / "公式.docx"
    write_docx(r"\frac{x_1^2}{\sqrt{y}}+\begin{bmatrix}a&b\\c&d\end{bmatrix}", path)
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        assert root.find(".//m:oMath", OMML) is not None
        for element in ("f", "sSubSup", "rad", "m"):
            assert root.find(".//m:" + element, OMML) is not None
        assert not any(name.startswith("word/media/") for name in archive.namelist())


def test_docx_invalid_input_does_not_overwrite_existing_file(tmp_path: Path):
    path = tmp_path / "keep.docx"
    path.write_bytes(b"original")
    with pytest.raises(ValueError):
        write_docx(r"\unknowncommand", path)
    assert path.read_bytes() == b"original"


def test_docx_square_root_hides_degree_but_indexed_root_keeps_degree(tmp_path: Path):
    path = tmp_path / "roots.docx"
    write_docx(r"\sqrt{x}+\sqrt[3]{y}", path)
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    square, cube = root.findall(".//m:rad", OMML)
    assert square.find("m:deg", OMML) is not None
    hidden = square.find("m:radPr/m:degHide", OMML)
    assert hidden is not None and hidden.get("{" + OMML["m"] + "}val") == "1"
    assert "".join(cube.find("m:deg", OMML).itertext()) == "3"
    assert cube.find("m:radPr/m:degHide", OMML) is None
