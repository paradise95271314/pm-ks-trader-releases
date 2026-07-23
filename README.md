# PM-KS Trader Updates

This repository hosts signed-by-hash Windows update manifests and installers.

## 修改日志

### v1.3.0 (2026-07-23)
- 清理 execute_arb.py 无用调试输出（KS原始响应）
- 新增整点前后8分钟不下单保护：分钟数 0-7 和 52-59 期间自动跳过交易
