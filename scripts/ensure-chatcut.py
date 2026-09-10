#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ChatCut 环境预检 / 自动安装（macOS + Windows）

本脚本给 slbb-chatcut-oneshot 技能做「第零步」环境自检：
装上技能后先跑它，缺 ChatCut 客户端就弹窗让用户登录下载，下载完自动装好。

用法：
    python3 scripts/ensure-chatcut.py            # 交互式（会弹窗，推荐）
    python3 scripts/ensure-chatcut.py --check    # 只体检，不安装、不弹窗
    python3 scripts/ensure-chatcut.py --yes      # 非交互，自动确认（批量/无人值守）

退出码：
    0  环境就绪
    2  用户选择稍后自己装（未就绪）
    3  客户端安装失败
    4  客户端已装，但 WorkBuddy 的 MCP 连接缺失
    5  当前系统不受支持

依赖：Python 3.7+（官方 WorkBuddy 安装流程本身也要求 python3）。无第三方库。
"""

import argparse
import base64
import glob
import json
import os
import plistlib
import shutil
import subprocess
import sys
import time

# ---------------------------------------------------------------- 基础工具

DOWNLOAD_WAIT_SECONDS = 1800      # 等用户登录 + 下载的最长时间（30 分钟）
APP_BOOT_WAIT_SECONDS = 25        # 等客户端首次启动并注册 MCP
WIN_INSTALL_WAIT_SECONDS = 300    # 等 Windows 安装向导跑完

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")

HOME = os.path.expanduser("~")
MCP_JSON = os.path.join(HOME, ".workbuddy", "mcp.json")

CHATCUT_SITE = "https://chatcut.io"
CHATCUT_DOC = "https://chatcut.io/workbuddy"


def out(msg=""):
    """跨平台安全打印（Windows 控制台可能不是 UTF-8）。"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def step(msg):
    out("  ▸ " + msg)


def ok(msg):
    out("  ✅ " + msg)


def warn(msg):
    out("  ⚠️  " + msg)


def fail(msg):
    out("  ❌ " + msg)


# ---------------------------------------------------------------- 弹窗

def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _ps(script):
    """用 -EncodedCommand 跑 PowerShell，彻底避开中文编码/引号问题。"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return _run(["powershell", "-NoProfile", "-EncodedCommand", encoded])


def dialog(title, message, buttons, default=0, icon="note"):
    """
    弹一个原生窗口。
    buttons: 按钮文字列表（第 1 个为默认按钮）
    返回：被点击按钮的索引；非交互环境或失败时返回 default
    """
    if os.environ.get("CHATCUT_NO_DIALOG") == "1":
        out("[dialog] %s — %s" % (title, message.replace("\n", " / ")))
        return default

    if IS_MAC:
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        safe_msg = message.replace("\\", "\\\\").replace('"', '\\"')
        btn_list = ", ".join(
            '"%s"' % b.replace("\\", "\\\\").replace('"', '\\"') for b in buttons
        )
        script = (
            'display dialog "%s" with title "%s" buttons {%s} '
            "default button 1 with icon %s"
        ) % (safe_msg, safe_title, btn_list, icon)
        r = _run(["osascript", "-e", script])
        if r.returncode != 0:
            return default
        returned = r.stdout.strip()
        # 形如：button returned:去登录下载
        clicked = returned.split(":", 1)[-1] if ":" in returned else returned
        return buttons.index(clicked) if clicked in buttons else default

    if IS_WIN:
        # MessageBox 只有 YesNo / OKCancel 这类固定组合，中文按钮文字由系统决定，
        # 所以把「每个按钮是什么意思」写进正文里，避免歧义。
        legend = "\n\n".join(
            "%s = %s" % ("是/Yes" if i == 0 else "否/No", b)
            for i, b in enumerate(buttons[:2])
        )
        body = message + "\n\n———\n" + legend
        tmp = os.path.join(
            os.environ.get("TEMP", HOME), "chatcut_dialog_%d.txt" % os.getpid()
        )
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(title + "\x00" + body)
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$raw=[IO.File]::ReadAllText('%s',[Text.Encoding]::UTF8);"
            "$p=$raw.Split([char]0);"
            "$r=[System.Windows.Forms.MessageBox]::Show($p[1],$p[0],"
            "[System.Windows.Forms.MessageBoxButtons]::YesNo,"
            "[System.Windows.Forms.MessageBoxIcon]::Information);"
            "if($r -eq 'Yes'){exit 0}else{exit 1}" % tmp.replace("'", "''")
        )
        r = _ps(ps)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return 0 if r.returncode == 0 else min(1, len(buttons) - 1)

    out("[dialog] %s — %s" % (title, message.replace("\n", " / ")))
    return default


def open_url(url):
    if IS_MAC:
        _run(["open", url])
    elif IS_WIN:
        os.startfile(url)  # noqa: S606  (Windows only)
    else:
        _run(["xdg-open", url])


# ---------------------------------------------------------------- 客户端检测

def app_candidates():
    if IS_MAC:
        return [
            "/Applications/ChatCut.app",
            os.path.join(HOME, "Applications", "ChatCut.app"),
        ]
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA", "")
        prog = os.environ.get("PROGRAMFILES", r"C:\Program Files")
        prog86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
        return [
            os.path.join(local, "Programs", "ChatCut", "ChatCut.exe"),
            os.path.join(local, "ChatCut", "ChatCut.exe"),
            os.path.join(prog, "ChatCut", "ChatCut.exe"),
            os.path.join(prog86, "ChatCut", "ChatCut.exe"),
        ]
    return []


def find_app():
    for p in app_candidates():
        if os.path.exists(p):
            return p
    if IS_WIN:
        try:
            r = _ps(
                "Get-ItemProperty "
                "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*',"
                "'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*' "
                "-ErrorAction SilentlyContinue | "
                "Where-Object {$_.DisplayName -like '*ChatCut*'} | "
                "Select-Object -ExpandProperty InstallLocation"
            )
            for line in (r.stdout or "").splitlines():
                line = line.strip()
                if line and os.path.isdir(line):
                    exe = os.path.join(line, "ChatCut.exe")
                    if os.path.exists(exe):
                        return exe
        except Exception:
            pass
    return None


def mcp_binary():
    if IS_MAC:
        p = os.path.join(
            HOME, "Library", "Application Support", "ChatCut", "chatcut-mcp"
        )
        return p if os.path.exists(p) else None
    if IS_WIN:
        base = os.environ.get("APPDATA", "")
        for name in ("chatcut-mcp.exe", "chatcut-mcp"):
            p = os.path.join(base, "ChatCut", name)
            if os.path.exists(p):
                return p
    return None


def launch_app(app):
    try:
        if IS_MAC:
            _run(["open", "-a", app])
        elif IS_WIN:
            subprocess.Popen([app], close_fds=True)
        else:
            subprocess.Popen([app])
        return True
    except Exception as e:
        warn("启动客户端失败：%s" % e)
        return False


# ---------------------------------------------------------------- 下载监听

def download_dirs():
    dirs = [os.path.join(HOME, "Downloads")]
    if IS_MAC:
        dirs.append(os.path.join(HOME, "Desktop"))  # 本机习惯：下载直接落桌面
    if IS_WIN:
        dirs.append(os.path.join(HOME, "Desktop"))
    return [d for d in dirs if os.path.isdir(d)]


def installer_patterns():
    return ["ChatCut*.dmg", "ChatCut*.pkg"] if IS_MAC else ["ChatCut*.exe", "ChatCut*.msi"]


def _installer_files():
    found = []
    for d in download_dirs():
        for pat in installer_patterns():
            found.extend(glob.glob(os.path.join(d, pat)))
    return found


def watch_for_installer(timeout=DOWNLOAD_WAIT_SECONDS):
    """
    盯着下载目录，等安装包落地。

    两道保险，防止拿到「下到一半」的文件：
    1. 只认本次流程开始之后才出现/被改写的文件（老安装包不算）
    2. 要求连续两轮大小完全一致，才认定下载结束
    """
    started = time.time()
    pre_existing = set(_installer_files())
    seen = {}

    out("")
    out("  ⏳ 正在等待安装包下载完成（最多等 %d 分钟）…" % max(1, timeout // 60))
    out("     下载目录：%s" % "、".join(download_dirs()))
    out("     下载完成后我会自动装好，中途不用你操作。")

    last_tick = 0
    while time.time() - started < timeout:
        for f in _installer_files():
            try:
                st = os.stat(f)
            except OSError:
                continue
            size = st.st_size
            if f in pre_existing and st.st_mtime <= started:
                continue                       # 之前就有的旧安装包，跳过
            if size < 5 * 1024 * 1024:
                continue                       # 明显不是安装包（或还没开始写）
            if seen.get(f) == size:
                return f                       # 连续两轮大小一致 → 下载完成
            seen[f] = size

        elapsed = int(time.time() - started)
        if elapsed - last_tick >= 30:
            last_tick = elapsed
            out("     …已等待 %d 分 %02d 秒" % (elapsed // 60, elapsed % 60))
        time.sleep(3)

    # 超时兜底：如果目录里本来就躺着一个像样的安装包，问一下要不要用它
    stale = []
    for f in _installer_files():
        try:
            if os.path.getsize(f) >= 5 * 1024 * 1024:
                stale.append(f)
        except OSError:
            pass
    if stale:
        warn("没等到新下载的安装包，但目录里有一个之前就存在的：")
        out("     %s" % stale[0])
        out("     如果要重新下载，请手动删掉它再重跑。")
    return None


# ---------------------------------------------------------------- 安装

def install_target():
    """macOS 安装落点。可用 CHATCUT_INSTALL_TARGET 覆盖（测试 / 特殊部署用）。"""
    override = os.environ.get("CHATCUT_INSTALL_TARGET")
    if override:
        return override
    return "/Applications/ChatCut.app" if IS_MAC else None


def install_mac(dmg):
    step("挂载安装包：%s" % os.path.basename(dmg))
    try:
        raw = subprocess.check_output(
            ["hdiutil", "attach", "-nobrowse", "-noverify", "-plist", dmg]
        )
        pl = plistlib.loads(raw)
    except Exception as e:
        fail("挂载失败：%s" % e)
        return None

    mount = None
    for e in pl.get("system-entities", []):
        if e.get("mount-point"):
            mount = e["mount-point"]
    if not mount:
        fail("没找到挂载点，安装包可能已损坏。")
        return None

    try:
        apps = glob.glob(os.path.join(mount, "*.app"))
        if not apps:
            apps = glob.glob(os.path.join(mount, "*", "*.app"))
        if not apps:
            fail("安装包里没有 .app，请手动安装。")
            return None
        src = apps[0]
        target = install_target()

        if os.path.exists(target):
            bak = target + ".bak-%s" % time.strftime("%Y%m%d%H%M%S")
            step("已存在旧版本，先备份到 %s" % os.path.basename(bak))
            try:
                os.rename(target, bak)
            except OSError:
                shutil.rmtree(target, ignore_errors=True)

        step("复制到 %s …" % os.path.dirname(target))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        r = _run(["ditto", src, target])
        if r.returncode != 0:
            _run(["cp", "-R", src, target])
        if not os.path.exists(target):
            fail("复制失败，请手动把 ChatCut 拖进「应用程序」。")
            return None

        step("解除隔离属性（否则会被 Gatekeeper 拦住）")
        _run(["xattr", "-dr", "com.apple.quarantine", target])
        ok("已安装：%s" % target)
        return target
    finally:
        _run(["hdiutil", "detach", mount, "-quiet", "-force"])


def install_win(installer):
    step("打开安装向导：%s" % os.path.basename(installer))
    try:
        subprocess.Popen([installer], close_fds=True)
    except Exception as e:
        fail("无法运行安装包：%s" % e)
        return None

    dialog(
        "ChatCut 安装向导已打开",
        "安装程序窗口已经弹出来了，请一路点「下一步」完成安装。\n"
        "装完我会自动检测到，你不用回来告诉我。",
        ["我知道了"],
    )

    deadline = time.time() + WIN_INSTALL_WAIT_SECONDS
    while time.time() < deadline:
        app = find_app()
        if app:
            ok("已安装：%s" % app)
            return app
        time.sleep(5)
    fail("等不到安装完成，请手动确认装好了再重跑本脚本。")
    return None


# ---------------------------------------------------------------- MCP 连接

def read_mcp():
    if not os.path.exists(MCP_JSON):
        return {"mcpServers": {}}
    try:
        with open(MCP_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        warn("mcp.json 解析失败（%s），将先备份再重建。" % e)
        return {"mcpServers": {}}


def chatcut_entries(data):
    servers = data.get("mcpServers", {}) or {}
    return {k: v for k, v in servers.items() if "chatcut" in k.lower()}


def write_mcp_entry(name, entry):
    data = read_mcp()
    data.setdefault("mcpServers", {})
    if os.path.exists(MCP_JSON):
        bak = MCP_JSON + ".bak-%s" % time.strftime("%Y%m%d%H%M%S")
        shutil.copy2(MCP_JSON, bak)
        step("已备份原配置：%s" % os.path.basename(bak))
    data["mcpServers"][name] = entry
    os.makedirs(os.path.dirname(MCP_JSON), exist_ok=True)
    with open(MCP_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    ok("已写入 %s 的 %s 条目" % (MCP_JSON, name))


def app_running():
    try:
        if IS_MAC:
            return _run(["pgrep", "-f", "ChatCut.app/Contents/MacOS/ChatCut"]).returncode == 0
        if IS_WIN:
            return _ps(
                "if(Get-Process ChatCut -ErrorAction SilentlyContinue){exit 0}else{exit 1}"
            ).returncode == 0
    except Exception:
        pass
    return False


def ensure_mcp(app, dry=False):
    """确保 WorkBuddy 里能连上 ChatCut。优先让客户端自己注册，其次手工补条目。"""
    data = read_mcp()
    entries = chatcut_entries(data)
    enabled = [k for k, v in entries.items() if not v.get("disabled")]

    if enabled:
        ok("MCP 已就绪：%s" % "、".join(enabled))
        return True, False

    if entries:
        warn("MCP 有条目但被禁用了：%s" % "、".join(entries))
        warn("去 WorkBuddy「连接器管理 → 自定义连接器」把 chatcut 打开，或删掉 disabled 字段。")
        return False, False

    if dry:
        fail("没有 ChatCut 的 MCP 连接条目。")
        out("     去掉 --check 重跑，脚本会自动补齐。")
        return False, False

    step("没找到 ChatCut 的 MCP 连接，启动一次客户端让它自动注册…")
    launch_app(app)
    deadline = time.time() + APP_BOOT_WAIT_SECONDS
    while time.time() < deadline:
        time.sleep(5)
        entries = chatcut_entries(read_mcp())
        enabled = [k for k, v in entries.items() if not v.get("disabled")]
        if enabled:
            ok("客户端已自动注册 MCP：%s" % "、".join(enabled))
            return True, True

    binary = mcp_binary()
    if binary:
        step("客户端没自动注册，改为手工补条目（本地 MCP：%s）" % binary)
        write_mcp_entry(
            "chatcut_desktop",
            {"command": binary, "env": {"CHATCUT_MCP_CLIENT": "workbuddy"}},
        )
        return True, True

    fail("找不到本地 MCP 程序，也没能自动注册。")
    out("     兜底方案（云端 MCP，需要走一次 OAuth）：")
    out("     见 references/install-chatcut.md，或读 %s" % CHATCUT_DOC)
    return False, False


# ---------------------------------------------------------------- 主流程

def preflight(app, do_install=True, assume_yes=False, dry=False):
    """返回 (就绪?, 退出码)"""
    installed_now = False

    # ---- 客户端
    if app:
        ok("客户端已安装：%s" % app)
    elif dry:
        fail("未检测到 ChatCut 客户端。")
        out("     去掉 --check 重跑，脚本会弹窗引导你登录下载并自动安装。")
        return False, 2
    else:
        choice = 0 if assume_yes else dialog(
            "还差一步：装 ChatCut 客户端",
            "本技能要靠 ChatCut 客户端干活，但你电脑上还没装。\n\n"
            "点「去登录下载」后会发生什么：\n"
            "1. 浏览器打开 ChatCut 官网，请先登录（没账号就注册一个）\n"
            "2. 登录后点右上角头像 → Desktop App → Download\n"
            "3. 下载完成后我自动帮你装好，不用你动手\n\n"
            "全程大概 2 分钟。",
            ["去登录下载", "稍后我自己装"],
            default=0,
            icon="caution",
        )

        if choice != 0:
            warn("已跳过安装。想装了随时双击 install-macos.command / install-windows.cmd。")
            return False, 2

        open_url(CHATCUT_SITE)
        out("")
        out("  🌐 已打开 %s —— 请登录，然后：头像 → Desktop App → Download" % CHATCUT_SITE)

        installer = watch_for_installer()
        if not installer:
            fail("等超时了，没看到安装包。")
            warn("确认下载确实开始了；或者手动装好客户端再重跑本脚本。")
            return False, 3

        ok("发现安装包：%s" % installer)

        installed = install_mac(installer) if IS_MAC else install_win(installer)
        if not installed:
            return False, 3
        app = installed
        installed_now = True

    # ---- MCP 连接
    out("")
    out("【2/3】检查 WorkBuddy 的 ChatCut 连接")
    mcp_ok, mcp_fixed = ensure_mcp(app, dry=dry)

    # ---- 客户端进程
    out("")
    out("【3/3】客户端运行状态")
    if app_running():
        ok("客户端正在运行")
    elif dry:
        warn("客户端没在运行（真正剪辑前需要打开它）")
    else:
        step("启动客户端…")
        launch_app(app)
        time.sleep(3)
        ok("已启动")

    if dry:
        return (True if mcp_ok else False), (0 if mcp_ok else 4)

    # ---- 收尾弹窗：只在这次真的干了活的时候弹，免得每次跑都吵人
    if installed_now or mcp_fixed:
        if mcp_ok:
            dialog(
                "ChatCut 装好了",
                "客户端和连接都就绪了。\n\n"
                "最后一步：请重启 WorkBuddy（或新开一个会话），"
                "新的 MCP 工具才会加载进来。\n\n"
                "然后就可以让我开始剪口播视频了。",
                ["好的"],
            )
        else:
            dialog(
                "ChatCut 装好了，但连接还没通",
                "客户端已安装，不过 WorkBuddy 里还没连上 ChatCut。\n\n"
                "请重启 WorkBuddy 后再试；仍然不行的话，"
                "让我按 references/install-chatcut.md 走一次授权流程。",
                ["知道了"],
            )

    return (True if mcp_ok else False), (0 if mcp_ok else 4)


def main():
    ap = argparse.ArgumentParser(
        description="ChatCut 环境预检 / 自动安装（macOS + Windows）"
    )
    ap.add_argument("--check", action="store_true", help="只体检，不安装、不弹窗")
    ap.add_argument("--yes", action="store_true", help="非交互，自动确认")
    args = ap.parse_args()

    if args.check:
        os.environ["CHATCUT_NO_DIALOG"] = "1"

    if not (IS_MAC or IS_WIN):
        fail("当前系统不受支持（只支持 macOS / Windows）。")
        return 5

    out("")
    out("═══ ChatCut 环境预检 ═══")
    out("系统：%s" % ("macOS" if IS_MAC else "Windows"))
    out("")

    out("【1/3】检查 ChatCut 客户端")
    app = find_app()
    ready, code = preflight(
        app, do_install=not args.check, assume_yes=args.yes, dry=args.check
    )

    out("")
    if ready:
        out("═══ 结果：环境就绪 ✅ ═══")
    else:
        out("═══ 结果：环境未就绪 ❌（退出码 %d）═══" % code)
    out("")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        out("")
        warn("被中断了。")
        sys.exit(130)
