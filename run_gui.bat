@echo off
cd /d C:\Users\jmskh\projects\zcyber-xhs
set PYTHONPATH=%CD%\src;%PYTHONPATH%
echo Starting ZCyber XHS GUI...
echo Open your browser at http://localhost:8501
echo Press Ctrl+C to stop.
echo.
C:\Users\jmskh\miniconda3\python.exe -m streamlit run src\zcyber_xhs\gui.py --server.headless false
pause
