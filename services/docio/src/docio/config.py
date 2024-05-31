LOGS = {
    "stderr": {
        "level": "INFO",
        "serialize": False,
        "backtrace": False,
        "diagnose": True,
        "enqueue": True,
        "catch": True,
    },
    "logs/docio.log": {
        "level": "INFO",
        "serialize": False,
        "backtrace": False,
        "diagnose": True,
        "enqueue": True,
        "catch": True,
        "rotation": "50 MB",
        "delay": False,
        "watch": False,
    },
}
