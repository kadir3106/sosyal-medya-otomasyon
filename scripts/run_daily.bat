@echo off
cd /d "c:\Projects\sosyal-medya-otomasyon"
"C:\Users\Victus\AppData\Local\Programs\Python\Python313\python.exe" "scripts\daily_autonomous_agent.py" --now >> "video-output\daily_scheduler.log" 2>&1
