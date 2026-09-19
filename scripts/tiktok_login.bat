@echo off
chcp 65001 >nul
title TikTok Giris ve Oturum Kurulumu
cd /d "c:\Projects\sosyal-medya-otomasyon"
python scripts\tiktok_browser_login.py
pause
