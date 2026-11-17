// SSE 事件解析器：把 HTTP 流里的 "data: {...}\n\n" 切成一个个事件对象。
//
// 三种模块都用它：闲聊走纯文本流，出行和客服走 SSE，解析方式一致。
//
// 用法：
//   const parser = createSseParser((ev) => { ... });
//   parser.push(decoder.decode(chunk, { stream: true }));
//   parser.end();

function createSseParser(onEvent){
  let buf = "";

  const emit = (raw) => {
    let name = "";
    const dataLines = [];

    raw.split(/\r?\n/).forEach((line) => {
      if (!line || line.startsWith(":")) return;
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);

      if (field === "data") dataLines.push(value);
      else if (field === "event") name = value.trim();
    });

    if (!dataLines.length && !name) return;
    const data = dataLines.join("\n");

    let payload = null;
    try{
      payload = JSON.parse(data);
    }catch(e){
      payload = null;
    }

    if (payload && typeof payload === "object"){
      if (!payload.kind && name) payload.kind = name;
      onEvent(payload);
      return;
    }

    // 不是 JSON 的纯文本 data：当成一次 TOKEN
    const kind = name || "TOKEN";
    if (data) onEvent({ kind, text: data });
    else if (name) onEvent({ kind });
  };

  return {
    push(chunk){
      if (!chunk) return;
      buf += chunk;
      let idx;
      while ((idx = buf.search(/\r?\n\r?\n/)) >= 0){
        const raw = buf.slice(0, idx);
        buf = buf.slice(idx).replace(/^\r?\n\r?\n/, "");
        emit(raw);
      }
    },
    end(){
      if (buf.trim()) emit(buf);
      buf = "";
    }
  };
}
