# 依赖与许可边界

本仓库原创代码和文档采用 MIT，版权署名为 itsGa1axy。第三方依赖未被重新许可，也未打包进 Release ZIP。

- **PyMuPDF 1.26.5**：PDF 读取、字体和渲染功能；安装时取得的发行包包含其自身许可与相关第三方声明。参见 [官方许可说明](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)。本项目的 MIT 不改变该依赖的授权条件。
- **PyYAML 6.0.2**：仅用于开发阶段读取 YAML 元数据，参见 [上游项目](https://github.com/yaml/pyyaml)。
- 测试从 PyMuPDF 内置字体生成临时文件，不向仓库或发布包提交字体程序。
- 实际转换的书籍、图片、字体由使用者按各自授权提供，不属于本项目的 MIT 授权对象。

Skill 格式依据 [Agent Skills](https://agentskills.io/specification)，不是复制官方 validator 的实现。更详细的规范来源在 [references/standards.md](../references/standards.md)。
