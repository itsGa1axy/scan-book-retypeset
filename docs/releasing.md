# 版本发布

本项目发布的是可安装的 Agent Skill ZIP，不是 PyPI 库，也不是自动转换整书的应用。

1. 更新 `SKILL.md` 的 `metadata.version` 与 `CHANGELOG.md`，并同步 README 下载文件名。
2. 安装 `requirements-dev.txt`，运行格式检查和完整测试。
3. 运行 `python tools/build_release.py`；`dist/` 中生成版本化 ZIP 和 `SHA256SUMS`。ZIP 只包含 skill 运行资源及 MIT 许可证，不含测试数据、书页、系统字体或本地路径配置。
4. 将修改提交并推送 `main`，等待 CI 成功。
5. 创建与版本一致的标签，例如 `git tag v1.0.0`，再 `git push origin v1.0.0`。
6. `release.yml` 核验标签、重新测试和打包，使用标签对应源码创建 GitHub Release，并上传 ZIP 与校验和。

发布流程只在标签推送时写入 Release；普通分支和 PR 的 CI 权限为只读。若 Release 已存在，流程拒绝覆盖；修复内容应发布新版本。首次发布或失败排查时查看 Actions 中具体作业结果，不把推送成功当成发布成功。

本地打包采用固定文件顺序、时间戳和权限；同一版本相同输入应生成相同字节。SHA-256 用于校验下载完整性，不代替代码签名或来源审核。

CI 结构参考 [GitHub 官方 Python 测试指南](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)。
