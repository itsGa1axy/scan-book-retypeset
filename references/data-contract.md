# 数据契约

这是本 skill 的重建数据约定，**不是 Agent Skills 开放标准的一部分**。允许使用等价结构；字段的含义和可追溯性不能丢失。

## 推荐目录

```text
job/
  work/                 # OCR、裁片、渲染与临时构建
  source/
    job.json            # 输入摘要、页序映射、区域与校验状态
    styles.json         # 字体/字号/颜色/基线/间距/替代说明
    content.json        # 原始OCR、校订文本、逻辑段落和视觉换行
    layout.*            # 可编辑页面源：TeX/HTML+CSS/程序/布局数据
    formulas/           # 实际存在的公式源码与索引
    images/             # 实际复用的图像资源
  rebuilt.pdf
  comparison.pdf
  review.json
```

不创建没有用途的空目录；没有公式时不制造公式文件。小任务可合并 JSON。排版源至少应能明确说明如何从文字、样式、坐标与素材重新生成输出，不能只交一串无法复现的逐字坐标。

## Job 字段

- `schema_version`：本数据格式版本，当前 `1.0`。
- `source`：文件名称、SHA-256、页数；可分享副本不需要包含个人绝对路径。
- `request`：请求页序、用户的图片/字体/公式/几何选择、已认可样张的样式配置。
- `coordinate_system`：统一坐标约定，推荐 `display-top-left-pt`。
- `pages`：输出页到源页的映射，以及实际 `regions` 与状态。
- `tool_versions`：OCR、渲染、排版引擎的实际版本和重要配置，不虚构版本。
- `uncertainties`：待决项列表；没有时为空数组，不把它省略成无法判断的状态。
- `structure`：`heading_tree`、`outline_tree`、`page_labels`、`named_destinations`、`links`、`tags` 与 `optional_content`；不存在时明确写 null/空数组。保留原目标、输出目标、父子关系及修复证据。

## 页面字段

- `source_page` / `output_page`：1 起始物理页序。
- `printed_label`：原书页码字符串或 null；可能是罗马数字，不强制转换为整数。
- `source_box`、`output_size`、`source_rotation`：保留原始框与工作画布。
- `transform`：源到输出的仿射矩阵，或对应的透视/网格变形资源。无变换写单位矩阵。
- `regions`：内容区域的有序列表；另设 `reading_order` 表示逻辑顺序。
- `status`：`pending` / `rebuilt` / `reviewed` / `needs-review`。
- `structure_status`：书签、标签、链接、图层分别记录 preserved/rebuilt/not-present/pending；不能用单一“结构已保留”覆盖所有情况。
- `evidence`：已检查的渲染/裁片路径、检查项和结论。

拆页、拼页或图像展平可使用多个 `source_regions` 建立映射，保留每个源区域及变换。随附对照/审核 CLI 只支持一对一同尺寸页：复杂映射先生成独立的对照参考 PDF，原始映射仍需保存。

## 区域字段

| 字段 | 含义 |
| --- | --- |
| `id`、`kind` | 稳定ID；text/formula/table/image/graphic/annotation 等 |
| `source_polygon`、`output_polygon` | 坐标明确的区域多边形，不只用笼统“在左边” |
| `protected` | 是否禁止清理或覆盖的图片/内容区 |
| `raw_text`、`corrected_text` | 原始识别与有依据的修订；图形可为 null |
| `confidence` | 引擎原始置信信息或 null；不同引擎不可假装同一标尺 |
| `style_id` | 指向样式表，不将 OCR 抖动当真实样式 |
| `lines` | 视觉行、基线、区间、运行方向，可附 glyph/word 坐标 |
| `render_mode` | font-text / native-reuse / vector-formula / original-graphic / unresolved |
| `asset` / `latex_source` | 实际素材或公式文件，不写伪链接 |
| `corrections` | 原值、新值、原因、对应原图证据 |
| `status`、`evidence` | 重建与复核状态分开 |

逐字排版的数据还应保存 Unicode 字符/组合、font face、字重、字号、位置、advance、旋转及所属行。行内 RTL/连写应保存 shaping 后字形与原 Unicode 文本的对应，不能只保存孤立码点。

## 例外与未决项

每条至少含 `page`、`region_id`、`issue`、`evidence`、`action`、`status`。例如“装饰性出版社书法标识保留原图”与“正文三个字无法辨认，暂留截图”必须是不同完成状态。

图片保护数据要足以检查清理 mask 与图片的交集。仅记录“图片已保留”不足以复核；至少记录源区域、输出区域和实际执行的变换/清理范围。

字体资源可能不允许重新分发，源文件记录字体名称、face 索引、获取方式或系统来源及替代样式；不把整份字体程序作为默认资源分发。
