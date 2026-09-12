# 验证记录 · 2026.09.12

- 来源：此前审计、修复和重构后的 `CGYRO_99949_compare_refactored.zip` 的已校验代码/设置模板。
- 新工程包含 CGYRO_TGLF_scan、OMFITtemplates 两个顶层模块；计算数据文件数为 0，仅保留空数据容器。所有 OMFITsave 文件引用可解析。
- 清空旧案例选择、结果缓存、个人运行路径、部署设置及相应动态表达式；MainSettings 使用中性默认值，不包含旧命令历史、个人邮箱和服务器配置。
- 增加 CGYRO/TGLF 主界面的 Templates / GitHub 按钮；通过相邻模块的 GUI.run 进入管理器，使 OMFITlib 导入在正确的模块命名空间执行。
- 修复 OMFITsave 的树输出顺序，按深度优先遍历保存模块及其 SETTINGS；验证 OMFIT 原生工程信息读取器的关联规则。
- GitHub 版本说明兼容 LF、CRLF 和 CR 换行，避免元数据被忽略。
- 管理器 89 项测试在 Ubuntu 22.04 / Python 3.10 / Tk 8.6 / WSLg 中通过，包括真实 Tk 操作、本机 HTTP GitHub 模拟、数据保留、失败恢复、模块元数据顺序和版本说明换行格式。
- 对比绘图及工程集成 40 项测试通过（Python 3.12、NumPy、Matplotlib）：包含空工程启动、按钮进入相邻模块、频率/增长率/通量处理和真实绘图。
- 发布包通过所有 Python 源码编译、Python 3.9 语法兼容性、ZIP CRC 和模板 SHA-256 校验；源计算工程未修改。
- 旧绘图脚本中的部分 LaTeX 字符串在 Python 3.12 下仍有无效转义 SyntaxWarning；此次均可编译，未在本次上传中扩大修改这些脚本。

GitHub 上传后另行校验提交树和 Release 附件。本测试未启动 CGYRO/TGLF 求解器，未在完整 OMFIT 安装中做整机联调。

复现：

```sh
python3 -m unittest discover -s OMFITtemplates/tests -v
python3 -m unittest discover -s tests -v
python3 tools/build_project.py
```
