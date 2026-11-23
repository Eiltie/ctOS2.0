-- ctOS 2.0 数据库结构
--
-- 怎么用：
--   1) 程序里建（推荐）：python -X utf8 -m databases.schema
--   2) 自己用 psql 跑：  psql -U ctos_app -d ctos2 -f databases/schema.sql
--
-- 约定：
--   · 全部是 CREATE ... IF NOT EXISTS / ADD COLUMN IF NOT EXISTS，
--     跑在已有数据的库上是安全的：已存在的表一个都不会动，数据不会丢。
--   · 顺序有讲究：tenants 是全局身份表，users / sessions / trip_* 都外键引用它，
--     必须排在最前面。
--   · 改表结构时在这里加语句，不要另写 python 的建表函数。

-- ============================================================
-- 一、全局身份
-- ============================================================

-- 租户：每个注册用户一个独立租户，是所有业务表数据隔离的根
CREATE TABLE IF NOT EXISTS tenants (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT        NOT NULL,
    slug        TEXT        NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 默认租户：建表即能用的兜底，slug 唯一约束保证重复跑不会插第二行
INSERT INTO tenants (name, slug) VALUES ('默认租户', 'default')
ON CONFLICT (slug) DO NOTHING;

-- 账号：邮箱唯一，密码存 bcrypt 哈希
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email          TEXT        NOT NULL UNIQUE,
    password_hash  TEXT        NOT NULL,
    display_name   TEXT        NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at  TIMESTAMPTZ
);

-- 在线统计用：老库补列
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS ix_users_tenant ON users (tenant_id);

-- ============================================================
-- 二、闲聊
-- ============================================================

-- 会话（闲聊和角色扮演共用这张表）
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 消息：删会话时级联删
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id  INTEGER     NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT        NOT NULL,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 图片附件：消息正文只存纯文字，图单独记在这里
-- 为什么不塞进 messages.content：历史回放是 HumanMessage(content=正文)，
-- 正文里若混着图片块，模型会当成用户在念代码。
CREATE TABLE IF NOT EXISTS message_images (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id  INTEGER     REFERENCES sessions(id) ON DELETE CASCADE,
    message_id  INTEGER     REFERENCES messages(id) ON DELETE CASCADE,
    rel_path    TEXT        NOT NULL,
    mime        TEXT        NOT NULL,
    byte_size   INTEGER     NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_sessions_tenant ON sessions (tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_messages_session ON messages (session_id);
CREATE INDEX IF NOT EXISTS ix_messages_tenant ON messages (tenant_id);
CREATE INDEX IF NOT EXISTS ix_message_images_message ON message_images (message_id);
CREATE INDEX IF NOT EXISTS ix_message_images_tenant ON message_images (tenant_id);

-- ============================================================
-- 三、角色扮演
-- ============================================================

-- 哪个聊天会话用的是哪个角色（预设角色写在代码里，不存表）
CREATE TABLE IF NOT EXISTS role_play_sessions (
    session_id  INTEGER     PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_id     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 角色记住的事：按「租户 + 角色」存一篇摘要
CREATE TABLE IF NOT EXISTS role_play_memories (
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    role_id     TEXT        NOT NULL,
    summary     TEXT        NOT NULL DEFAULT '',
    rounds      INTEGER     NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, role_id)
);

-- 用户自己写的角色
CREATE TABLE IF NOT EXISTS role_play_roles (
    id           INTEGER     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name         TEXT        NOT NULL,
    emoji        TEXT        NOT NULL DEFAULT '🙂',
    tagline      TEXT        NOT NULL DEFAULT '',
    age          TEXT        NOT NULL DEFAULT '',
    gender       TEXT        NOT NULL DEFAULT '',
    personality  TEXT        NOT NULL DEFAULT '',
    deeds        TEXT        NOT NULL DEFAULT '',
    background   TEXT        NOT NULL DEFAULT '',
    extra        TEXT        NOT NULL DEFAULT '',
    speaking     TEXT        NOT NULL DEFAULT '',
    boundaries   TEXT        NOT NULL DEFAULT '',
    opening      TEXT        NOT NULL DEFAULT '',
    source       TEXT        NOT NULL DEFAULT 'custom',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 老库补列
ALTER TABLE role_play_roles ADD COLUMN IF NOT EXISTS age TEXT NOT NULL DEFAULT '';
ALTER TABLE role_play_roles ADD COLUMN IF NOT EXISTS gender TEXT NOT NULL DEFAULT '';
ALTER TABLE role_play_roles ADD COLUMN IF NOT EXISTS deeds TEXT NOT NULL DEFAULT '';
ALTER TABLE role_play_roles ADD COLUMN IF NOT EXISTS background TEXT NOT NULL DEFAULT '';
ALTER TABLE role_play_roles ADD COLUMN IF NOT EXISTS extra TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_role_sessions_tenant ON role_play_sessions (tenant_id);
CREATE INDEX IF NOT EXISTS ix_role_memories_tenant ON role_play_memories (tenant_id);
CREATE INDEX IF NOT EXISTS ix_role_roles_tenant ON role_play_roles (tenant_id);

-- ============================================================
-- 四、智能出行
-- ============================================================

-- 出行会话（一个会话一行）
CREATE TABLE IF NOT EXISTS trip_chats (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 出行的每一轮
CREATE TABLE IF NOT EXISTS trip_sessions (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    chat_id     INTEGER     REFERENCES trip_chats(id) ON DELETE CASCADE,
    title       TEXT        NOT NULL,
    turn_kind   TEXT        NOT NULL DEFAULT 'TRAVEL',
    destination TEXT        NOT NULL DEFAULT '',
    days        INTEGER     NOT NULL DEFAULT 0,
    start_date  TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 每一轮的用户原话
CREATE TABLE IF NOT EXISTS trip_user_inputs (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id   INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    trip_id     INTEGER     NOT NULL REFERENCES trip_sessions(id) ON DELETE CASCADE,
    content     TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 每一轮的 AI 产出（路线四段 + 攻略四段 + 闲聊回复）
CREATE TABLE IF NOT EXISTS trip_ai_outputs (
    id             INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      INTEGER     NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    trip_id        INTEGER     NOT NULL REFERENCES trip_sessions(id) ON DELETE CASCADE,
    weather        TEXT        NOT NULL DEFAULT '',
    spots          TEXT        NOT NULL DEFAULT '',
    itinerary      TEXT        NOT NULL DEFAULT '',
    advice         TEXT        NOT NULL DEFAULT '',
    route_plan     TEXT        NOT NULL DEFAULT '',
    route_need     TEXT        NOT NULL DEFAULT '',
    route_compare  TEXT        NOT NULL DEFAULT '',
    route_decision TEXT        NOT NULL DEFAULT '',
    route_tips     TEXT        NOT NULL DEFAULT '',
    chat_reply     TEXT        NOT NULL DEFAULT '',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 老库补列：路线四段 + 攻略建议
ALTER TABLE trip_ai_outputs ADD COLUMN IF NOT EXISTS route_need TEXT NOT NULL DEFAULT '';
ALTER TABLE trip_ai_outputs ADD COLUMN IF NOT EXISTS route_compare TEXT NOT NULL DEFAULT '';
ALTER TABLE trip_ai_outputs ADD COLUMN IF NOT EXISTS route_decision TEXT NOT NULL DEFAULT '';
ALTER TABLE trip_ai_outputs ADD COLUMN IF NOT EXISTS route_tips TEXT NOT NULL DEFAULT '';
ALTER TABLE trip_ai_outputs ADD COLUMN IF NOT EXISTS advice TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_trip_chats_tenant ON trip_chats (tenant_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS ix_trip_sessions_chat ON trip_sessions (chat_id);
CREATE INDEX IF NOT EXISTS ix_trip_user_inputs_trip ON trip_user_inputs (trip_id);
CREATE INDEX IF NOT EXISTS ix_trip_ai_outputs_trip ON trip_ai_outputs (trip_id);

-- ============================================================
-- 五、反馈
-- ============================================================

CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER     GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    content     TEXT        NOT NULL DEFAULT '',
    contact     TEXT        NOT NULL DEFAULT '',
    rating      TEXT,
    page        TEXT        NOT NULL DEFAULT '',
    tenant_id   INTEGER,
    user_agent  TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_feedback_created ON feedback (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_feedback_page ON feedback (page);
