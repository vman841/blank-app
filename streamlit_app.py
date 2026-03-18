"""
🗑️ Bin Inventory App - Complete Streamlit app with Google Sheets backend
Ready to deploy to Streamlit Cloud!
"""

import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from streamlit_gsheets import GSheetsConnection

st.set_page_config(
    page_title="SmartBins",
    page_icon="🗑️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------- Google Sheets Connection ----------
@st.cache_resource
def get_conn():
    """Get Google Sheets connection."""
    return st.connection("gsheets", type=GSheetsConnection)

def load_sheet(sheet_name: str) -> pd.DataFrame:
    """Load sheet as DataFrame."""
    conn = get_conn()
    df = conn.read(worksheet=sheet_name)
    if df is None or df.empty:
        df = pd.DataFrame()
    return df

def write_sheet(sheet_name: str, df: pd.DataFrame):
    """Write DataFrame to sheet."""
    conn = get_conn()
    conn.update(worksheet=sheet_name, data=df)

# ---------- Initialization (runs ONCE) ----------
def init_users_if_empty():
    users_df = load_sheet("users")
    if users_df.empty:
        cols = ["username", "name", "password_hash", "role"]
        write_sheet("users", pd.DataFrame(columns=cols))

def init_bins_if_empty():
    bins_df = load_sheet("bins")
    if bins_df.empty:
        data = {
            "bin_id": list(range(1, 11)),
            "bin_name": [f"Bin {i}" for i in range(1, 11)]
        }
        write_sheet("bins", pd.DataFrame(data))

def init_items_if_empty():
    items_df = load_sheet("items")
    if items_df.empty:
        cols = ["item_id", "bin_id", "item_name", "quantity", "category"]
        write_sheet("items", pd.DataFrame(columns=cols))

# ---------- Authentication ----------
def load_credentials_from_sheet():
    users_df = load_sheet("users")
    if users_df.empty:
        return {"usernames": {}}

    # Ensure columns exist
    for col in ["username", "name", "password_hash", "role"]:
        if col not in users_df.columns:
            users_df[col] = ""

    # Drop invalid rows
    users_df = users_df.dropna(subset=["username", "password_hash"])
    
    creds = {"usernames": {}}
    for _, row in users_df.iterrows():
        username = str(row["username"]).strip()
        password_hash = str(row["password_hash"]).strip()
        if username and password_hash:
            creds["usernames"][username] = {
                "name": str(row["name"]).strip(),
                "password": password_hash,
                "role": str(row.get("role", "user")).strip() or "user"
            }
    return creds

def get_authenticator():
    credentials = load_credentials_from_sheet()
    authenticator = stauth.Authenticate(
        credentials,
        "bin_app_cookie",
        "bin_app_signature_key", 
        cookie_expiry_days=7
    )
    return authenticator, credentials

# ---------- Admin Panel ----------
def admin_panel():
    st.subheader("🔧 Admin - User Management")
    
    with st.expander("➕ Create new user", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Username")
            new_name = st.text_input("Full name")
        with col2:
            new_password = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["user", "admin"])
        
        if st.button("Create user", use_container_width=True):
            if new_username and new_password and new_name:
                try:
                    hashed = stauth.utilities.hasher.Hasher([new_password]).generate()[0]
                    users_df = load_sheet("users")
                    new_row = {
                        "username": new_username,
                        "name": new_name,
                        "password_hash": hashed,
                        "role": role
                    }
                    users_df = pd.concat([users_df, pd.DataFrame([new_row])], ignore_index=True)
                    write_sheet("users", users_df)
                    st.success(f"✅ User '{new_username}' created!")
                    st.rerun()
                except:
                    st.error("❌ Failed to create user")
            else:
                st.error("❌ All fields required")

    # Show users table
    users_df = load_sheet("users")
    if not users_df.empty:
        st.subheader("👥 Existing users")
        st.dataframe(users_df[["username", "name", "role"]], use_container_width=True)

# ---------- Bins UI ----------
@st.cache_data
def load_bins():
    df = load_sheet("bins")
    if df.empty:
        init_bins_if_empty()
        df = load_sheet("bins")
    return df

def add_bin(bin_name: str):
    bins_df = load_bins()
    next_id = bins_df["bin_id"].max() + 1 if not bins_df.empty else 1
    new_row = {"bin_id": next_id, "bin_name": bin_name}
    bins_df = pd.concat([bins_df, pd.DataFrame([new_row])], ignore_index=True)
    write_sheet("bins", bins_df)

def rename_bin(bin_id: int, new_name: str):
    bins_df = load_bins()
    bins_df.loc[bins_df["bin_id"] == bin_id, "bin_name"] = new_name
    write_sheet("bins", bins_df)

def bins_ui():
    st.subheader("🗂️ Bins Management")
    
    # Show bins
    bins_df = load_bins()
    st.dataframe(bins_df, use_container_width=True)
    
    # Add bin
    st.markdown("### ➕ Add new bin")
    new_bin_name = st.text_input("Bin name")
    if st.button("Add bin", use_container_width=True) and new_bin_name.strip():
        add_bin(new_bin_name.strip())
        st.success("✅ Bin added!")
        st.rerun()
    
    # Rename bin
    st.markdown("### ✏️ Rename bin")
    if not bins_df.empty:
        bin_options = {f"{row['bin_name']} (ID:{row['bin_id']})": row['bin_id'] 
                      for _, row in bins_df.iterrows()}
        selected = st.selectbox("Select bin", list(bin_options.keys()))
        new_name = st.text_input("New name")
        if st.button("Rename", use_container_width=True) and new_name.strip():
            bin_id = bin_options[selected]
            rename_bin(bin_id, new_name.strip())
            st.success("✅ Bin renamed!")
            st.rerun()

# ---------- Items UI ----------
@st.cache_data
def load_items():
    df = load_sheet("items")
    if df.empty:
        init_items_if_empty()
        df = load_sheet("items")
    return df

def add_item(bin_id: int, item_name: str, quantity: str, category: str):
    items_df = load_items()
    next_id = items_df["item_id"].max() + 1 if not items_df.empty else 1
    new_row = {
        "item_id": next_id,
        "bin_id": bin_id,
        "item_name": item_name,
        "quantity": quantity,
        "category": category
    }
    items_df = pd.concat([items_df, pd.DataFrame([new_row])], ignore_index=True)
    write_sheet("items", items_df)

def search_items(query: str, bin_filter: int | None):
    items_df = load_items()
    bins_df = load_bins()
    
    if items_df.empty:
        return pd.DataFrame()
    
    # Merge with bins
    merged = items_df.merge(bins_df, on="bin_id", how="left")
    
    # Filter by bin
    if bin_filter:
        merged = merged[merged["bin_id"] == bin_filter]
    
    # Search
    if query:
        q = query.lower()
        mask = (
            merged["item_name"].astype(str).str.contains(q, case=False, na=False) |
            merged["category"].astype(str).str.contains(q, case=False, na=False)
        )
        merged = merged[mask]
    
    return merged[["item_id", "bin_id", "bin_name", "item_name", "quantity", "category"]]

def items_ui():
    st.subheader("📦 Items Management")
    
    bins_df = load_bins()
    if bins_df.empty:
        st.error("❌ No bins! Create bins first.")
        return
    
    # Add item form
    col1, col2 = st.columns([1, 2])
    with col1:
        bin_options = {row["bin_name"]: row["bin_id"] for _, row in bins_df.iterrows()}
        selected_bin = st.selectbox("Select bin", list(bin_options.keys()))
        selected_bin_id = bin_options[selected_bin]
    
    with col2:
        item_name = st.text_input("Item name *")
        quantity = st.text_input("Quantity (optional)")
        category = st.text_input("Category (optional)")
    
    if st.button("➕ Add item", use_container_width=True):
        if item_name.strip():
            add_item(selected_bin_id, item_name.strip(), quantity, category)
            st.success("✅ Item added!")
            st.rerun()
        else:
            st.error("❌ Item name required")
    
    # Search
    st.markdown("### 🔍 Search items")
    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("Search (name/category)")
    with col2:
        bin_filter_name = st.selectbox("Filter by bin", ["All"] + list(bin_options.keys()))
        bin_filter_id = bin_options.get(bin_filter_name) if bin_filter_name != "All" else None
    
    if st.button("Search", use_container_width=True):
        results = search_items(search_query, bin_filter_id)
        st.dataframe(results, use_container_width=True)
    
    # All items
    st.markdown("### 📋 All items")
    all_items = search_items("", None)
    st.dataframe(all_items, use_container_width=True)

# ---------- MAIN APP ----------
def main():
    st.title("🗑️ Bin Inventory App")

    # ONE-TIME INITIALIZATION (quota safe)
    if "sheets_initialized" not in st.session_state:
        with st.spinner("🔄 Initializing sheets (one time only)..."):
            try:
                init_users_if_empty()
                init_bins_if_empty()
                init_items_if_empty()
                st.session_state.sheets_initialized = True
                st.success("✅ Ready! Login below.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Setup failed: {e}")
                st.info("👉 Create sheets: 'users', 'bins', 'items' with proper headers")
                return

    # Authentication
    authenticator, credentials = get_authenticator()
    name, auth_status, username = authenticator.login("🔐 Login", "main")

    if auth_status is False:
        st.error("❌ Wrong credentials")
        return
    elif auth_status is None:
        st.info("👤 Enter your credentials")
        return

    # Success! Show UI
    st.sidebar.success(f"👋 {name}")
    st.sidebar.button("🚪 Logout", on_click=lambda: authenticator.logout("Logout", "sidebar") or st.rerun())

    user_role = credentials["usernames"][username]["role"]

    # Tabs
    tabs = st.tabs(["📦 Items", "🗂️ Bins"] + (["🔧 Admin"] if user_role == "admin" else []))

    with tabs[0]:
        items_ui()
    with tabs[1]:
        bins_ui()
    if len(tabs) == 3:
        with tabs[2]:
            admin_panel()

if __name__ == "__main__":
    main()
