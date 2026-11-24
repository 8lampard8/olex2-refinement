# olex2-refinement

一个面向 Codex 的中文小分子单晶 X 射线精修 skill。给它已有 Olex2 工程或配套的 INS/RES 和 HKL，可以从原模型复算开始，按差值密度和化学证据处理氢、无序、占位和溶剂，最后交付可重新打开的工程和 CIF。结构判断由操作者结合数据完成。

## 安装

已安装 Git 和 Codex 的 Windows 用户可在 PowerShell 中运行：

```powershell
$skills = Join-Path $HOME '.codex/skills'
New-Item -ItemType Directory -Force $skills | Out-Null
git clone https://github.com/8lampard8/olex2-refinement.git (Join-Path $skills 'olex2-refinement')
```

若使用自定义 `CODEX_HOME`，把仓库克隆到该目录的 `skills/olex2-refinement` 下。开启新会话后示例请求为：

> 使用 $olex2-refinement 精修附件里的晶体。请先复现原模型，再核对末端无序，并交付可复算的工程、CIF 和修改前后指标。

## 用 Olex2 自带的蔗糖样例复算

无界面脚本使用 **Windows 版 Olex2 1.5 的 olex2.refine** 和外部 Python 3。比较 CIF/FCF 另需 Python 的 Gemmi 包。安装了其他版本或要使用 SHELXL 时，可在 Olex2 图形界面按 [操作步骤](SKILL.md) 执行。仓库不分发 Olex2、SHELXL 或衍射数据。[官方蔗糖教程](https://www.olexsys.org/olex2/docs/tutorials/sucrose/refining/)

在仓库根目录运行以下命令。示例从 Olex2 安装目录读取输入，在临时目录创建两个独立试验；如果 Olex2 装在别处，修改第一行。

```powershell
$ox = Join-Path $env:ProgramFiles 'Olex2-1.5'
$sample = Join-Path $ox 'sample_data/sucrose/sucrose.ins'
$trial = Join-Path $env:TEMP ('olex2-demo-' + [guid]::NewGuid())
python -m pip install gemmi
python scripts/run_refine.py $sample --olex-dir $ox --out "$trial/first"
python scripts/run_refine.py "$trial/first/sucrose.res" --olex-dir $ox --out "$trial/repeat"
python scripts/compare_cif.py "$trial/first/sucrose.cif" "$trial/repeat/sucrose.cif"
```

在本仓库发布时的 Windows 实测中，两轮都得到 2,691 条反射，R1(gt) 为 0.0280，wR2(all) 为 0.0647，GooF 为 1.0453。两个 FCF 的 h,k,l 逐条计数相同。这组数值用于辨认该样例和设置；不同样例版本或引擎设置可能产生不同结果。

## 输入和适用范围

- 脚本接收自包含的常规独立原子模型、普通 `HKLF 4`、`ACTA`、`LIST 4` 和同名 HKL。在全新目录暂存模型，运行日志在 `engine.log` 和 `console.log`，引擎命令在 `commands.txt`。目录已存在时脚本退出。输入来自陌生来源时，先检查模型与附属文件。
- 普通无掩膜模型可省略 `--mask`。已有掩膜时，`--mask reuse` 使用同基名 FAB，`--mask recompute` 重新计算。只有确认工程原先采用的 SUMP 方式才传入相应的 `--sump-mode`。运行前检查 FAB、晶胞和反射设置属于同一模型；运行后从日志、CIF 和差值图核对实际处理。
- 无界面脚本使用 Olex2 1.5 的本地服务接口，其可用性随安装版本而异。涉及孪晶、HKLF 5、外部包含文件、自定义散射因子或额外设置时，在 Olex2 中操作完整工程并检查设置。脚本完成一次最小二乘计算；化学归属、收敛质量和 checkCIF 警报需要分别核验。

[精修判断与命令](references/refinement.md) · [模型核验与交付](references/verification.md) · [MIT 许可证](LICENSE)
