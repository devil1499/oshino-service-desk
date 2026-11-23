# 中文模拟工单与处理记录

来源：[SupportOps Agent 初始知识库样例](https://github.com/ChEnylnti/SupportOps-Agent/tree/main/docs/knowledge_base_sample)。其说明称数据是合成演示样例，可用于项目原型和 GitHub 展示。这里从 20 条模拟工单中选出原始状态为“已解决”或“已关闭”的 14 条；另 6 条尚未解决，未纳入可检索的处理案例。

每个 Markdown 文件对应一条工单，保留原始问题标题和 `solution` 处理记录。原始记录大多只有一句话；有同仓库 FAQ、SOP 或 IT 指南支持的案例，另列“相关标准排查步骤”。该节是流程参考，不代表该工单实际上逐步执行过。不要把这些演示内容当作本系统真实历史工单、实际客户规则或已验证的处理结果。

## 放入当前知识库

1. 在“基础管理”中单独建一个演示产品（例如“SupportOps 演示平台”）及需要的模块、分类；避免混入“演示协作平台”的真实产品规则。
2. 在“知识库 → 录入或上传文档”逐个选择本目录中以 `T` 开头的 `.md` 文件；确认标题和正文后保存、发布。不要上传本说明文件。
3. 按项目第六部分教程停止后端、重建知识索引、重新启动；再用具体问题检索，核对引用的原文与处理记录。

在项目根目录执行 Docker 命令：

```bash
docker compose --env-file .env.docker stop backend
docker compose --env-file .env.docker run --rm --no-deps backend python -m app.rebuild_knowledge --replace
docker compose --env-file .env.docker up -d --wait backend
```

本目录只准备导入文件，没有自动写入数据库或发布知识。源仓库未提供独立许可证文件；若以后公开重新分发，先核对源仓库的使用说明与授权范围。
