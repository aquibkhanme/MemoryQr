import sqlite3
from datetime import datetime, timedelta


DB = "analytics.db"


def init_db():

    conn = sqlite3.connect(DB)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT,
            visit_time TEXT,
            device TEXT,
            browser TEXT,
            memory_id TEXT
        )
    """)

    conn.commit()
    conn.close()


def detect_device(user_agent):

    ua = user_agent.lower()

    if (
        "mobile" in ua
        or "android" in ua
        or "iphone" in ua
    ):
        return "Mobile"

    if (
        "tablet" in ua
        or "ipad" in ua
    ):
        return "Tablet"

    return "Desktop"


def detect_browser(user_agent):

    ua = user_agent.lower()

    if "edg" in ua:
        return "Edge"

    if "chrome" in ua:
        return "Chrome"

    if "firefox" in ua:
        return "Firefox"

    if "safari" in ua:
        return "Safari"

    return "Other"


def track_request(req):

    path = req.path

    if (
        path.startswith("/static/")
        or path.startswith("/admin")
        or path.startswith("/memories/")
    ):
        return

    memory_id = None

    if path.startswith("/memory/"):

        memory_id = (
            path.split(
                "/memory/",
                1
            )[1]
            .strip("/")
        )

    user_agent = req.headers.get(
        "User-Agent",
        ""
    )

    conn = sqlite3.connect(DB)

    conn.execute(
        """
        INSERT INTO visits
        (
            path,
            visit_time,
            device,
            browser,
            memory_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            path,
            datetime.now().isoformat(),
            detect_device(user_agent),
            detect_browser(user_agent),
            memory_id
        )
    )

    conn.commit()
    conn.close()


def get_stats():

    conn = sqlite3.connect(DB)

    cur = conn.cursor()

    cur.execute(
        "SELECT COUNT(*) FROM visits"
    )

    total_visits = cur.fetchone()[0]

    today = datetime.now().strftime(
        "%Y-%m-%d"
    )

    cur.execute(
        """
        SELECT COUNT(*)
        FROM visits
        WHERE visit_time LIKE ?
        """,
        (today + "%",)
    )

    today_visits = cur.fetchone()[0]

    seven_days_ago = (
        datetime.now()
        - timedelta(days=6)
    ).strftime("%Y-%m-%d")

    cur.execute(
        """
        SELECT COUNT(*)
        FROM visits
        WHERE visit_time >= ?
        """,
        (seven_days_ago + "T00:00:00",)
    )

    seven_day_visits = cur.fetchone()[0]

    cur.execute(
        """
        SELECT COUNT(*)
        FROM visits
        WHERE path LIKE '/memory/%'
        """
    )

    memory_views = cur.fetchone()[0]

    cur.execute(
        """
        SELECT memory_id, COUNT(*)
        FROM visits
        WHERE memory_id IS NOT NULL
        GROUP BY memory_id
        ORDER BY COUNT(*) DESC
        LIMIT 1
        """
    )

    most_viewed = cur.fetchone()

    cur.execute(
        """
        SELECT device, COUNT(*)
        FROM visits
        GROUP BY device
        ORDER BY COUNT(*) DESC
        """
    )

    devices = cur.fetchall()

    cur.execute(
        """
        SELECT browser, COUNT(*)
        FROM visits
        GROUP BY browser
        ORDER BY COUNT(*) DESC
        """
    )

    browsers = cur.fetchall()

    conn.close()

    return {
        "total_visits": total_visits,
        "today_visits": today_visits,
        "seven_day_visits": seven_day_visits,
        "memory_views": memory_views,
        "most_viewed": most_viewed,
        "devices": devices,
        "browsers": browsers
    }
