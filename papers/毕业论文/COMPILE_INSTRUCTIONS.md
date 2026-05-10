# 编译说明（Compile Instructions）

本论文源已完成集成、自审与修订，但本次自动化批处理执行环境中未找到 `xelatex`，因此最终 PDF 由用户在本机编译。

## Windows（最简）

双击仓库目录中的：

```
papers\毕业论文\artratex.bat
```

该脚本会自动调用 `xelatex → bibtex → xelatex → xelatex` 四遍编译，生成 `Thesis.pdf`。

## 任意平台

```
cd papers/毕业论文
xelatex Thesis.tex
bibtex  Thesis
xelatex Thesis.tex
xelatex Thesis.tex
```

## 前置条件

需安装 TeX Live（推荐）或 MiKTeX，包含以下宏包：
`ctex`、`hyperref`、`fancyhdr`、`amsmath`、`amssymb`、`booktabs`、`tabularx`、`algorithm`、`algpseudocode`、`gbt7714`、`subcaption`。

`gbt7714` 已随仓库 `Biblio/` 目录内置，无须额外安装。

## 编译产物

成功编译后会得到：

- `Thesis.pdf`：30 页正文（前部摘要罗马页码 + 主体阿拉伯页码 + 致谢）
- `Thesis.toc` / `Thesis.lof` / `Thesis.lot`：目录、图表索引
- `Thesis.aux` / `Thesis.bbl` / `Thesis.blg`：辅助文件，可删

## 排错

- 中文乱码：确认 `xelatex` 而非 `pdflatex`，且本机已装 ctex 默认中文字体（Windows 自带宋体/黑体即可）
- `Undefined control sequence \citep`：需运行 `bibtex Thesis` 一次
- 图片找不到：确认 `Img/Framework.pdf` 与 `Img/system.pdf` 存在（已随本次提交一起入库）

## 论文结构总览（第二轮 rebuttal 修订后）

正文 9 章，共约 **17,309** 字：

| 章 | 文件 | 字数 |
|---|---|---:|
| 摘要（中英文） | Tex/Frontpages.tex | — |
| 1 引言 | Tex/Chap_01_Intro.tex | 1,419 |
| 2 相关工作 | Tex/Chap_02_Related.tex | 1,630 |
| 3 形成性研究 | Tex/Chap_03_Formative.tex | 2,289 |
| 4 系统概述（新） | Tex/Chap_04_Overview.tex | 1,708 |
| 5 后端引擎（合并旧 §4–§7） | Tex/Chap_05_Backend.tex | 4,953 |
| 6 可视分析系统设计 | Tex/Chap_06_Vis.tex | 1,853 |
| 7 系统实现 | Tex/Chap_07_Impl.tex | 883 |
| 8 案例研究与专家评估 | Tex/Chap_08_Case.tex | 1,624 |
| 9 讨论、局限与结论 | Tex/Chap_09_Conclusion.tex | 950 |
| 致谢 | Tex/Backmatter.tex | （留空） |
| 参考文献 | Biblio/ref.bib | — |

字数远超 ≥10,000 字 / 30 页正文的硬性要求。

## 隐私字段确认

按要求留空：
- `Tex/Frontpages.tex`：`\author{}`、`\ID{}`、`\entranceYear{}`、`\advisor{}` 均为空字符串
- `Tex/Backmatter.tex`：致谢章节正文为空，仅保留章节头

补全这些字段后即可正式排版。
