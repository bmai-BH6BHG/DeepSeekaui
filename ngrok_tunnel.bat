@echo off
REM 使用前先: ngrok config add-authtoken YOUR_TOKEN
set NGROK=H:\download\PULSE-7B\ngrok-v3-stable-windows-amd64\ngrok.exe
"%NGROK%" tcp 9876
