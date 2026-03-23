## Requirements

- **Python ≥ 3.13**
- **Windows** (MetaTrader 5 terminal requirement)
- A MetaTrader 5 trading account

---

## Installation

```bash
pip install aiomql
```

**Optional extras:**

```bash
# TA-Lib technical indicators
pip install aiomql[talib]

# Optional (Cython, Numba, tqdm)
pip install aiomql[optional]

# Both
pip install aiomql[all]
```

---

## Build Exe

```bash
python -m PyInstaller --onefile --collect-all aiomql --collect-all talib --collect-all pandas_ta --clean main.py
```

## Quick Start
- Create file config on the same directory, file name: config.json
- Example file config.json:
```json
{
    "login": 104557397,
    "password": "Gc-fTv8n",
    "server": "MetaQuotes-Demo",
    "path": "D:\\Projects\\MetaTrader 5\\terminal64.exe"
}
```
- Run with python: python main.py
