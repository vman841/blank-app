"""
🗑️ SmartBins – Bin Inventory App
Refactored & bug-fixed for Streamlit Cloud + Google Sheets backend
"""

import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from streamlit_gsheets import GSheetsConnection
from typing import Optional

st.set_page_config(
    page_title="SmartBins",
    page_icon="🗑️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ══════════════════════════════════════════════
#  Google Sheets helpers
# ══════════════════════════════════════════════

@st.cache_resource
def get_conn():
    return st.connection("gsheets", type=GSheetsConnection)


def load_sheet(sheet_name: str) -> pd.DataFrame:
    """Always fetch fresh data (ttl=0) so stale cache never blocks writes."""
    conn = get_conn()
    df = conn.read(worksheet=sheet_name, ttl=0)
    if df is None:
        return pd.DataFrame()
    return df.dropna(how="all").reset_index(drop=True)


def write_sheet(sheet_name: str, df: pd.DataFrame):
    conn = get_conn()
    conn.update(worksheet=sheet_name, data=df)

import bcrypt  # add this at the top of the file

def hash_password(plain: str) -> str:
    """Pure bcrypt hash — works independently of stauth version."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
# ══════════════════════════════════════════════
#  One-time sheet initialisation
# ══════════════════════════════════════════════

def init_sheets():
    """
    Create all required sheets on first deploy.
    Seeds a default admin account so the app is immediately usable.
    Passwords are stored as plain text here; auto_hash=True hashes them in memory.
    """
    # ── Users ──
    users_df = load_sheet("users")
    if users_df.empty or "username" not in users_df.columns:
        users_df = pd.DataFrame([{
            "username": "admin",
            "name":     "Administrator",
            "email":    "admin@example.com",
            "password": hash_password("admin123"),   # plain text – will be auto-hashed in memory
            "role":     "admin",
        }])
        write_sheet("users", users_df)
        st.session_state["first_run"] = True

    # ── Bins ──
    bins_df = load_sheet("bins")
    if bins_df.empty or "bin_id" not in bins_df.columns:
        write_sheet("bins", pd.DataFrame({
            "bin_id":   list(range(1, 11)),
            "bin_name": [f"Bin {i}" for i in range(1, 11)],
        }))

    # ── Items ──
    items_df = load_sheet("items")
    if items_df.empty or "item_id" not in items_df.columns:
        write_sheet("items", pd.DataFrame(
            columns=["item_id", "bin_id", "item_name", "quantity", "category"]
        ))


# ══════════════════════════════════════════════
#  Authentication
# ══════════════════════════════════════════════

def build_credentials() -> dict:
    """
    Convert the flat users sheet into the dict format expected by
    streamlit-authenticator ≥ 0.3 (email, first_name, last_name, password, roles).
    """
    users_df = load_sheet("users")

    if users_df.empty or "username" not in users_df.columns or "password" not in users_df.columns:
        return {"usernames": {}}

    # Fill missing optional columns with sensible defaults
    for col, default in [("name", ""), ("email", ""), ("role", "user")]:
        if col not in users_df.columns:
            users_df[col] = default

    users_df = (
        users_df
        .dropna(subset=["username", "password"])
        .pipe(lambda d: d[d["username"].astype(str).str.strip() != ""])
        .pipe(lambda d: d[d["password"].astype(str).str.strip() != ""])
    )

    creds = {"usernames": {}}
    for _, row in users_df.iterrows():
        username = str(row["username"]).strip()
        name     = str(row.get("name", username)).strip() or username
        parts    = name.split(" ", 1)

        creds["usernames"][username] = {
            "email":      str(row.get("email", f"{username}@example.com")).strip(),
            "first_name": parts[0],
            "last_name":  parts[1] if len(parts) > 1 else "",
            "password":   str(row["password"]).strip(),
            "roles":      [str(row.get("role", "user")).strip() or "user"],
        }
    return creds


def get_authenticator():
    credentials = build_credentials()
    authenticator = stauth.Authenticate(
        credentials,
        cookie_name="bin_app_cookie",
        cookie_key="bin_app_s3cur3_k3y",
        cookie_expiry_days=7,
        auto_hash=True,   # plain text passwords hashed in memory automatically
    )
    return authenticator, credentials


# ══════════════════════════════════════════════
#  Admin panel
# ══════════════════════════════════════════════

def admin_panel():
    st.subheader("🔧 Admin – User Management")

    with st.expander("➕ Create new user", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Username",         key="adm_username")
            new_name     = st.text_input("Full name",        key="adm_name")
            new_email    = st.text_input("Email (optional)", key="adm_email")
        with col2:
            new_password = st.text_input("Password", type="password", key="adm_password")
            role         = st.selectbox("Role", ["user", "admin"], key="adm_role")

        if st.button("Create user", use_container_width=True, key="adm_create_btn"):
            if not (new_username.strip() and new_name.strip() and new_password.strip()):
                st.error("❌ Username, full name, and password are all required")
                return

            users_df = load_sheet("users")
            if (not users_df.empty
                    and "username" in users_df.columns
                    and new_username.strip() in users_df["username"].astype(str).values):
                st.error("❌ Username already exists")
                return

            new_row = {
                "username": new_username.strip(),
                "name":     new_name.strip(),
                "email":    new_email.strip() or f"{new_username.strip()}@example.com",
                "password": hash_password(new_password),     # plain text; auto-hashed in memory
                "role":     role,
            }
            users_df = pd.concat([users_df, pd.DataFrame([new_row])], ignore_index=True)
            write_sheet("users", users_df)
            st.success(f"✅ User '{new_username.strip()}' created!")
            st.rerun()

    users_df = load_sheet("users")
    if not users_df.empty and "username" in users_df.columns:
        st.subheader("👥 Existing Users")
        display_cols = [c for c in ["username", "name", "email", "role"] if c in users_df.columns]
        st.dataframe(users_df[display_cols], use_container_width=True)


# ══════════════════════════════════════════════
#  Bins
# ══════════════════════════════════════════════

def load_bins() -> pd.DataFrame:
    df = load_sheet("bins")
    if df.empty or "bin_id" not in df.columns:
        return pd.DataFrame(columns=["bin_id", "bin_name"])
    df["bin_id"] = pd.to_numeric(df["bin_id"], errors="coerce")
    return df.dropna(subset=["bin_id"]).reset_index(drop=True)


def add_bin(bin_name: str):
    df      = load_bins()
    next_id = int(df["bin_id"].max()) + 1 if not df.empty else 1
    df      = pd.concat([df, pd.DataFrame([{"bin_id": next_id, "bin_name": bin_name}])],
                        ignore_index=True)
    write_sheet("bins", df)


def rename_bin(bin_id: int, new_name: str):
    df = load_bins()
    df.loc[df["bin_id"] == bin_id, "bin_name"] = new_name
    write_sheet("bins", df)


def bins_ui():
    st.subheader("🗂️ Bins Management")
    bins_df = load_bins()

    st.dataframe(bins_df if not bins_df.empty else pd.DataFrame(columns=["bin_id", "bin_name"]),
                 use_container_width=True)

    st.markdown("### ➕ Add New Bin")
    new_bin_name = st.text_input("Bin name", key="bins_add_name")
    if st.button("Add bin", use_container_width=True, key="bins_add_btn"):
        if new_bin_name.strip():
            add_bin(new_bin_name.strip())
            st.success("✅ Bin added!")
            st.rerun()
        else:
            st.error("❌ Bin name required")

    st.markdown("### ✏️ Rename Bin")
    bins_df = load_bins()   # reload after possible add
    if not bins_df.empty:
        bin_options = {
            f"{row['bin_name']} (ID:{int(row['bin_id'])})": int(row["bin_id"])
            for _, row in bins_df.iterrows()
        }
        selected  = st.selectbox("Select bin", list(bin_options.keys()), key="bins_rename_sel")
        new_name  = st.text_input("New name", key="bins_rename_name")
        if st.button("Rename", use_container_width=True, key="bins_rename_btn"):
            if new_name.strip():
                rename_bin(bin_options[selected], new_name.strip())
                st.success("✅ Bin renamed!")
                st.rerun()
            else:
                st.error("❌ New name required")


# ══════════════════════════════════════════════
#  Items
# ══════════════════════════════════════════════

def load_items() -> pd.DataFrame:
    df = load_sheet("items")
    if df.empty or "item_id" not in df.columns:
        return pd.DataFrame(columns=["item_id", "bin_id", "item_name", "quantity", "category"])
    df["item_id"] = pd.to_numeric(df["item_id"], errors="coerce")
    df["bin_id"]  = pd.to_numeric(df["bin_id"],  errors="coerce")
    return df.dropna(subset=["item_id", "bin_id"]).reset_index(drop=True)


def add_item(bin_id: int, item_name: str, quantity: str, category: str):
    df      = load_items()
    next_id = int(df["item_id"].max()) + 1 if not df.empty else 1
    df      = pd.concat([df, pd.DataFrame([{
        "item_id":   next_id,
        "bin_id":    bin_id,
        "item_name": item_name,
        "quantity":  quantity,
        "category":  category,
    }])], ignore_index=True)
    write_sheet("items", df)


def search_items(query: str, bin_filter_id: Optional[int]) -> pd.DataFrame:
    items_df = load_items()
    bins_df  = load_bins()
    empty_cols = ["item_id", "bin_id", "bin_name", "item_name", "quantity", "category"]

    if items_df.empty:
        return pd.DataFrame(columns=empty_cols)

    merged = items_df.merge(bins_df, on="bin_id", how="left")

    if bin_filter_id is not None:            # NOTE: 'if bin_filter_id:' would skip bin_id=0
        merged = merged[merged["bin_id"] == bin_filter_id]

    if query.strip():
        mask = (
            merged["item_name"].astype(str).str.contains(query, case=False, na=False) |
            merged["category"].astype(str).str.contains(query, case=False, na=False)
        )
        merged = merged[mask]

    cols = [c for c in empty_cols if c in merged.columns]
    return merged[cols].reset_index(drop=True)


def items_ui():
    st.subheader("📦 Items Management")
    bins_df = load_bins()

    if bins_df.empty:
        st.error("❌ No bins found – create some in the Bins tab first.")
        return

    bin_options = {row["bin_name"]: int(row["bin_id"]) for _, row in bins_df.iterrows()}

    st.markdown("### ➕ Add New Item")
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_bin    = st.selectbox("Select bin", list(bin_options.keys()), key="items_add_bin")
        selected_bin_id = bin_options[selected_bin]
    with col2:
        item_name = st.text_input("Item name *",         key="items_add_name")
        quantity  = st.text_input("Quantity (optional)", key="items_add_qty")
        category  = st.text_input("Category (optional)", key="items_add_cat")

    if st.button("➕ Add item", use_container_width=True, key="items_add_btn"):
        if item_name.strip():
            add_item(selected_bin_id, item_name.strip(), quantity, category)
            st.success("✅ Item added!")
            st.rerun()
        else:
            st.error("❌ Item name is required")

    st.markdown("### 🔍 Search Items")
    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("Search by name or category", key="items_search_q")
    with col2:
        filter_opts     = {"All bins": None, **bin_options}
        bin_filter_name = st.selectbox("Filter by bin", list(filter_opts.keys()), key="items_filter_bin")
        bin_filter_id   = filter_opts[bin_filter_name]

    st.markdown("### 📋 All Items")
    st.dataframe(search_items(search_query, bin_filter_id), use_container_width=True)


# ══════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════

def main():
    st.title("🗑️ Bin Inventory App")

    # ── One-time initialisation ──
    if "sheets_initialized" not in st.session_state:
        with st.spinner("🔄 Initialising sheets…"):
            init_sheets()
            st.session_state["sheets_initialized"] = True
        st.rerun()

    # ── First-run banner ──
    if st.session_state.get("first_run"):
        st.info(
            "🆕 **First run!** A default admin account was created.\n\n"
            "**Username:** `admin`  |  **Password:** `admin123`\n\n"
            "⚠️ Please delete or replace this account after logging in."
        )

    # ── Authentication ──
    authenticator, credentials = get_authenticator()

    try:
        authenticator.login(location="main")
    except Exception as e:
        st.error(f"Login widget error: {e}")
        return

    auth_status = st.session_state.get("authentication_status")
    name        = st.session_state.get("name", "User")
    username    = st.session_state.get("username", "")

    if auth_status is False:
        st.error("❌ Incorrect username or password")
        return
    elif auth_status is None:
        st.info("👤 Please enter your credentials to log in")
        return

    # ── Authenticated ──
    user_data = credentials.get("usernames", {}).get(username, {})
    roles     = user_data.get("roles", ["user"])
    user_role = roles[0] if roles else "user"

    with st.sidebar:
        st.success(f"👋 {name}")
        st.caption(f"Role: {user_role}")
        if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
            authenticator.logout(location="unrendered")
            st.rerun()

    # ── Tabs ──
    tab_labels = ["📦 Items", "🗂️ Bins"]
    if user_role == "admin":
        tab_labels.append("🔧 Admin")

    tabs = st.tabs(tab_labels)

    with tabs[0]:
        items_ui()
    with tabs[1]:
        bins_ui()
    if user_role == "admin" and len(tabs) == 3:
        with tabs[2]:
            admin_panel()


if __name__ == "__main__":
    main()
