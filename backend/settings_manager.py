"""
Settings REST API — 读取/保存 bot_config.json
"""
import json

from app_paths import CONFIG_FILE, ensure_data_dir

DEFAULT_CONFIG = {
    "poll_interval": 2,
    "cooldown": 30,
    "min_profit_cents": 10,
    "price_min_cents": 70,
    "price_max_cents": 88,
    "min_shares": 5,
    "order_shares": 5,
    "min_total_balance": 5.0,
    "target_usd": 10.0,
    "start_delay_mins": 8,
    "fail_cooldown_base": 30,
    "fail_cooldown_max": 300,
    "liquidity_buffer": 2.0,
    "stop_on_unhedged": True,
    "max_trades_per_hour": 1,
    "enabled_coins": ["BTC"],
    "esports_min_profit_cents": 10,
    "esports_fee_buffer_cents": 2,
    "esports_order_shares": 5,
    "esports_poll_interval": 5,
    "update_manifest_url": "",
}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open(encoding="utf-8") as f:
                cfg.update(json.load(f))
        else:
            legacy = __import__("pathlib").Path(__file__).with_name("bot_config.json")
            if legacy.exists():
                with legacy.open(encoding="utf-8") as f:
                    cfg.update(json.load(f))
                save_config(cfg)
    except:
        pass
    return cfg

def save_config(updates):
    try:
        ensure_data_dir()
        cfg = dict(DEFAULT_CONFIG)
        if CONFIG_FILE.exists():
            with CONFIG_FILE.open(encoding="utf-8") as f:
                cfg.update(json.load(f))
        cfg.update(updates)
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        return True
    except:
        return False
