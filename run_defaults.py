"""Shared default run examples; no interactive code runs on import."""
DEFAULT_RUN_PROFILES = {
    "Cam": {
        "messages": [
            "BEGIN PROCESS",
            "END PROCESS",
            "> LOGIN HQ ...",
            "> LOGIN PAYER ...",
            "No more pending notifications.",
            "> LOGOUT HQ ...",
            "> LOGOUT PAYER ...",
            "Info: The session was successfully closed.",
            "> INITIALIZING TIME ..."
        ],
        "labels": ["Run_Start", "Run_End"] + ["Other"] * 7
    },

    "UNITRANSFER": {
        "messages": [
            "INFO HQ BEGIN PROCESS",
            "INFO HQ END PROCESS",
            "INFO HQ GIROSOL WEB SERVICE LOGIN...",
            "INFO HQ GIROSOL WEB SERVICE LOGIN OK",
            "INFO HQ Login to Unitransfer Successfull",
            "INFO HQ PAYER LOGIN SUCCESSFUL",
            "INFO HQ GETTING PENDING DISTRIBUTION ORDERS...",
            "INFO HQ NO MORE PENDING ORDERS",
            "INFO HQ NO MORE CANCELLATION REQUEST",
            "INFO PAYER GETTING NOTIFICATIONS...",
            "INFO PAYER Order sent and Pending to be process.",
            "INFO PAYER Order Pending to be paid.",
            "INFO HQ Logout to Unitransfer Successfull",
            "INFO HQ GIROSOL WEB SERVICE LOGOUT...",
            "INFO HQ GIROSOL WEB SERVICE LOGOUT OK",
            "> INITIALIZING TIME ..."
        ],
        "labels": ["Run_Start", "Run_End"] + ["Other"] * 14
    }
}
