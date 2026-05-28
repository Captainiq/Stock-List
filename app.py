import json
import urllib.request
import pandas as pd
import pyotp
import streamlit as st
from SmartApi import SmartConnect

# ---------------------------------------------------------
# 1. API CONFIGURATION & LOGIN
# ---------------------------------------------------------
# Replace these with your actual credentials
API_KEY = st.secrets["API_KEY"]
CLIENT_ID = st.secrets["CLIENT_ID"]
PASSWORD = st.secrets["PASSWORD"]
TOTP_SECRET = st.secrets["TOTP_SECRET"]


@st.cache_resource
def get_broker_session():
    """Establishes and caches a secure broker session."""
    try:
        smart_api = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smart_api.generateSession(CLIENT_ID, PASSWORD, totp)

        if data["status"]:
            return smart_api
        else:
            st.error(f"Login Failed: {data['message']}")
            return None
    except Exception as e:
        st.error(f"Error establishing session: {e}")
        return None


# ---------------------------------------------------------
# 2. NSE TOKEN LOOKUP ENGINE
# ---------------------------------------------------------
@st.cache_data
def load_instrument_list():
    """Downloads Angel One's master list of all stock tokens."""
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    response = urllib.request.urlopen(url)
    return json.loads(response.read())


def get_stock_token(symbol, instrument_list):
    """Finds the unique numeric token for a given stock symbol."""
    # Ensure standard NSE formatting (e.g., RELIANCE -> RELIANCE-EQ)
    if not symbol.endswith("-EQ"):
        symbol = f"{symbol.upper()}-EQ"

    for item in instrument_list:
        if item["symbol"] == symbol and item["exch_seg"] == "NSE":
            return item["token"], item["symbol"]
    return None, None


# ---------------------------------------------------------
# 3. STREAMLIT UI INTERFACE
# ---------------------------------------------------------
st.set_page_config(page_title="Live Indian Stock CMP", layout="wide")
st.title("📊 Indian Stock Live CMP Dashboard")
st.caption("Powered by direct exchange feeds via Angel One SmartAPI")

# Initialize session and load master token sheet
smart_api = get_broker_session()
instrument_list = load_instrument_list()

if smart_api:
    # Choose Input Mechanism
    input_method = st.sidebar.radio(
        "Data Input Method:", ("Upload CSV / Spreadsheet", "Manual Entry")
    )
    stocks_to_fetch = []

    if input_method == "Upload CSV / Spreadsheet":
        uploaded_file = st.sidebar.file_uploader(
            "Upload CSV File", type=["csv"]
        )
        if uploaded_file is not None:
            df_input = pd.read_csv(uploaded_file)
            # Looks for a column called 'Symbol' or 'Stock'
            col_name = (
                "Symbol"
                if "Symbol" in df_input.columns
                else (
                    "Stock" if "Stock" in df_input.columns else df_input.columns[0]
                )
            )
            stocks_to_fetch = df_input[col_name].dropna().tolist()
            st.sidebar.success(f"Loaded {len(stocks_to_fetch)} symbols from file.")

    else:
        manual_input = st.sidebar.text_area(
            "Enter NSE Symbols (comma separated):", "RELIANCE, TCS, INFY, SBIN"
        )
        if manual_input:
            stocks_to_fetch = [
                s.strip() for s in manual_input.split(",") if s.strip()
            ]

    # Process and Display Live Data
    if stocks_to_fetch:
        if st.button("Fetch Live Prices", type="primary"):
            results = []

            with st.spinner("Fetching data from NSE servers..."):
                for stock in stocks_to_fetch:
                    # Clear common entries like RELIANCE.NS to pure ticker
                    clean_stock = stock.split(".")[0].split(":")[0].strip()

                    token, formal_symbol = get_stock_token(
                        clean_stock, instrument_list
                    )

                    if token:
                        try:
                            # Request precise last traded price
                            response = smart_api.ltpData("NSE", formal_symbol, token)
                            if (
                                response["status"]
                                and response["data"] is not None
                            ):
                                cmp = response["data"]["ltp"]
                                results.append(
                                    {
                                        "Input Stock": stock,
                                        "Exchange Trading Symbol": formal_symbol,
                                        "Token ID": token,
                                        "Live CMP (₹)": f"₹{cmp:,.2f}",
                                    }
                                )
                            else:
                                results.append(
                                    {
                                        "Input Stock": stock,
                                        "Exchange Trading Symbol": "API Error",
                                        "Token ID": "-",
                                        "Live CMP (₹)": "N/A",
                                    }
                                )
                        except Exception:
                            results.append(
                                {
                                    "Input Stock": stock,
                                    "Exchange Trading Symbol": "Fetch Failed",
                                    "Token ID": "-",
                                    "Live CMP (₹)": "Error",
                                }
                            )
                    else:
                        results.append(
                            {
                                "Input Stock": stock,
                                "Exchange Trading Symbol": "Not Found in NSE",
                                "Token ID": "-",
                                "Live CMP (₹)": "Invalid Symbol",
                            }
                        )

            # Render data inside a clean web-ready table
            df_output = pd.DataFrame(results)
            st.subheader("🎯 Real-Time Market Feed")
            st.dataframe(df_output, use_container_width=True, hide_index=True)
else:
    st.warning(
        "Please check your API configuration setup to log into your backend feed."
    )
