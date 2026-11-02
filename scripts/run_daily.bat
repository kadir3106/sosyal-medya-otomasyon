@echo off
REM Gunluk otonom tur.
REM
REM Varsayilan: `--director` = Telegram onay akisi. Video uretilir, Telegram'a
REM onizleme + "Yayinla / Iptal" butonlari gider. Onay gelirse hemen yayinlanir;
REM yanit gelmezse 180 sn sonra otomatik yayinlanir. "Iptal" her zaman kazanir.
REM
REM Bu bayrak daha once YOKTU: `run_daily.bat` dogrudan `--now` cagiriyordu,
REM yani gunluk otomasyon onay adimini tamamen atliyordu. Ustelik o halde
REM ALLOW_AUTONOMOUS_PUBLISH de .env'de tanimli olmadigi icin tur video uretip
REM sessizce yayinlamadan bitiyordu.
REM
REM Tamamen onaysiz yayin istiyorsaniz: .env'de ALLOW_AUTONOMOUS_PUBLISH=true
REM yapin VE asagidaki satirda --director yerine --now kullanin. Iki degisiklik
REM ayri ayri anlamli: bayrak "onaysiz yayina izin ver" der, --now "onay sorma"
REM der. Yalnizca bayragi acmak onay akisini korur (onerilen).
cd /d "c:\Projects\sosyal-medya-otomasyon"
"C:\Users\Victus\AppData\Local\Programs\Python\Python313\python.exe" "scripts\daily_autonomous_agent.py" --director >> "video-output\daily_scheduler.log" 2>&1

