"""客服的检索系统（RAG）。

只有客服模块用，所以放在 customer/ 里面，不占公共层。

   rag_config.py   配置：文档目录、向量库目录、模型名、切块参数
   rag_ingest.py   入库：docs/corpus/ 的 Markdown → 切块 → 向量化 → Chroma
   rag_store.py    加载：进程内唯一一份 Chroma 集合 + BM25 索引
   rag_search.py   检索：关键词（BM25）→ 向量 → 混合打分
   rag_eval.py     测评：40 题题库跑一遍，看命中率

常用命令（都在项目根目录执行）：

    python -X utf8 -m modules.customer.rag.rag_ingest     # 改了知识库文档后重新入库
    python -X utf8 -m modules.customer.rag.rag_eval       # 跑检索测评
    python -X utf8 -m modules.customer.rag.rag_store      # 检查知识库是否就绪
"""
