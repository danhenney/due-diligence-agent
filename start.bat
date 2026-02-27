@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install --user -r requirements.txt
echo.
echo Starting Due Diligence Agent...
python -m streamlit run app.py
pause
