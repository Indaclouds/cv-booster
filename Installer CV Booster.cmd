@echo off
chcp 65001 >nul
title Installation de CV Booster
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0.app\installer.ps1" %*
