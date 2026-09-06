# Scan Book Retypeset · 扫描书籍同版重建

[![CI](https://github.com/itsGa1axy/scan-book-retypeset/actions/workflows/ci.yml/badge.svg)](https://github.com/itsGa1axy/scan-book-retypeset/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

**让扫描书的正文真正变成清晰的排版文字，保留原来的版式、图片与 PDF 层级。**

一个遵循 [Agent Skills 开放规范](https://agentskills.io/specification) 的 agent skill，附带 PDF 探查、对照和有限结构审核工具。它指导 agent 分析、转录、排版和逐页验收；随附脚本不自动完成 OCR 或整书重建。

[English](docs/README.en.md) · [Skill 正文](SKILL.md) · [完整下载](https://github.com/itsGa1axy/scan-book-retypeset/releases) · [验证范围](docs/validation.md)

## 能做什么

- 将扫描正文重建为**真正可见的字体文字**，保留原页映射、文字区域与断行关系。
- 处理多栏、环绕图片、异形文字区、竖排、脚注、名单和目录等特殊布局。
- 保留插图、照片、印章及装饰标识；对不可分离的图内文字明确登记。
- 将公式重排为 LaTeX 等可编辑源码对应的清晰公式，逐项检查数学语义。
- 保留章节、书签父子关系、页面标签和内部跳转；分别核验已有 Tagged PDF 和可选图层。
- 用 **17 条核心质量约束**防止猜字、漏字、错误公式、损坏图片、静默降级与结构丢失。

“能复制文字”或“看起来相似”不足以通过验收。完整质量边界见 [SKILL.md](SKILL.md) 与 [质量门槛](references/quality-gates.md)。

## 安装与调用

从 [Releases](https://github.com/itsGa1axy/scan-book-retypeset/releases) 下载 `scan-book-retypeset-v1.0.0.zip`，解压后将**整个 `scan-book-retypeset` 目录**放入 agent 支持的 skills 目录。压缩包已包含参考文档、脚本和许可证。

也可以从源码安装到 Codex（macOS / Linux；目标已存在时先检查，脚本不会覆盖）：

```bash
git clone https://github.com/itsGa1axy/scan-book-retypeset.git
cd scan-book-retypeset
python3 tools/install_skill.py
```

安装器默认使用 `$CODEX_HOME/skills`，未设置时使用 `~/.codex/skills`。其他宿主或自定义位置可用 `--destination /path/to/skills`。这只复制 skill 文件，不安装 Python 依赖。支持该格式的其他 agent 可忽略 `agents/openai.yaml`。

在新一轮对话中调用：

```text
使用 $scan-book-retypeset，把这本 PDF 的前 10 个物理页重建为清晰文字。
保留插图、异形布局、分页、PDF 目录层级与内部跳转，公式用 LaTeX 重排。
交付重建 PDF、逐页对照、排版源文件与未解决问题记录。
```

首轮默认按物理页序计算，含封面和空白页；已经认可的样式继续沿用。

## 独立运行辅助工具

Python 3.9+；建议在独立环境中安装固定依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/pdf_probe.py input.pdf --pages 1-10 --output work/probe.json --render-dir work/previews
python scripts/pdf_compare.py input.pdf rebuilt.pdf --source-pages 1-10 --output work/comparison.pdf
python scripts/pdf_audit.py input.pdf rebuilt.pdf --source-pages 1-10 --report work/audit.json
```

Windows 可用 `.venv\Scripts\Activate.ps1` 激活环境，随后命令相同。辅助工具要求输入与重建页一对一、尺寸相同。拆页或透视校正需要先建立归一化参考，详见 [数据契约](references/data-contract.md)。所有输出使用新路径，不覆盖输入或已有输出。

| 工具 | 输出 | 边界 |
| --- | --- | --- |
| `pdf_probe.py` | 页面、文字、字体、图片与结构信息，可选预览 | 结构入口存在不代表有效 |
| `pdf_compare.py` | 原页与重建页并排 PDF | 对照文件不承担原书导航结构 |
| `pdf_audit.py` | 结构差异与风险 JSON | 不证明 OCR、公式、标签内部或视觉还原正确 |

审核退出码：`0` 为有限检查未发现差异，仍需人工/agent 目视复核；`1` 为发现差异；`2` 为参数或运行错误。每个工具提供 `--help`。

## 项目结构

```text
SKILL.md                  核心约束与执行入口
references/               8 份按需读取的详细规则
agents/openai.yaml        可选 Codex 界面元数据
assets/job-template.json  任务数据模板
scripts/                  PDF 检查和对照工具
tests/                    自建 PDF 回归用例
tools/                    格式检查、安装、可复现打包
docs/                     英文说明、验证边界和发布说明
.github/                  CI、发布流程及问题模板
```

## 开发与验证

```bash
python -m pip install -r requirements-dev.txt
python tools/validate_skill.py
python -m unittest discover -s tests -v
python tools/build_release.py
```

测试动态生成 PDF，使用依赖内置字体，不需要系统字体或真实书籍。CI 在 Linux / Python 3.9、3.12 和 macOS / Python 3.12 上执行；发布标签必须与 skill 版本一致。具体步骤见 [发布指南](docs/releasing.md)，修改约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 验证范围与限制

25 个 PDF CLI 回归场景覆盖输入保护、页序、书签层级及目标、链接丢失、页面标签、隐藏文字、字体与结构入口。另有安装、打包与格式检查测试。真实十页视觉样张用于改进规则，但不随公开仓库分发；复杂公式、竖排、异形布局和标签内部迁移尚未全部进行端到端书页验证。

工具只提供部分证据；完整 Tagged PDF 重建、数学语义与图片保真仍须按 skill 逐项验收。见 [验证说明](docs/validation.md)。

## 作者与许可

作者与贡献者：**[itsGa1axy](https://github.com/itsGa1axy)**。

本项目原创代码与文档采用 [MIT](LICENSE)。PyMuPDF 等外部依赖、字体和输入书籍适用各自的许可；本仓库不包含书籍页面或第三方字体文件。参见 [依赖说明](docs/dependencies.md)。
