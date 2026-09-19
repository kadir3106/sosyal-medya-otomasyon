@echo off
chcp 65001 >nul
echo ========================================================
echo   Peak Motivation - Günlük Otonom Zamanlayıcı Kurulumu
echo ========================================================
echo.
echo Bu işlem, her gün 2 altın saatte (12:45 ve 18:45 TSİ) otomatik olarak:
echo  1. Sıradaki gizem konusunu seçecek,
echo  2. Kling AI + ElevenLabs ile 1080p Shorts render edecek,
echo  3. YouTube kanalınıza (Peak Motivation) herkese açık yükleyecek,
echo  4. Yorumlarda tartışma kancası sabitleyecek,
echo  5. Telegram'dan canlı izleme linkini gönderecektir.
echo.

set BATCH_PATH=c:\Projects\sosyal-medya-otomasyon\scripts\run_daily.bat

schtasks /create /tn "PeakMotivationNoonShorts" /tr "%BATCH_PATH%" /sc daily /st 12:45 /f
schtasks /create /tn "PeakMotivationDailyShorts" /tr "%BATCH_PATH%" /sc daily /st 18:45 /f

if %ERRORLEVEL% equ 0 (
    echo.
    echo [BAŞARILI] Görevler Windows Zamanlayıcı'ya eklendi!
    echo Her gün 12:45 ve 18:45'te arka planda otomatik çalışacaktır.
) else (
    echo.
    echo [UYARI] Görev eklenirken yönetici yetkisi gerekebilir.
    echo Lütfen bu dosyaya sağ tıklayıp "Yönetici olarak çalıştır" deyin.
)
echo.
pause
