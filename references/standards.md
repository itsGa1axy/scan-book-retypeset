# 通用标准与兼容性

核对日期：2026-09-06。

## 采用的开放格式

以 [Agent Skills 官方格式规范](https://agentskills.io/specification) 为格式依据，另参考官方的 [编写最佳实践](https://agentskills.io/skill-creation/best-practices) 与 [脚本指南](https://agentskills.io/skill-creation/using-scripts)。它们分别定义格式、提供写作建议和说明可执行资源设计，不把三者都当作强制格式要求。

### 格式要求

- skill 是包含 `SKILL.md` 的目录；文件由 YAML frontmatter 和 Markdown 正文组成。
- `name` 和 `description` 必填；名称与目录一致，采用小写字母、数字及连字符，不首尾连字符或连续双连字符。
- 名称最多 64 字符；描述非空且最多 1024 字符。附加 `metadata` 使用字符串键值。
- `license`、`compatibility` 等为可选字段。没有授权依据不随意添加开源许可证；不为显得完整而填写无关元数据。

### 官方建议与本包选择

- 正文简明，详细规则按需读取；官方建议主文件小于 500 行、约 5000 token，不是“越接近上限越好”。
- 核心约束留在 `SKILL.md`，条件流程放 `references/`，CLI 放 `scripts/`；所有资源由主文件直接指向，避免深层引用链。
- 描述写明触发范围，避免普通 PDF 摘要、翻译与 OCR 隐藏层任务误触发。
- 严格约束集中于内容、图像、公式、结构与验收；具体 OCR/排版引擎允许在等价且已验证的路径间选择。
- 脚本不交互等待、不联网、不修改输入，提供 `--help` 和 JSON 结果；输入路径显式传入，不硬编码机器用户名或书名。

## 可移植部分与宿主扩展

`SKILL.md`、`references/`、`scripts/` 与 `assets/` 不依赖某一家 agent 的工具名称。脚本使用 Python 与 PyMuPDF，分别声明依赖；其他引擎可依照同样的验收契约实现。

`agents/openai.yaml` 是本包附带的可选 Codex 界面元数据，不属于通用必需格式。其他宿主可以忽略它，通用执行指令不引用该文件。没有使用实验性 `allowed-tools` 把权限写死，也没有把宿主专用调用语法写入核心工作流。

skill 目录格式不定义所有宿主的安装目录。复制完整目录到所用 agent 支持的位置，保留相对路径；不要只复制 `SKILL.md` 而漏掉引用资源。

## 验证方式

官方规范推荐 [skills-ref](https://github.com/agentskills/agentskills/tree/main/skills-ref) 验证命名与元数据：

```bash
skills-ref validate ./scan-book-retypeset
```

另做相对链接存在性检查、脚本实际运行和行为评测。通过格式验证只证明文件结构合规，不证明排版或 OCR 质量。

## 技术参考与证据边界

- [PyMuPDF 页面 API](https://pymupdf.readthedocs.io/en/latest/page.html)：提取、图像放置和页面操作的实际参数以所用版本为准。
- [PyMuPDF 文本追踪](https://pymupdf.readthedocs.io/en/latest/functions.html#Page.get_texttrace)：用于检查文字绘制模式，不能单独证明肉眼可见。
- [PyMuPDF 文档 API](https://pymupdf.readthedocs.io/en/latest/document.html)：书签、标签、命名目标等须分别处理。
- [PyMuPDF 可选内容支持](https://pymupdf.readthedocs.io/en/latest/recipes-optional-content.html)：OCG 与普通扫描图层不同。
- [unicode-math 项目](https://ctan.org/pkg/unicode-math)：可选的 Unicode 数学排版路径，不是所有任务强制依赖。

同版重建的质量门槛是本 skill 根据实际样张和用户要求制定的工作约束，并非 Agent Skills 标准规定的 PDF 质量认证。
