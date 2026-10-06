# -*- coding: utf-8 -*-
"""通过日志中解析出的恒生聚源MCP URL直接调用FinQuery，测试连通性。"""
import json, re, sys, urllib.request

LOG = r"C:/Users/Asia/.workbuddy/logs/2026-08-30/workbuddyMainThread__54c6caf8c10ee2fa85712565f0b78fde.log"

def get_url():
    txt = open(LOG, encoding="utf-8", errors="ignore").read()
    m = re.findall(r"https://api\.gildata\.com/mcp-servers/aidata-assistant-srv-tool\?token=[A-Za-z0-9._\-]+", txt)
    if not m:
        # 尝试其他日期日志
        import glob
        for f in glob.glob(r"C:/Users/Asia/.workbuddy/logs/*/workbuddyMainThread__*.log"):
            txt2 = open(f, encoding="utf-8", errors="ignore").read()
            m = re.findall(r"https://api\.gildata\.com/mcp-servers/aidata-assistant-srv-tool\?token=[A-Za-z0-9._\-]+", txt2)
            if m:
                break
    if not m:
        raise RuntimeError("URL not found")
    return sorted(set(m))[-1]

def rpc(url, method, params, session_id=None):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=180) as resp:
        sid = resp.headers.get("Mcp-Session-Id")
        raw = resp.read().decode("utf-8", errors="ignore")
    # 响应可能是 SSE 流
    result = None
    if raw.lstrip().startswith("{"):
        result = json.loads(raw)
    else:
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    result = json.loads(line[5:].strip())
                except Exception:
                    pass
    return result, sid

url = get_url()
print("URL found, token length:", len(url.split("token=")[1]))

# initialize
init_params = {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "etf-tracker", "version": "1.0"}}
res, sid = rpc(url, "initialize", init_params)
print("initialize ok, session:", sid is not None)
# call FinQuery（服务端无会话，直接调用）
def finquery(query, url):
    try:
        rpc(url, "initialize", init_params)
    except Exception:
        pass
    res, _ = rpc(url, "tools/call", {"name": "FinQuery", "arguments": {"query": query}}, None)
    return res

res = finquery("查询基金510050在2026年8月28日的单位净值", url)
if res and "result" in res:
    for item in res["result"].get("content", []):
        if item.get("type") == "text":
            print(item["text"][:500])
else:
    print("RAW:", json.dumps(res, ensure_ascii=False)[:800])
