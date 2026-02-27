@echo off
cd /d C:\Users\minju\clone\tools\confluence-weekly-report
python weekly_report.py new-week >> weekly-report.log 2>&1
