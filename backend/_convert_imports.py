# 工具脚本：把 backend/app 下所有相对导入(以"."或".."开头)改为以 app 为根的绝对导入。
# 转换规则：文件所在包 = app / app.analysis / app.api / app.data / app.services
#   from .X import Y        -> from <当前包>.X import Y
#   from . import Y         -> from <当前包> import Y
#   from ..X import Y       -> from app.X import Y
#   from .. import Y        -> from app import Y
import re
import pathlib

ROOT = pathlib.Path(r"D:/Public Opinion/backend/app")

def pkg_of(path: pathlib.Path) -> str:
    """返回该文件所属的包名(以 app 为根)。

    模块文件 app/analysis/engine.py 的包是 app.analysis(目录)，
    不是 app.analysis.engine(把文件名也算进包是错误的)。
    因此一律去掉路径最后一段(模块名 / __init__)。
    """
    rel = path.relative_to(ROOT).with_suffix("")  # 去 .py，如 analysis/engine
    parts = list(rel.parts)
    parts = parts[:-1]  # 去掉末段，得到所属包目录
    if not parts:
        return "app"
    return "app." + ".".join(parts)

# 匹配: from <若干个.><可选模块路径> import <名称...>
pat = re.compile(r'^(\s*)from\s+(\.+)\s*([A-Za-z0-9_.]*)\s+import\s+(.+)$')

changed = 0
for py in sorted(ROOT.rglob("*.py")):
    if "__pycache__" in str(py):
        continue
    pkg = pkg_of(py)
    text = py.read_text(encoding="utf-8")
    out_lines = []
    for line in text.split("\n"):
        m = pat.match(line)
        if not m:
            out_lines.append(line)
            continue
        indent, dots, rest, names = m.group(1), m.group(2), m.group(3), m.group(4)
        n = len(dots)
        if n == 1:
            target = pkg if not rest else f"{pkg}.{rest}"
        elif n == 2:
            target = "app" if not rest else f"app.{rest}"
        else:
            # 超过两级相对导入(本项目不存在)
            out_lines.append(line)
            continue
        out_lines.append(f"{indent}from {target} import {names}")
        changed += 1
    py.write_text("\n".join(out_lines), encoding="utf-8")

print(f"已转换相对导入 {changed} 处")
