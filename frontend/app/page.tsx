"use client"
import { useCallback, useEffect, useState, useRef } from "react"
import { Activity, Shield, Wallet, Play, Square, TrendingUp, TrendingDown, Settings, KeyRound, HandCoins, X, TestTube2, Gamepad2 } from "lucide-react"
interface AutoStatus { enabled: boolean; cooldown_remaining: number; trade_count: number; last_trade_result: any }
interface ArbCheck { kalshi_strike: number; type: string; poly_leg: string; kalshi_leg: string; poly_cost: number; kalshi_cost: number; total_cost: number; is_arbitrage: boolean; margin: number; ks_ticker?: string }
interface Position {
  time: string; coin: string; poly_leg: string; kalshi_leg: string; kalshi_strike: number
  total_cost_cents: number; profit_cents: number
  pm_filled_qty: number; ks_fill_count: number; hedged_qty: number
  pm_price: number; ks_price: number; token_id?: string; ks_ticker?: string; ks_side?: string
  pm_remaining?: number; ks_remaining?: number
}
interface HistoryEntry {
  time: string; coin: string; poly_leg: string; kalshi_leg: string; kalshi_strike: number
  total_cost_cents: number; profit_cents: number; success: boolean; error?: string
  pm_filled_qty: number; ks_fill_count: number; hedged_qty: number
  pm_price: number; ks_price: number; size_warning?: string
  ks_ticker?: string; ks_side?: string
}
interface BuyResult { success: boolean; error?: string; pm?: any; ks?: any; balances?: any; pm_plan?: any; ks_plan?: any }
interface CoinData { polymarket: any; kalshi: any; checks: ArbCheck[]; opportunities: ArbCheck[]; best_check?: ArbCheck | null; errors: string[] }
interface MarketData { timestamp: string; coins: Record<string, CoinData>; errors: string[] }
interface BalData { pm: number | null; ks: number | null; pm_error?: string; ks_error?: string }
interface EsportsOpportunity {
  id: string; game: string; title: string; pm_team: string; ks_team: string; ks_side: string
  pm_price: number; ks_price: number; total_cost: number; estimated_profit_cents: number
  gross_profit_cents: number; fee_buffer_cents: number; match_score: number
}
interface EsportsData { time: string; matched_markets: number; opportunities: EsportsOpportunity[]; total: number; error?: string }
const API = process.env.NEXT_PUBLIC_API_URL ?? ""
const COIN_ORDER = ["BTC"]
const COIN_NAMES: Record<string, string> = { BTC: "Bitcoin" }
function StatChip({ icon, title, value, sub }: { icon: React.ReactNode; title: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-blue-500/20 bg-[#071120] px-3 py-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-blue-400/30 bg-blue-500/10 text-blue-300">{icon}</div>
        <div className="min-w-0">
          <div className="text-[11px] leading-tight text-white/70">{title}</div>
          <div className="text-sm font-semibold leading-tight text-blue-200 truncate">{value}</div>
          <div className="text-[10px] leading-tight text-slate-400 truncate">{sub}</div>
        </div>
      </div>
    </div>
  )
}
function CoinPanel({ symbol, data, onBuy, buying }: {
  symbol: string
  data: CoinData
  onBuy: (coin: string, polyLeg: string, kalshiLeg: string, kalshiStrike: number, ksTicker: string) => void
  buying: boolean
}) {
  const poly = data.polymarket
  const kalshi = data.kalshi
  const best = data.best_check || null
  const bestCents = best ? best.margin * 100 : null
  const hasData = poly && kalshi
  return (
    <div className="rounded-2xl border border-blue-500/20 bg-[#071120] p-4 text-white">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-2xl font-bold">{symbol} <span className="ml-1 text-sm font-normal text-slate-400">{COIN_NAMES[symbol]}</span></div>
          <div className="mt-1 text-xs text-slate-400">实时盘口监控</div>
        </div>
        <div className="text-right">
          <div className="text-xs text-slate-400">最佳利润</div>
          <div className={`text-2xl font-bold ${bestCents == null ? "text-slate-400" : bestCents > 0 ? "text-emerald-400" : "text-amber-300"}`}>
            {bestCents == null ? "--" : `${bestCents > 0 ? "+" : ""}${bestCents.toFixed(1)}¢`}
          </div>
          <div className="mt-1 text-[10px] text-slate-500">本轮检查 {data.checks.length} 组</div>
        </div>
      </div>
      {data.errors.length > 0 && (
        <div className="mb-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {data.errors.map((e, i) => <div key={i}>{e}</div>)}
        </div>
      )}
      {!hasData && data.errors.length === 0 && (
        <div className="rounded-xl border border-blue-500/15 bg-[#0b1729] px-4 py-8 text-center text-sm text-slate-400">加载中...</div>
      )}
      {hasData && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="rounded-xl border border-blue-500/15 bg-[#0b1729] p-3">
              <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Polymarket</div>
              <div className="mb-2 truncate font-mono text-[10px] text-slate-500" title={poly?.slug}>{poly?.slug || "未识别市场"}</div>
              <div className="space-y-1.5 text-sm">
                <div className="flex justify-between"><span className="text-slate-400">阈值</span><span className="font-mono text-white">{poly?.price_to_beat?.toLocaleString() ?? "--"}</span></div>
                <div className="flex justify-between"><span className="text-slate-400">现价</span><span className="font-mono text-white">{poly?.current_price?.toLocaleString() ?? "--"}</span></div>
                <div className="flex justify-between"><span className="text-emerald-400">UP {(poly?.prices?.Up * 100 || 0).toFixed(1)}c</span><span className="text-rose-400">DOWN {(poly?.prices?.Down * 100 || 0).toFixed(1)}c</span></div>
              </div>
            </div>
            <div className="rounded-xl border border-blue-500/15 bg-[#0b1729] p-3">
              <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Kalshi</div>
              <div className="mb-2 truncate font-mono text-[10px] text-slate-500" title={kalshi?.event_ticker}>{kalshi?.event_ticker || "未识别市场"}</div>
              <div className="space-y-1.5 text-xs font-mono">
                {[...(kalshi?.markets || [])].sort((a: any, b: any) => Math.abs(a.strike - (poly?.price_to_beat || 0)) - Math.abs(b.strike - (poly?.price_to_beat || 0))).slice(0, 3).map((m: any, i: number) => (
                  <div key={i} className="flex justify-between border-b border-blue-500/10 pb-1 last:border-0 last:pb-0">
                    <span className="text-slate-300">s={m.strike.toLocaleString()}</span>
                    <span><span className="text-emerald-400">Y:{m.yes_ask.toFixed(3)}</span> <span className="text-rose-400">N:{m.no_ask.toFixed(3)}</span></span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="rounded-xl border border-blue-500/15 bg-[#0b1729] p-3">
            <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">套利机会</div>
            {data.opportunities.length > 0 ? (
              <div className="space-y-2">
                {data.opportunities.slice(0, 4).map((c, i) => (
                  <div key={i} className="flex items-center justify-between rounded-xl border border-emerald-500/15 bg-emerald-500/10 px-3 py-2 text-xs">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-slate-300">s={c.kalshi_strike.toLocaleString()}</span>
                      <span className="text-slate-200">{c.poly_leg}+{c.kalshi_leg}</span>
                      <span className="font-mono text-slate-400">cost {c.total_cost.toFixed(3)}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-bold text-emerald-400">+{c.margin.toFixed(3)}</span>
                      <button className="rounded-lg bg-blue-600 px-2 py-1 text-[11px] font-semibold text-white hover:bg-blue-500 disabled:opacity-50" onClick={() => onBuy(symbol, c.poly_leg, c.kalshi_leg, c.kalshi_strike, c.ks_ticker || "")} disabled={buying}>{buying ? "..." : "买入"}</button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-blue-500/15 px-3 py-3 text-center text-xs text-slate-500">暂无套利窗口</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
function EsportsPanel({ data, loading, autoEnabled, onOpen }: { data: EsportsData | null; loading: boolean; autoEnabled: boolean; onOpen: () => void }) {
  const best = data?.opportunities?.[0] || null
  return (
    <button onClick={onOpen} className="rounded-2xl border border-violet-500/25 bg-[#071120] p-4 text-left text-white hover:bg-violet-500/10">
      <div className="mb-3 flex items-center justify-between">
        <div><div className="flex items-center gap-2 text-2xl font-bold"><Gamepad2 className="h-5 w-5 text-violet-300" />电竞双边套利</div><div className="mt-1 text-xs text-slate-400">整场胜负盘 / PM + KS 同时下单</div></div>
        <span className={`rounded-full px-2 py-1 text-xs ${autoEnabled ? "bg-emerald-500/15 text-emerald-400" : "bg-slate-500/15 text-slate-400"}`}>{autoEnabled ? "自动运行中" : "自动关闭"}</span>
      </div>
      <div className="mb-3 grid grid-cols-3 gap-2">
        <div className="rounded-xl bg-[#0b1729] p-3"><div className="text-[10px] text-slate-400">已匹配赛事</div><div className="mt-1 font-mono text-xl font-bold">{data?.matched_markets ?? "--"}</div></div>
        <div className="rounded-xl bg-[#0b1729] p-3"><div className="text-[10px] text-slate-400">达标机会</div><div className={`mt-1 font-mono text-xl font-bold ${(data?.total || 0) > 0 ? "text-emerald-400" : "text-slate-300"}`}>{data?.total ?? "--"}</div></div>
        <div className="rounded-xl bg-[#0b1729] p-3"><div className="text-[10px] text-slate-400">最佳利润</div><div className="mt-1 font-mono text-xl font-bold text-violet-300">{best ? `+${best.estimated_profit_cents.toFixed(1)}¢` : "--"}</div></div>
      </div>
      {loading && !data ? <div className="rounded-xl border border-dashed border-violet-500/20 px-3 py-5 text-center text-xs text-slate-400">正在匹配电竞市场...</div> : data?.error ? <div className="rounded-xl bg-red-500/10 px-3 py-3 text-xs text-rose-300">{data.error}</div> : best ? <div className="rounded-xl border border-emerald-500/15 bg-emerald-500/10 px-3 py-3 text-xs"><div className="truncate font-semibold text-white">{best.title}</div><div className="mt-2 flex flex-wrap gap-x-3 gap-y-1"><span className="text-blue-300">PM {best.pm_team} {(best.pm_price * 100).toFixed(1)}¢</span><span className="text-emerald-300">KS {best.ks_team} {(best.ks_price * 100).toFixed(1)}¢</span></div></div> : <div className="rounded-xl border border-dashed border-violet-500/20 px-3 py-5 text-center text-xs text-slate-500">当前没有达到利润阈值的机会</div>}
      <div className="mt-3 text-center text-xs font-semibold text-violet-300">点击查看全部电竞市场与下单设置</div>
    </button>
  )
}
export default function Dashboard() {
  const [data, setData] = useState<MarketData | null>(null)
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [buying, setBuying] = useState(false)
  const [buyResult, setBuyResult] = useState<BuyResult | null>(null)
  const [showResult, setShowResult] = useState(false)
  const [selling, setSelling] = useState<{coin:string,platform:string} | null>(null)
  const [sellResult, setSellResult] = useState<any>(null)
  const [showSellResult, setShowSellResult] = useState(false)
  const [autoStatus, setAutoStatus] = useState<AutoStatus | null>(null)
  const [bal, setBal] = useState<BalData | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [historyHours, setHistoryHours] = useState(6)
  const [historyData, setHistoryData] = useState<HistoryEntry[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const initialTotalRef = useRef<number | null>(null)
  const total = bal?.pm != null && bal?.ks != null ? (bal.pm / 1e6 + bal.ks) : null
  if (total !== null && initialTotalRef.current === null) { initialTotalRef.current = total }
  const profit = total !== null && initialTotalRef.current !== null ? total - initialTotalRef.current : null
  const [showSettings, setShowSettings] = useState(false)
  const [settingsData, setSettingsData] = useState<any>(null)
  const [settingsLoading, setSettingsLoading] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)
  const [logLines, setLogLines] = useState<string[]>([])
  const [credentialStatus, setCredentialStatus] = useState<any>(null)
  const [showCredentials, setShowCredentials] = useState(false)
  const [credentialSaving, setCredentialSaving] = useState(false)
  const [credentialTesting, setCredentialTesting] = useState(false)
  const [credentialImporting, setCredentialImporting] = useState(false)
  const [credentialImportPassword, setCredentialImportPassword] = useState("")
  const [credentialTest, setCredentialTest] = useState<any>(null)
  const [showManualTrade, setShowManualTrade] = useState(false)
  const [manualCoin, setManualCoin] = useState("BTC")
  const [manualIndex, setManualIndex] = useState(0)
  const [manualShares, setManualShares] = useState(5)
  const [showEsports, setShowEsports] = useState(false)
  const [esportsData, setEsportsData] = useState<EsportsData | null>(null)
  const [esportsAuto, setEsportsAuto] = useState<any>(null)
  const [esportsShares, setEsportsShares] = useState(5)
  const [esportsLoading, setEsportsLoading] = useState(false)
  const [esportsExecuting, setEsportsExecuting] = useState(false)
  const [updateInfo, setUpdateInfo] = useState<any>(null)
  const [currentVersion, setCurrentVersion] = useState("")
  const [updateChecking, setUpdateChecking] = useState(false)
  const [showUpdate, setShowUpdate] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const refreshInFlightRef = useRef(false)
  const fetchLog = useCallback(async () => {
    try {
      const r = await fetch(API + "/log?lines=80")
      if (r.ok) { const d = await r.json(); if (d.lines) setLogLines(d.lines) }
    } catch {}
  }, [])
  useEffect(() => {
    fetchLog()
    const id = setInterval(fetchLog, 3000)
    return () => clearInterval(id)
  }, [fetchLog])
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [logLines])
  const fetchCredentialStatus = useCallback(async () => {
    try {
      const r = await fetch(API + "/credentials")
      if (r.ok) {
        const status = await r.json()
        setCredentialStatus(status)
        if (!status.polymarket_configured || !status.kalshi_configured) setShowCredentials(true)
      }
    } catch {}
  }, [])
  useEffect(() => { fetchCredentialStatus() }, [fetchCredentialStatus])
  const [restarting, setRestarting] = useState(false)
  const fetchSettings = useCallback(async () => {
    setSettingsLoading(true)
    try { const r = await fetch(API + "/settings"); if (r.ok) setSettingsData(await r.json()) } catch {}
    setSettingsLoading(false)
  }, [])
  const saveSettings = useCallback(async (updates: Record<string, any>) => {
    setSavingSettings(true)
    try {
      const r = await fetch(API + "/settings", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(updates),
      })
      if (r.ok) {
        setSettingsData((current: any) => ({ ...(current || {}), ...updates }))
      }
    } catch {}
    setSavingSettings(false)
  }, [])
  const fetchHistory = useCallback(async (hours: number) => {
    setHistoryLoading(true)
    try {
      const r = await fetch(API + "/history?hours=" + hours)
      if (r.ok) { const d = await r.json(); setHistoryData(d.trades || []) }
    } catch {}
    setHistoryLoading(false)
  }, [])
  const fetchAll = useCallback(async () => {
    if (refreshInFlightRef.current) return
    refreshInFlightRef.current = true
    const fetchJson = async (path: string, timeoutMs = 10000) => {
      const controller = new AbortController()
      const timer = window.setTimeout(() => controller.abort(), timeoutMs)
      try {
        const response = await fetch(API + path, { signal: controller.signal })
        return response.ok ? await response.json() : null
      } catch { return null }
      finally { window.clearTimeout(timer) }
    }
    try {
      const [ar, au, ab, ap] = await Promise.all([
        fetchJson("/arbitrage", 12000),
        fetchJson("/auto", 5000),
        fetchJson("/balance", 12000),
        fetchJson("/positions", 8000),
      ])
      if (ar) { setData(ar); setConnected(true); setLastUpdated(new Date()); setLoading(false) }
      if (au) setAutoStatus(au)
      if (ab) setBal(ab)
      if (ap) setPositions(ap.positions || [])
      if (!ar) setConnected(false)
    } catch { setConnected(false) }
    finally {
      refreshInFlightRef.current = false
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    fetchAll()
    const id = setInterval(fetchAll, 5000)
    return () => clearInterval(id)
  }, [fetchAll])
  const toggleAuto = async () => {
    const action = autoStatus?.enabled ? "stop" : "start"
    await fetch(API + "/auto/" + action, { method: "POST" }).catch(() => {})
    fetchAll()
  }
  const buyArbitrage = async (coin: string, polyLeg: string, kalshiLeg: string, kalshiStrike: number, ksTicker: string, shares?: number) => {
    setBuying(true)
    try {
      const res = await fetch(API + "/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ coin, poly_leg: polyLeg, kalshi_leg: kalshiLeg, kalshi_strike: kalshiStrike, ks_ticker: ksTicker, shares: shares || undefined }),
      })
      const result: BuyResult = await res.json()
      setBuyResult(result)
      setShowResult(true)
    } catch (e: any) {
      setBuyResult({ success: false, error: e.message || "请求失败" })
      setShowResult(true)
    } finally {
      setBuying(false)
    }
  }
  const handleSell = async (coin: string, platform: string, p: Position) => {
    setSelling({coin, platform})
    try {
      const body: any = { coin, platform, amount: platform === "PM" ? (p.pm_remaining ?? p.hedged_qty) : (p.ks_remaining ?? p.hedged_qty) }
      if (platform === "PM") {
        body.token_id = p.token_id || ""
        body.pm_price = p.pm_price
      } else {
        body.ks_ticker = p.ks_ticker || ""
        body.ks_price = p.ks_price
        body.ks_side = p.ks_side || (p.kalshi_leg || "yes").toLowerCase()
      }
      const res = await fetch(API + "/sell", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })
      const r = await res.json()
      setSellResult(r)
      setShowSellResult(true)
    } catch (e: any) {
      setSellResult({ success: false, error: e.message || "请求失败", coin, platform })
      setShowSellResult(true)
    } finally {
      setSelling(null)
    }
  }
  const saveCredentials = async () => {
    setCredentialSaving(true)
    try {
      const fields = ["polymarket_private_key", "polymarket_funder", "polymarket_signature_type", "kalshi_api_key_id", "kalshi_private_key_pem"]
      const payload: Record<string, string> = {}
      fields.forEach(f => {
        const element = document.getElementById("c_" + f) as HTMLInputElement | HTMLTextAreaElement | null
        if (element?.value.trim()) payload[f] = element.value.trim()
      })
      const r = await fetch(API + "/credentials", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) })
      const d = await r.json()
      if (r.ok && d.saved) { setCredentialStatus(d.status); setCredentialTest(null) }
      else setCredentialTest({ ok: false, error: d.error || "保存失败" })
    } catch (e: any) { setCredentialTest({ ok: false, error: e.message || "保存失败" }) }
    setCredentialSaving(false)
  }
  const testCredentials = async () => {
    setCredentialTesting(true)
    try {
      const r = await fetch(API + "/credentials/test", { method: "POST" })
      setCredentialTest(await r.json())
    } catch (e: any) { setCredentialTest({ ok: false, error: e.message || "连接测试失败" }) }
    setCredentialTesting(false)
  }
  const importCredentialBackup = async () => {
    const input = document.getElementById("credential_backup_file") as HTMLInputElement | null
    const file = input?.files?.[0]
    if (!file || !credentialImportPassword) {
      setCredentialTest({ ok: false, error: "请选择备份文件并输入备份密码" })
      return
    }
    setCredentialImporting(true)
    try {
      const bundle = await file.text()
      const response = await fetch(API + "/credentials/import", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bundle, password: credentialImportPassword }),
      })
      const result = await response.json()
      if (result.imported) {
        setCredentialStatus(result.status)
        setCredentialTest({ ok: true, error: "服务器凭据已导入并使用当前Windows账户重新加密" })
        setCredentialImportPassword("")
        if (input) input.value = ""
      } else setCredentialTest({ ok: false, error: result.error || "导入失败" })
    } catch (e: any) {
      setCredentialTest({ ok: false, error: e.message || "导入失败" })
    }
    setCredentialImporting(false)
  }
  const checkForUpdate = async (openDialog = true) => {
    setUpdateChecking(true)
    try {
      const response = await fetch(API + "/update/check")
      const info = await response.json()
      setUpdateInfo(info)
      if (info.current_version) setCurrentVersion(info.current_version)
      if (openDialog) setShowUpdate(true)
    } catch (e: any) {
      setUpdateInfo({ available: false, error: e.message || "检查更新失败" })
      if (openDialog) setShowUpdate(true)
    }
    setUpdateChecking(false)
  }
  useEffect(() => {
    fetch(API + "/version").then(r => r.json()).then(info => setCurrentVersion(info.version || "")).catch(() => {})
    const timer = window.setTimeout(() => { void checkForUpdate(false) }, 3000)
    const interval = window.setInterval(() => { void checkForUpdate(false) }, 30 * 60 * 1000)
    return () => { window.clearTimeout(timer); window.clearInterval(interval) }
  }, [])
  const applyUpdate = async () => {
    if (!updateInfo) return
    const response = await fetch(API + "/update/apply", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ update: updateInfo }) })
    const result = await response.json()
    setUpdateInfo((current: any) => ({ ...current, applyResult: result }))
  }
  const fetchEsports = useCallback(async () => {
    setEsportsLoading(true)
    try {
      const [markets, auto] = await Promise.all([
        fetch(API + "/esports/arbitrage").then(r => r.json()),
        fetch(API + "/esports/auto").then(r => r.json()),
      ])
      setEsportsData(markets)
      setEsportsAuto(auto)
    } catch {}
    setEsportsLoading(false)
  }, [])
  useEffect(() => {
    if (!showEsports) return
    fetchEsports()
    const id = setInterval(fetchEsports, 10000)
    return () => clearInterval(id)
  }, [showEsports, fetchEsports])
  useEffect(() => {
    const timer = window.setTimeout(fetchEsports, 5000)
    const id = window.setInterval(fetchEsports, 120 * 1000)
    return () => { window.clearTimeout(timer); window.clearInterval(id) }
  }, [fetchEsports])
  const toggleEsportsAuto = async () => {
    const action = esportsAuto?.enabled ? "stop" : "start"
    await fetch(API + "/esports/auto/" + action, { method: "POST" }).catch(() => {})
    fetchEsports()
  }
  const executeEsports = async (opportunity: EsportsOpportunity) => {
    setEsportsExecuting(true)
    try {
      const response = await fetch(API + "/esports/execute", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opportunity_id: opportunity.id, shares: esportsShares }),
      })
      setBuyResult(await response.json())
      setShowResult(true)
      fetchEsports()
    } catch (e: any) {
      setBuyResult({ success: false, error: e.message || "电竞双边下单失败" })
      setShowResult(true)
    }
    setEsportsExecuting(false)
  }
  const coins = data?.coins || {}
  const coinKeys = COIN_ORDER.filter(k => k in coins)
  const manualChecks = (data?.coins?.[manualCoin]?.checks || []).filter((c: ArbCheck) => c.kalshi_strike && c.poly_leg && c.kalshi_leg)
  const manualChoice = manualChecks[manualIndex] || manualChecks[0]
  if (loading) return <div className="flex h-screen items-center justify-center bg-[#030712] text-slate-300">连接中...</div>
  return (
    <div className="h-[100dvh] overflow-hidden bg-[radial-gradient(circle_at_top,rgba(37,99,235,0.25),transparent_35%),linear-gradient(180deg,#020617,#060d1a,#020617)] p-3 text-white sm:p-4">
      <div className="mx-auto grid h-full min-h-0 max-w-[1800px] grid-cols-[clamp(220px,18vw,270px)_minmax(480px,1fr)_clamp(260px,22vw,320px)] gap-3 xl:gap-4">
        <aside className="flex min-h-0 flex-col overflow-y-auto rounded-[28px] border border-blue-500/20 bg-[#040b17]/95 p-4 shadow-[0_0_40px_rgba(30,64,175,0.12)] xl:p-5" style={{scrollbarWidth:"thin"}}>
          <div>
            <div className="text-[22px] font-bold tracking-tight text-white">Polymarket <span className="bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">套利监控</span></div>
            <div className="mt-2 flex items-center justify-between gap-2 text-sm text-slate-400"><span>BTC / 电竞 双边套利面板</span><span className="rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-0.5 font-mono text-[11px] text-blue-200">v{currentVersion || "--"}</span></div>
          </div>
          <div className="mt-6 space-y-3">
            <button className="flex w-full items-center gap-3 rounded-2xl border border-blue-500/30 bg-gradient-to-r from-blue-600/30 to-cyan-500/20 px-4 py-3 text-left text-white">
              <Activity className="h-5 w-5 text-blue-300" />
              <div>
                <div className="text-sm font-semibold">仪表盘</div>
                <div className="text-xs text-slate-300">实时盘口与机会</div>
              </div>
            </button>
          </div>
            <button className="mb-2 flex w-full items-center gap-3 rounded-2xl border border-blue-500/20 bg-[#071120] px-4 py-3 text-left text-white hover:bg-blue-500/10" onClick={() => { setShowSettings(true); fetchSettings() }}>
              <Settings className="h-5 w-5 text-blue-300" />
              <div>
                <div className="text-sm font-semibold">系统设置</div>
                <div className="text-xs text-slate-400">份额 / 阀值 / 冷却参数</div>
              </div>
            </button>
            <button className="relative mb-3 flex w-full items-center gap-3 rounded-2xl border border-cyan-500/20 bg-[#071120] px-4 py-3 text-left text-white hover:bg-cyan-500/10" onClick={() => checkForUpdate(true)} disabled={updateChecking}>
              {updateInfo?.available && <span className="absolute right-3 top-3 flex items-center gap-1 rounded-full bg-red-500 px-1.5 py-0.5 text-[9px] font-bold text-white shadow-[0_0_12px_rgba(239,68,68,0.7)]"><span className="h-1.5 w-1.5 rounded-full bg-white" />NEW</span>}
              <TrendingUp className="h-5 w-5 text-cyan-300" />
              <div><div className="text-sm font-semibold">软件更新</div><div className="text-xs text-slate-400">{updateChecking ? "检查中..." : updateInfo?.available ? `发现新版 v${updateInfo.latest_version}` : "在线检查并安装新版"}</div></div>
            </button>
            <button className="mb-2 flex w-full items-center gap-3 rounded-2xl border border-amber-500/20 bg-[#071120] px-4 py-3 text-left text-white hover:bg-amber-500/10" onClick={() => setShowCredentials(true)}>
              <KeyRound className="h-5 w-5 text-amber-300" />
              <div className="min-w-0">
                <div className="text-sm font-semibold">API连接</div>
                <div className="text-xs text-slate-400">{credentialStatus?.polymarket_configured && credentialStatus?.kalshi_configured ? "已配置并加密保存" : "需要配置API密钥"}</div>
              </div>
            </button>
            <button className="mb-3 flex w-full items-center gap-3 rounded-2xl border border-emerald-500/20 bg-[#071120] px-4 py-3 text-left text-white hover:bg-emerald-500/10" onClick={() => setShowManualTrade(true)}>
              <HandCoins className="h-5 w-5 text-emerald-300" />
              <div>
                <div className="text-sm font-semibold">手动双边下单</div>
                <div className="text-xs text-slate-400">选择市场、方向和份数</div>
              </div>
            </button>
            <button className="relative mb-3 flex w-full items-center gap-3 rounded-2xl border border-violet-500/25 bg-[#071120] px-4 py-3 text-left text-white hover:bg-violet-500/10" onClick={() => setShowEsports(true)}>
              {(esportsData?.total || 0) > 0 && <span className="absolute right-3 top-3 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">{esportsData?.total}</span>}
              <Gamepad2 className="h-5 w-5 text-violet-300" />
              <div>
                <div className="text-sm font-semibold">电竞双边套利</div>
                <div className="text-xs text-slate-400">整场胜负盘 / 两边同时下单</div>
              </div>
            </button>
            <button className="mb-3 flex w-full items-center gap-3 rounded-2xl border border-blue-500/20 bg-[#071120] px-4 py-3 text-left text-white hover:bg-blue-500/10" onClick={() => { setShowHistory(true); fetchHistory(historyHours) }}>
              <Activity className="h-5 w-5 text-blue-300" />
              <div>
                <div className="text-sm font-semibold">查询历史订单</div>
                <div className="text-xs text-slate-400">按小时查看成交记录</div>
              </div>
            </button>
          <div className="rounded-2xl border border-blue-500/15 bg-[#071120] p-4 text-sm">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-slate-400">自动交易</span>
              <span className={`rounded-full px-2 py-1 text-xs ${autoStatus?.enabled ? "bg-emerald-500/15 text-emerald-400" : "bg-slate-500/15 text-slate-400"}`}>{autoStatus?.enabled ? "运行中" : "关闭"}</span>
            </div>
            <button onClick={toggleAuto} className={`flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-white ${autoStatus?.enabled ? "bg-red-500 hover:bg-red-400" : "bg-emerald-600 hover:bg-emerald-500"}`}>
              {autoStatus?.enabled ? <Square className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {autoStatus?.enabled ? "停止自动交易" : "启动自动交易"}
            </button>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-400">
              <div className="rounded-xl bg-[#0b1729] p-2">交易次数<div className="mt-1 font-mono text-lg text-white">{autoStatus?.trade_count ?? 0}</div></div>
              <div className="rounded-xl bg-[#0b1729] p-2">冷却剩余<div className="mt-1 font-mono text-lg text-white">{autoStatus ? `${autoStatus.cooldown_remaining.toFixed(0)}s` : "--"}</div></div>
            </div>
          </div>
        </aside>
        <main className="min-h-0 overflow-y-auto pr-1" style={{scrollbarWidth:"thin"}}>
          <div className="grid min-h-full grid-rows-[auto_auto_minmax(320px,1fr)] gap-3 xl:gap-4">
          <section className="flex gap-3">
            <StatChip icon={<Activity className="h-4 w-4" />} title="总余额" value={total != null ? "$" + total.toFixed(2) : "--"} sub={connected ? (lastUpdated ? lastUpdated.toLocaleTimeString() : "") : "断开"} />
            <StatChip icon={<TrendingUp className="h-4 w-4" />} title="净利润" value={profit != null ? (profit >= 0 ? "+" : "") + "$" + profit.toFixed(2) : "--"} sub={profit != null ? (profit >= 0 ? "盈利" : "亏损") : "等待数据"} />
            <StatChip icon={<Wallet className="h-4 w-4" />} title="Polymarket" value={bal?.pm != null ? "$" + (bal.pm / 1e6).toFixed(2) : "--"} sub={bal?.pm_error ? "错误" : "可用余额"} />
            <StatChip icon={<Shield className="h-4 w-4" />} title="Kalshi" value={bal?.ks != null ? "$" + bal.ks.toFixed(2) : "--"} sub={bal?.ks_error ? "错误" : "可用余额"} />
          </section>
          <section className="grid min-h-0 grid-cols-2 gap-4">
            {coins.BTC && <CoinPanel symbol="BTC" data={coins.BTC} onBuy={buyArbitrage} buying={buying} />}
            <EsportsPanel data={esportsData} loading={esportsLoading} autoEnabled={!!esportsAuto?.enabled} onOpen={() => setShowEsports(true)} />
          </section>
          <section className="grid min-h-0 grid-cols-1 gap-4">
            {["BTC"].map(coin => {
              const coinPositions = positions.filter(p => p.coin === coin)
              return (
                <div key={coin} className="rounded-[28px] border border-blue-500/20 bg-[#040b17]/95 p-5">
                  <div className="mb-4 flex items-center justify-between">
                    <div className="text-xl font-bold">{coin} 持仓</div>
                    <div className="text-xs text-slate-400">{coinPositions.length > 0 ? coinPositions.length + " 笔" : "无"}</div>
                  </div>
                  {coinPositions.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-blue-500/10 text-left text-xs uppercase tracking-wide text-slate-400">
                            <th className="pb-2 pr-2">平台</th>
                            <th className="pb-2 pr-2">方向</th>
                            <th className="pb-2 pr-2 text-right">单价</th>
                            <th className="pb-2 pr-2 text-right">份额</th>
                            <th className="pb-2 pr-2 text-right">合计</th>
                            <th className="pb-2 text-right">操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {coinPositions.slice().reverse().flatMap((p, i) => {
                            const up = p.poly_leg.toLowerCase() === "up"
                            const pmQty = p.pm_remaining ?? p.hedged_qty
                            const ksQty = p.ks_remaining ?? p.hedged_qty
                            const pmTotal = (p.pm_price * pmQty).toFixed(3)
                            const ksTotal = (p.ks_price * ksQty).toFixed(3)
                            return [
                              pmQty > 0.01 ? (
                              <tr key={i+"pm"} className="border-b border-blue-500/5 hover:bg-blue-500/5">
                                <td className="py-2 pr-2"><span className="rounded bg-blue-500/15 px-1.5 py-0.5 text-[11px] text-blue-300">PM</span></td>
                                <td className="py-2 pr-2"><span className={up ? "text-emerald-400" : "text-rose-400"}>{p.poly_leg}</span></td>
                                <td className="py-2 pr-2 text-right font-mono text-white">{p.pm_price.toFixed(3)}</td>
                                <td className="py-2 pr-2 text-right font-mono text-white">{pmQty}</td>
                                <td className="py-2 pr-2 text-right font-mono text-white">${pmTotal}</td>
                                <td className="py-2 text-right">
                                  <button className="rounded-lg bg-rose-600/80 px-2 py-1 text-[11px] font-semibold text-white hover:bg-rose-500 disabled:opacity-40" onClick={() => handleSell(p.coin, "PM", p)} disabled={pmQty <= 0.01 || (selling?.coin === p.coin && selling?.platform === "PM")}>{selling?.coin === p.coin && selling?.platform === "PM" ? "..." : "卖出"}</button>
                                </td>
                              </tr>) : null,
                              ksQty > 0.01 ? (
                              <tr key={i+"ks"} className="border-b border-blue-500/5 hover:bg-blue-500/5">
                                <td className="py-2 pr-2"><span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] text-emerald-300">KS</span></td>
                                <td className="py-2 pr-2"><span className="text-slate-300">{(p.ks_side || p.kalshi_leg || "").toUpperCase()}</span></td>
                                <td className="py-2 pr-2 text-right font-mono text-white">{p.ks_price.toFixed(3)}</td>
                                <td className="py-2 pr-2 text-right font-mono text-white">{ksQty}</td>
                                <td className="py-2 pr-2 text-right font-mono text-white">${ksTotal}</td>
                                <td className="py-2 text-right">
                                  <button className="rounded-lg bg-rose-600/80 px-2 py-1 text-[11px] font-semibold text-white hover:bg-rose-500 disabled:opacity-40" onClick={() => handleSell(p.coin, "KS", p)} disabled={ksQty <= 0.01 || !(p.ks_ticker || "") || (selling?.coin === p.coin && selling?.platform === "KS")}>{selling?.coin === p.coin && selling?.platform === "KS" ? "..." : "卖出"}</button>
                                </td>
                              </tr>) : null,
                            ].filter(Boolean)
                          })}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="rounded-xl border border-dashed border-blue-500/15 px-4 py-8 text-center text-sm text-slate-500">暂无记录</div>
                  )}
                </div>
              )
            })}
          </section>
          </div>
        </main>
          <aside className="flex min-h-0 flex-col rounded-[28px] border border-blue-500/20 bg-[#040b17]/95 p-4 shadow-[0_0_40px_rgba(30,64,175,0.12)] overflow-hidden">
            <div className="mb-2 flex items-center justify-between shrink-0">
              <div className="text-sm font-bold text-blue-300">运行日志</div>
              <button className="text-[10px] text-slate-500 hover:text-slate-300" onClick={() => setLogLines([])}>清空</button>
            </div>
            <div className="flex-1 overflow-y-auto font-mono text-[11px] leading-relaxed" style={{scrollbarWidth:"thin"}}>
              {(() => {
                const filtered = logLines.filter(l => !l.includes("HTTP/1.1") && !l.includes("/api/log") && !l.includes("Uvicorn running") && !l.includes("Waiting for application") && !l.includes("Started server process") && !l.includes("Application startup") && !l.includes("shutdown") && !l.includes("reload") && !l.includes("check_event_type(") && !l.includes("py_clob_client_v2"))
                return filtered.length > 0
                  ? filtered.map((line, i) => {
                      let cls = "text-slate-400"
                      if (line.includes("✅") || line.includes("成功")) cls = "text-emerald-400"
                      else if (line.includes("❌") || line.includes("失败") || line.includes("Error") || line.includes("error")) cls = "text-rose-400"
                      else if (line.includes("[AutoTrade]")) cls = "text-cyan-300"
                      else if (line.includes("[Config]")) cls = "text-yellow-400"
                      else if (line.includes("[SimV2]")) cls = "text-purple-400"
                      else if (line.includes("[Balance]") || line.includes("余额检查") || line.includes("发现机会")) cls = "text-slate-300"
                      return <div key={i} className={"whitespace-pre-wrap break-all " + cls}>{line}</div>
                    })
                  : <div className="text-slate-600 text-center pt-8">等待日志...</div>
              })()}
              <div ref={logEndRef} />
            </div>
          </aside>
      </div>
      {showResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowResult(false)}>
          <div className="w-full max-w-sm rounded-2xl border border-blue-500/20 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="text-lg font-bold">{buyResult?.success ? "下单成功" : "下单失败"}</div>
            {buyResult?.error ? (
              <div className="mt-2 text-sm text-rose-300">{buyResult.error}</div>
            ) : (
              <div className="mt-2 space-y-1 text-sm text-slate-300">
                <div>余额: PM {buyResult?.balances?.pm?.toFixed(2)} / KS {buyResult?.balances?.ks?.toFixed(2)}</div>
                {buyResult?.pm_plan && <div>PM: {buyResult.pm_plan.size} @ {buyResult.pm_plan.price}</div>}
                {buyResult?.ks_plan && <div>KS: {buyResult.ks_plan.size} @ {buyResult.ks_plan.price}</div>}
              </div>
            )}
            <button className="mt-4 rounded-xl bg-slate-700 px-3 py-2 text-sm hover:bg-slate-600" onClick={() => setShowResult(false)}>关闭</button>
          </div>
        </div>
      )}
      {showSellResult && sellResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowSellResult(false)}>
          <div className="w-full max-w-sm rounded-2xl border border-blue-500/20 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="text-lg font-bold">{sellResult.success ? "卖出成功" : "卖出失败"}</div>
            {sellResult.error ? (
              <div className="mt-2 text-sm text-rose-300">{sellResult.error}</div>
            ) : (
              <div className="mt-2 space-y-1 text-sm text-slate-300">
                <div>平台: {sellResult.platform}</div>
                <div>卖出数量: {sellResult.filled}</div>
                <div>成交价: {sellResult.price}</div>
                <div>总金额: {sellResult.total}</div>
              </div>
            )}
            <button className="mt-4 rounded-xl bg-slate-700 px-3 py-2 text-sm hover:bg-slate-600" onClick={() => setShowSellResult(false)}>关闭</button>
          </div>
        </div>
      )}
      {showHistory && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowHistory(false)}>
          <div className="flex max-h-[80vh] w-full max-w-4xl flex-col rounded-2xl border border-blue-500/20 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div className="text-lg font-bold">历史订单查询</div>
              <button className="rounded-lg bg-slate-700 px-3 py-1.5 text-sm hover:bg-slate-600" onClick={() => setShowHistory(false)}>关闭</button>
            </div>
            <div className="mb-4 flex items-center gap-2">
              <span className="text-sm text-slate-400">查询范围：</span>
              {[1, 6, 12, 24, 48].map(h => (
                <button key={h} className={"rounded-lg px-3 py-1.5 text-sm " + (historyHours === h ? "bg-blue-600 text-white" : "bg-slate-700 text-slate-300 hover:bg-slate-600")} onClick={() => { setHistoryHours(h); fetchHistory(h) }}>
                  {h < 24 ? h + "小时" : h/24 + "天"}
                </button>
              ))}
            </div>
            {historyLoading ? (
              <div className="flex-1 flex items-center justify-center text-slate-400">加载中...</div>
            ) : historyData.length > 0 ? (
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-blue-500/10 text-left text-xs uppercase tracking-wide text-slate-400">
                      <th className="pb-2 pr-3">时间</th>
                      <th className="pb-2 pr-3">币种</th>
                      <th className="pb-2 pr-3">方向</th>
                      <th className="pb-2 pr-3 text-right">成本(¢)</th>
                      <th className="pb-2 pr-3 text-right">利润(¢)</th>
                      <th className="pb-2 pr-3">状态</th>
                      <th className="pb-2 pr-3">PM成交</th>
                      <th className="pb-2 pr-3">KS成交</th>
                      <th className="pb-2 pr-3">对冲量</th>
                      <th className="pb-2">备注</th>
                    </tr>
                  </thead>
                  <tbody>
                    {historyData.slice().reverse().map((t, i) => (
                      <tr key={i} className={"border-b border-blue-500/5 " + (t.success ? "" : "bg-red-500/5")}>
                        <td className="py-2 pr-3 text-xs text-slate-400 whitespace-nowrap">{new Date(t.time).toLocaleTimeString()}</td>
                        <td className="py-2 pr-3 font-bold text-white">{t.coin}</td>
                        <td className="py-2 pr-3"><span className={t.poly_leg === "Up" ? "text-emerald-400" : "text-rose-400"}>{t.poly_leg}</span></td>
                        <td className="py-2 pr-3 text-right font-mono">{t.total_cost_cents?.toFixed(1)}</td>
                        <td className="py-2 pr-3 text-right font-mono" style={{color: (t.profit_cents || 0) >= 0 ? "#34d399" : "#fb7185"}}>{t.profit_cents?.toFixed(1)}</td>
                        <td className="py-2 pr-3"><span className={"rounded-full px-2 py-0.5 text-xs " + (t.success ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-rose-400")}>{t.success ? "成功" : "失败"}</span></td>
                        <td className="py-2 pr-3 text-right font-mono text-white">{t.pm_filled_qty}</td>
                        <td className="py-2 pr-3 text-right font-mono text-white">{t.ks_fill_count}</td>
                        <td className="py-2 pr-3 text-right font-mono text-white">{t.hedged_qty}</td>
                        <td className="py-2 text-xs text-slate-500">{t.size_warning || t.error || ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500">暂无记录</div>
            )}
            <div className="mt-3 text-xs text-slate-500">共 {historyData.length} 条记录</div>
          </div>
        </div>
      )}
      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowSettings(false)}>
          <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl border border-blue-500/20 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <div className="text-lg font-bold">系统设置</div>
              <button className="rounded-lg bg-slate-700 px-3 py-1.5 text-sm hover:bg-slate-600" onClick={() => setShowSettings(false)}>关闭</button>
            </div>
            {settingsLoading ? (
              <div className="flex-1 flex items-center justify-center py-16 text-slate-400">加载中...</div>
            ) : settingsData ? (
              <div className="flex-1 overflow-y-auto space-y-5">
                <div>
                  <div className="mb-3 text-sm font-semibold text-blue-300 uppercase tracking-wide">份额设置</div>
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs text-slate-400">最低下单份数 (min_shares)</label>
                      <input type="number" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.min_shares} id="s_min_shares" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">每组双边份额</label>
                      <input type="number" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.order_shares} id="s_order_shares" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">总余额下限 USD (min_total_balance)</label>
                      <input type="number" step="0.1" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.min_total_balance} id="s_min_total_balance" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">单笔目标金额 USD (target_usd)</label>
                      <input type="number" step="0.1" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.target_usd} id="s_target_usd" />
                    </div>
                  </div>
                </div>
                <div className="h-px bg-blue-500/10" />
                <div>
                  <div className="mb-3 text-sm font-semibold text-violet-300 uppercase tracking-wide">电竞双边套利</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div><label className="text-xs text-slate-400">最低净利润 (¢/份)</label><input type="number" className="mt-1 w-full rounded-xl border border-violet-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.esports_min_profit_cents ?? 10} id="s_esports_min_profit_cents" /></div>
                    <div><label className="text-xs text-slate-400">手续费缓冲 (¢/份)</label><input type="number" className="mt-1 w-full rounded-xl border border-violet-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.esports_fee_buffer_cents ?? 2} id="s_esports_fee_buffer_cents" /></div>
                    <div><label className="text-xs text-slate-400">固定双边份数</label><input type="number" className="mt-1 w-full rounded-xl border border-violet-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.esports_order_shares ?? 5} id="s_esports_order_shares" /></div>
                    <div><label className="text-xs text-slate-400">扫描间隔 (秒)</label><input type="number" step="0.5" className="mt-1 w-full rounded-xl border border-violet-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.esports_poll_interval ?? 5} id="s_esports_poll_interval" /></div>
                    <div className="col-span-2"><label className="text-xs text-slate-400">更新清单地址（HTTPS JSON）</label><input type="url" placeholder="例如 https://你的域名/pmks/update.json" className="mt-1 w-full rounded-xl border border-cyan-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.update_manifest_url ?? ""} id="s_update_manifest_url" /></div>
                  </div>
                </div>
                <div className="h-px bg-blue-500/10" />
                <div>
                  <div className="mb-3 text-sm font-semibold text-blue-300 uppercase tracking-wide">下单阀值设置</div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs text-slate-400">最低利润 (¢/份，建议8)</label>
                      <input type="number" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.min_profit_cents} id="s_min_profit_cents" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">允许下浮 (¢/份，默认1)</label>
                      <input type="number" min="0" step="0.1" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.profit_tolerance_cents ?? 1} id="s_profit_tolerance_cents" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500">PM价格下限（已停用）</label>
                      <input type="number" disabled className="mt-1 w-full rounded-xl border border-blue-500/10 bg-[#0b1729] px-3 py-2 text-sm text-slate-500 opacity-60" defaultValue={settingsData.price_min_cents} id="s_price_min_cents" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500">PM价格上限（已停用）</label>
                      <input type="number" disabled className="mt-1 w-full rounded-xl border border-blue-500/10 bg-[#0b1729] px-3 py-2 text-sm text-slate-500 opacity-60" defaultValue={settingsData.price_max_cents} id="s_price_max_cents" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">交易冷却 (cooldown 秒)</label>
                      <input type="number" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.cooldown} id="s_cooldown" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">轮询间隔 (poll_interval 秒)</label>
                      <input type="number" step="0.1" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.poll_interval} id="s_poll_interval" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-500">整点禁交易时间（已停用）</label>
                      <input type="number" disabled className="mt-1 w-full rounded-xl border border-blue-500/10 bg-[#0b1729] px-3 py-2 text-sm text-slate-500 opacity-60" defaultValue={settingsData.start_delay_mins} id="s_start_delay_mins" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">连续失败基础冷却 (秒)</label>
                      <input type="number" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.fail_cooldown_base} id="s_fail_cooldown_base" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">连续失败最大冷却 (秒)</label>
                      <input type="number" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.fail_cooldown_max} id="s_fail_cooldown_max" />
                    </div>
                    <div>
                      <label className="text-xs text-slate-400">每小时最多组数</label>
                      <input type="number" min="1" step="1" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" defaultValue={settingsData.max_trades_per_hour ?? 5} id="s_max_trades_per_hour" />
                    </div>
                  </div>
                </div>
                <button className="w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50" disabled={savingSettings} onClick={() => {
                  const fields = ["min_shares","order_shares","min_total_balance","target_usd","min_profit_cents","profit_tolerance_cents","price_min_cents","price_max_cents","cooldown","poll_interval","start_delay_mins","fail_cooldown_base","fail_cooldown_max","max_trades_per_hour","esports_min_profit_cents","esports_fee_buffer_cents","esports_order_shares","esports_poll_interval","update_manifest_url"]
                  const updates: Record<string,any> = {}
                  fields.forEach(f => {
                    const el = document.getElementById("s_"+f) as HTMLInputElement
                    if (el) updates[f] = f === "update_manifest_url" ? el.value.trim() : (el.value.includes(".") ? parseFloat(el.value) : parseInt(el.value))
                  })
                  saveSettings(updates)
                }}>
                  {savingSettings ? "保存中..." : "保存设置并立即生效"}
                </button>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center py-16 text-rose-400">加载设置失败</div>
            )}
          </div>
        </div>
      )}
      {showCredentials && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setShowCredentials(false)}>
          <div className="flex max-h-[88vh] w-full max-w-xl flex-col rounded-2xl border border-amber-500/20 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="mb-1 flex items-center justify-between">
              <div className="flex items-center gap-2 text-lg font-bold"><KeyRound className="h-5 w-5 text-amber-300" /> API连接与密钥</div>
              <button className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700 hover:text-white" onClick={() => setShowCredentials(false)} aria-label="关闭"><X className="h-5 w-5" /></button>
            </div>
            <div className="mb-4 text-xs text-slate-400">密钥只在本机加密保存，不会显示在日志或界面上。保存后点击连接测试。</div>
            <div className="flex-1 space-y-3 overflow-y-auto">
              <div className="rounded-xl border border-blue-500/15 bg-[#0b1729] p-3">
                <div className="mb-2 text-sm font-semibold text-blue-300">Polymarket</div>
                <label className="text-xs text-slate-400">钱包私钥（64位十六进制）</label>
                <input id="c_polymarket_private_key" type="password" autoComplete="new-password" placeholder="留空表示保持已保存的密钥" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#071120] px-3 py-2 text-sm text-white" />
                <label className="mt-3 block text-xs text-slate-400">Funder / Proxy钱包地址</label>
                <input id="c_polymarket_funder" placeholder="0x..." className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#071120] px-3 py-2 text-sm text-white" />
                <label className="mt-3 block text-xs text-slate-400">签名类型</label>
                <select id="c_polymarket_signature_type" defaultValue={credentialStatus?.signature_type || "0"} className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#071120] px-3 py-2 text-sm text-white"><option value="0">EOA</option><option value="1">Proxy</option><option value="2">Gnosis Safe</option><option value="3">服务器兼容类型 3</option></select>
                <div className="mt-2 text-xs text-slate-500">状态：{credentialStatus?.polymarket_configured ? `已配置 ${credentialStatus.funder_hint || ""}` : "未配置"}</div>
              </div>
              <div className="rounded-xl border border-emerald-500/15 bg-[#0b1729] p-3">
                <div className="mb-2 text-sm font-semibold text-emerald-300">Kalshi</div>
                <label className="text-xs text-slate-400">API Key ID</label>
                <input id="c_kalshi_api_key_id" placeholder="例如 UUID" className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#071120] px-3 py-2 text-sm text-white" />
                <label className="mt-3 block text-xs text-slate-400">RSA私钥 PEM</label>
                <textarea id="c_kalshi_private_key_pem" rows={6} autoComplete="off" placeholder="-----BEGIN PRIVATE KEY-----\n..." className="mt-1 w-full resize-y rounded-xl border border-blue-500/20 bg-[#071120] px-3 py-2 font-mono text-xs text-white" />
                <div className="mt-2 text-xs text-slate-500">状态：{credentialStatus?.kalshi_configured ? `已配置 ${credentialStatus.kalshi_key_hint || ""}` : "未配置"}</div>
              </div>
              <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-3">
                <div className="mb-2 text-sm font-semibold text-violet-300">导入服务器凭据备份</div>
                <div className="mb-3 text-xs text-slate-400">选择加密的 .pmksbackup 文件。导入成功后会绑定当前Windows账户加密保存。</div>
                <input id="credential_backup_file" type="file" accept=".pmksbackup,text/plain" className="block w-full text-xs text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-600 file:px-3 file:py-2 file:text-xs file:text-white" />
                <input type="password" value={credentialImportPassword} onChange={e => setCredentialImportPassword(e.target.value)} placeholder="备份密码" className="mt-3 w-full rounded-xl border border-violet-500/20 bg-[#071120] px-3 py-2 text-sm text-white" />
                <button disabled={credentialImporting} onClick={importCredentialBackup} className="mt-3 w-full rounded-xl bg-violet-600 py-2.5 text-sm font-semibold hover:bg-violet-500 disabled:opacity-50">{credentialImporting ? "正在导入..." : "导入并加密保存"}</button>
              </div>
              {credentialTest && <div className={`rounded-xl border px-3 py-2 text-sm ${credentialTest.ok ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-rose-500/30 bg-rose-500/10 text-rose-300"}`}>
                {credentialTest.error || (credentialTest.ok ? "两个平台连接成功" : "连接测试未通过")}
                {credentialTest.polymarket && <div className="mt-1 text-xs">PM：{credentialTest.polymarket.ok ? `成功，余额 $${credentialTest.polymarket.balance}` : credentialTest.polymarket.error}</div>}
                {credentialTest.kalshi && <div className="text-xs">KS：{credentialTest.kalshi.ok ? `成功，余额 $${credentialTest.kalshi.balance}` : credentialTest.kalshi.error}</div>}
              </div>}
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <button className="flex items-center justify-center gap-2 rounded-xl border border-blue-500/25 bg-[#0b1729] py-3 text-sm font-semibold text-white hover:bg-blue-500/10 disabled:opacity-50" disabled={credentialTesting} onClick={testCredentials}><TestTube2 className="h-4 w-4" />{credentialTesting ? "测试中..." : "连接测试"}</button>
              <button className="rounded-xl bg-amber-600 py-3 text-sm font-semibold text-white hover:bg-amber-500 disabled:opacity-50" disabled={credentialSaving} onClick={saveCredentials}>{credentialSaving ? "保存中..." : "加密保存"}</button>
            </div>
          </div>
        </div>
      )}
      {showManualTrade && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setShowManualTrade(false)}>
          <div className="w-full max-w-lg rounded-2xl border border-emerald-500/20 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="mb-1 flex items-center justify-between"><div className="flex items-center gap-2 text-lg font-bold"><HandCoins className="h-5 w-5 text-emerald-300" />手动双边下单</div><button className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700" onClick={() => setShowManualTrade(false)} aria-label="关闭"><X className="h-5 w-5" /></button></div>
            <div className="mb-4 text-xs text-slate-400">只从当前监控到的PM/KS配对中选择，程序下单前会重新读取盘口并使用FOK。</div>
            <div className="space-y-3">
              <div><label className="text-xs text-slate-400">币种</label><select value={manualCoin} onChange={e => { setManualCoin(e.target.value); setManualIndex(0) }} className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white">{coinKeys.map(c => <option key={c} value={c}>{c}</option>)}</select></div>
              <div><label className="text-xs text-slate-400">市场配对（行权价 / 方向）</label><select value={manualIndex} onChange={e => setManualIndex(parseInt(e.target.value))} className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white">{manualChecks.map((c: ArbCheck, i: number) => <option key={i} value={i}>KS {c.kalshi_strike.toLocaleString()}：PM {c.poly_leg} + KS {c.kalshi_leg}，成本 {c.total_cost.toFixed(3)}</option>)}</select></div>
              <div><label className="text-xs text-slate-400">两边份数（相同数量）</label><input type="number" min={1} step={1} value={manualShares} onChange={e => setManualShares(Math.max(1, parseInt(e.target.value || "1")))} className="mt-1 w-full rounded-xl border border-blue-500/20 bg-[#0b1729] px-3 py-2 text-sm text-white" /></div>
              <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">手动下单不代表无风险套利，请确认方向、行权价和两边可用余额。当前策略配置的最低份额仍会生效。</div>
            </div>
            <button disabled={!manualChoice || buying} onClick={() => { if (manualChoice) { setShowManualTrade(false); buyArbitrage(manualCoin, manualChoice.poly_leg, manualChoice.kalshi_leg, manualChoice.kalshi_strike, manualChoice.ks_ticker || "", manualShares) } }} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 py-3 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"><HandCoins className="h-4 w-4" />{buying ? "下单中..." : "确认双边下单"}</button>
          </div>
        </div>
      )}
      {showEsports && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" onClick={() => setShowEsports(false)}>
          <div className="flex max-h-[88vh] w-full max-w-4xl flex-col rounded-2xl border border-violet-500/25 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-2 text-lg font-bold"><Gamepad2 className="h-5 w-5 text-violet-300" />电竞双边套利</div>
                <div className="mt-1 text-xs text-slate-400">只匹配PM与KS同一场比赛的整场胜负盘；地图、单局、让分和总局数盘口已排除。</div>
              </div>
              <button className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700" onClick={() => setShowEsports(false)} aria-label="关闭"><X className="h-5 w-5" /></button>
            </div>
            <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
              <div className="rounded-xl border border-violet-500/15 bg-[#0b1729] p-3"><div className="text-xs text-slate-400">已匹配市场</div><div className="mt-1 text-xl font-bold">{esportsData?.matched_markets ?? "--"}</div></div>
              <div className="rounded-xl border border-violet-500/15 bg-[#0b1729] p-3"><div className="text-xs text-slate-400">达标机会</div><div className="mt-1 text-xl font-bold text-emerald-400">{esportsData?.total ?? "--"}</div></div>
              <div className="rounded-xl border border-violet-500/15 bg-[#0b1729] p-3"><label className="text-xs text-slate-400">两边份数</label><input type="number" min={1} step={1} value={esportsShares} onChange={e => setEsportsShares(Math.max(1, parseInt(e.target.value || "1")))} className="mt-1 w-full rounded-lg border border-violet-500/20 bg-[#071120] px-2 py-1.5 text-sm" /></div>
              <button onClick={toggleEsportsAuto} className={`rounded-xl px-3 py-2 text-sm font-semibold ${esportsAuto?.enabled ? "bg-red-600 hover:bg-red-500" : "bg-violet-600 hover:bg-violet-500"}`}>
                {esportsAuto?.enabled ? "停止电竞自动交易" : "启动电竞自动交易"}
              </button>
            </div>
            <div className="mb-3 rounded-xl border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">利润已扣除预留手续费缓冲；真正下单前还会重新读取两边盘口，利润不足或深度不足会直接拒绝，不会追价。</div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {esportsLoading && !esportsData ? <div className="py-16 text-center text-slate-400">正在匹配电竞市场...</div> : esportsData?.error ? <div className="rounded-xl bg-red-500/10 p-4 text-sm text-rose-300">{esportsData.error}</div> : (esportsData?.opportunities || []).length === 0 ? <div className="py-16 text-center text-slate-500">当前没有达到利润阈值的电竞双边机会</div> : (
                <div className="space-y-3">
                  {(esportsData?.opportunities || []).map(op => (
                    <div key={op.id} className="rounded-xl border border-violet-500/15 bg-[#0b1729] p-4">
                      <div className="flex flex-col justify-between gap-3 lg:flex-row lg:items-center">
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-white">{op.title}</div>
                          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
                            <span className="text-blue-300">PM买 {op.pm_team} @ {(op.pm_price * 100).toFixed(1)}¢</span>
                            <span className="text-emerald-300">KS买 {op.ks_team} ({op.ks_side.toUpperCase()}) @ {(op.ks_price * 100).toFixed(1)}¢</span>
                            <span className="text-slate-400">总成本 {(op.total_cost * 100).toFixed(1)}¢</span>
                            <span className="text-violet-300">配对可信度 {(op.match_score * 100).toFixed(0)}%</span>
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-3">
                          <div className="text-right"><div className="text-xs text-slate-400">预估净利润/份</div><div className="font-mono text-xl font-bold text-emerald-400">+{op.estimated_profit_cents.toFixed(1)}¢</div></div>
                          <button disabled={esportsExecuting || esportsAuto?.enabled} onClick={() => executeEsports(op)} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold hover:bg-emerald-500 disabled:opacity-50">{esportsExecuting ? "下单中..." : "立即双边下单"}</button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {esportsAuto?.last_result?.error && <div className="mt-3 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-rose-300">最近执行：{esportsAuto.last_result.error}</div>}
          </div>
        </div>
      )}
      {showUpdate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setShowUpdate(false)}>
          <div className="w-full max-w-md rounded-2xl border border-cyan-500/25 bg-[#071120] p-5 text-white" onClick={e => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between"><div className="text-lg font-bold">软件更新</div><button className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-700" onClick={() => setShowUpdate(false)} aria-label="关闭"><X className="h-5 w-5" /></button></div>
            {updateInfo?.error ? <div className="rounded-xl bg-red-500/10 p-3 text-sm text-rose-300">{updateInfo.error}</div> : !updateInfo?.configured ? <div className="rounded-xl bg-amber-500/10 p-3 text-sm text-amber-200">尚未配置更新清单地址。请在系统设置中填写HTTPS JSON地址。</div> : updateInfo?.available ? <div className="space-y-3 text-sm"><div>当前版本：<span className="font-mono">{updateInfo.current_version}</span></div><div>最新版本：<span className="font-mono text-emerald-400">{updateInfo.latest_version}</span></div>{updateInfo.notes && <div className="rounded-xl bg-[#0b1729] p-3 text-xs text-slate-300">{updateInfo.notes}</div>}<button onClick={applyUpdate} disabled={!!updateInfo.applyResult} className="w-full rounded-xl bg-cyan-600 py-3 font-semibold hover:bg-cyan-500 disabled:opacity-50">{updateInfo.applyResult?.message || "下载并安装更新"}</button>{updateInfo.applyResult?.error && <div className="text-xs text-rose-300">{updateInfo.applyResult.error}</div>}</div> : <div className="rounded-xl bg-emerald-500/10 p-3 text-sm text-emerald-300">当前已经是最新版本（{updateInfo?.current_version || "未知"}）。</div>}
          </div>
        </div>
      )}
      {restarting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-sm rounded-2xl border border-blue-500/20 bg-[#071120] p-8 text-center text-white">
            <div className="mb-4 text-2xl">🔄</div>
            <div className="text-lg font-bold">设置已保存</div>
            <div className="mt-2 text-sm text-slate-300">后端正在重启，页面即将自动刷新...</div>
            <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-blue-500/20">
              <div className="h-full animate-pulse rounded-full bg-blue-500" style={{width: "100%"}} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
