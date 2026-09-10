# ChatCut 安装事实来源（AI 与人都读这份）

本文件是 `scripts/ensure-chatcut.py` 的依据与兜底手册。脚本跑不通时照这里手工来。

## 0. 一句话：要装两样东西

| # | 装什么 | 能否全自动 | 说明 |
|---|---|---|---|
| 1 | **ChatCut 客户端**（macOS `.app` / Windows `.exe`） | ⚠️ 半自动 | 安装包在**登录后**的头像菜单里，**没有公开直链**，必须先由人登录并点 Download；之后挂载、拷贝、去隔离、启动全部自动 |
| 2 | **WorkBuddy 的 ChatCut 连接**（MCP） | ✅ 全自动 | 客户端首次启动会自动注册本地 MCP；没注册成功时脚本会手工补条目，或用下面的 OAuth 流程建云端连接 |

## 1. 官方域名：`chatcut.io`

**不是 `chatcut.com`。** 别猜域名，猜错了下到的是空气。

- 官网 / 登录：`https://chatcut.io`
- WorkBuddy 专用安装指南（**给 AI 读的纯文本**）：`https://chatcut.io/workbuddy`
- 客户端说明：`https://chatcut.io/docs/desktop-app`
- 插件说明：`https://chatcut.io/docs/agent-plugin`

> 官方指南里原话：*"If you are a WorkBuddy agent reading this file for a user, set up the ChatCut MCP server for them. Do not only describe these commands; run them when the user has asked you to set up ChatCut."*
> —— 也就是说，**AI 应该直接执行，而不是念说明书给用户听**。

## 2. 客户端安装（要人配合的一步）

官方只提供这条路（`https://chatcut.io/docs/desktop-app`）：

1. 打开 ChatCut 网页端并**登录**
2. 点右上角**头像**
3. 悬停 **Desktop App**
4. 点对应平台的 **Download**：`macOS — Apple silicon` / `macOS — Intel` / `Windows`
5. 打开下载好的安装包，走完系统提示
6. 启动客户端，登录同一个 ChatCut 账号

**没有 Linux 版。客户端也不会自动更新**——要升级就重新下一遍覆盖安装。

### 实测结论（别浪费时间重试）

以下路径均已实测 **404**，不存在公开下载接口：

```
https://chatcut.io/download                       404
https://chatcut.io/downloads                      404
https://chatcut.io/desktop                        404
https://api.chatcut.io/api/desktop/download       404
https://api.chatcut.io/api/desktop-app/download   404
```

客户端 `.app` 包内也**没有** appcast / 自更新地址（已翻过 `Contents/Resources`）。
所以「AI 直接 curl 下载 dmg」这条路**物理上不通**，不要反复尝试。

### 平台落点

| 平台 | 装完在哪 |
|---|---|
| macOS | `/Applications/ChatCut.app`（或 `~/Applications/ChatCut.app`） |
| Windows | `%LOCALAPPDATA%\Programs\ChatCut\ChatCut.exe`，也可能在 `Program Files` |

### macOS 安装要点

```sh
hdiutil attach -nobrowse -noverify -plist "ChatCut.dmg"   # 取挂载点
ditto "/Volumes/ChatCut/ChatCut.app" "/Applications/ChatCut.app"
hdiutil detach "/Volumes/ChatCut" -quiet -force
xattr -dr com.apple.quarantine /Applications/ChatCut.app   # 不去隔离会被 Gatekeeper 拦
open -a /Applications/ChatCut.app
```

## 3. MCP 连接

### 3.1 优先：让客户端自己注册（本地 MCP）

客户端首次启动会把本地 MCP 注册进支持的 agent。WorkBuddy 的配置在：

```
~/.workbuddy/mcp.json
```

> **重要：文件名就是 `mcp.json`，没有前导点。**
> 不要写成 `~/.workbuddy/.mcp.json`。写错文件名是「chatcut 服务一直不出现」的头号原因。

本地 MCP 程序位置：

| 平台 | 路径 |
|---|---|
| macOS | `~/Library/Application Support/ChatCut/chatcut-mcp` |
| Windows | `%APPDATA%\ChatCut\chatcut-mcp.exe` |

对应条目长这样（`chatcut_desktop`）：

```json
{
  "mcpServers": {
    "chatcut_desktop": {
      "command": "/Users/<你>/Library/Application Support/ChatCut/chatcut-mcp",
      "env": { "CHATCUT_MCP_CLIENT": "workbuddy" }
    }
  }
}
```

### 3.2 兜底：云端 MCP（手动 OAuth）

只有当本地 MCP 死活注册不上时才走这条。WorkBuddy **没有内置 `mcp login`**，要手工跑 OAuth 2.0：

**前提**：`curl` 和 `python3` 都在 `PATH` 里。

**第 1 步 · 注册 OAuth 客户端**（返回 `client_id`，回调端口固定 `52961`）

```sh
curl -s -X POST "https://api.chatcut.io/auth/mcp/register" \
  -H "Content-Type: application/json" \
  -d '{
    "client_name": "workbuddy",
    "redirect_uris": ["http://127.0.0.1:52961/callback"],
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "token_endpoint_auth_method": "none",
    "scope": "openid profile email offline_access"
  }'
```

**第 2 步 · 生成 PKCE 参数**

```sh
python3 -c "
import secrets, hashlib, base64
verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode()
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
print(f'VERIFIER={verifier}')
print(f'CHALLENGE={challenge}')
"
```

**第 3 步 · 授权**（会自动打开浏览器，登录后点 Allow ChatCut，本地端口收 code）

```sh
python3 -c "
import http.server, socketserver, urllib.parse, webbrowser
URL = 'https://api.chatcut.io/auth/mcp/authorize?response_type=code&client_id=<CLIENT_ID>&code_challenge=<CHALLENGE>&code_challenge_method=S256&redirect_uri=http://127.0.0.1:52961/callback&scope=openid+profile+email+offline_access&state=chatcut'
captured = {}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if 'code' in q:
            captured['code'] = q['code'][0]
            self.send_response(200); self.end_headers()
            self.wfile.write(b'ChatCut authorized - you can close this tab.')
    def log_message(*a): pass
with socketserver.TCPServer(('127.0.0.1', 52961), H) as s:
    s.timeout = 1
    webbrowser.open(URL)
    print('Opened the authorization page. Log in and click Allow ChatCut...')
    for _ in range(180):
        s.handle_request()
        if 'code' in captured: break
print('CODE=' + captured.get('code', '(timed out - copy the URL above and open it manually)'))
"
```

**第 4 步 · 换 token**

```sh
curl -s -X POST "https://api.chatcut.io/auth/mcp/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=<AUTHORIZATION_CODE>" \
  -d "redirect_uri=http://127.0.0.1:52961/callback" \
  -d "client_id=<CLIENT_ID>" \
  -d "code_verifier=<VERIFIER>"
```

**第 5 步 · 写进 `~/.workbuddy/mcp.json`**（已有 `mcpServers` 就合并，别覆盖）

```json
{
  "mcpServers": {
    "chatcut": {
      "type": "http",
      "url": "https://api.chatcut.io/api/external-mcp/mcp",
      "headers": { "Authorization": "Bearer <access_token>" }
    }
  }
}
```

**第 6 步 · 验证**

```sh
curl -s -X POST "https://api.chatcut.io/api/external-mcp/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"workbuddy","version":"1.0.0"}}}'
```

返回 server capabilities 和工具列表即成功。

### 3.3 token 过期

access_token 约 **1 小时**过期。报 `Unauthorized` 就刷新：

```sh
curl -s -X POST "https://api.chatcut.io/auth/mcp/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=refresh_token" \
  -d "refresh_token=<REFRESH_TOKEN>" \
  -d "client_id=<CLIENT_ID>"
```

把新的 `access_token` 换进 `mcp.json` 的 `Authorization` 头。refresh_token 也过期了就重跑第 2 步。

## 4. 常见坑

| 现象 | 原因 / 解法 |
|---|---|
| `chatcut` 服务在 WorkBuddy 里不出现 | `mcp.json` 文件名写错了（多写了点）；或没重启 WorkBuddy |
| 装了但工具列表里没有 ChatCut | **必须新开会话**，工具列表在会话开始时固定，旧会话拿不到 |
| 请求返回 `Unauthorized` | access_token 过期（约 1 小时），刷新即可 |
| 客户端装完打不开 | macOS 去隔离：`xattr -dr com.apple.quarantine /Applications/ChatCut.app` |
| 授权页超时 | 别同时开多个授权流程；让安装流程从失败的那一步继续 |

## 5. 安全提醒

- **不要把 cookie、access_token、账号密码粘进对话里。** 授权一律在浏览器页面完成。
- 脚本写 `mcp.json` 前会自动备份成 `mcp.json.bak-<时间戳>`。
- macOS 覆盖安装前会把旧版改名成 `ChatCut.app.bak-<时间戳>`，不直接删除。
