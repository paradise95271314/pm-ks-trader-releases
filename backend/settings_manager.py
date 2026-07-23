"""
Settings REST API — 读取/保存 bot_config.json
"""
import json

from app_paths import CONFIG_FILE, ensure_data_dir

DEFAULT_CONFIG = {
    "config_schema_version": 4,
    "poll_interval": 2,
    "cooldown": 30,
    "min_profit_cents": 8,
    "profit_tolerance_cents": 1,
    "price_min_cents": 70,
    "price_max_cents": 88,
    "min_shares": 5,
    "order_shares": 5,
    "min_total_balance": 5.0,
    "target_usd": 10.0,
    "start_delay_mins": 0,
    "fail_cooldown_base": 30,
    "fail_cooldown_max": 300,
    "liquidity_buffer": 1.0,
    "stop_on_unhedged": True,
    "max_trades_per_hour": 5,
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
                stored = json.load(f)
            if int(stored.get("config_schema_version", 1) or 1) < 4:
                stored.update({
                    "config_schema_version": 4,
                    "min_profit_cents": 8,
                    "profit_tolerance_cents": 1,
                    "start_delay_mins": 0,
                    "liquidity_buffer": 1.0,
                    "max_trades_per_hour": 5,
                })
                with CONFIG_FILE.open("w", encoding="utf-8") as f:
                    json.dump(stored, f, indent=2, ensure_ascii=False)
            cfg.update(stored)
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
