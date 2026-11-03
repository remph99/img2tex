"""Checks and resource selection shared by the frozen build and its tests."""

from pathlib import PurePosixPath


def keep_resource(destination: str) -> bool:
    path = PurePosixPath(destination.replace("\\", "/"))
    if path.parts[0] != "PySide6":
        return True
    if ".debug." in path.name:
        return False
    if "qtwebengine_locales" in path.parts:
        return path.stem in {"en-US", "zh-CN", "zh-TW"}
    if "translations" in path.parts and path.suffix == ".qm":
        return path.stem.endswith(("_zh_CN", "_zh_TW", "_en"))
    return True


def validate_torch_build(torch_version, vision_version, cuda_version, edition):
    suffix = "+cpu" if edition == "cpuonly" else "+cu130"
    if (torch_version != "2.14.0" + suffix or vision_version != "0.29.0" + suffix
            or cuda_version != (None if edition == "cpuonly" else "13.0")):
        raise ValueError(f"Mismatched {edition} build: torch={torch_version}, "
                         f"torchvision={vision_version}, CUDA={cuda_version}")
