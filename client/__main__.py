"""python -m client 入口."""

from __future__ import annotations

import sys


def main() -> int:
    from .app import RecruitApp

    app = RecruitApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
