# BTC 套利机器人 - Polymarket × Kalshi

> 微信交流：**IBO0OK**

一个实时监控 Polymarket 和 Kalshi 两个预测市场平台的 BTC 1小时价格市场，自动发现无风险套利机会的工具。

---

## 功能特点

- **实时监控**：每秒刷新两个平台的最新价格
- **自动匹配**：自动找到 Polymarket 和 Kalshi 上对应的市场
- **套利检测**：当两个平台的对立仓位总价低于 $1.00 时，标记为套利机会
- **可视化仪表盘**：实时显示价格变化、最佳套利机会、成本分析图表

---

## 安装教程

## Windows桌面版

Windows桌面版把后端和监控界面封装在一个窗口中，支持：

- 自动交易开关、实时盘口和运行日志
- 手动选择当前PM/KS配对并按相同份数双边下单
- 查询本程序成交的PM/KS持仓，分别手动卖出
- 电竞整场胜负盘跨平台自动匹配和双边FOK套利（CS2、LoL、Dota 2、Valorant）
- 在界面输入API参数，凭据使用Windows账户DPAPI加密保存

解压后直接双击项目目录里的`build_windows.bat`即可。源码包内置Python 3.12、Node.js 20和Microsoft Edge WebView2安装器：如果系统缺少它们，脚本会先自动安装，再继续构建。安装器可能会弹出管理员权限确认。构建完成后：

- 有Inno Setup时，会生成`output/PM-KS-Trader-Setup.exe`
- 没有Inno Setup时，可直接运行`dist/PM-KS交易桌面/PM-KS交易桌面.exe`

首次启动会弹出API连接设置。私钥只在本机加密保存；不要把私钥写进`.env`、截图、日志或发给任何人。连接测试成功后，再手动点击“启动自动交易”。

Windows版使用本机用户数据目录保存设置和日志：`%LOCALAPPDATA%\\PolymarketKalshiTrader`。卸载程序不会自动删除该目录，避免误删历史成交和凭据。

### 电竞双边套利

电竞模式只处理同一场比赛的整场胜负盘。程序会核对游戏类型、两支队伍和市场标题，并排除地图/单局胜负、让分、总局数及组合盘口。发现机会后按“PM一队 + KS相反结果”计算总成本，扣除手续费缓冲后达到最低利润才允许下单；执行时仍采用KS先FOK、PM后FOK，并在第二腿失败时尝试卖回第一腿。

电竞自动交易默认关闭。首次使用应先在电竞窗口核对已匹配的比赛名称和两边方向，再开启自动交易。即使显示利润，盘口跳动、平台拒单和两边结算规则差异仍可能造成风险。

### 在线更新

程序支持通过HTTPS更新清单检查新版本。清单必须是JSON，例如：

```json
{"version":"1.3.0","url":"https://example.com/PM-KS-Trader-Setup.exe","sha256":"64位小写SHA-256","notes":"本次更新说明"}
```

在“系统设置”填写清单地址后，点击“检查软件更新”。程序会校验安装包SHA-256，下载完成后自动退出并启动新版安装器。更新地址和安装包需要放在你自己的HTTPS站点或发布服务上；当前源码没有绑定任何第三方站点。

### 环境准备

在开始之前，请确保你的电脑上安装了以下软件：

| 软件 | 最低版本 | 下载地址 |
|------|---------|---------|
| Python | 3.10-3.12（推荐3.12） | https://www.python.org/downloads/windows/ |
| Node.js（包含npm） | 18+（推荐20 LTS） | https://nodejs.org/en/download |
| Git | 任意 | https://git-scm.com/ |

**检查是否安装成功**：打开终端（Windows 用户打开 CMD 或 PowerShell），输入以下命令：

```bash
python --version    # 应显示 Python 3.10.x、3.11.x 或3.12.x
node --version      # 应显示 v18.x.x 或更高
git --version       # 应显示 git version x.x.x
```

如果某个命令提示"不是内部或外部命令"，说明该软件未安装或未配置环境变量，请先安装。

---

### 第一步：克隆项目

解压到目录下即可

### 第二步：安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```

> 💡 如果 `pip` 命令不可用，尝试 `pip3 install -r requirements.txt`

---

### 第三步：安装前端依赖

```bash
cd ../frontend
npm install
```

> 💡 如果 npm 下载速度慢，可以使用国内镜像：
> `npm install --registry=https://registry.npmmirror.com`

---

### 第四步：启动项目

需要同时运行后端和前端，**打开两个终端窗口**：

**终端 1 - 启动后端**：
```bash
cd polymarket-kalshi-btc-arbitrage-bot/backend
python api.py
```

看到类似 `Uvicorn running on http://localhost:8000` 的提示说明启动成功。

**终端 2 - 启动前端**：
```bash
cd polymarket-kalshi-btc-arbitrage-bot/frontend
npm run dev
```

看到类似 `Ready on http://localhost:3000` 的提示说明启动成功。

**打开浏览器访问**：http://localhost:3000

---

### Docker 方式（可选）

如果你安装了 Docker，可以用更简单的方式一键启动：

```bash
cd polymarket-kalshi-btc-arbitrage-bot
make build
```

然后访问 http://localhost:3000

其他常用命令：
```bash
make up       # 启动
make down     # 停止
make logs     # 查看日志
make clean    # 清理所有容器和镜像
```

---

## 项目结构

```
polymarket-kalshi-btc-arbitrage-bot/
├── backend/                # 后端代码
│   ├── api.py             # 主服务入口（FastAPI）
│   ├── fetch_current_polymarket.py  # 获取 Polymarket 数据
│   ├── fetch_current_kalshi.py      # 获取 Kalshi 数据
│   ├── get_current_markets.py       # 自动匹配当前市场
│   └── requirements.txt   # Python 依赖
├── frontend/               # 前端代码
│   ├── app/page.tsx       # 仪表盘主页面
│   ├── components/        # UI 组件
│   └── package.json       # Node.js 依赖
├── docker/                 # Docker 配置
└── Makefile               # Docker 快捷命令
```

---

## 使用说明

启动后，仪表盘会自动：

1. 每秒从 Polymarket 和 Kalshi 获取最新的 BTC 1小时价格市场数据
2. 对比两个平台的对立仓位价格
3. 当发现总成本低于 $1.00 的组合时，标记为套利机会并高亮显示

> ⚠️ **注意**：套利机会转瞬即逝，发现机会后需要在两个平台上快速下单执行。

---

## 常见问题

**Q: 启动后显示 "No data available"？**
A: 检查后端是否正常运行（终端 1 是否显示 Uvicorn running），以及是否能正常访问 Polymarket 和 Kalshi 的 API（可能需要科学上网）。

**Q: npm install 报错？**
A: 尝试删除 `frontend/node_modules` 文件夹后重新运行 `npm install`。如果仍然失败，检查 Node.js 版本是否 >= 18。

**Q: pip install 报错？**
A: 尝试使用 `pip3 install -r requirements.txt`，或检查 Python 是否正确安装。

---


## 修改日志

### 2026-07-23
- 清理 execute_arb.py 无用调试输出（KS原始响应）
- 新增整点前后8分钟不下单保护：分钟数 0-7 和 52-59 期间自动跳过交易

## 许可证

MIT License
