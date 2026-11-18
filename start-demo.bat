@echo off
setlocal
cd /d "%~dp0"
echo WUSA Rewards Map demo
echo Serving this project folder so the docs page can find demo-rewards.json.
echo Leave this window open. Open http://localhost:8000/docs/ in your browser.
echo Press Ctrl+C in this window to stop the server.
echo.
python -m http.server 8000
if errorlevel 1 (
    echo.
    echo The server could not start. If port 8000 is in use, stop the other server and try again.
    pause
)
