$app = Split-Path -Parent $PSScriptRoot
Start-Process python -ArgumentList '-m','streamlit','run','ss_dash.py','--server.port','8501','--server.headless','true','--browser.gatherUsageStats','false','--server.fileWatcherType','none' -WorkingDirectory $app -WindowStyle Hidden
