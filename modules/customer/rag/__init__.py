"""客服的检索系统。只有客服模块用，所以放在 customer/ 里面。

    rag_config.py   配置：文档目录、向量库目录、模型名、切块参数
    rag_ingest.py   入库：把 docs/corpus/ 的 Markdown 切块、向量化、写进 Chroma
    rag_store.py    加载：进程内只加载一次 Chroma 集合和 BM25 索引
    rag_search.py   检索：关键词 + 向量 + 混合打分
    rag_eval.py     测评：跑 40 题题库看命中率

改了知识库文档后要重新入库，然后重启服务：

    python -X utf8 -m modules.customer.rag.rag_ingest
"""
