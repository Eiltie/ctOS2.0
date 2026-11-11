// 前端全局配置：接口地址、视图顺序、打字机参数。
//
// 放在 common/ 最前面加载，其他文件只读不改。
// 换部署地址只改这里的 base。

const API = {
  base: "",            // 同源访问；前后端分域时填后端地址，例如 "http://127.0.0.1:8080"
  chat: "/chat",
  sessions: "/sessions",
  model: "deepseek-v4-flash"
};

// 三个视图的切换顺序，switchView() 按这个决定谁显示谁隐藏
const VIEW_ORDER = ["chat", "trip", "customer"];

// 每个视图右上角的状态标签 + 底部端点 + 输入框提示语
const VIEW_STATUS = {
  chat:     { tag: "LANGGRAPH",   endpoint: "POST /chat",          ph: "向 ctOS 发送指令... (Enter 发送)" },
  trip:     { tag: "TRIP AGENT",  endpoint: "POST /trip/chat",     ph: "告诉我想去哪儿玩..." },
  customer: { tag: "RAG",         endpoint: "POST /customer/chat", ph: "问一个关于本项目的问题..." }
};

// 闲聊空状态的欢迎语
const WELCOME = "你好。ctOS 在线。";

// 打字机的渲染参数：每帧间隔、最低/最高字符每秒
const TYPE_FRAME_MS = 16;
const TYPE_MIN_CPS  = 45;
const TYPE_MAX_CPS  = 220;
