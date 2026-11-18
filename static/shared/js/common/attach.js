// 图片附件：选图 / 粘贴 / 预览 / 上传。
//
// 为什么放在 shared/：
//   闲聊和出行都要一模一样的「选图、看缩略图、删掉、传上去」，
//   两套主题（themeA / themeB）也都各要一份。逻辑跟主题无关，
//   所以只写这一份，样式留各主题的 css 去管。
//
// 用法：
//   const dock = createAttachDock({ input: 输入框, host: 缩略图容器, onCount: 回调 });
//   dock.attachPaste(input);      // 让这个输入框支持 Ctrl+V 贴图
//   const ids = await dock.upload();   // 发消息前上传，拿到 image_ids
//   dock.clear();                  // 发完清空
//   dock.renderImages(bubble, [id]);   // 历史消息里把图渲染出来
//
// 后端约定：
//   POST /chat/attachment  （multipart，字段名 file）→ { image_id, url }
//   GET  /chat/attachment/{id}  → 图片本身（要带 Authorization）

(function () {
  // 和后端 modules/chat/attachments.py 里的限制保持一致
  const MAX_IMAGES = 3;
  const MAX_BYTES = 8 * 1024 * 1024;
  const OK_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];

  /** 图片地址：带 id 拼成取图接口 */
  function imageUrl(id) {
    return `${(typeof API !== "undefined" && API.base) || ""}/chat/attachment/${id}`;
  }

  /**
   * 把一张图渲染成 <img>。
   *
   * 为什么不用 <img src> 直接指向接口：
   *   取图要鉴权，<img> 发不了 Authorization 头。
   *   所以先用 fetch 带 token 拉成 blob，再转成 objectURL。
   *   为了不重复请求，同一张图在一个页面里只拉一次，缓存在 blobCache。
   */
  const blobCache = new Map();

  async function loadImageBlob(id) {
    if (blobCache.has(id)) return blobCache.get(id);

    const url = imageUrl(id);
    const res = await fetch(url, { headers: authHeaders({}) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    blobCache.set(id, objectUrl);
    return objectUrl;
  }

  /** 历史消息里的图片：往气泡里挂缩略图，点开能看大图 */
  async function renderImages(bubble, imageIds) {
    if (!bubble || !Array.isArray(imageIds) || !imageIds.length) return;

    const wrap = document.createElement("div");
    wrap.className = "msg-images";
    bubble.appendChild(wrap);

    for (const id of imageIds) {
      const img = document.createElement("img");
      img.className = "msg-image";
      img.alt = "图片";
      img.loading = "lazy";
      img.title = "点击查看大图";
      wrap.appendChild(img);

      try {
        img.src = await loadImageBlob(id);
      } catch (e) {
        img.alt = "图片加载失败";
        img.classList.add("is-broken");
        continue;
      }

      img.addEventListener("click", () => openLightbox(img.src));
    }
  }

  /** 点缩略图看大图 */
  function openLightbox(src) {
    const mask = document.createElement("div");
    mask.className = "lightbox-mask";

    const big = document.createElement("img");
    big.src = src;
    big.className = "lightbox-img";

    mask.appendChild(big);
    document.body.appendChild(mask);

    const close = () => mask.remove();
    mask.addEventListener("click", close);
    document.addEventListener("keydown", function onEsc(e) {
      if (e.key === "Escape") {
        close();
        document.removeEventListener("keydown", onEsc);
      }
    });
  }

  /**
   * 建一个"待发图片"的小工具栏。
   *
   * opts.input  —— 输入框元素（选图按钮会插在它旁边）
   * opts.host   —— 缩略图容器（默认画在这里）
   * opts.target—— 可选：返回"当前真正该画的容器"。
   *                出行模块有两个输入框（开场态 / 对话态），
   *                由它决定缩略图此刻挂在哪一个上面。
   * opts.onCount—— 数量变化时回调，用来更新按钮状态
   */
  function createAttachDock(opts) {
    const input = opts.input;
    const fallbackHost = opts.host;
    const pickHost = opts.target || (() => fallbackHost);
    const onCount = opts.onCount || function () {};

    // 待发的文件，还没上传；发消息时才 upload()
    let pending = [];
    let busy = false;

    // 上一次画在哪个容器上：换容器时要把旧的清干净，
    // 否则切到对话态后，开场态那份缩略图会留在屏幕上
    let lastHost = null;

    function currentHost() {
      return pickHost() || fallbackHost;
    }

    function notify() {
      onCount(pending.length);
    }

    function renderPreview() {
      const host = currentHost();

      // 换了容器：把上一个清空（只清我们自己的缩略图）
      if (lastHost && lastHost !== host) {
        lastHost.innerHTML = "";
        lastHost.classList.remove("has-items");
      }
      lastHost = host;

      if (!host) return;
      host.innerHTML = "";

      pending.forEach((item, index) => {
        const cell = document.createElement("div");
        cell.className = "attach-cell";
        cell.title = "点击移除";

        const img = document.createElement("img");
        img.src = item.preview;
        img.alt = item.file.name || "图片";
        cell.appendChild(img);

        cell.addEventListener("click", () => {
          URL.revokeObjectURL(item.preview);
          pending.splice(index, 1);
          renderPreview();
          notify();
        });

        host.appendChild(cell);
      });

      host.classList.toggle("has-items", pending.length > 0);
    }

    /** 校验后加入待发列表 */
    function addFiles(files) {
      const list = Array.from(files || []);
      if (!list.length) return;

      for (const file of list) {
        if (pending.length >= MAX_IMAGES) {
          toast(`一次最多 ${MAX_IMAGES} 张图`);
          break;
        }
        // 浏览器给的 type 可能是空的（拖拽某些文件时），按扩展名兜一下
        const type = file.type || guessType(file.name);
        if (!OK_TYPES.includes(type)) {
          toast(`「${file.name}」格式不支持，换 JPEG / PNG / GIF / WebP`);
          continue;
        }
        if (file.size > MAX_BYTES) {
          toast(`「${file.name}」超过 8 MiB，压一下再发`);
          continue;
        }
        pending.push({ file, preview: URL.createObjectURL(file) });
      }

      renderPreview();
      notify();
    }

    function guessType(name) {
      const ext = String(name || "").toLowerCase().split(".").pop();
      return { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
               gif: "image/gif", webp: "image/webp" }[ext] || "";
    }

    /** 弹系统文件选择框 */
    function pick() {
      if (busy) return;
      const picker = document.createElement("input");
      picker.type = "file";
      picker.accept = OK_TYPES.join(",");
      picker.multiple = true;
      picker.style.display = "none";
      document.body.appendChild(picker);

      picker.addEventListener("change", () => {
        addFiles(picker.files);
        picker.remove();
      });

      picker.click();
    }

    /** 让输入框支持 Ctrl+V 贴图 */
    function attachPaste(target) {
      (target || input).addEventListener("paste", (e) => {
        const items = (e.clipboardData && e.clipboardData.items) || [];
        const files = [];
        for (const item of items) {
          if (item.kind === "file" && item.type.startsWith("image/")) {
            const file = item.getAsFile();
            if (file) files.push(file);
          }
        }
        if (files.length) {
          e.preventDefault();      // 别让图片变成输入框里的乱码
          addFiles(files);
        }
      });
    }

    /** 上传所有待发图片，返回 image_ids。一张都没成功就返回空数组 */
    async function upload() {
      if (!pending.length) return [];

      busy = true;
      const ids = [];

      try {
        for (const item of pending) {
          const form = new FormData();
          form.append("file", item.file, item.file.name || "image");

          const res = await fetch(`${(typeof API !== "undefined" && API.base) || ""}/chat/attachment`, {
            method: "POST",
            headers: authHeaders({}),     // 不要手动设 Content-Type，浏览器自己带 boundary
            body: form,
          });

          if (res.status === 401) {
            handleAuthExpired();
            throw new Error("登录已过期，请重新登录");
          }
          if (!res.ok) {
            const detail = await res.text().catch(() => "");
            throw new Error(detail ? `上传失败：${detail.slice(0, 80)}` : `HTTP ${res.status}`);
          }

          const data = await res.json();
          if (data && data.image_id) ids.push(data.image_id);
        }
      } catch (e) {
        toast(e.message || "图片上传失败");
      } finally {
        busy = false;
      }

      return ids;
    }

    /** 发完消息后清空 */
    function clear() {
      for (const item of pending) URL.revokeObjectURL(item.preview);
      pending = [];
      renderPreview();
      notify();
    }

    function count() {
      return pending.length;
    }

    return { pick, attachPaste, addFiles, upload, clear, count };
  }

  /** 一句轻提示，不打断操作 */
  function toast(message) {
    let box = document.getElementById("attach-toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "attach-toast";
      box.className = "attach-toast";
      document.body.appendChild(box);
    }

    box.textContent = message;
    box.classList.add("show");

    clearTimeout(box._timer);
    box._timer = setTimeout(() => box.classList.remove("show"), 2600);
  }

  // 暴露给页面用（不带模块系统，直接挂全局）
  window.Attach = { createAttachDock, renderImages, imageUrl, MAX_IMAGES, toast };
})();
