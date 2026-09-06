# 修改与反馈

当前作者与贡献者署名：**itsGa1axy**。

提交问题时提供最小复现步骤、Python / PyMuPDF 版本、退出码与预期行为。优先使用自建 PDF；不要在 issue 中上传未授权的书籍、个人信息、密码或令牌。

修改 skill 时保留用户授权范围，避免把某一本书的偶然特征写成普遍规定。详细规则放在对应 references 文件中，入口保留清晰链接。新增验收规则必须能说明实际失败模式。

修改脚本时维持输入不可覆盖、页码显式指定、输出 JSON、非交互和不联网的行为。为实际行为变化补回归用例，不以检查文案包含某个词替代行为测试。

在提交前运行：

```bash
python -m pip install -r requirements-dev.txt
python tools/validate_skill.py
python -m unittest discover -s tests -v
python tools/build_release.py
```

PR 描述包含触发问题、修改后的行为、实际验证和已知限制。版本与发布步骤见 [发布指南](docs/releasing.md)。项目采用 [MIT](LICENSE)。
