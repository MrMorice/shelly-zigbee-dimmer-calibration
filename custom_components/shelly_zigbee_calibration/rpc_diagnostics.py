"""Interpret transport observations without claiming a firmware root cause."""


def summarize(report):
    if report.get("status") == "cancelled":
        return "RPC-Prüfung unterbrochen"
    if report.get("status") == "complete":
        if report.get("settings_supported") is False:
            return "RPC vollständig; Dimmparameter fehlen"
        return "RPC-Antwort vollständig"
    if report.get("rpc_error_received"):
        return "Shelly meldet RPC-Fehler"
    if report.get("rpc_frames_unmatched", 0):
        return "RPC-Antwort nicht zugeordnet"
    if report.get("data_read_attempts", 0):
        if report.get("data_bytes", 0):
            return "RPC-Daten unvollständig oder ungültig"
        return "RPC-Datenantwort fehlt oder ist ungültig"
    if report.get("rxctl_reads_succeeded", 0):
        return "RxCtl meldet keine Antwortdaten"
    if report.get("rxctl_read_attempts", 0):
        return "RxCtl-Antwort fehlt oder ist ungültig"
    return "RPC-Anfrage nicht vollständig übertragen"
