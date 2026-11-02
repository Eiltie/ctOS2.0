"""反馈表：用户在页面上提交的意见与建议。

================================ 关于这个文件 ================================
独立功能，和主流程解耦。反馈内容只给项目维护者看，不对外展示。

不需要了这个功能，删掉下面这几处即可，其余代码不受影响：
  1. databases/db_feedback.py       （本文件）
  2. databases/feedback_view.py     （命令行查看工具）
  3. api/main.py 里「# ===== 反馈 =====」到文件末尾的那一段
  4. core/db.py 的 module_builders 里那一行（不删也会自动跳过）
  5. 前端：static/js/common/feedback.js、index.html 里的按钮块、modules.css 里的样式

数据表 feedback 独立存在，不影响其他任何表。
============================================================================
"""

from core.db import execute, execute_returning_id, query, query_one

# 反馈表
#
# 设计要点：
#   - content 和 contact 都用空字符串而不是 NULL，查询时不用判断两遍
#   - rating 存中文原文（"很满意" 等），不存 1-5 的数字：
#     统计时直接看文字更直观，也不用维护一张「数字 → 含义」的映射
#   - tenant_id 可以为空：没登录也能提交，登录了就顺带记下是谁
#   - user_agent 留着排查问题用（手机还是电脑、什么浏览器）
CREATE_FEEDBACK_TABLE = """
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content     TEXT        NOT NULL DEFAULT '',
    contact     TEXT        NOT NULL DEFAULT '',
    rating      TEXT,
    page        TEXT        NOT NULL DEFAULT '',
    tenant_id   INTEGER,
    user_agent  TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

# 两个索引：
#   created_at DESC —— 查看时永远按时间倒序
#   page            —— 想看「出行模块的问题多不多」时按模块筛
CREATE_FEEDBACK_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_feedback_created ON feedback (created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_feedback_page ON feedback (page)",
)

# 合法评价值。前端传上来的必须在这个集合里，否则当没填
VALID_RATINGS = ("很满意", "满意", "一般", "不太满意")

# 合法页面值，对应三个功能模块
VALID_PAGES = ("chat", "trip", "customer", "login", "")


def create_feedback_tables():
    """建表和索引，已存在就跳过。"""
    execute(CREATE_FEEDBACK_TABLE)
    for sql in CREATE_FEEDBACK_INDEXES:
        execute(sql)


def add_feedback(content: str = "", contact: str = "", rating: str | None = None,
                 page: str = "", tenant_id: int | None = None, user_agent: str = "") -> int:
    """存一条反馈，返回新记录的 id。

    注意必须用 execute_returning_id 而不是 query_one：
    query_one 只管读、不提交事务，拿它执行 INSERT 会在连接关闭时被回滚
    （踩过这个坑：接口返回 200，但库里查不到）。

    内容长度在这里再截断一次：API 层已经截过，这里兜底，
    防止以后有别的入口调进来绕过校验。
    """
    return execute_returning_id(
        "INSERT INTO feedback (content, contact, rating, page, tenant_id, user_agent) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        ((content or "")[:500], (contact or "")[:100], rating,
         page or "", tenant_id, (user_agent or "")[:300]),
    )


def list_feedback(limit: int = 20, only_with_contact: bool = False) -> list[dict]:
    """最近的若干条反馈，按时间倒序。"""
    sql = ("SELECT id, content, contact, rating, page, tenant_id, user_agent, created_at "
           "FROM feedback")
    params: tuple = ()

    if only_with_contact:
        sql += " WHERE contact <> ''"

    sql += " ORDER BY created_at DESC LIMIT %s"
    params = (limit,)

    return query(sql, params)


def feedback_stats() -> dict:
    """总量、按评价分布、按模块分布、按日期分布。"""
    total_row = query_one("SELECT COUNT(*) AS n FROM feedback")
    total = total_row["n"] if total_row else 0

    by_rating = {row["rating"] or "未填评价": row["n"]
                 for row in query(
                     "SELECT rating, COUNT(*) AS n FROM feedback "
                     "GROUP BY rating ORDER BY n DESC")}

    by_page = {row["page"] or "未标注": row["n"]
               for row in query(
                   "SELECT page, COUNT(*) AS n FROM feedback "
                   "GROUP BY page ORDER BY n DESC")}

    by_day = query(
        "SELECT to_char(created_at, 'MM-DD') AS day, COUNT(*) AS n "
        "FROM feedback GROUP BY day ORDER BY day DESC LIMIT 7")

    contact_row = query_one("SELECT COUNT(*) AS n FROM feedback WHERE contact <> ''")
    with_contact = contact_row["n"] if contact_row else 0

    return {
        "total": total,
        "by_rating": by_rating,
        "by_page": by_page,
        "by_day": by_day,
        "with_contact": with_contact,
    }


def count_feedback() -> int:
    """反馈总数，排查用。"""
    row = query_one("SELECT COUNT(*) AS n FROM feedback")
    return row["n"] if row else 0


if __name__ == "__main__":
    create_feedback_tables()
    print(f"feedback 表建好了，当前反馈数：{count_feedback()}")
