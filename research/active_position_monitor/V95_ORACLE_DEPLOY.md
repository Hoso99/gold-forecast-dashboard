# V9.5 isolated Oracle paper monitor

**Not a validated profitable strategy.** The M15 breakout / H1 trend / 10-M1 candle-body proxy is an exploratory SELL-entry rule, **not** the live V9.4 model. Dynamic exits are hypothetical and do not represent broker fills. No broker integration, no automatic orders, and no modifications to V9.4.

## Preconditions
- Existing Oracle Ubuntu host with `/home/ubuntu/v95-research` separate checkout and Python `.venv`.
- A Twelve Data API key entitled to XAU/USD M1.
- Check UTC timestamp semantics and whether the feed is tradable before using alerts for decisions.
- Do not paste credentials in GitHub, chat, terminal logs or commands. GitHub Actions secrets do not automatically propagate to Oracle.
- No automatic trade opening or closing; position state is paper-only.

## Setup (after reviewing code and confirming)
1. Update only the V9.5 checkout to the reviewed research commit.
2. Create `/home/ubuntu/.config/v95-research` owned by ubuntu with mode 0700.
3. Create `monitor.env` in that directory, mode 0600, with `TWELVE_DATA_API_KEY` set from the existing secure Oracle environment. Use `V95_TELEGRAM_ENABLED=0` initially. Do not copy tokens into shared terminal history.
4. Verify `.venv/bin/python` and run `python -m py_compile research/active_position_monitor/v95_paper_monitor.py`.
5. Install `v95-research-monitor.service` in `/etc/systemd/system/` (root required); run `sudo systemctl daemon-reload`, `sudo systemctl enable --now v95-research-monitor`.
6. Inspect `sudo systemctl status v95-research-monitor --no-pager` and `journalctl -u v95-research-monitor -n 30 --no-pager`. No service success claim until logs show completed M1 evaluations.
7. Only after secure Telegram provisioning and an approved test notification, set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `V95_TELEGRAM_ENABLED=1` in the protected env file and restart **only** this service.

## Safety and limitations
- Provider M1 timestamps are treated as **OPEN-stamped**; not independently verified. Any gap in the required recent M1 history or stale data causes WAIT_DATA, not a signal.
- The monitor computes 10-bar body-direction pressure, **not** exchange order-flow pressure or Biquote pressure.
- It uses a fixed structure + 1.5 ATR buffer and 2R target, **not** the full adaptive V9.4 ATR/event logic.
- A paper position is opened at the last completed M1 close, not a tradable fill.
- Stop-first M1 touch handling and hypothetical partials can differ materially from broker execution. No slippage, spread or commissions are modeled in monitoring.
- Paper state is local at `~/.local/state/v95-research/state.json`; backup or reset only after reviewing its contents. Do not run multiple instances against one state file.
- Telegram messages are labeled PAPER RESEARCH. A Telegram send failure does not imply an order was placed.
- Avoid enabling during unverified weekend/holiday quotes; assess provider market hours.
- For a full production-quality monitor: validate timestamps, incorporate event/volatility feeds, reconcile a real read-only position ledger, test rate limits and run independent forward validation.

## V9.5 shadow journal and initial smoke test
- The research-only monitor writes V9.5 SELL and WAIT decisions to `~/.local/state/v95-research/decisions.jsonl`; it never reads or writes V9.4 state or signals.
- Set `V95_PAPER_EQUITY` to an explicitly chosen *hypothetical* positive account balance to enable 2% paper sizing; do not infer or reuse real account equity. 3% UTC-day realized paper loss lock is a research approximation, not a broker-level safeguard.
- From the existing Ubuntu shell, update **only** `/home/ubuntu/v95-research` using `cd /home/ubuntu/v95-research && git fetch origin research/v94-reliability-audit-20261011 && git checkout --detach FETCH_HEAD` after CI succeeds.
- Run the offline test suite, then `V95_TELEGRAM_ENABLED=0 .venv/bin/python research/active_position_monitor/v95_paper_monitor.py --once` to check one observation. The environment must already contain the Twelve Data key; do not display it.
- The `--once` check does not install a daemon. Review data timestamps, WAIT reasons, and journal before enabling notifications. An observed SELL is a hypothetical paper signal, not a broker trade.
- No automatic V9.4 comparison is claimed until a separate read-only historical V9.4 journal is obtained with matching timestamps and verified source parity.
