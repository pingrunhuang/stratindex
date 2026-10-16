"""CLI: python -m race [seed|fetch|run]"""
import sys

from race import data, store


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "run"
    c = store.conn()
    if cmd in ("seed", "run"):
        print("seeded", store.seed(c))
    if cmd == "fetch":
        for s in data.SYMBOLS:
            data.refresh(s, verbose=True)
    if cmd == "run":
        rid = store.run_race(c, refresh="--no-fetch" not in argv)
        run, rows = store.leaderboard(c)
        print(f"run #{rid}")
        print(f"{'P':>2} {'strategy':26} {'OOS Sh':>7} {'OOS DD':>7} {'OOS ret':>8} {'Full ret':>9} {'CAGR':>7} {'Sharpe':>7} {'MaxDD':>7} {'Win%':>5} {'#Tr':>4} {'30d':>6}")
        for r in rows:
            o, f = r["res"]["oos"], r["res"]["full"]
            print(f"{r['position']:>2} {r['name'][:26]:26} {o['sharpe']:>7.2f} {o['max_dd']:>7.1f} {o['total_return']:>8.1f} "
                  f"{f['total_return']:>9.1f} {f['cagr'] or 0:>7.1f} {f['sharpe']:>7.2f} {f['max_dd']:>7.1f} {f['win_rate'] or 0:>5.1f} {f['trades']:>4} {r['res']['ret_30d'] or 0:>6.1f}")


if __name__ == "__main__":
    main(sys.argv)
