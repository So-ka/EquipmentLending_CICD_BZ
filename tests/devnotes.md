py -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest

//
.venv\Scripts\Activate.ps1
//

python -m flask --app wsgi run --port 8000

